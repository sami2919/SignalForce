"""Source resolution: turn a domain into a set of URLs worth watching.

Runs once per account. See docs/decisions/0004-url-registry-and-source-resolution.md
for the rationale behind heuristic path probing, GET-not-HEAD, mandatory soft-404
detection, storing the post-redirect URL, and respecting robots.txt.

Pure logic only — no database writes. `resolve_sources()` returns a report;
persisting to `account_sources` is Task 1.3's job.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.robotparser import RobotFileParser

import httpx

from scripts.net.guard import get_capped, guarded_client
from scripts.registry.models import (
    ResolutionOutcome,
    ResolutionReport,
    ResolvedSource,
    SourceAttempt,
    SourceType,
)
from scripts.watch.normalize import content_hash, normalize_html

logger = logging.getLogger(__name__)

_PATHS_BY_TYPE: dict[SourceType, tuple[str, ...]] = {
    "careers": ("/careers", "/jobs", "/careers/", "/company/careers", "/about/careers"),
    "docs": ("/docs", "/documentation", "/developers"),
    "changelog": ("/changelog", "/releases", "/whats-new", "/blog/changelog"),
    "pricing": ("/pricing", "/plans"),
    "blog": ("/blog", "/news"),
}

# Phrase matching only applies below this length. Real careers pages run to
# thousands of characters; the measured Lever soft-404 was 144. A long page
# containing "no longer available" inside one listing is legitimate content.
_SHORT_PAGE_CHARS = 500

# Below this, there is not enough server-rendered text to detect change against.
# A JS shell hashes stably forever and proves nothing while looking healthy.
# Provisional — revisit once Task 1.3 reports real distributions.
_MIN_CONTENT_CHARS = 200

_NOT_FOUND_PHRASES = (
    "couldn't find anything",
    "could not find anything",
    "404 error",
    "page not found",
    "no longer available",
    "position has been filled",
    "this job is closed",
)

_KNOWN_ATS_HOSTS = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "workable.com",
    "myworkdayjobs.com",
)

_USER_AGENT = "SignalForce/0.2 (+https://signalforce.fly.dev)"
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
# Same DoS bound as the watch fetcher (scripts/watch/fetcher.py). A body over it
# raises BodyTooLarge (an httpx.HTTPError) mid-stream, so each call site's
# existing fetch-error path handles it: robots -> permissive, homepage ->
# unreachable, candidate path -> fetch_error.
_MAX_BYTES = 8_000_000

# When no candidate path resolves, several different outcomes can occur across
# the list of paths tried for one source type (e.g. one path is blocked by
# robots, another 404s, another is a soft-404). The most diagnostically useful
# outcome should win over a merely generic one — a blocked path or a soft-404
# says more about what happened than "not_found" does, so a later not_found
# from an unrelated unlisted path must never paper over an earlier finding.
_OUTCOME_PRIORITY: dict[ResolutionOutcome, int] = {
    "not_found": 0,
    "fetch_error": 1,
    "blocked_by_robots": 2,
    "low_content": 3,
    "soft_404": 4,
}


def _is_known_ats_host(host: str) -> bool:
    return any(host == ats or host.endswith(f".{ats}") for ats in _KNOWN_ATS_HOSTS)


def _looks_like_not_found(text: str) -> bool:
    if len(text) >= _SHORT_PAGE_CHARS:
        return False
    lowered = text.lower()
    return any(phrase in lowered for phrase in _NOT_FOUND_PHRASES)


async def _fetch_robots(domain: str, client: httpx.AsyncClient) -> RobotFileParser:
    """Fetch robots.txt once. Missing or errored -> permissive, not deny-all."""
    parser = RobotFileParser()
    url = f"https://{domain}/robots.txt"
    try:
        resp = await get_capped(
            client,
            url,
            max_bytes=_MAX_BYTES,
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            parser.parse(resp.text.splitlines())
        else:
            parser.parse([])
    except httpx.HTTPError:
        logger.info(
            "robots.txt fetch failed; treating as permissive",
            extra={"domain": domain, "source_type": None, "outcome": "robots_fetch_error"},
        )
        parser.parse([])
    return parser


async def _fetch_homepage(
    domain: str, client: httpx.AsyncClient
) -> tuple[bool, str | None, str | None]:
    """Fetch the homepage once. Returns (reachable, final_url, content_hash)."""
    url = f"https://{domain}/"
    try:
        resp = await get_capped(
            client,
            url,
            max_bytes=_MAX_BYTES,
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        logger.info(
            "homepage unreachable",
            extra={"domain": domain, "source_type": None, "outcome": "fetch_error"},
        )
        return False, None, None

    if resp.status_code != 200:
        logger.info(
            "homepage non-200",
            extra={"domain": domain, "source_type": None, "outcome": "fetch_error"},
        )
        return False, None, None

    final_url = str(resp.url)
    h = content_hash(resp.text)
    return True, final_url, h


def _normalize_final_url(url: str) -> str:
    """Compare final URLs ignoring a trailing slash, so https://x.com/ == https://x.com."""
    return url.rstrip("/")


async def _resolve_one_type(
    domain: str,
    source_type: SourceType,
    client: httpx.AsyncClient,
    robots: RobotFileParser,
    homepage_final_url: str,
    homepage_hash: str,
) -> tuple[SourceAttempt, ResolvedSource | None]:
    """Probe candidate paths sequentially; stop at the first accepted success."""
    paths = _PATHS_BY_TYPE[source_type]
    best_outcome: ResolutionOutcome = "not_found"
    best_detail = ""

    def _record(outcome: ResolutionOutcome, detail: str) -> None:
        nonlocal best_outcome, best_detail
        if _OUTCOME_PRIORITY[outcome] >= _OUTCOME_PRIORITY[best_outcome]:
            best_outcome = outcome
            best_detail = detail

    for path in paths:
        url = f"https://{domain}{path}"
        if not robots.can_fetch(_USER_AGENT, url):
            _record("blocked_by_robots", "robots.txt disallows this path")
            continue

        try:
            resp = await get_capped(
                client,
                url,
                max_bytes=_MAX_BYTES,
                headers={"User-Agent": _USER_AGENT},
                timeout=_TIMEOUT,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            _record("fetch_error", f"{type(exc).__name__}: {exc}")
            continue

        if resp.status_code != 200:
            _record("not_found", f"HTTP {resp.status_code}")
            continue

        final_url = str(resp.url)

        if _normalize_final_url(final_url) == _normalize_final_url(homepage_final_url):
            _record("soft_404", "final URL equals homepage")
            continue

        text = normalize_html(resp.text)
        h = content_hash(resp.text)

        if h == homepage_hash:
            _record("soft_404", "content matches homepage (SPA shell)")
            continue

        if _looks_like_not_found(text):
            _record("soft_404", "matched not-found phrasing on a short page")
            continue

        if len(text) < _MIN_CONTENT_CHARS:
            _record("low_content", f"normalized length {len(text)} < {_MIN_CONTENT_CHARS}")
            continue

        confidence = 0.9 if _is_known_ats_host(resp.url.host) else 0.8
        attempt = SourceAttempt(
            source_type=source_type, outcome="resolved", url=final_url, detail=""
        )
        source = ResolvedSource(
            source_type=source_type, url=final_url, method="heuristic", confidence=confidence
        )
        logger.info(
            "source resolved",
            extra={"domain": domain, "source_type": source_type, "outcome": "resolved"},
        )
        return attempt, source

    logger.info(
        "source not resolved",
        extra={"domain": domain, "source_type": source_type, "outcome": best_outcome},
    )
    return (
        SourceAttempt(source_type=source_type, outcome=best_outcome, url=None, detail=best_detail),
        None,
    )


async def resolve_sources(domain: str, client: httpx.AsyncClient) -> ResolutionReport:
    """Resolve a domain to signal-bearing URLs, once.

    Order: robots.txt once, homepage once (soft-404 baseline), then each source
    type is probed for its candidate paths (sequentially within a type, first
    200-that-passes-soft-404-checks wins). Different types may run concurrently.
    """
    robots = await _fetch_robots(domain, client)
    reachable, homepage_final_url, homepage_hash = await _fetch_homepage(domain, client)

    if not reachable or homepage_final_url is None or homepage_hash is None:
        attempts = [
            SourceAttempt(
                source_type=st,
                outcome="fetch_error",
                url=None,
                detail="homepage unreachable; no soft-404 baseline",
            )
            for st in _PATHS_BY_TYPE
        ]
        return ResolutionReport(
            domain=domain, sources=[], attempts=attempts, homepage_reachable=False
        )

    results = await asyncio.gather(
        *(
            _resolve_one_type(domain, st, client, robots, homepage_final_url, homepage_hash)
            for st in _PATHS_BY_TYPE
        )
    )

    attempts = [r[0] for r in results]
    sources = [r[1] for r in results if r[1] is not None]

    return ResolutionReport(
        domain=domain, sources=sources, attempts=attempts, homepage_reachable=True
    )


if __name__ == "__main__":
    import sys

    async def _main() -> None:
        domain = sys.argv[1] if len(sys.argv) > 1 else "example.com"
        async with guarded_client() as client:
            report = await resolve_sources(domain, client)
        print(report.model_dump_json(indent=2))

    asyncio.run(_main())
