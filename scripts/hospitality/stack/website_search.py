"""Website lookup by search (Exa primary, Firecrawl search fallback) with deterministic proof.

A search result is only a candidate. A site is accepted when its own pages (home page plus at
most `max_verify_pages` likely pages, fetched with the robots-respecting fetcher) show the
venue's DOHMH phone number or its street address as recorded in the public data. A name match
alone is never enough. A venue with no DOHMH record (not yet open) has no phone and can only
verify on address; that is recorded in `WebsiteLookup.verified_by`.

Never fetched: `loyalist.com/for/` and LinkedIn. A robots-blocked page is not retried through
Firecrawl. Zero or ambiguous verified candidates take no website, and the miss reason is kept.
"""

import asyncio
import logging
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import date
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict
from selectolax.parser import HTMLParser

from scripts.firecrawl_client import FirecrawlClient
from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.config import WebsitesConfig
from scripts.hospitality.discover.exa import ExaClient
from scripts.hospitality.models import Venue, WebsiteLookup
from scripts.hospitality.resolve.normalize import normalize_address, registrable_domain
from scripts.hospitality.stack.crawl import FORBIDDEN_URL_PARTS
from scripts.net.guard import guarded_client
from scripts.watch.fetcher import SourceRef, fetch_all

logger = logging.getLogger(__name__)

# Domains that are never fetched, whatever the config list says (scraping them is off limits).
NEVER_FETCH_DOMAINS: tuple[str, ...] = ("linkedin.com",)
SEARCH_SOURCE = "search"
_MIN_ADDRESS_TOKENS = 3  # house number + at least two more tokens ("123 w 27 st" is 4)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.\-]*)?\(?(\d{3})\)?[\s.\-]*(\d{3})[\s.\-]*(\d{4})(?!\d)")


class FetchedPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    status: Literal["ok", "robots", "failed"]
    body: str | None


PageFetcher = Callable[[Sequence[str]], Mapping[str, FetchedPage]]


# --- fetching --------------------------------------------------------------------------


def is_fetchable(url: str) -> bool:
    """False for any URL this pipeline must never request (Loyalist /for/ pages, LinkedIn)."""
    lowered = url.lower()
    if any(part in lowered for part in FORBIDDEN_URL_PARTS):
        return False
    return registrable_domain(url) not in NEVER_FETCH_DOMAINS


def fetch_pages(urls: Sequence[str]) -> dict[str, FetchedPage]:
    """Fetch pages with the robots-respecting fetcher (SSRF guard, body caps, per-host limits)."""
    allowed = [u for u in urls if is_fetchable(u)]
    out = {u: FetchedPage(url=u, status="failed", body=None) for u in urls}
    if not allowed:
        return out
    refs = [SourceRef(source_id=i, url=u) for i, u in enumerate(allowed)]

    async def run() -> list:
        async with guarded_client() as client:
            return await fetch_all(refs, client, retain_bodies=True)

    for result in asyncio.run(run()):
        url = allowed[result.source_id]
        if result.robots_blocked:
            out[url] = FetchedPage(url=url, status="robots", body=None)
        elif result.error or result.status_code != 200 or result.body is None:
            logger.info(
                "website verify fetch failed: url=%s status=%s error=%s",
                url,
                result.status_code,
                result.error,
            )
        else:
            out[url] = FetchedPage(url=url, status="ok", body=result.body)
    return out


# --- verification primitives -----------------------------------------------------------


def _phone10(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def page_shows_phone(body: str, phone: str) -> bool:
    """True when the page carries `phone` (digits compared, any punctuation, tel: links too)."""
    want = _phone10(phone)
    if want is None:
        return False
    return any("".join(m.groups()) == want for m in _PHONE_RE.finditer(body))


def _page_text(body: str) -> str:
    """Visible text plus JSON-LD bodies (structured addresses), tags and scripts removed."""
    tree = HTMLParser(body)
    ld = " ".join(n.text() for n in tree.css('script[type="application/ld+json"]'))
    tree.strip_tags(["script", "style"])
    text = tree.body.text(separator=" ") if tree.body is not None else body
    return f"{text} {ld}"


def page_shows_address(body: str, address: str, zip_code: str, cfg: WebsitesConfig) -> bool:
    """House number + street (normalized) with the zip or a locality term right after it."""
    want = normalize_address(address).split()
    if len(want) < _MIN_ADDRESS_TOKENS or not want[0].isdigit():
        return False
    tokens = normalize_address(_page_text(body), strip_unit=False).split()
    n = len(want)
    terms = [t.split() for t in cfg.address_context_terms]
    for i in range(len(tokens) - n + 1):
        if tokens[i : i + n] != want:
            continue
        after = tokens[i + n : i + n + cfg.address_context_tokens]
        if zip_code and zip_code in after:
            return True
        if any(after[j : j + len(t)] == t for t in terms for j in range(len(after))):
            return True
    return False


# --- candidates ------------------------------------------------------------------------


def _root(url: str) -> str | None:
    parts = urlsplit(url if "://" in url else f"https://{url}")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return f"{parts.scheme}://{parts.hostname}/"


def candidate_roots(
    urls: Sequence[str], excluded: Sequence[str], limit: int
) -> tuple[list[str], int]:
    """Home-page URLs of unfiltered, distinct-domain results (at most `limit`), and how many
    results were dropped by the filter."""
    drop = {d.lower() for d in excluded} | set(NEVER_FETCH_DOMAINS)
    seen: set[str] = set()
    roots: list[str] = []
    dropped = 0
    for url in urls:
        domain = registrable_domain(url)
        root = _root(url)
        if not domain or root is None or domain in drop or not is_fetchable(url):
            dropped += 1
            continue
        if domain in seen:
            continue
        seen.add(domain)
        roots.append(root)
    return roots[:limit], dropped


def _firecrawl_urls(response: dict) -> list[str]:
    """URLs from a Firecrawl search response (the one place that knows its shape)."""
    data = response.get("data") or []
    if isinstance(data, dict):  # tolerate a grouped response
        data = data.get("web") or []
    return [r["url"] for r in data if isinstance(r, dict) and r.get("url")]


class _Verdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    root: str
    outcome: Literal["verified", "mismatch", "robots", "failed"]
    method: Literal["phone", "address"] | None = None
    evidence_url: str | None = None


class WebsiteFinder:
    """Finds and proves one venue's website. Spends each budget before its call."""

    def __init__(
        self,
        cfg: WebsitesConfig,
        *,
        exa: ExaClient | None,
        firecrawl: FirecrawlClient | None,
        firecrawl_budget: CallBudget | None,
        fetch: PageFetcher = fetch_pages,
        phones: Mapping[str, str] | None = None,
    ) -> None:
        if exa is None and firecrawl is None:
            raise ValueError("WebsiteFinder needs an Exa or a Firecrawl client")
        if firecrawl is not None and firecrawl_budget is None:
            raise ValueError("a Firecrawl client needs its CallBudget")
        self.cfg = cfg
        self._exa = exa
        self._fc = firecrawl
        self._fc_budget = firecrawl_budget
        self._fetch = fetch
        self._phones = phones or {}
        self._off: set[str] = set()  # exhausted or erroring providers, for this run
        self._errors: dict[str, int] = {}

    # -- search ---------------------------------------------------------------------

    def _provider_failed(self, name: str, exc: Exception) -> None:
        self._errors[name] = self._errors.get(name, 0) + 1
        logger.error("%s search failed (%d in a row): %r", name, self._errors[name], exc)
        if self._errors[name] >= self.cfg.max_provider_errors:
            logger.error("%s search switched off for this run after repeated errors", name)
            self._off.add(name)

    def _search_one(self, name: str, query: str) -> list[str] | None:
        """Result URLs, or None when the provider could not answer (spent, off or errored)."""
        if name in self._off:
            return None
        try:
            if name == "exa" and self._exa is not None:
                results = self._exa.search(
                    query, num_results=self.cfg.search_results, include_text=False
                )
                urls = [r.url for r in results]
            elif name == "firecrawl" and self._fc is not None and self._fc_budget is not None:
                self._fc_budget.spend()  # spend first: the call over the limit never goes out
                raw = self._fc.search(query, limit=self.cfg.search_results, scrape_options={})
                urls = _firecrawl_urls(raw)
            else:
                return None
        except BudgetExceeded as exc:
            logger.warning("%s search budget spent: %s", name, exc)
            self._off.add(name)
            return None
        except Exception as exc:  # noqa: BLE001 (logged with context; the run continues)
            self._provider_failed(name, exc)
            return None
        self._errors[name] = 0
        return urls

    def _candidates(self, venue: Venue) -> tuple[list[str], str | None]:
        """(roots to verify, miss reason when there are none)."""
        query = f"{venue.name} {venue.address} New York"
        answered = False
        total = 0
        for name in ("exa", "firecrawl"):
            urls = self._search_one(name, query)
            if urls is None:
                continue
            answered = True
            total += len(urls)
            roots, _ = candidate_roots(urls, self.cfg.excluded_domains, self.cfg.max_candidates)
            if roots:
                return roots, None
        if not answered:
            if self._off:
                raise BudgetExceeded("no search provider left (budget spent or switched off)")
            return [], "search_error"
        return [], "all_filtered" if total else "no_candidates"

    # -- verification ---------------------------------------------------------------

    def _verify(self, root: str, venue: Venue, phone: str) -> _Verdict:
        home = self._fetch([root])[root]
        if home.status != "ok":
            return _Verdict(root=root, outcome="robots" if home.status == "robots" else "failed")
        pages = [home]
        extras = [root.rstrip("/") + p for p in self.cfg.verify_paths][: self.cfg.max_verify_pages]
        if not self._shows(home, venue, phone):
            fetched = self._fetch([u for u in extras if is_fetchable(u)])
            pages += [fetched[u] for u in extras if u in fetched and fetched[u].status == "ok"]
        for method, shows in (("phone", self._shows_phone), ("address", self._shows_address)):
            for page in pages:
                if shows(page, venue, phone):
                    return _Verdict(
                        root=root,
                        outcome="verified",
                        method=method,
                        evidence_url=page.url,  # type: ignore[arg-type]
                    )
        return _Verdict(root=root, outcome="mismatch")

    @staticmethod
    def _shows_phone(page: FetchedPage, venue: Venue, phone: str) -> bool:
        return page_shows_phone(page.body or "", phone)

    def _shows_address(self, page: FetchedPage, venue: Venue, phone: str) -> bool:
        return page_shows_address(page.body or "", venue.address, venue.zip_code, self.cfg)

    def _shows(self, page: FetchedPage, venue: Venue, phone: str) -> bool:
        return self._shows_phone(page, venue, phone) or self._shows_address(page, venue, phone)

    # -- the lookup -----------------------------------------------------------------

    def find(self, venue: Venue, today: date) -> WebsiteLookup:
        """One lookup (hit or miss). Raises BudgetExceeded when no provider can be queried."""

        def miss(reason: str) -> WebsiteLookup:
            logger.info("website miss: venue=%s reason=%s", venue.venue_id, reason)
            return WebsiteLookup(
                venue_id=venue.venue_id,
                website=None,
                looked_up_on=today,
                source=SEARCH_SOURCE,
                miss_reason=reason,
            )

        roots, reason = self._candidates(venue)
        if reason:
            return miss(reason)
        phone = self._phones.get(venue.camis or "", "")
        verdicts = [self._verify(r, venue, phone) for r in roots]
        by_method = {
            m: [v for v in verdicts if v.outcome == "verified" and v.method == m]
            for m in ("phone", "address")
        }
        for method in ("phone", "address"):
            hits = by_method[method]
            if len(hits) > 1:
                logger.warning(
                    "ambiguous website: venue=%s %s-verified domains %s",
                    venue.venue_id,
                    method,
                    [h.root for h in hits],
                )
                return miss("ambiguous")
            if hits:
                return WebsiteLookup(
                    venue_id=venue.venue_id,
                    website=hits[0].root,
                    looked_up_on=today,
                    source=SEARCH_SOURCE,
                    verified_by=method,
                    evidence_url=hits[0].evidence_url,
                )
        outcomes = {v.outcome for v in verdicts}
        if "mismatch" in outcomes:
            return miss("none_verified")
        return miss("robots_blocked" if "robots" in outcomes else "fetch_failed")

    @property
    def exa_calls(self) -> int:
        return self._exa.budget.used if self._exa is not None else 0

    @property
    def firecrawl_calls(self) -> int:
        return self._fc_budget.used if self._fc_budget is not None else 0


def iter_search_lookups(
    venues: Sequence[Venue], finder: WebsiteFinder, priority_ids: Sequence[str], today: date
) -> Iterator[WebsiteLookup]:
    """One lookup per priority venue, in priority order; stops once no provider is left.

    A generator so the caller keeps every lookup made before an error ends the run. A search
    that errored records nothing (an error is not a miss; the venue stays due).
    """
    by_id = {v.venue_id: v for v in venues}
    for vid in priority_ids:
        venue = by_id.get(vid)
        if venue is None:
            continue
        try:
            lookup = finder.find(venue, today)
        except BudgetExceeded as exc:
            logger.warning("Stopping website lookups: %s", exc)
            return
        if lookup.miss_reason == "search_error":
            continue
        yield lookup
