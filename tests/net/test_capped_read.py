"""get_capped: a GET whose DECODED body is bounded while it streams.

`client.get()` + `resp.content` buffers the whole decompressed body before any
size check, so a gzip bomb or an endless body could OOM the machine. These
tests drive the helper with httpx.MockTransport and multi-chunk streams.
"""

from __future__ import annotations

import gzip
import socket
import zlib

import httpx
import pytest

from scripts.net import guard
from scripts.net.guard import BlockedAddress, BodyTooLarge, get_capped, guarded_client

CAP = 64 * 1024


class _Chunks(httpx.AsyncByteStream):
    """A response body served in pieces, recording how many were pulled."""

    def __init__(self, chunks):
        self._chunks = chunks
        self.pulled = 0

    async def __aiter__(self):
        for chunk in self._chunks:
            self.pulled += 1
            yield chunk


class _Endless(httpx.AsyncByteStream):
    def __init__(self, chunk=b"x" * 4096):
        self._chunk = chunk
        self.pulled = 0

    async def __aiter__(self):
        while True:
            self.pulled += 1
            yield self._chunk


def _gzip_bomb_chunks(decoded_size: int, raw_chunk: int = 1024) -> list[bytes]:
    compressed = gzip.compress(b"\0" * decoded_size)
    return [compressed[i : i + raw_chunk] for i in range(0, len(compressed), raw_chunk)]


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_a_gzip_bomb_is_aborted_before_it_is_fully_inflated():
    chunks = _gzip_bomb_chunks(200 * 1024 * 1024)  # ~200 KB on the wire, 200 MB decoded
    stream = _Chunks(chunks)

    def handler(request):
        return httpx.Response(200, headers={"content-encoding": "gzip"}, stream=stream)

    async with _client(handler) as client:
        with pytest.raises(BodyTooLarge) as info:
            await get_capped(client, "https://bomb.example/", max_bytes=CAP)
    assert stream.pulled < len(chunks)
    assert info.value.status_code == 200
    assert CAP < info.value.bytes_read <= CAP + 1


@pytest.mark.asyncio
async def test_a_single_huge_compressed_chunk_is_not_inflated_whole():
    body = gzip.compress(b"\0" * (50 * 1024 * 1024))  # one raw chunk, 50 MB decoded

    def handler(request):
        return httpx.Response(200, headers={"content-encoding": "gzip"}, stream=_Chunks([body]))

    async with _client(handler) as client:
        with pytest.raises(BodyTooLarge) as info:
            await get_capped(client, "https://bomb.example/", max_bytes=CAP)
    assert info.value.bytes_read <= CAP + 1


@pytest.mark.asyncio
async def test_an_endless_body_is_aborted_at_the_cap():
    stream = _Endless()

    def handler(request):
        return httpx.Response(200, stream=stream)

    async with _client(handler) as client:
        with pytest.raises(BodyTooLarge):
            await get_capped(client, "https://endless.example/", max_bytes=CAP)
    assert stream.pulled <= CAP // 4096 + 1


@pytest.mark.asyncio
async def test_body_too_large_is_an_httpx_error_so_existing_handlers_catch_it():
    assert issubclass(BodyTooLarge, httpx.HTTPError)


def _page_handler(request):
    if request.url.path == "/old":
        return httpx.Response(301, headers={"location": "https://site.example/new"})
    return httpx.Response(
        200,
        headers={"content-type": "text/html; charset=iso-8859-1"},
        content="café".encode("iso-8859-1"),
    )


@pytest.mark.asyncio
async def test_a_small_page_matches_client_get_including_after_a_redirect():
    async with _client(_page_handler) as client:
        plain = await client.get("https://site.example/old", follow_redirects=True)
        capped = await get_capped(
            client, "https://site.example/old", max_bytes=CAP, follow_redirects=True
        )
    assert capped.status_code == plain.status_code == 200
    assert str(capped.url) == str(plain.url) == "https://site.example/new"
    assert capped.text == plain.text == "café"
    assert capped.content == plain.content
    assert [r.status_code for r in capped.history] == [301]


@pytest.mark.asyncio
async def test_gzip_content_is_decoded_once_not_twice():
    page = "<html>" + "hello " * 500 + "</html>"

    def handler(request):
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip", "content-type": "text/html; charset=utf-8"},
            stream=_Chunks([gzip.compress(page.encode())]),
        )

    async with _client(handler) as client:
        resp = await get_capped(client, "https://site.example/", max_bytes=CAP)
    assert resp.text == page
    assert "content-encoding" not in resp.headers


@pytest.mark.parametrize("wbits", [zlib.MAX_WBITS, -zlib.MAX_WBITS])
@pytest.mark.asyncio
async def test_deflate_with_and_without_zlib_header_decodes(wbits):
    page = b"deflated page " * 100
    compressor = zlib.compressobj(wbits=wbits)
    body = compressor.compress(page) + compressor.flush()

    def handler(request):
        return httpx.Response(200, headers={"content-encoding": "deflate"}, stream=_Chunks([body]))

    async with _client(handler) as client:
        resp = await get_capped(client, "https://site.example/", max_bytes=CAP)
    assert resp.content == page


@pytest.mark.asyncio
async def test_a_page_exactly_at_the_cap_is_allowed():
    def handler(request):
        return httpx.Response(200, content=b"x" * CAP)

    async with _client(handler) as client:
        resp = await get_capped(client, "https://site.example/", max_bytes=CAP)
    assert len(resp.content) == CAP


@pytest.mark.asyncio
async def test_a_redirect_to_an_internal_address_is_still_blocked(monkeypatch):
    requested: list[str] = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    def fake_getaddrinfo(host, port, *args, **kwargs):
        table = {"good.example": "93.184.216.34", "169.254.169.254": "169.254.169.254"}
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (table[host], 0))]

    monkeypatch.setattr(guard.socket, "getaddrinfo", fake_getaddrinfo)
    async with guarded_client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BlockedAddress):
            await get_capped(client, "http://good.example/", max_bytes=CAP, follow_redirects=True)
    assert requested == ["http://good.example/"]


@pytest.mark.asyncio
async def test_a_pre_read_compressed_response_is_still_returned_decoded():
    page = b"already in memory " * 50

    def handler(request):
        return httpx.Response(200, headers={"content-encoding": "gzip"}, content=gzip.compress(page))

    async with _client(handler) as client:
        resp = await get_capped(client, "https://site.example/", max_bytes=CAP)
    assert resp.content == page
