"""Crawl venue websites, detect their stack, and fall back to Firecrawl for JS-only widgets.

The existing `fetch_all` is reused (robots.txt, body caps, SSRF guard, per-host limits).
Firecrawl is spent only on pages where no reservation platform was found, because booking
widgets are often injected by JavaScript (spec §6.13).
"""

import asyncio
import logging
from collections.abc import Sequence
from datetime import datetime

from scripts.firecrawl_client import FirecrawlClient
from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.models import StackObservation, Venue
from scripts.hospitality.stack.fingerprints import RESERVATION, detect_platforms
from scripts.net.guard import guarded_client
from scripts.watch.fetcher import SourceRef, fetch_all

logger = logging.getLogger(__name__)

FORBIDDEN_URL_PARTS = ("loyalist.com/for/",)  # Global constraint: never fetch these.


def _allowed(url: str) -> bool:
    lowered = url.lower()
    return not any(part in lowered for part in FORBIDDEN_URL_PARTS)


def _firecrawl_html(response: dict) -> str | None:
    data = response.get("data") or {}
    return data.get("rawHtml") or data.get("html") or None


async def crawl_stacks(
    venues: Sequence[Venue],
    now: datetime,
    *,
    firecrawl: FirecrawlClient | None,
    firecrawl_budget: CallBudget,
) -> list[StackObservation]:
    """Fetch each venue website and record its platforms; only venues with a website."""
    targets = [v for v in venues if v.website and _allowed(v.website)]
    refs = [SourceRef(source_id=i, url=v.website or "") for i, v in enumerate(targets)]
    async with guarded_client() as client:
        results = await fetch_all(refs, client, retain_bodies=True)
    by_source = {r.source_id: r for r in results}

    observations: list[StackObservation] = []
    firecrawl_open = firecrawl is not None
    for i, venue in enumerate(targets):
        url = venue.website or ""
        result = by_source.get(i)
        if result is None or result.error or result.robots_blocked or result.body is None:
            logger.warning(
                "stack fetch failed; no observation: venue=%s url=%s status=%s error=%s robots=%s",
                venue.venue_id,
                url,
                result.status_code if result else None,
                result.error if result else "no result",
                result.robots_blocked if result else None,
            )
            continue
        found = dict(detect_platforms(result.body))
        via = "fetcher"
        if firecrawl_open and firecrawl is not None and not RESERVATION & found.keys():
            try:
                firecrawl_budget.spend()  # spend first: the call over the limit never goes out
            except BudgetExceeded as exc:
                logger.warning("firecrawl fallback disabled: %s", exc)
                firecrawl_open = False
            else:
                try:
                    response = await asyncio.to_thread(
                        firecrawl.scrape, url, formats=["rawHtml"], only_main_content=False
                    )
                    html = _firecrawl_html(response)
                except Exception:
                    logger.exception(
                        "firecrawl scrape failed: venue=%s url=%s", venue.venue_id, url
                    )
                    html = None
                if html:
                    found = {**found, **dict(detect_platforms(html))}
                    via = "firecrawl"
        platforms = tuple(sorted(found))
        observations.append(
            StackObservation(
                venue_id=venue.venue_id,
                url=url,
                observed_at=now,
                platforms=platforms,
                evidence=tuple(found[p] for p in platforms),
                fetched_via=via,  # type: ignore[arg-type]
            )
        )
    return observations
