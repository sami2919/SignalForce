"""Culinary Agents (culinaryagents.com): hiring, opening-soon and group evidence.

Employer-side facts only, from the server-rendered public search pages: job cards (company,
title, address, optional parent group, relative posting age) and company cards (name, address,
"Part of <group>", description, an "Opening Soon" status and a "Hiring Now" tag). Nothing is
read from `/users` or any login-gated page, and no job-seeker or employee data is collected.

The site's user agreement appears to restrict automated collection, so the source is disabled by
default (`culinary_agents.enabled`), fetches go through a robots-respecting, rate-limited,
page-budgeted fetcher, and every page spends `CallBudget` before the request goes out.

Parsing is deterministic and tolerant: a card that cannot be read is logged and skipped. Matching
a company to the venue universe is deterministic too: a company that matches zero or several
venues emits nothing (it is logged as an unmatched candidate), never a guess.
"""

import asyncio
import hashlib
import logging
import re
import time
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote_plus, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from selectolax.lexbor import LexborHTMLParser, LexborNode

from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.config import CulinaryAgentsConfig
from scripts.hospitality.models import (
    CACompany,
    CAJob,
    Group,
    GroupEvidence,
    Signal,
    SignalType,
    Venue,
)
from scripts.hospitality.resolve.normalize import (
    normalize_address,
    normalize_name,
    registrable_domain,
    strict_name_match,
)
from scripts.net.guard import get_capped, guarded_client

logger = logging.getLogger(__name__)

BASE = "https://culinaryagents.com"
SOURCE = "culinary_agents"
USER_AGENT = "SignalForce/0.2 (+https://signalforce.fly.dev)"  # same identity as the watch fetcher
MAX_BYTES = 2_000_000
_HOSTS = frozenset({"culinaryagents.com", "www.culinaryagents.com"})
_PLACE_SUFFIX = frozenset({"nyc", "ny", "brooklyn", "manhattan", "queens", "bronx"})
_GENERIC_GROUP = frozenset({"", "group", "restaurant group", "hospitality group"})
_POSTED = re.compile(r"posted (\d+) (day|week|month)s? ago", re.IGNORECASE)
_PHONE = re.compile(r"^[\d\s().+-]{7,}$")
_ENTITY_ID = re.compile(r"/entities/(\d+)")

Fetch = Callable[[str], str | None]


# ---- URLs and the fetcher -------------------------------------------------------------------


def is_fetchable(url: str) -> bool:
    """True only for public culinaryagents.com pages: never /users, login or other hosts."""
    parts = urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "") not in _HOSTS:
        return False
    path = parts.path.lower()
    if path == "/users" or path.startswith(("/users/", "/users?")):
        return False
    query = parts.query.lower()
    return "login=true" not in query and "intent=" not in query


def _search_url(path: str, params: list[tuple[str, str]]) -> str:
    query = "&".join(f"{quote_plus(k, safe='[]')}={quote_plus(v)}" for k, v in params)
    return f"{BASE}{path}?{query}"


def job_search_url(location: str, *, opening_soon: bool = False) -> str:
    params = [("search[location]", location)]
    if opening_soon:
        params.append(("search[entity_status][]", "opening_soon"))
    return _search_url("/search/jobs", params)


def company_search_url(location: str) -> str:
    params = [("search[location]", location), ("search[open_status][]", "opening_soon")]
    return _search_url("/companies/search", params)


def _disallow_all() -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse(["User-agent: *", "Disallow: /"])
    return parser


class PoliteFetcher:
    """Sync GET of one public page: robots.txt (fetched once per run; unreadable = fetch
    nothing), SSRF guard, body cap."""

    def __init__(
        self, client_factory: Callable[[], httpx.AsyncClient] = lambda: guarded_client()
    ) -> None:
        self._factory = client_factory
        self._robots: RobotFileParser | None = None

    def __call__(self, url: str) -> str | None:
        if not is_fetchable(url):
            logger.warning("culinary agents: refusing to fetch %s", url)
            return None
        return asyncio.run(self._get(url))

    async def _get(self, url: str) -> str | None:
        headers = {"User-Agent": USER_AGENT}
        timeout = httpx.Timeout(15.0, connect=5.0)
        async with self._factory() as client:
            if self._robots is None:
                self._robots = await self._load_robots(client, headers, timeout)
            if not self._robots.can_fetch(USER_AGENT, url):
                logger.warning("culinary agents: robots.txt disallows %s", url)
                return None
            try:
                resp = await get_capped(
                    client,
                    url,
                    max_bytes=MAX_BYTES,
                    headers=headers,
                    timeout=timeout,
                    follow_redirects=True,
                )
            except httpx.HTTPError as exc:
                logger.warning("culinary agents fetch failed: url=%s error=%s", url, exc)
                return None
        if resp.status_code != 200 or not is_fetchable(str(resp.url)):
            logger.warning(
                "culinary agents fetch failed: url=%s status=%s final=%s",
                url,
                resp.status_code,
                resp.url,
            )
            return None
        return resp.text

    @staticmethod
    async def _load_robots(
        client: httpx.AsyncClient, headers: dict[str, str], timeout: httpx.Timeout
    ) -> RobotFileParser:
        parser = RobotFileParser()
        try:
            resp = await get_capped(
                client,
                f"{BASE}/robots.txt",
                max_bytes=MAX_BYTES,
                headers=headers,
                timeout=timeout,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            logger.warning("culinary agents robots.txt fetch failed; fetching nothing: %s", exc)
            return _disallow_all()
        if resp.status_code != 200:
            # Fail closed (M8): the source's terms restrict automated collection, and RFC 9309
            # treats an unreachable robots.txt as disallow; a missing one is not a licence here.
            logger.warning(
                "culinary agents robots.txt status=%s; fetching nothing", resp.status_code
            )
            return _disallow_all()
        parser.parse(resp.text.splitlines())
        return parser


# ---- parsing --------------------------------------------------------------------------------


def entity_id(url: str) -> str | None:
    match = _ENTITY_ID.search(url)
    return match.group(1) if match else None


def _text(node: LexborNode | None) -> str:
    return " ".join(node.text().split()) if node is not None else ""


def _posted(text: str, today: date) -> date | None:
    match = _POSTED.search(text)
    if match:
        n, unit = int(match.group(1)), match.group(2).lower()
        return today - timedelta(days={"day": 1, "week": 7, "month": 30}[unit] * n)
    return today if "posted today" in text.lower() else None


def _job_from_card(card: LexborNode, today: date, opening_soon: bool) -> CAJob | None:
    anchor = card.css_first("a.ca-single-job-card")
    if anchor is None:
        return None
    title = (anchor.attributes.get("data-title") or "").strip()
    company = (anchor.attributes.get("data-entity") or "").strip()
    href = anchor.attributes.get("href") or ""
    if not title or not company or not href:
        return None
    rows = [_text(n) for n in card.css(".key-info > div")]
    # rows: title, company, employment, [parent group], "address • cuisine"
    group = rows[3] if len(rows) >= 5 and rows[3] else None
    address = rows[-1].split("•")[0].strip() if len(rows) >= 4 else ""
    avatar = card.css_first("div.avatar")
    ident = None
    if avatar is not None:
        found = re.search(r"js-entity-(\d+)", avatar.attributes.get("class") or "")
        ident = found.group(1) if found else None
    if ident is None:
        save = card.css_first("a.js-action")
        ident = entity_id(save.attributes.get("href") or "") if save is not None else None
    tags = card.css_first(".my-job-tags")
    return CAJob(
        company=company,
        company_url=f"{BASE}/entities/{ident}" if ident else "",
        title=title,
        location=address,
        group=group,
        posted=_posted(_text(tags), today),
        url=urljoin(BASE, urlsplit(href).path),
        opening_soon=opening_soon,
    )


def parse_job_search(html: str, today: date, *, opening_soon: bool = False) -> list[CAJob]:
    """Job cards on a search page; an unreadable card is logged and skipped, never fatal."""
    if not html.strip():
        return []
    out: list[CAJob] = []
    for node in LexborHTMLParser(html).css("div.new-job-card"):
        classes = (node.attributes.get("class") or "").split()
        if "card" in classes:  # the inner wrapper of the same card
            continue
        try:
            job = _job_from_card(node, today, opening_soon)
        except Exception:
            logger.exception("culinary agents: unparseable job card")
            continue
        if job is None:
            logger.warning("culinary agents: unparseable job card skipped (no title/company/url)")
            continue
        out.append(job)
    return out


def _company_from_card(card: LexborNode) -> CACompany | None:
    link = card.css_first("a.stretched-link")
    href = (link.attributes.get("href") or "") if link is not None else ""
    name = _text(card.css_first(".name"))
    if "/entities/" not in href or not name:
        return None  # group cards link to /groups/; skip those and nameless cards
    address = _text(card.css_first(".my-1"))
    group: str | None = None
    description = ""
    for node in card.css(".left-container > .text-muted"):
        text = _text(node)
        if text.startswith("Part of "):
            group = text.removeprefix("Part of ").strip() or None
        elif text and not _PHONE.match(text) and not description:
            description = text
    tags = {_text(n) for n in card.css(".tags-container .tag")}
    return CACompany(
        name=name,
        url=urljoin(BASE, urlsplit(href).path),
        description=description,
        locations=(address,) if address else (),
        group=group,
        opening_soon="opening soon" in _text(card.css_first(".entity-status")).lower(),
        hiring="Hiring Now" in tags,
        website=None,
    )


def parse_company_search(html: str) -> list[CACompany]:
    """Company (entity) cards on a company search page; unreadable cards are skipped."""
    if not html.strip():
        return []
    out: list[CACompany] = []
    for card in LexborHTMLParser(html).css("div.company-card"):
        try:
            company = _company_from_card(card)
        except Exception:
            logger.exception("culinary agents: unparseable company card")
            continue
        if company is not None:
            out.append(company)
    return out


def parse_company(html: str, url: str) -> CACompany | None:
    """A company profile page: name, address, description and website. Never reads people."""
    tree = LexborHTMLParser(html)
    tree.strip_tags(["script", "style"])  # profile pages inline jQuery inside the About section
    name = _text(tree.css_first("h1"))
    if not name:
        return None
    geo = tree.css_first("i.bi-geo-alt-fill")
    address = _text(geo.next) if geo is not None and geo.next is not None else ""
    link = tree.css_first("#links a[href^='http']")
    return CACompany(
        name=name,
        url=url,
        description=_text(tree.css_first("#about .section-view")),
        locations=(address,) if address else (),
        group=None,  # profile pages do not state a group; the search cards do
        opening_soon=False,  # not shown on the profile page; the filtered search is the source
        hiring=False,
        website=link.attributes.get("href") if link is not None else None,
    )


# ---- fetching -------------------------------------------------------------------------------


class _Pacer:
    """Sleeps `delay` seconds before every request except the first."""

    def __init__(self, delay: float, sleep: Callable[[float], None]) -> None:
        self._delay, self._sleep, self._started = delay, sleep, False

    def __call__(self) -> None:
        if self._started:
            self._sleep(self._delay)
        self._started = True


def _get(url: str, budget: CallBudget, fetch: Fetch, pace: Callable[[], None]) -> str | None:
    """One budgeted page. Refused URLs cost nothing; the budget is spent before the request."""
    if not is_fetchable(url):
        logger.warning("culinary agents: refusing to fetch %s", url)
        return None
    budget.spend()  # raises BudgetExceeded before the request over the limit goes out
    pace()
    html = fetch(url)
    if html is None:
        logger.warning("culinary agents fetch failed: %s", url)
    return html


def _company_from_job(job: CAJob) -> CACompany:
    return CACompany(
        name=job.company,
        url=job.company_url,
        description="",
        locations=(job.location,) if job.location else (),
        group=job.group,
        opening_soon=True,
        hiring=True,
        website=None,
    )


def _enrich_websites(
    companies: Sequence[CACompany],
    cfg: CulinaryAgentsConfig,
    budget: CallBudget,
    fetch: Fetch,
    pace: Callable[[], None],
) -> list[CACompany]:
    """Fetch a few opening-soon company profile pages for their website (domain matching)."""
    out = list(companies)
    fetched = 0
    for i, company in enumerate(out):
        if fetched >= cfg.max_company_pages:
            break
        if not (company.opening_soon and company.website is None and company.url):
            continue
        if not is_fetchable(company.url):
            continue
        try:
            html = _get(company.url, budget, fetch, pace)
        except BudgetExceeded as exc:
            logger.warning("culinary agents enrichment stopped: %s", exc)
            break
        fetched += 1
        page = parse_company(html, company.url) if html else None
        if page is not None and page.website:
            out[i] = company.model_copy(update={"website": page.website})
    return out


def fetch_nyc(
    cfg: CulinaryAgentsConfig,
    budget: CallBudget,
    fetch: Fetch | None = None,
    today: date | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[list[CAJob], list[CACompany]]:
    """Job and opening-soon company searches per configured location, within the page budget.

    Only the first server-rendered page of each search is reachable by a plain GET (further
    pages load through an XHR the site redirects away), so coverage comes from the locations and
    the opening-soon filters. When the budget is spent the run stops and keeps what it has.
    """
    fetch = fetch or PoliteFetcher()
    today = today or date.today()
    pace = _Pacer(cfg.delay_seconds, sleep)
    jobs: dict[str, CAJob] = {}
    companies: dict[str, CACompany] = {}
    try:
        for location in cfg.locations:
            html = _get(job_search_url(location), budget, fetch, pace)
            for job in parse_job_search(html or "", today):
                jobs.setdefault(job.url, job)
            html = _get(job_search_url(location, opening_soon=True), budget, fetch, pace)
            soon = parse_job_search(html or "", today, opening_soon=True)
            for job in soon:
                jobs[job.url] = job
            html = _get(company_search_url(location), budget, fetch, pace)
            for company in parse_company_search(html or ""):
                companies.setdefault(entity_id(company.url) or company.url, company)
            for job in soon:  # an opening-soon employer's job implies an opening-soon company
                key = entity_id(job.company_url) or job.company_url
                if key and key not in companies:
                    companies[key] = _company_from_job(job)
        enriched = _enrich_websites(list(companies.values()), cfg, budget, fetch, pace)
    except BudgetExceeded as exc:
        logger.warning("culinary agents stopped: %s", exc)
        enriched = list(companies.values())
    return list(jobs.values()), enriched


# ---- matching and signals -------------------------------------------------------------------


def _fold_title(title: str) -> str:
    folded = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[’'`]", " ", folded.lower()).split())


def classify_title(title: str, cfg: CulinaryAgentsConfig) -> SignalType | None:
    """The people signal a senior title emits (section 7 table), else None.

    First match wins, in order: `new_chef`, `new_gm`, `events_role_hire`, `guest_role_hire`,
    then the leftover senior titles as `role_hire`. Line-level and fine-dining service titles
    emit nothing here (they feed `hiring_burst` and the `fine_dining_service` fit).
    """
    text = _fold_title(title)
    if any(word in re.split(r"\W+", text) for word in cfg.exclude_title_words):
        return None
    lists: tuple[tuple[SignalType, tuple[str, ...]], ...] = (
        ("new_chef", cfg.chef_titles),
        ("new_gm", cfg.gm_titles),
        ("events_role_hire", cfg.events_titles),
        ("guest_role_hire", cfg.guest_titles),
        ("role_hire", cfg.leadership_titles),
    )
    for kind, patterns in lists:
        if any(re.search(p, text) for p in patterns):
            return kind
    return None


def is_service_title(title: str, cfg: CulinaryAgentsConfig) -> bool:
    """A fine-dining service role (sommelier, wine/beverage director, captain, service manager)."""
    text = _fold_title(title)
    return any(re.search(p, text) for p in cfg.service_titles)


def is_open_call(title: str, cfg: CulinaryAgentsConfig) -> bool:
    text = _fold_title(title)
    return any(re.search(p, text) for p in cfg.open_call_titles)


def is_private_listing(job: CAJob) -> bool:
    """A "Private Listing" posting hides its employer, so it can never be matched."""
    return " ".join(job.company.lower().split()) == "private listing"


def drop_private_listings(jobs: Sequence[CAJob]) -> tuple[list[CAJob], int]:
    """(jobs with an employer, how many private listings were skipped)."""
    kept = [j for j in jobs if not is_private_listing(j)]
    return kept, len(jobs) - len(kept)


def job_key(job: CAJob) -> str:
    """The seen-store key of a job: its numeric id, else its URL."""
    return f"job:{job.job_id or job.url}"


def company_key(company: CACompany) -> str:
    return f"entity:{entity_id(company.url) or company.url}"


def _key(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    tokens = normalize_name(folded).split()
    while len(tokens) > 1 and tokens[-1] in _PLACE_SUFFIX:
        tokens = tokens[:-1]
    return " ".join(tokens)


def _same_name(a: str, b: str) -> bool:
    """Near-exact after dropping place suffixes; strict (a match merges groups), so a token
    subset never passes."""
    ka, kb = _key(a), _key(b)
    return bool(ka and kb) and (ka == kb or strict_name_match(ka, kb))


def _street_conflict(location: str, venue_address: str) -> bool:
    """True when both are street addresses and the number and street clearly differ."""
    p = normalize_address(location.split(",")[0]).split()
    v = normalize_address(venue_address).split()
    if not p or not v or not p[0].isdigit() or not v[0].isdigit():
        return False
    n = min(len(p), len(v), 3)
    return p[:n] != v[:n]


def _candidates(
    name: str, locations: Sequence[str], website: str | None, venues: Sequence[Venue]
) -> list[Venue]:
    found = [
        v
        for v in venues
        if _same_name(name, v.name)
        and not (locations and all(_street_conflict(loc, v.address) for loc in locations))
    ]
    domain = registrable_domain(website) if website else None
    if len(found) > 1 and domain:
        narrowed = [v for v in found if v.website and registrable_domain(v.website) == domain]
        found = narrowed or found
    return found


def _short(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:8]


def _observed(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


class _Resolver:
    """Resolves a company to exactly one venue, logging every miss once."""

    def __init__(self, venues: Sequence[Venue]) -> None:
        self._venues = venues
        self._cache: dict[tuple[str, tuple[str, ...], str], str | None] = {}

    def venue_id(self, name: str, locations: Sequence[str], website: str | None) -> str | None:
        key = (_key(name), tuple(locations), website or "")
        if key not in self._cache:
            found = _candidates(name, locations, website, self._venues)
            if len(found) != 1:
                reason = "no matching venue" if not found else f"{len(found)} matching venues"
                logger.info("culinary agents unmatched candidate: %s (%s)", name, reason)
            self._cache[key] = found[0].venue_id if len(found) == 1 else None
        return self._cache[key]


def to_signals(
    jobs: Sequence[CAJob],
    companies: Sequence[CACompany],
    venues: Sequence[Venue],
    groups: Sequence[Group],
    today: date,
    cfg: CulinaryAgentsConfig | None = None,
    first_seen: Mapping[str, date] | None = None,
) -> tuple[list[Signal], list[GroupEvidence]]:
    """Signals and group evidence for fetched jobs and companies, matched to known venues.

    `first_seen` (seen-store key -> the day the item was first seen) dates a signal whose card
    gives no posting date, so it decays from when it appeared, not from today.
    """
    cfg = cfg or CulinaryAgentsConfig()
    first_seen = first_seen or {}
    resolver = _Resolver(venues)
    signals: dict[str, Signal] = {}
    observed = _observed(today)

    def add(kind: SignalType, vid: str, url: str, extra: str, detail: str, when: date | None):
        """`extra` disambiguates two signals on one URL; a `hiring_burst` id ignores the URL
        (one burst per venue, however it was found)."""
        ident = _short(vid, "burst") if kind == "hiring_burst" else _short(url, extra)
        sig = Signal(
            signal_id=f"{kind}:{vid}:{ident}",
            signal_type=kind,
            entity_id=vid,
            observed_at=observed,
            occurred_at=_observed(when) if when else None,
            source=SOURCE,
            evidence_ref=url,
            detail=detail,
        )
        signals.setdefault(sig.signal_id, sig)

    members: list[tuple[str, str, str, str]] = []  # (group, company name, venue id, ref url)
    by_venue: dict[str, list[tuple[CAJob, date]]] = {}  # matched jobs, for hiring_burst
    for job in drop_private_listings(jobs)[0]:
        vid = resolver.venue_id(job.company, (job.location,) if job.location else (), None)
        if vid is None:
            continue
        if job.group and job.company_url:
            members.append((job.group, job.company, vid, job.company_url))
        when = job.posted or first_seen.get(job_key(job))
        by_venue.setdefault(vid, []).append((job, when or today))
        posted = f", posted {when.isoformat()}" if when else ""
        kind = classify_title(job.title, cfg)
        if kind is not None:
            add(
                kind, vid, job.url, job.title, f"{job.company} is hiring: {job.title}{posted}", when
            )
        if is_service_title(job.title, cfg):
            add(
                "fine_dining_service",
                vid,
                job.url,
                job.title,
                f"{job.company} is hiring fine-dining service staff: {job.title}{posted}",
                when,
            )
    for vid, items in by_venue.items():
        _hiring_burst(vid, items, today, cfg, add)
    for company in companies:
        vid = resolver.venue_id(company.name, company.locations, company.website)
        if vid is None:
            continue
        if company.group:
            members.append((company.group, company.name, vid, company.url))
        if company.opening_soon:
            add(
                "opening_soon",
                vid,
                company.url,
                "",
                f"{company.name} is listed as opening soon on Culinary Agents",
                first_seen.get(company_key(company)),
            )
    return list(signals.values()), _group_evidence(members, groups)


def _hiring_burst(
    vid: str,
    items: Sequence[tuple[CAJob, date]],
    today: date,
    cfg: CulinaryAgentsConfig,
    add: Callable[[SignalType, str, str, str, str, date | None], None],
) -> None:
    """One `hiring_burst` per venue: an "Open Call" posting, or `burst_min_roles` distinct
    roles (any level) from the employer within `burst_window_days`."""
    since = today - timedelta(days=cfg.burst_window_days)
    recent = [(job, when) for job, when in items if when >= since]
    open_calls = [(job, when) for job, when in recent if is_open_call(job.title, cfg)]
    roles = {_fold_title(job.title) for job, _ in recent}
    if not open_calls and len(roles) < cfg.burst_min_roles:
        return
    evidence = open_calls or recent
    first = min(when for _, when in evidence)
    ref = min(job.url for job, _ in evidence)
    company = evidence[0][0].company
    why = (
        f"an open call ({evidence[0][0].title})"
        if open_calls
        else f"{len(roles)} distinct roles in {cfg.burst_window_days} days"
    )
    add("hiring_burst", vid, ref, "", f"{company} is staffing up: {why}", first)


def _group_evidence(
    members: Sequence[tuple[str, str, str, str]], groups: Sequence[Group]
) -> list[GroupEvidence]:
    by_key: dict[str, tuple[str, set[str], list[str]]] = {}
    for group, company, vid, ref in members:
        key = _key(group)
        if key in _GENERIC_GROUP or key == _key(company):
            continue
        _, vids, refs = by_key.setdefault(key, (group.strip(), set(), []))
        vids.add(vid)
        refs.append(ref)
    out: list[GroupEvidence] = []
    for display, vids, refs in by_key.values():
        linked = set(vids)
        for g in groups:
            if _same_name(display, g.name):
                linked.update(g.venue_ids)
        if len(linked) >= 2:
            out.append(
                GroupEvidence(
                    venue_ids=tuple(sorted(linked)),
                    name=display,
                    resolution="job_board",
                    evidence_ref=min(refs),
                )
            )
    return out
