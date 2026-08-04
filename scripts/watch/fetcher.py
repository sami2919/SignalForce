"""Async fetch-and-hash layer for the watch pass.

Pure function over HTTP: given a list of sources, fetch them all concurrently,
hash the results with `content_hash` from Task 1.2, and return one
`ProbeResult` per input. No database, no confirm-on-change logic, no
`scan_runs` — those belong to the runner built in Task 1.3b.

Two properties dominate the design (see
docs/decisions/0005-watch-layer-concurrency-and-persistence.md, Decision 1):

1. This must never raise. A failure on one source becomes a `ProbeResult`
   with `.error` set, not an exception — one dead domain must not abort a
   pass over thousands of sources.
2. Per-host concurrency must be genuinely bounded independently of the
   global limit. The global semaphore protects us (fds, memory, egress);
   the per-host semaphore protects the site being fetched. A single global
   limit would allow every in-flight slot to land on one domain, which reads
   as an attack and invites a ban — producing empty results indistinguishable
   from a quiet account. The global semaphore is always acquired before the
   per-host one, in every code path, to avoid deadlock under load.
"""

from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import BaseModel

from scripts.watch.normalize import content_hash

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

# Peak memory is roughly concurrency x response size. Typical pages are
# ~200KB, so a 100-wide pass holds ~20MB. The cap bounds the pathological
# case: 100 x 8MB = 800MB worst case, which is why Task 1.3b provisions the
# worker machine at 1GB rather than the 256MB default.
#
# 2MB was the original value and was wrong: measured 2026-08-04, neon.com's
# changelog is 2.7MB raw but only 18,805 chars normalized, and neon.com/blog
# is 3.8MB raw / 2,076 normalized. Raw transport size is not a proxy for
# content size on JS-heavy sites.
_MAX_BYTES = 8_000_000  # skip hashing pathological pages (DoS bound, not content filter)
_USER_AGENT = "SignalForce/0.2 (+https://signalforce.fly.dev)"


class SourceRef(BaseModel, frozen=True):
    source_id: int
    url: str


class ProbeResult(BaseModel, frozen=True):
    source_id: int
    content_hash: str | None = None
    status_code: int | None = None
    latency_ms: int = 0
    bytes: int = 0
    error: str | None = None
    robots_blocked: bool = False


async def _fetch_robots(host: str, client: httpx.AsyncClient) -> RobotFileParser:
    """Fetch robots.txt once for a host. Missing or errored -> permissive."""
    parser = RobotFileParser()
    url = f"https://{host}/robots.txt"
    try:
        resp = await client.get(
            url, headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT, follow_redirects=True
        )
        if resp.status_code == 200:
            parser.parse(resp.text.splitlines())
        else:
            parser.parse([])
    except httpx.HTTPError as exc:
        logger.info(
            "robots.txt fetch failed; treating as permissive",
            extra={"host": host, "error": str(exc)},
        )
        parser.parse([])
    return parser


async def _fetch_one(
    ref: SourceRef,
    client: httpx.AsyncClient,
    global_sem: asyncio.Semaphore,
    host_sems: dict[str, asyncio.Semaphore],
    robots_cache: dict[str, RobotFileParser],
) -> ProbeResult:
    """Fetch and hash a single source. Never raises."""
    try:
        parts = urlsplit(ref.url)
        host = parts.netloc
        if not host:
            return ProbeResult(source_id=ref.source_id, error=f"malformed url: {ref.url}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "failed to parse source url",
            extra={"source_id": ref.source_id, "url": ref.url, "error": str(exc)},
        )
        return ProbeResult(source_id=ref.source_id, error=f"malformed url: {exc}")

    robots = robots_cache.get(host)
    if robots is not None and not robots.can_fetch(_USER_AGENT, ref.url):
        return ProbeResult(source_id=ref.source_id, robots_blocked=True)

    host_sem = host_sems[host]
    try:
        async with global_sem:
            async with host_sem:
                start = time.perf_counter()
                resp = await client.get(
                    ref.url,
                    headers={"User-Agent": _USER_AGENT},
                    timeout=_TIMEOUT,
                    follow_redirects=True,
                )
                latency_ms = int((time.perf_counter() - start) * 1000)

        body = resp.content
        n_bytes = len(body)

        if resp.status_code != 200:
            return ProbeResult(
                source_id=ref.source_id,
                status_code=resp.status_code,
                latency_ms=latency_ms,
                bytes=n_bytes,
                error=f"non-200 status: {resp.status_code}",
            )

        if n_bytes > _MAX_BYTES:
            logger.warning(
                "oversized body skipped",
                extra={"source_id": ref.source_id, "url": ref.url, "bytes": n_bytes},
            )
            return ProbeResult(
                source_id=ref.source_id,
                status_code=resp.status_code,
                latency_ms=latency_ms,
                bytes=n_bytes,
                error=f"body too large: {n_bytes} bytes",
            )

        text = resp.text
        return ProbeResult(
            source_id=ref.source_id,
            content_hash=content_hash(text),
            status_code=resp.status_code,
            latency_ms=latency_ms,
            bytes=n_bytes,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "fetch failed",
            extra={"source_id": ref.source_id, "url": ref.url, "error": str(exc)},
        )
        return ProbeResult(source_id=ref.source_id, error=str(exc))


async def fetch_all(
    sources: list[SourceRef],
    client: httpx.AsyncClient,
    concurrency: int = 100,
    per_host: int = 2,
) -> list[ProbeResult]:
    """Fetch and hash every source concurrently. Never raises.

    Global concurrency is bounded by `concurrency`; per-host concurrency is
    independently bounded by `per_host`. robots.txt is fetched once per
    distinct host and cached for the duration of this call.
    """
    if not sources:
        return []

    hosts: dict[str, None] = {}
    parseable: list[SourceRef] = []
    unparseable: list[ProbeResult] = []
    for ref in sources:
        try:
            host = urlsplit(ref.url).netloc
        except Exception:  # noqa: BLE001
            host = ""
        if not host:
            unparseable.append(
                ProbeResult(source_id=ref.source_id, error=f"malformed url: {ref.url}")
            )
            continue
        hosts.setdefault(host, None)
        parseable.append(ref)

    global_sem = asyncio.Semaphore(concurrency)
    host_sems = {host: asyncio.Semaphore(per_host) for host in hosts}

    robots_cache: dict[str, RobotFileParser] = {}
    if hosts:
        robots_results = await asyncio.gather(*(_fetch_robots(host, client) for host in hosts))
        robots_cache = dict(zip(hosts.keys(), robots_results))

    fetched = await asyncio.gather(
        *(_fetch_one(ref, client, global_sem, host_sems, robots_cache) for ref in parseable)
    )

    return [*unparseable, *fetched]


if __name__ == "__main__":
    import sys

    print("scripts.watch.fetcher provides fetch_all(); not a CLI entrypoint.", file=sys.stderr)
    sys.exit(1)
