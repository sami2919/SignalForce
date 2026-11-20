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

Logged-in mode (`culinary_agents.authenticated`, off by default). The user chose to run it with
their own account knowing the agreement (section 7) bans robots and scrapers without written
permission and limits accounts to personal use; the risk is a banned account or a legal letter.
It walks the paginated XHR search (`iter_search_pages`, 20 items a page, `offset` / `page` /
`sj_offset` as captured) with the session cookie from CULINARY_AGENTS_COOKIE, read only from the
environment, never logged, stored or put in an error. Same footprint rules as the public reader:
robots.txt (fails closed), `/users` refused, the budget spent before every request, a fixed
delay, one account, one IP, an honest User-Agent. Deliberately absent: secondary accounts,
proxies, TLS impersonation and randomised timing. 401/403/429, a sign-in redirect or an empty page
stops the run (never a retry) and keeps what was read. `--backfill` walks every page once; the
daily run stops a search after `daily_stop_after_known` already-seen organic items (`ca_seen`).

Scheduling (where the cookie lives; a fixed time, no jitter), e.g. a crontab line:

    15 6 * * * cd /path/to/SignalForce && .venv/bin/python -m scripts.hospitality.cli culinary-agents
"""

import asyncio
import hashlib
import json
import logging
import re
import time
import unicodedata
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote_plus, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import BaseModel, ConfigDict
from selectolax.lexbor import LexborHTMLParser, LexborNode

from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.config import CulinaryAgentsConfig
from scripts.hospitality.discover.press import press_to_records
from scripts.hospitality.models import (
    CACompany,
    CAJob,
    CASeen,
    Group,
    GroupEvidence,
    PressFacts,
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
_JOB_ID = re.compile(r"/jobs/(\d+)")
_POSTED_ABS = re.compile(
    r"posted (?:on )?([a-z]{3,9}\.? \d{1,2},? \d{4}|\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE
)
_CSRF = re.compile(
    r"<meta[^>]+name=[\"']csrf-token[\"'][^>]+content=[\"']([^\"']+)[\"']", re.IGNORECASE
)
PAGE_SIZE = 20  # items per page of the logged-in XHR search
XHR_ACCEPT = (
    "text/javascript, application/javascript, application/ecmascript, "
    "application/x-ecmascript, */*; q=0.01"
)
COOKIE_ENV = "CULINARY_AGENTS_COOKIE"
SESSION_EXPIRED = "session expired — refresh CULINARY_AGENTS_COOKIE"

Fetch = Callable[[str], str | None]
# Logged-in fetch: (url, xhr) -> body text; raises SessionStopped instead of returning None.
SessionFetch = Callable[[str, bool], str]


class SessionStopped(RuntimeError):
    """The logged-in walk must stop, never retry: 401/403/429, a sign-in redirect, an empty or
    unrecognised page, a refused URL or a network error. `auth` marks a dead session. The reason
    never contains the cookie (pinned by tests)."""

    def __init__(self, reason: str, *, auth: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.auth = auth


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


def session_search_url(
    kind: str,
    location: str,
    page: int,
    sj_offset: int,
    cfg: CulinaryAgentsConfig,
    *,
    opening_soon: bool = False,
) -> str:
    """A logged-in search page, with the parameters exactly as captured from the site.

    Page 1 is the server-rendered page (no offset); later pages add `offset=(page-1)*20`,
    `page` and, for jobs, `sj_offset` (sponsored jobs shown so far).
    """
    paging = [("offset", str((page - 1) * PAGE_SIZE)), ("page", str(page))] if page > 1 else []
    if kind == "companies":
        params = [
            *paging,
            ("search[location]", location),
            ("search[open_status][]", "opening_soon"),
        ]
        return _search_url("/companies/search", params)
    params = [
        *paging,
        ("search[country]", "US"),
        ("search[location]", location),
        *(("search[segment_ids][]", sid) for sid in cfg.segment_ids),
    ]
    if opening_soon:
        params.append(("search[entity_status][]", "opening_soon"))
    if page > 1:
        params.append(("sj_offset", str(sj_offset)))
    return _search_url("/search/jobs", params)


def _disallow_all() -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse(["User-agent: *", "Disallow: /"])
    return parser


class PoliteFetcher:
    """Sync GET of one culinaryagents.com page: robots.txt (fetched once per run; unreadable =
    fetch nothing), SSRF guard, body cap.

    With `cookie` (the operator's own session, from CULINARY_AGENTS_COOKIE) `page()` reads
    logged-in pages: the cookie goes only to page requests on the site (never robots.txt), XHR
    requests carry the CSRF token read from page 1 of this session (kept in memory only), and
    every failure raises `SessionStopped` instead of retrying. The cookie is never logged and
    never appears in an exception.
    """

    def __init__(
        self,
        client_factory: Callable[[], httpx.AsyncClient] = lambda: guarded_client(),
        cookie: str | None = None,
    ) -> None:
        self._factory = client_factory
        self._robots: RobotFileParser | None = None
        self._cookie = cookie or None
        self._csrf: str | None = None

    def __call__(self, url: str) -> str | None:
        if not is_fetchable(url):
            logger.warning("culinary agents: refusing to fetch %s", url)
            return None
        return asyncio.run(self._get(url))

    def page(self, url: str, xhr: bool = False) -> str:
        """One logged-in page (or XHR response) body; raises `SessionStopped` on any failure."""
        if not is_fetchable(url):
            raise SessionStopped(f"refused url {urlsplit(url).path}")
        if xhr and self._csrf is None:
            raise SessionStopped("no csrf token from page 1 of this session", auth=True)
        text = asyncio.run(self._get_session(url, xhr))
        if not xhr:
            found = _CSRF.search(text)
            self._csrf = found.group(1) if found else self._csrf
        return text

    def _redact(self, text: str) -> str:
        if self._cookie:
            text = text.replace(self._cookie, "[redacted]")
            for part in self._cookie.split(";"):
                value = part.split("=", 1)[-1].strip()
                if len(value) >= 6:
                    text = text.replace(value, "[redacted]")
        return text

    async def _get_session(self, url: str, xhr: bool) -> str:
        plain = {"User-Agent": USER_AGENT}
        headers = {**plain, "Cookie": self._cookie or ""}
        if not self._cookie:
            headers.pop("Cookie")
        if xhr:
            headers |= {
                "Accept": XHR_ACCEPT,
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRF-Token": self._csrf or "",
            }
        timeout = httpx.Timeout(15.0, connect=5.0)
        failure: str | None = None
        async with self._factory() as client:
            if self._robots is None:
                self._robots = await self._load_robots(client, plain, timeout)
            if not self._robots.can_fetch(USER_AGENT, url):
                raise SessionStopped(f"robots.txt disallows {urlsplit(url).path}")
            try:
                resp = await get_capped(
                    client,
                    url,
                    max_bytes=MAX_BYTES,
                    headers=headers,
                    timeout=timeout,
                    follow_redirects=False,  # a redirect is a stop, and the cookie never follows
                )
            except httpx.HTTPError as exc:
                failure = f"network error: {type(exc).__name__}: {self._redact(str(exc))}"
        if failure is not None:  # raised outside `except`: no chained httpx error (whose request
            logger.warning("culinary agents stopped: %s", failure)  # holds the cookie) rides along
            raise SessionStopped(failure)
        return self._check(resp)

    def _check(self, resp: httpx.Response) -> str:
        status = resp.status_code
        stop: SessionStopped | None = None
        if status in (401, 403):
            stop = SessionStopped(f"http {status}", auth=True)
        elif status == 429:
            stop = SessionStopped("http 429 rate limited")
        elif 300 <= status < 400:
            target = urlsplit(resp.headers.get("location", "")).path
            if target.startswith("/users/sign_in"):
                stop = SessionStopped("sign-in redirect", auth=True)
            else:
                stop = SessionStopped(f"unexpected redirect (http {status}) to {target}")
        elif status != 200:
            stop = SessionStopped(f"http {status}")
        elif not resp.text.strip():
            stop = SessionStopped("empty page")
        if stop is not None:
            logger.warning("culinary agents stopped: %s", stop.reason)
            raise stop
        return resp.text

    async def _get(self, url: str) -> str | None:
        headers = {"User-Agent": USER_AGENT}
        timeout = httpx.Timeout(15.0, connect=5.0)
        async with self._factory() as client:
            if self._robots is None:
                self._robots = await self._load_robots(client, headers, timeout)
            if not self._robots.can_fetch(USER_AGENT, url):
                logger.warning("culinary agents: robots.txt disallows %s", url)
                return None
            if self._cookie:
                headers = {**headers, "Cookie": self._cookie}
            try:
                resp = await get_capped(
                    client,
                    url,
                    max_bytes=MAX_BYTES,
                    headers=headers,
                    timeout=timeout,
                    follow_redirects=not self._cookie,
                )
            except httpx.HTTPError as exc:
                logger.warning(
                    "culinary agents fetch failed: url=%s error=%s", url, self._redact(str(exc))
                )
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


def _absolute_date(text: str) -> date | None:
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text.replace(".", ""), fmt).date()
        except ValueError:
            continue
    return None


def _posted(text: str, today: date) -> date | None:
    """The posting date: absolute ("Posted on Nov 10, 2026", logged-in cards) when shown, else
    derived from a relative age ("Posted 3 days ago")."""
    absolute = _POSTED_ABS.search(text)
    if absolute and (day := _absolute_date(absolute.group(1))) is not None:
        return day
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
    job_id = _JOB_ID.search(urlsplit(href).path)
    sponsored = (anchor.attributes.get("data-sponsored") or "").lower() == "true"
    return CAJob(
        company=company,
        company_url=f"{BASE}/entities/{ident}" if ident else "",
        title=title,
        location=address,
        group=group,
        posted=_posted(_text(tags), today),
        url=urljoin(BASE, urlsplit(href).path),
        opening_soon=opening_soon,
        job_id=job_id.group(1) if job_id else None,
        sponsored=sponsored or _text(tags).lower() == "sponsored",
    )


def _inside_job_card(node: LexborNode) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.tag == "div" and "new-job-card" in (parent.attributes.get("class") or "").split():
            return True
        parent = parent.parent
    return False


def parse_job_search(html: str, today: date, *, opening_soon: bool = False) -> list[CAJob]:
    """Job cards on a search page; an unreadable card is logged and skipped, never fatal."""
    if not html.strip():
        return []
    out: list[CAJob] = []
    for node in LexborHTMLParser(html).css("div.new-job-card"):
        if _inside_job_card(node):  # the inner div of a wrapped card (page 1); XHR pages
            continue  # send the inner div alone, so it is the outermost card there
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


_JS_LITERAL = r""""(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'"""
_JS_NAME = r"[A-Za-z_$][\w$]*"
# One left-to-right scan of a UJS response. Every string literal is consumed as a token, so
# nothing inside one is ever read as code. Tokens: `name = "...";`, a jQuery injection whose
# argument is a literal or a variable (`$("#x").append("...")`, `.append(result)`), any
# other literal (skipped).
_UJS_TOKEN = re.compile(
    rf"(?<![\w$.])(?P<name>{_JS_NAME})\s*=\s*(?P<value>{_JS_LITERAL})\s*;"
    rf"|\.(?:append|prepend|html|replaceWith)\(\s*(?:(?P<arg>{_JS_LITERAL})|(?P<var>{_JS_NAME}))\s*\)"
    rf"|{_JS_LITERAL}",
    re.DOTALL,
)
# Card markup in a raw response: a page that has it but yields no card is unrecognised.
_CARD_MARKUP = {
    "jobs": re.compile(r"ca-single-job-card\b"),
    "companies": re.compile(r"company-card\b"),
}
_JS_ESCAPE = re.compile(r'\\x([0-9a-fA-F]{2})|\\(.)|"', re.DOTALL)


def _js_string(body: str) -> str:
    """Decode a JS string literal's body with the JSON decoder (not `unicode_escape`, which
    corrupts non-ASCII text): JS-only escapes (\\' \\` \\$ \\xHH) and raw double quotes from
    single-quoted literals are first rewritten into JSON form."""

    def to_json(m: re.Match[str]) -> str:
        if m.group(1) is not None:
            return f"\\u00{m.group(1)}"
        if m.group(2) is None:
            return '\\"'  # a raw double quote inside a single-quoted literal
        char = m.group(2)
        return char if char in "'`$" else m.group(0)

    return json.loads(f'"{_JS_ESCAPE.sub(to_json, body)}"', strict=False)


def _decode_literal(literal: str) -> str | None:
    try:
        return _js_string(literal[1:-1])
    except ValueError:
        logger.warning("culinary agents: undecodable UJS string skipped")
        return None


def extract_ujs_html(js_text: str) -> str:
    """The HTML a Rails UJS response injects, decoded and joined in order: `.append("...")` /
    `.html("...")` literals, and HTML assigned to a variable then injected by name
    (`result = "..."; $("#x").append(result);`, the live page-2 shape). The same HTML injected
    into a second target counts once; empty injections add nothing. Raw HTML passes through
    unchanged; anything else gives "".

    The only function that knows the XHR response shape, so it is the one to change if the
    live response changes again.
    """
    if js_text.lstrip().startswith("<"):
        return js_text
    variables: dict[str, str | None] = {}
    parts: list[str] = []
    for m in _UJS_TOKEN.finditer(js_text):
        if m.group("name") is not None:
            variables[m.group("name")] = _decode_literal(m.group("value"))
            continue
        if m.group("arg") is not None:
            html = _decode_literal(m.group("arg"))
        elif m.group("var") is not None:
            html = variables.get(m.group("var"))
        else:
            continue  # a literal outside any assignment or injection
        if html and html not in parts:
            parts.append(html)
    return "".join(parts)


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


# Public names for callers outside this module (the CLI's article reader).
Pacer = _Pacer
read_page = _get


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


# ---- logged-in walk ---------------------------------------------------------------------------


class SearchPage(BaseModel):
    """One page of a logged-in search: its number and the cards on it."""

    model_config = ConfigDict(frozen=True)

    page: int
    jobs: tuple[CAJob, ...] = ()
    companies: tuple[CACompany, ...] = ()


def iter_search_pages(
    kind: str,
    location: str,
    fetch: SessionFetch,
    budget: CallBudget,
    *,
    opening_soon: bool,
    cfg: CulinaryAgentsConfig,
    today: date,
    pace: Callable[[], None] = lambda: None,
    max_pages: int | None = None,
) -> Iterator[SearchPage]:
    """Parsed cards page by page (`kind` is "jobs" or "companies"), newest first.

    Page 1 is HTML (it also carries the session's CSRF token); later pages are UJS XHR
    responses. Ends at the first page with no cards or at `max_pages`; an empty first page or an
    unrecognised XHR response is a stop (`SessionStopped`), since NYC always has listings.
    The budget is spent before every request.
    """
    sponsored_so_far = 0
    for page in range(1, (max_pages or cfg.max_pages_per_search) + 1):
        url = session_search_url(
            kind, location, page, sponsored_so_far, cfg, opening_soon=opening_soon
        )
        budget.spend()  # raises BudgetExceeded before the request over the limit goes out
        pace()
        text = fetch(url, page > 1)
        html = extract_ujs_html(text) if page > 1 else text
        if page > 1 and not html and ".append(" not in text and ".html(" not in text:
            raise SessionStopped(f"unrecognised XHR response on {kind} page {page}")
        if kind == "companies":
            found = SearchPage(page=page, companies=tuple(parse_company_search(html)))
        else:
            jobs = tuple(parse_job_search(html, today, opening_soon=opening_soon))
            sponsored_so_far += sum(j.sponsored for j in jobs)
            found = SearchPage(page=page, jobs=jobs)
        if not found.jobs and not found.companies:
            if _CARD_MARKUP[kind].search(text):  # cards were sent but none could be read
                raise SessionStopped(
                    f"unrecognised response on {kind} page {page}: card markup but no readable"
                    " cards"
                )
            if page == 1:
                raise SessionStopped(f"empty page ({kind} page 1 has no cards)")
            return
        yield found


class WalkResult(BaseModel):
    """What one logged-in run read, and why it ended."""

    model_config = ConfigDict(frozen=True)

    jobs: tuple[CAJob, ...]
    companies: tuple[CACompany, ...]
    seen: tuple[CASeen, ...]  # every item seen this run, first_seen kept from earlier runs
    pages: int
    new_jobs: int
    new_companies: int
    private_skipped: int
    early_exit: tuple[str, ...]  # "<search> page N" for each search the daily rule stopped
    stopped: str  # "" when the walk finished; else the stop reason
    auth_failure: bool


_SEARCHES: tuple[tuple[str, bool, str], ...] = (
    ("jobs", False, "jobs"),
    ("jobs", True, "opening-soon jobs"),
    ("companies", True, "opening-soon companies"),
)


def walk_nyc(
    cfg: CulinaryAgentsConfig,
    budget: CallBudget,
    fetch: SessionFetch,
    seen: Mapping[str, CASeen],
    today: date,
    *,
    backfill: bool,
    sleep: Callable[[float], None] = time.sleep,
    known_companies: Mapping[str, CACompany] | None = None,
) -> WalkResult:
    """The logged-in walk over each location's job, opening-soon job and opening-soon company
    searches, then opening-soon company profiles.

    Daily mode stops a search after `daily_stop_after_known` consecutive organic items already
    in `seen` (sponsored cards neither count nor reset the run). Backfill walks every page up to
    `max_pages_per_search`. A stop keeps what was fetched; already-seen items keep `first_seen`,
    so a crashed backfill resumes for free.
    """
    pace = _Pacer(cfg.delay_seconds, sleep)
    known_companies = known_companies or {}
    jobs: dict[str, CAJob] = {}
    companies: dict[str, CACompany] = {}
    touched: dict[str, CASeen] = {}
    exits: list[str] = []
    private = 0
    stopped, auth = "", False

    def touch(key: str) -> bool:
        """Record `key` as seen today; True when an earlier run had already seen it."""
        before = seen.get(key)
        record = touched.get(key) or before
        touched[key] = (
            record.model_copy(update={"last_seen": today})
            if record
            else CASeen(key=key, first_seen=today, last_seen=today)
        )
        return before is not None

    try:
        for location in cfg.locations:
            for kind, soon, label in _SEARCHES:
                run_known = 0
                for found in iter_search_pages(
                    kind,
                    location,
                    fetch,
                    budget,
                    opening_soon=soon,
                    cfg=cfg,
                    today=today,
                    pace=pace,
                ):
                    kept, skipped = drop_private_listings(found.jobs)
                    private += skipped
                    for job in kept:
                        key = job_key(job)
                        known = touch(key)
                        if soon or key not in jobs:
                            jobs[key] = job  # the opening-soon copy carries the flag
                        if not job.sponsored:
                            run_known = run_known + 1 if known else 0
                    for company in found.companies:
                        key = company_key(company)
                        known = touch(key)
                        companies.setdefault(key, company)
                        run_known = run_known + 1 if known else 0
                    if not backfill and run_known >= cfg.daily_stop_after_known:
                        exits.append(f"{label} page {found.page}")
                        break
                if soon and kind == "jobs":
                    for job in jobs.values():  # an opening-soon employer is an opening company
                        if job.opening_soon and job.company_url:
                            derived = _company_from_job(job)
                            key = company_key(derived)
                            if key not in companies:
                                touch(key)
                                companies[key] = derived
        _profiles(companies, touched, known_companies, cfg, budget, fetch, pace, today)
    except SessionStopped as exc:
        stopped, auth = exc.reason, exc.auth
    except BudgetExceeded as exc:
        stopped = str(exc)
    return WalkResult(
        jobs=tuple(jobs.values()),
        companies=tuple(companies.values()),
        seen=tuple(touched.values()),
        pages=budget.used,
        new_jobs=sum(k not in seen for k in jobs),
        new_companies=sum(k not in seen for k, c in companies.items() if c.opening_soon),
        private_skipped=private,
        early_exit=tuple(exits),
        stopped=stopped,
        auth_failure=auth,
    )


def _profiles(
    companies: dict[str, CACompany],
    touched: dict[str, CASeen],
    known: Mapping[str, CACompany],
    cfg: CulinaryAgentsConfig,
    budget: CallBudget,
    fetch: SessionFetch,
    pace: Callable[[], None],
    today: date,
) -> None:
    """Opening-soon company profiles for a website, each fetched once and not again while the
    last fetch is under `profile_refresh_days` old (the stored website is reused)."""
    fetched = 0
    for key, company in list(companies.items()):
        if not company.opening_soon or company.website or not is_fetchable(company.url):
            continue
        record = touched.get(key)
        last = record.profile_fetched_on if record else None
        if last is not None and (today - last).days < cfg.profile_refresh_days:
            stored = known.get(key)
            if stored is not None and stored.website:
                companies[key] = company.model_copy(update={"website": stored.website})
            continue
        if fetched >= cfg.max_company_pages:
            break
        budget.spend()
        pace()
        page = parse_company(fetch(company.url, False), company.url)
        fetched += 1
        if record is not None:
            touched[key] = record.model_copy(update={"profile_fetched_on": today})
        if page is not None and page.website:
            companies[key] = company.model_copy(update={"website": page.website})


# ---- articles (public /resources) -------------------------------------------------------------

RESOURCES_URL = f"{BASE}/resources"
_ARTICLE_SKIP = frozenset({"category", "tag", "page", "author", "search"})


def parse_article_index(html: str) -> list[str]:
    """Article URLs on the public /resources index (no query or fragment), in page order.

    An article is a `/resources/<section>/<slug>` link on the site; category, tag, paging and
    author listings are not articles."""
    out: list[str] = []
    for a in LexborHTMLParser(html).css("a[href]"):
        url = urljoin(BASE, a.attributes.get("href") or "")
        parts = urlsplit(url)
        segments = [seg for seg in parts.path.split("/") if seg]
        if (parts.hostname or "") not in _HOSTS or len(segments) < 3:
            continue
        if segments[0] != "resources" or segments[1] in _ARTICLE_SKIP:
            continue
        clean = f"{BASE}{parts.path.rstrip('/')}"
        if is_fetchable(clean) and clean not in out:
            out.append(clean)
    return out


def article_text(html: str) -> str:
    """The readable text of an article page: <article>, else <main>, else <body>."""
    tree = LexborHTMLParser(html)
    tree.strip_tags(["script", "style", "noscript"])
    node = tree.css_first("article") or tree.css_first("main") or tree.body
    return _text(node)


def article_urls(
    cfg: CulinaryAgentsConfig, budget: CallBudget, fetch: Fetch, pace: Callable[[], None]
) -> list[str]:
    """Article URLs from the public index, at most `cfg.max_articles` (one budgeted page)."""
    html = _get(RESOURCES_URL, budget, fetch, pace)
    return parse_article_index(html or "")[: cfg.max_articles]


def article_signals(
    url: str,
    text: str,
    extract: Callable[[str, str], PressFacts],
    venues: Sequence[Venue],
    groups: Sequence[Group],
    today: date,
) -> tuple[list[Signal], list[Venue], list[GroupEvidence]]:
    """`press_opening` signals (article URL as evidence) from one article, via the press
    extractor, which drops any name not in the article text. People are never read: their
    names are dropped before matching, so no person signal or detail comes out."""
    facts = extract(text, url).model_copy(update={"people": (), "hotel_partner": None})
    signals, created, evidence = press_to_records(facts, url, today, venues, groups, frozenset())
    return [s for s in signals if s.signal_type == "press_opening"], created, evidence


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
