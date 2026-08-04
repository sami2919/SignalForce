"""Fetcher tests.

Two properties dominate: the fetcher must never raise (one dead domain cannot
abort a pass over thousands of sources), and per-host concurrency must be
genuinely bounded (100 simultaneous requests to one domain reads as an attack,
and the resulting ban produces empty results indistinguishable from a quiet
account).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from scripts.watch.fetcher import SourceRef, fetch_all

PAGE = "<html><body><h1>Open roles</h1><p>Senior Engineer</p></body></html>"
ROBOTS_ALLOW = "User-agent: *\nAllow: /\n"
ROBOTS_DENY = "User-agent: *\nDisallow: /careers\n"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _ok(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text=ROBOTS_ALLOW)
    return httpx.Response(200, text=PAGE)


# --- happy path ---


@pytest.mark.asyncio
async def test_fetches_and_hashes_every_source() -> None:
    refs = [SourceRef(source_id=i, url=f"https://a{i}.com/careers") for i in range(5)]
    async with _client(_ok) as c:
        results = await fetch_all(refs, client=c, concurrency=3)
    assert len(results) == 5
    assert all(r.content_hash and r.status_code == 200 for r in results)


@pytest.mark.asyncio
async def test_returns_one_result_per_input_even_on_failure() -> None:
    """Result count must equal input count. A dropped source is a silent gap."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        if "bad" in request.url.host:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, text=PAGE)

    refs = [
        SourceRef(source_id=i, url=f"https://{'bad' if i % 2 else 'ok'}{i}.com/c") for i in range(6)
    ]
    async with _client(handler) as c:
        results = await fetch_all(refs, client=c, concurrency=4)
    assert len(results) == 6
    assert {r.source_id for r in results} == set(range(6))


@pytest.mark.asyncio
async def test_identical_content_hashes_identically() -> None:
    refs = [
        SourceRef(source_id=1, url="https://a.com/c"),
        SourceRef(source_id=2, url="https://b.com/c"),
    ]
    async with _client(_ok) as c:
        results = await fetch_all(refs, client=c)
    assert results[0].content_hash == results[1].content_hash


# --- never raises ---


@pytest.mark.asyncio
async def test_connect_error_is_recorded_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        raise httpx.ConnectError("refused")

    async with _client(handler) as c:
        results = await fetch_all([SourceRef(source_id=1, url="https://x.com/c")], client=c)
    assert results[0].error is not None
    assert results[0].content_hash is None


@pytest.mark.asyncio
async def test_timeout_is_recorded_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        raise httpx.ReadTimeout("slow")

    async with _client(handler) as c:
        results = await fetch_all([SourceRef(source_id=1, url="https://x.com/c")], client=c)
    assert results[0].error is not None


@pytest.mark.asyncio
async def test_non_200_is_recorded_with_status_and_no_hash() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        return httpx.Response(503, text="down")

    async with _client(handler) as c:
        results = await fetch_all([SourceRef(source_id=1, url="https://x.com/c")], client=c)
    assert results[0].status_code == 503
    assert results[0].content_hash is None
    assert results[0].error is not None


@pytest.mark.asyncio
async def test_malformed_url_is_recorded_not_raised() -> None:
    async with _client(_ok) as c:
        results = await fetch_all([SourceRef(source_id=1, url="not-a-url")], client=c)
    assert len(results) == 1
    assert results[0].error is not None


# --- concurrency limits ---


@pytest.mark.asyncio
async def test_respects_per_host_concurrency() -> None:
    """20 sources on ONE host must not run 20-wide. This is the limit that
    prevents a ban, and a ban looks exactly like a quiet account."""
    inflight = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal inflight, peak
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        inflight += 1
        peak = max(peak, inflight)
        await asyncio.sleep(0.01)
        inflight -= 1
        return httpx.Response(200, text=PAGE)

    refs = [SourceRef(source_id=i, url=f"https://same.com/p{i}") for i in range(20)]
    async with _client(handler) as c:
        await fetch_all(refs, client=c, concurrency=20, per_host=2)
    assert peak <= 2


@pytest.mark.asyncio
async def test_respects_global_concurrency_across_hosts() -> None:
    inflight = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal inflight, peak
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        inflight += 1
        peak = max(peak, inflight)
        await asyncio.sleep(0.01)
        inflight -= 1
        return httpx.Response(200, text=PAGE)

    refs = [SourceRef(source_id=i, url=f"https://h{i}.com/c") for i in range(30)]
    async with _client(handler) as c:
        await fetch_all(refs, client=c, concurrency=5, per_host=2)
    assert peak <= 5


@pytest.mark.asyncio
async def test_different_hosts_run_in_parallel() -> None:
    """Per-host limiting must not serialise the whole pass."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        await asyncio.sleep(0.05)
        return httpx.Response(200, text=PAGE)

    refs = [SourceRef(source_id=i, url=f"https://h{i}.com/c") for i in range(10)]
    loop = asyncio.get_running_loop()
    start = loop.time()
    async with _client(handler) as c:
        await fetch_all(refs, client=c, concurrency=10, per_host=2)
    elapsed = loop.time() - start
    assert elapsed < 0.4, f"10 hosts took {elapsed:.2f}s — appears serialised"


# --- robots.txt ---


@pytest.mark.asyncio
async def test_skips_disallowed_paths() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_DENY)
        return httpx.Response(200, text=PAGE)

    async with _client(handler) as c:
        results = await fetch_all([SourceRef(source_id=1, url="https://x.com/careers")], client=c)
    assert results[0].robots_blocked is True
    assert results[0].content_hash is None


@pytest.mark.asyncio
async def test_robots_fetched_once_per_host_not_per_source() -> None:
    """10 sources on one host must produce ONE robots.txt fetch, not 10."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        return httpx.Response(200, text=PAGE)

    refs = [SourceRef(source_id=i, url=f"https://same.com/p{i}") for i in range(10)]
    async with _client(handler) as c:
        await fetch_all(refs, client=c)
    assert len([u for u in calls if u.endswith("/robots.txt")]) == 1


@pytest.mark.asyncio
async def test_missing_robots_is_permissive() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404, text="")
        return httpx.Response(200, text=PAGE)

    async with _client(handler) as c:
        results = await fetch_all([SourceRef(source_id=1, url="https://x.com/careers")], client=c)
    assert results[0].robots_blocked is False
    assert results[0].content_hash is not None


@pytest.mark.asyncio
async def test_robots_fetch_failure_is_permissive_not_deny_all() -> None:
    """A deny-all-on-error bug would silently zero out an entire scan pass."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            raise httpx.ConnectError("robots unreachable")
        return httpx.Response(200, text=PAGE)

    async with _client(handler) as c:
        results = await fetch_all([SourceRef(source_id=1, url="https://x.com/careers")], client=c)
    assert results[0].robots_blocked is False
    assert results[0].content_hash is not None


# --- metadata ---


@pytest.mark.asyncio
async def test_records_latency_and_bytes() -> None:
    async with _client(_ok) as c:
        results = await fetch_all([SourceRef(source_id=1, url="https://x.com/c")], client=c)
    assert results[0].latency_ms >= 0
    assert results[0].bytes == len(PAGE.encode("utf-8"))


@pytest.mark.asyncio
async def test_empty_input_returns_empty_without_error() -> None:
    async with _client(_ok) as c:
        assert await fetch_all([], client=c) == []


@pytest.mark.asyncio
async def test_oversized_body_is_skipped_not_hashed() -> None:
    """A pathological page must not blow memory or dominate the pass."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        return httpx.Response(200, text="x" * 9_000_000)

    async with _client(handler) as c:
        results = await fetch_all([SourceRef(source_id=1, url="https://x.com/c")], client=c)
    assert results[0].content_hash is None
    assert results[0].error is not None


@pytest.mark.asyncio
async def test_large_but_reasonable_body_is_hashed() -> None:
    """JS-heavy sites (Next.js bundles, base64 images) legitimately ship large
    raw HTML with small normalized content. Raw transport size is not a proxy
    for content size, so a large-but-real page (well under the 8MB DoS cap)
    must still be fetched and hashed, not rejected as pathological."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        padding = "<!-- " + ("x" * 3_000_000) + " -->"
        return httpx.Response(200, text=f"<html><body>{PAGE}{padding}</body></html>")

    async with _client(handler) as c:
        results = await fetch_all([SourceRef(source_id=1, url="https://x.com/c")], client=c)
    assert results[0].content_hash is not None
    assert results[0].error is None
