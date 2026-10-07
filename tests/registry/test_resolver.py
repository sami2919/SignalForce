"""Source resolution tests.

The soft-404 cases are the important ones. A resolver that trusts status codes
registers an error page and then hashes it daily forever, emitting nothing while
looking exactly like a quiet account.
"""

from __future__ import annotations

import httpx
import pytest

from scripts.registry.resolver import resolve_sources

HOMEPAGE = (
    "<html><body><h1>Acme</h1><p>We build things for teams.</p>"
    + ("<p>Lorem ipsum dolor sit amet consectetur.</p>" * 12)
    + "</body></html>"
)

CAREERS = (
    "<html><body><h1>Open roles</h1>"
    + ("<div><h2>Senior Engineer</h2><p>San Francisco</p></div>" * 10)
    + "</body></html>"
)

LEVER_SOFT_404 = (
    "<html><body>Sorry, we couldn't find anything here The job posting you're "
    "looking for might have closed, or it has been removed. (404 error). "
    "Jobs powered by</body></html>"
)

ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /\n"
ROBOTS_DENY_CAREERS = "User-agent: *\nDisallow: /careers\nDisallow: /jobs\n"


def _transport(routes: dict[str, httpx.Response], default_status: int = 404):
    """Map path -> Response. Unlisted paths return default_status."""

    def handler(request: httpx.Request) -> httpx.Response:
        for path, resp in routes.items():
            if request.url.path == path:
                return resp
        return httpx.Response(default_status, text="<html><body>Not found</body></html>")

    return httpx.MockTransport(handler)


async def _resolve(routes, default_status=404):
    async with httpx.AsyncClient(
        transport=_transport(routes, default_status), base_url="https://acme.com"
    ) as client:
        return await resolve_sources("acme.com", client)


# --- happy path ---


@pytest.mark.asyncio
async def test_resolves_careers_from_conventional_path() -> None:
    report = await _resolve(
        {
            "/robots.txt": httpx.Response(200, text=ROBOTS_ALLOW_ALL),
            "/": httpx.Response(200, text=HOMEPAGE),
            "/careers": httpx.Response(200, text=CAREERS),
        }
    )
    careers = [s for s in report.sources if s.source_type == "careers"]
    assert len(careers) == 1
    assert careers[0].url == "https://acme.com/careers"


@pytest.mark.asyncio
async def test_records_an_attempt_for_every_source_type() -> None:
    """Absence must never be the signal — every type gets a recorded outcome."""
    report = await _resolve(
        {
            "/robots.txt": httpx.Response(200, text=ROBOTS_ALLOW_ALL),
            "/": httpx.Response(200, text=HOMEPAGE),
            "/careers": httpx.Response(200, text=CAREERS),
        }
    )
    assert {a.source_type for a in report.attempts} == {
        "careers",
        "docs",
        "changelog",
        "pricing",
        "blog",
    }
    assert next(a for a in report.attempts if a.source_type == "docs").outcome == "not_found"


# --- SOFT-404: the cases that matter ---


@pytest.mark.asyncio
async def test_rejects_page_whose_content_equals_the_homepage() -> None:
    """SPA shell: 200 for every path, same content. Registering it means hashing
    the homepage daily, whose churn would blow the change-rate budget."""
    report = await _resolve(
        {
            "/robots.txt": httpx.Response(200, text=ROBOTS_ALLOW_ALL),
            "/": httpx.Response(200, text=HOMEPAGE),
            "/careers": httpx.Response(200, text=HOMEPAGE),
        }
    )
    assert report.resolved_types == set()
    assert next(a for a in report.attempts if a.source_type == "careers").outcome == "soft_404"


@pytest.mark.asyncio
async def test_rejects_lever_style_not_found_page() -> None:
    """Measured 2026-08-04: jobs.lever.co returns HTTP 200 with a 404 body."""
    report = await _resolve(
        {
            "/robots.txt": httpx.Response(200, text=ROBOTS_ALLOW_ALL),
            "/": httpx.Response(200, text=HOMEPAGE),
            "/careers": httpx.Response(200, text=LEVER_SOFT_404),
        }
    )
    assert report.resolved_types == set()
    assert next(a for a in report.attempts if a.source_type == "careers").outcome == "soft_404"


@pytest.mark.asyncio
async def test_does_not_reject_a_long_page_containing_notfound_wording() -> None:
    """A real careers page may say 'no longer available' inside one listing.
    Phrase matching must only apply to short pages, or it eats real sources."""
    long_page = (
        "<html><body><h1>Open roles</h1>"
        + ("<div><h2>Senior Engineer</h2><p>This position is no longer available</p></div>" * 10)
        + "</body></html>"
    )
    report = await _resolve(
        {
            "/robots.txt": httpx.Response(200, text=ROBOTS_ALLOW_ALL),
            "/": httpx.Response(200, text=HOMEPAGE),
            "/careers": httpx.Response(200, text=long_page),
        }
    )
    assert "careers" in report.resolved_types


@pytest.mark.asyncio
async def test_rejects_page_with_too_little_content_to_hash() -> None:
    """A JS-rendered shell with no server-side text hashes stably forever and
    detects nothing — a probe that proves the source is alive while being blind."""
    report = await _resolve(
        {
            "/robots.txt": httpx.Response(200, text=ROBOTS_ALLOW_ALL),
            "/": httpx.Response(200, text=HOMEPAGE),
            "/careers": httpx.Response(200, text="<html><body><div id='root'></div></body></html>"),
        }
    )
    assert next(a for a in report.attempts if a.source_type == "careers").outcome == "low_content"


# --- redirects ---


@pytest.mark.asyncio
async def test_stores_final_url_after_redirect() -> None:
    """/careers -> boards.greenhouse.io/acme. The ATS URL is the better registry
    entry: more stable, more structured, and it avoids paying the redirect daily."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        if request.url.host == "acme.com" and request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE)
        if request.url.host == "acme.com" and request.url.path == "/careers":
            return httpx.Response(302, headers={"Location": "https://boards.greenhouse.io/acme"})
        if request.url.host == "boards.greenhouse.io":
            return httpx.Response(200, text=CAREERS)
        return httpx.Response(404, text="nope")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await resolve_sources("acme.com", client)

    careers = [s for s in report.sources if s.source_type == "careers"]
    assert careers and careers[0].url == "https://boards.greenhouse.io/acme"


@pytest.mark.asyncio
async def test_rejects_redirect_to_homepage() -> None:
    """A redirect to / is a soft-404 wearing a different hat."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE)
        return httpx.Response(302, headers={"Location": "https://acme.com/"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await resolve_sources("acme.com", client)

    assert report.resolved_types == set()


# --- robots.txt ---


@pytest.mark.asyncio
async def test_respects_robots_disallow() -> None:
    report = await _resolve(
        {
            "/robots.txt": httpx.Response(200, text=ROBOTS_DENY_CAREERS),
            "/": httpx.Response(200, text=HOMEPAGE),
            "/careers": httpx.Response(200, text=CAREERS),
        }
    )
    attempt = next(a for a in report.attempts if a.source_type == "careers")
    assert attempt.outcome == "blocked_by_robots"
    assert "careers" not in report.resolved_types


@pytest.mark.asyncio
async def test_missing_robots_txt_is_permissive() -> None:
    """404 on robots.txt means no restrictions, not 'deny everything'."""
    report = await _resolve(
        {
            "/": httpx.Response(200, text=HOMEPAGE),
            "/careers": httpx.Response(200, text=CAREERS),
        }
    )
    assert "careers" in report.resolved_types


@pytest.mark.asyncio
async def test_robots_is_fetched_once_not_per_path() -> None:
    """Resolution probes ~20 paths. Re-fetching robots each time is 20x the load
    on a file that cannot change mid-run."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE)
        if request.url.path == "/careers":
            return httpx.Response(200, text=CAREERS)
        return httpx.Response(404, text="nope")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await resolve_sources("acme.com", client)

    assert calls.count("/robots.txt") == 1


# --- failure handling ---


@pytest.mark.asyncio
async def test_unreachable_homepage_still_returns_a_report() -> None:
    """No homepage means no soft-404 baseline. Degrade, do not crash — and record it."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        raise httpx.ConnectError("unreachable")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await resolve_sources("acme.com", client)

    assert report.homepage_reachable is False
    assert report.sources == []


@pytest.mark.asyncio
async def test_network_error_on_one_path_does_not_abort_the_rest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE)
        if request.url.path == "/careers":
            raise httpx.ConnectError("boom")
        if request.url.path == "/docs":
            return httpx.Response(200, text=CAREERS)
        return httpx.Response(404, text="nope")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await resolve_sources("acme.com", client)

    assert "docs" in report.resolved_types


@pytest.mark.asyncio
async def test_resolution_is_idempotent() -> None:
    routes = {
        "/robots.txt": httpx.Response(200, text=ROBOTS_ALLOW_ALL),
        "/": httpx.Response(200, text=HOMEPAGE),
        "/careers": httpx.Response(200, text=CAREERS),
    }
    first = await _resolve(routes)
    second = await _resolve(routes)
    assert [s.url for s in first.sources] == [s.url for s in second.sources]


# --- streaming size cap (gzip bomb / endless body) ---


class _Endless(httpx.AsyncByteStream):
    def __init__(self, chunk: bytes = b"<p>" + b"x" * 4093):
        self._chunk = chunk
        self.pulled = 0

    async def __aiter__(self):
        while True:
            self.pulled += 1
            yield self._chunk


@pytest.mark.asyncio
async def test_an_endless_homepage_is_aborted_and_treated_as_unreachable(monkeypatch) -> None:
    from scripts.registry import resolver

    monkeypatch.setattr(resolver, "_MAX_BYTES", 100_000)
    stream = _Endless()
    report = await _resolve(
        {"/robots.txt": httpx.Response(200, text=ROBOTS_ALLOW_ALL), "/": httpx.Response(200, stream=stream)}
    )
    assert report.homepage_reachable is False
    assert stream.pulled <= 100_000 // 4096 + 1


@pytest.mark.asyncio
async def test_a_gzip_bomb_candidate_is_a_fetch_error_not_a_crash(monkeypatch) -> None:
    import gzip

    from scripts.registry import resolver

    monkeypatch.setattr(resolver, "_MAX_BYTES", 100_000)
    bomb = gzip.compress(b"\0" * (50 * 1024 * 1024))
    report = await _resolve(
        {
            "/robots.txt": httpx.Response(200, text=ROBOTS_ALLOW_ALL),
            "/": httpx.Response(200, text=HOMEPAGE),
            "/careers": httpx.Response(
                200, headers={"content-encoding": "gzip"}, stream=httpx.ByteStream(bomb)
            ),
        }
    )
    careers = next(a for a in report.attempts if a.source_type == "careers")
    assert careers.outcome == "fetch_error" and "BodyTooLarge" in careers.detail


@pytest.mark.asyncio
async def test_an_endless_robots_txt_is_treated_as_permissive(monkeypatch) -> None:
    from scripts.registry import resolver

    monkeypatch.setattr(resolver, "_MAX_BYTES", 100_000)
    report = await _resolve(
        {
            "/robots.txt": httpx.Response(200, stream=_Endless(b"Disallow: /\n" * 300)),
            "/": httpx.Response(200, text=HOMEPAGE),
            "/careers": httpx.Response(200, text=CAREERS),
        }
    )
    assert "careers" in report.resolved_types


@pytest.mark.asyncio
@pytest.mark.parametrize("hostile_path", ["/robots.txt", "/careers", "/"])
async def test_a_corrupt_deflate_body_does_not_raise(hostile_path) -> None:
    routes = {
        "/robots.txt": httpx.Response(200, text=ROBOTS_ALLOW_ALL),
        "/": httpx.Response(200, text=HOMEPAGE),
        "/careers": httpx.Response(200, text=CAREERS),
    }
    routes[hostile_path] = httpx.Response(
        200,
        headers={"content-encoding": "deflate"},
        stream=httpx.ByteStream(b"garbage-not-deflate"),
    )
    report = await _resolve(routes)
    if hostile_path == "/":
        assert report.homepage_reachable is False
    elif hostile_path == "/careers":
        careers = next(a for a in report.attempts if a.source_type == "careers")
        assert careers.outcome == "fetch_error" and "DecodingError" in careers.detail
