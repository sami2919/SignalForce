"""Outbound-request guard: refuse any request that would reach a non-public address.

Users can add domains to a watchlist, and the server then fetches them, so every
outbound fetch is a potential SSRF (cloud metadata, Fly's private network,
localhost). The check runs on every request including each redirect hop.

`get_capped` is the size half: a GET whose decoded body is bounded while it
streams, so a gzip bomb or an endless body from a user-supplied domain cannot
exhaust memory before any size check runs.

Residual risk: DNS can change between this check and the connection (rebinding).
Closing that fully needs a connect-time address pin; this guard stops the direct
and redirect cases, which is what a user-supplied domain list can reach.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import zlib
from collections.abc import AsyncIterator, Callable

import httpx


class BlockedAddress(httpx.TransportError):
    """A request would reach a non-public address. Subclasses httpx.TransportError so existing
    `except httpx.HTTPError` handlers record it as a failed fetch instead of crashing."""


_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_SIIT = ipaddress.ip_network("::ffff:0:0:0/96")
_ALWAYS_BLOCKED = tuple(
    ipaddress.ip_network(n) for n in ("::/96", "64:ff9b:1::/48", "fec0::/10")
)


def _embedded_ipv4(address: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """The IPv4 address an IPv6 address wraps (mapped, 6to4, NAT64, SIIT), if any."""
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address.sixtofour is not None:
        return address.sixtofour
    if address in _NAT64 or address in _SIIT:
        return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    return None


def _is_public(raw: str) -> bool:
    address = ipaddress.ip_address(raw.split("%")[0])
    if address.version == 6:
        if any(address in net for net in _ALWAYS_BLOCKED):
            return False
        embedded = _embedded_ipv4(address)
        if embedded is not None:
            address = embedded
    return address.is_global and not address.is_multicast


def _resolve_addresses(host: str, resolver: Callable | None) -> list[str]:
    lookup = resolver or socket.getaddrinfo
    try:
        infos = lookup(host, None)
        addresses = sorted({info[4][0] for info in infos})
        if not addresses:
            raise BlockedAddress(f"{host} has no addresses")
        bad = [a for a in addresses if not _is_public(a)]
    except BlockedAddress:
        raise
    except Exception as exc:  # any resolve/parse failure is a failed fetch, never a crash
        raise BlockedAddress(f"{host} could not be checked ({exc.__class__.__name__})") from exc
    if bad:
        raise BlockedAddress(f"{host} resolves to a non-public address ({bad[0]})")
    return addresses


def assert_public_host(host: str, resolver: Callable | None = None) -> None:
    """Raise BlockedAddress unless every address `host` resolves to is globally routable."""
    if not host:
        raise BlockedAddress("empty host")
    _resolve_addresses(host, resolver)


async def _check_request(request: httpx.Request) -> None:
    await asyncio.to_thread(assert_public_host, request.url.host)


def guarded_client(**kwargs) -> httpx.AsyncClient:
    """An AsyncClient that checks every request, redirects included."""
    hooks = dict(kwargs.pop("event_hooks", {}))
    hooks["request"] = [_check_request, *hooks.get("request", [])]
    return httpx.AsyncClient(event_hooks=hooks, **kwargs)


class BodyTooLarge(httpx.TransportError):
    """A response body grew past the caller's cap while streaming. Subclasses
    httpx.TransportError so existing `except httpx.HTTPError` handlers treat it
    as a failed fetch; callers with their own over-cap result catch it first."""

    def __init__(self, url: str, *, status_code: int, bytes_read: int, max_bytes: int) -> None:
        super().__init__(f"body over {max_bytes} bytes from {url}")
        self.status_code = status_code
        self.bytes_read = bytes_read
        self.max_bytes = max_bytes


# Headers that describe the wire body, not the decoded one we return. Keeping
# content-encoding would make httpx decode the already-decoded body again.
_WIRE_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})


class _BoundedInflater:
    """gzip/deflate decoding that never produces more than it is asked for.

    httpx's own decoders inflate a whole network chunk at once, so one 64 KiB
    chunk of a gzip bomb can become ~64 MB before any size check. zlib's
    max_length bounds each step instead.
    """

    def __init__(self, encoding: str) -> None:
        self._deflate = encoding == "deflate"
        self._first = True
        wbits = zlib.MAX_WBITS if self._deflate else zlib.MAX_WBITS | 16
        self._d = zlib.decompressobj(wbits)

    def feed(self, data: bytes, budget: int) -> bytes:
        """Decode `data`, stopping once more than `budget` bytes are produced."""
        try:
            out = self._d.decompress(data, budget + 1)
        except zlib.error:
            if not (self._deflate and self._first):
                raise httpx.DecodingError("malformed compressed body") from None
            self._d = zlib.decompressobj(-zlib.MAX_WBITS)  # raw deflate, as httpx does
            out = self._d.decompress(data, budget + 1)
        self._first = False
        parts = [out]
        produced = len(out)
        while self._d.unconsumed_tail and produced <= budget:
            more = self._d.decompress(self._d.unconsumed_tail, budget + 1 - produced)
            parts.append(more)
            produced += len(more)
        return b"".join(parts)

    def flush(self) -> bytes:
        return self._d.flush()


async def _decoded_chunks(streamed: httpx.Response, max_bytes: int) -> AsyncIterator[bytes]:
    encoding = streamed.headers.get("content-encoding", "").strip().lower()
    if "," in encoding:
        # Stacked encodings (e.g. "gzip, gzip") multiply the inflation ratio and
        # httpx would decode each chunk whole. No real page needs them.
        raise httpx.DecodingError(f"stacked content-encoding refused: {encoding}")
    # A body already in memory (a pre-read response) has nothing left to bound.
    if encoding in ("gzip", "x-gzip", "deflate") and not streamed.is_stream_consumed:
        inflater = _BoundedInflater("deflate" if encoding == "deflate" else "gzip")
        produced = 0
        async for raw in streamed.aiter_raw():
            chunk = inflater.feed(raw, max_bytes - produced)
            produced += len(chunk)
            yield chunk
            if produced > max_bytes:
                return
        yield inflater.flush()
        return
    async for chunk in streamed.aiter_bytes():  # identity, or an encoding httpx decodes
        yield chunk


async def get_capped(
    client: httpx.AsyncClient, url: str, *, max_bytes: int, **kwargs
) -> httpx.Response:
    """GET `url` with the DECODED body bounded at `max_bytes` while it streams.

    Drop-in for `await client.get(url, **kwargs)` followed by `.content` /
    `.text`: the returned Response carries the status, headers, final `.url`,
    `history` and charset handling of the streamed one. Redirect hops still pass
    through the client's request hooks (the guard). Raises BodyTooLarge as soon
    as the body passes the cap, without reading the rest.
    """
    async with client.stream("GET", url, **kwargs) as streamed:
        parts: list[bytes] = []
        seen = 0
        async for chunk in _decoded_chunks(streamed, max_bytes):
            seen += len(chunk)
            if seen > max_bytes:
                raise BodyTooLarge(
                    str(streamed.url),
                    status_code=streamed.status_code,
                    bytes_read=seen,
                    max_bytes=max_bytes,
                )
            parts.append(chunk)
        headers = [(k, v) for k, v in streamed.headers.multi_items() if k.lower() not in _WIRE_HEADERS]
        return httpx.Response(
            status_code=streamed.status_code,
            headers=headers,
            content=b"".join(parts),
            request=streamed.request,
            history=streamed.history,
            extensions=streamed.extensions,
            default_encoding=streamed.default_encoding,
        )
