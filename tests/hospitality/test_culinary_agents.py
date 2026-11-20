import logging
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from scripts.hospitality import cli
from scripts.hospitality.budget import CallBudget
from scripts.hospitality.config import CulinaryAgentsConfig, load_config
from scripts.hospitality.models import CAJob, CASeen, Group, GroupEvidence, Signal, Venue
from scripts.hospitality.resolve.groups import merge_groups
from scripts.hospitality.scoring import rank_prospects, score_group
from scripts.hospitality.sources import culinary_agents as ca
from scripts.hospitality.sources.culinary_agents import (
    PoliteFetcher,
    classify_title,
    fetch_nyc,
    is_fetchable,
    parse_company,
    parse_company_search,
    parse_job_search,
    to_signals,
)
from tests.hospitality.factories import make_estimate, make_signal, make_venue

FIX = Path(__file__).resolve().parents[1] / "fixtures/hospitality/culinary_agents"
TODAY = date(2026, 11, 16)
CFG = CulinaryAgentsConfig(enabled=True)


def read(name: str) -> str:
    return (FIX / name).read_text()


def jobs() -> list[CAJob]:
    return parse_job_search(read("job_search.html"), TODAY)


def companies():
    return parse_company_search(read("company_search_opening_soon.html"))


# ---- parsers ----


def test_parse_job_search_fields() -> None:
    by = {(j.company, j.title): j for j in jobs()}
    assert len(by) == 7
    sous = by[("Brasada", "Sous Chef")]
    assert sous.location == "New York, New York 10014"
    assert sous.posted == TODAY and sous.group is None
    assert sous.url == "https://culinaryagents.com/jobs/9100001-Sous-Chef"  # no tracking query
    assert sous.company_url == "https://culinaryagents.com/entities/9000001"
    grill = by[("La Pâte d’Ambre", "Grill Cook")]
    assert grill.group == "The Harbor Table Group, the Restaurant Group of Chef Ada Moreau"
    assert grill.location == "One Example Plaza, New York, NY 10010"
    assert grill.posted is None  # sponsored cards carry no posting date
    assert "ad_id" not in grill.url
    assert by[("Verdigris", "General Manager")].posted == date(2026, 11, 14)


def test_parse_job_search_skips_unparseable_card_and_logs(caplog) -> None:
    html = (
        '<div id="js-jobs-result"><div class="new-job-card"><div class="card">'
        '<a class="ca-single-job-card" data-entity="Nameless"></a></div></div>'
        + read("job_search.html").split('id="js-jobs-result">')[1]
    )
    with caplog.at_level(logging.WARNING):
        parsed = parse_job_search(html, TODAY)
    assert len(parsed) == 7
    assert "unparseable" in caplog.text


def test_parse_job_search_on_garbage_returns_empty() -> None:
    assert parse_job_search("<html><body>nothing</body></html>", TODAY) == []
    assert parse_job_search("", TODAY) == []


def test_parse_company_search() -> None:
    by = {c.name: c for c in companies()}
    assert len(by) == 5
    marinella = by["MARINELLA NYC"]
    assert marinella.opening_soon and marinella.hiring
    assert marinella.locations == ("149 Sample Street, New York, NY",)
    assert marinella.url == "https://culinaryagents.com/entities/9200001-MARINELLA-NYC"
    assert marinella.group is None and marinella.website is None
    assert by["Corner Famous"].group == "Mira's Bakery + Cafe & Corner Famous Ice Cream"
    assert by["Corner Famous"].description.startswith("Corner Famous Ice Cream is")
    assert by["Bar Solano"].group == "Casaverde"


def test_parse_company_page() -> None:
    url = "https://culinaryagents.com/entities/9000001-Brasada"
    c = parse_company(read("company_page.html"), url)
    assert c is not None and c.name == "Brasada" and c.url == url
    assert c.website == "https://www.brasada.example/"
    assert c.locations == ("New York, New York 10014",)
    assert c.description.startswith("Brasada is a live-fire tavern")
    assert "click(" not in c.description  # inline script text is not description
    assert parse_company("<html></html>", url) is None


# ---- role classification ----


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("General Manager", "new_gm"),
        ("GM", "new_gm"),
        ("Opening GM", "new_gm"),
        ("Director of Operations", "new_gm"),
        ("Private Dining Manager", "events_role_hire"),
        ("Events Manager", "events_role_hire"),
        ("Pre-Opening Team Member", "role_hire"),
        ("Director of Food & Beverage", "role_hire"),
        ("Maître d’", "guest_role_hire"),
        ("Reservations Manager", "guest_role_hire"),
        ("Guest Relations Manager", "guest_role_hire"),
        ("Assistant General Manager", None),
        ("Line Cook", None),
        ("Server", None),
        ("Dishwasher", None),
        ("Barista", None),
        ("Sous Chef", None),
        ("Host", None),
    ],
)
def test_classify_title(title: str, expected: str | None) -> None:
    assert classify_title(title, CFG) == expected


# ---- signals ----


def _job(company: str, title: str, **kw) -> CAJob:
    base = {
        "company": company,
        "company_url": "https://culinaryagents.com/entities/9",
        "title": title,
        "location": "13 Example Street, New York, NY",
        "group": None,
        "posted": date(2026, 11, 14),
        "url": f"https://culinaryagents.com/jobs/1-{title.replace(' ', '-')}",
    }
    base.update(kw)
    return CAJob(**base)  # type: ignore[arg-type]


def _co(name: str, **kw):
    from scripts.hospitality.models import CACompany

    base = {
        "name": name,
        "url": f"https://culinaryagents.com/entities/5-{name.replace(' ', '-')}",
        "description": "",
        "locations": (),
        "group": None,
        "opening_soon": False,
        "hiring": True,
        "website": None,
    }
    base.update(kw)
    return CACompany(**base)  # type: ignore[arg-type]


def run(js, cs, venues, groups=(), cfg=CFG):
    return to_signals(js, cs, venues, list(groups), TODAY, cfg)


VERDIGRIS = make_venue("v:verdigris", name="Verdigris", address="13 EXAMPLE ST")


def test_gm_posting_emits_new_gm_on_matched_venue() -> None:
    sigs, _ = run([_job("Verdigris", "General Manager")], [], [VERDIGRIS])
    assert len(sigs) == 1
    s = sigs[0]
    assert s.signal_type == "new_gm" and s.entity_id == "v:verdigris"
    assert s.source == "culinary_agents"
    assert s.evidence_ref == "https://culinaryagents.com/jobs/1-General-Manager"
    assert "General Manager" in s.detail and "Verdigris" in s.detail
    assert s.occurred_at == datetime(2026, 11, 14, tzinfo=UTC)


def test_leadership_posting_emits_role_hire() -> None:
    sigs, _ = run([_job("Verdigris", "Events Manager")], [], [VERDIGRIS])
    assert [s.signal_type for s in sigs] == ["events_role_hire"]
    sigs, _ = run([_job("Verdigris", "Director of Hospitality")], [], [VERDIGRIS])
    assert [s.signal_type for s in sigs] == ["role_hire"]  # the leftover senior titles


def test_line_level_and_assistant_roles_emit_nothing() -> None:
    js = [
        _job("Verdigris", t)
        for t in ("Line Cook", "Server", "Dishwasher", "Assistant General Manager")
    ]
    sigs, _ = run(js, [], [VERDIGRIS])
    assert sigs == []


def test_opening_soon_company_emits_opening_soon_with_company_url() -> None:
    co = _co("Verdigris", opening_soon=True, locations=("13 Example Street, New York, NY",))
    sigs, _ = run([], [co], [VERDIGRIS])
    assert [s.signal_type for s in sigs] == ["opening_soon"]
    assert sigs[0].evidence_ref == co.url and sigs[0].entity_id == "v:verdigris"
    assert "opening soon" in sigs[0].detail.lower()


def test_company_not_opening_soon_emits_no_opening_signal() -> None:
    sigs, _ = run([], [_co("Verdigris")], [VERDIGRIS])
    assert sigs == []


def test_trailing_nyc_and_case_do_not_block_a_match() -> None:
    v = make_venue("v:marinella", name="Marinella", address="149 SAMPLE ST")
    co = _co("MARINELLA NYC", opening_soon=True, locations=("149 Sample Street, New York, NY",))
    sigs, _ = run([], [co], [v])
    assert [s.entity_id for s in sigs] == ["v:marinella"]


def test_ambiguous_company_gets_no_signal_and_is_logged(caplog) -> None:
    a = make_venue("v:a", name="Verdigris", address="13 EXAMPLE ST")
    b = make_venue("v:b", name="Verdigris", address="13 EXAMPLE ST")
    co = _co("Verdigris", opening_soon=True)
    with caplog.at_level(logging.INFO):
        sigs, ev = run([_job("Verdigris", "General Manager")], [co], [a, b])
    assert sigs == [] and ev == []
    assert "unmatched" in caplog.text.lower()


def test_unmatched_company_gets_no_signal_and_is_logged(caplog) -> None:
    with caplog.at_level(logging.INFO):
        sigs, _ = run([_job("Nowhere Bistro", "General Manager")], [], [VERDIGRIS])
    assert sigs == []
    assert "Nowhere Bistro" in caplog.text


def test_same_name_at_a_different_street_number_does_not_match() -> None:
    far = _co("Verdigris", opening_soon=True, locations=("500 Broadway, New York, NY",))
    sigs, _ = run([], [far], [VERDIGRIS])
    assert sigs == []


def test_website_domain_disambiguates_two_same_name_venues() -> None:
    a = make_venue("v:a", name="Verdigris", address="1 A ST", website="https://verdigris.com")
    b = make_venue("v:b", name="Verdigris", address="2 B ST", website="https://other.com")
    co = _co("Verdigris", opening_soon=True, website="https://www.verdigris.com/menu")
    sigs, _ = run([], [co], [a, b])
    assert [s.entity_id for s in sigs] == ["v:a"]


def test_group_evidence_from_part_of_links_two_venues() -> None:
    a = make_venue("v:a", name="Alpha", address="1 A ST")
    b = make_venue("v:b", name="Beta", address="2 B ST")
    cs = [
        _co("Alpha", group="Kings Hospitality", locations=("1 A Street, New York, NY",)),
        _co("Beta", group="Kings Hospitality", locations=("2 B Street, New York, NY",)),
    ]
    _, ev = run([], cs, [a, b])
    assert len(ev) == 1
    assert ev[0].resolution == "job_board" and ev[0].name == "Kings Hospitality"
    assert set(ev[0].venue_ids) == {"v:a", "v:b"}
    assert ev[0].evidence_ref.startswith("https://culinaryagents.com/entities/")
    _venues, groups = merge_groups(
        [a, b],
        [
            Group(group_id="g:v:a", name="Alpha", venue_ids=("v:a",), resolution="singleton"),
            Group(group_id="g:v:b", name="Beta", venue_ids=("v:b",), resolution="singleton"),
        ],
        ev,
    )
    assert len(groups) == 1 and groups[0].resolution == "job_board"


def test_group_name_matching_known_group_links_its_members() -> None:
    a = make_venue("v:a", name="Alpha", address="1 A ST")
    c = make_venue("v:c", name="Gamma", address="3 C ST")
    known = Group(
        group_id="g:v:c", name="Kings Hospitality", venue_ids=("v:c",), resolution="shared_domain"
    )
    co = _co("Alpha", group="Kings Hospitality", locations=("1 A Street, New York, NY",))
    _, ev = run([], [co], [a, c], [known])
    assert len(ev) == 1 and set(ev[0].venue_ids) == {"v:a", "v:c"}


def test_single_venue_or_generic_group_name_gives_no_evidence() -> None:
    a = make_venue("v:a", name="Alpha", address="1 A ST")
    one = _co("Alpha", group="Solo Group", locations=("1 A Street, New York, NY",))
    assert run([], [one], [a])[1] == []
    b = make_venue("v:b", name="Beta", address="2 B ST")
    cs = [
        _co("Alpha", group="The Group ", locations=("1 A Street, New York, NY",)),
        _co("Beta", group="The Group ", locations=("2 B Street, New York, NY",)),
    ]
    assert run([], cs, [a, b])[1] == []


def test_job_card_group_line_feeds_group_evidence() -> None:
    a = make_venue("v:a", name="Alpha", address="1 A ST")
    b = make_venue("v:b", name="Beta", address="2 B ST")
    js = [
        _job("Alpha", "Line Cook", group="Kings Hospitality", location="1 A Street, New York, NY"),
        _job("Beta", "Line Cook", group="Kings Hospitality", location="2 B Street, New York, NY"),
    ]
    sigs, ev = run(js, [], [a, b])
    assert sigs == [] and len(ev) == 1


# ---- scoring interactions ----


def _score(group_venues, sigs, *, is_customer=False):
    cfg = load_config()
    g = Group(
        group_id="g:v:verdigris",
        name="Verdigris",
        venue_ids=tuple(v.venue_id for v in group_venues),
        resolution="singleton",
    )
    return score_group(
        g,
        sigs,
        {"v:verdigris": make_estimate("v:verdigris", estimated_open=date(2027, 1, 1))},
        group_venues,
        [],
        cfg,
        datetime(2026, 11, 16, tzinfo=UTC),
        is_customer=is_customer,
        disqualified_reason=None,
    )


def test_opening_soon_folds_with_license_signal_no_double_count() -> None:
    lic = make_signal("license_pending", "v:verdigris")
    co = _co("Verdigris", opening_soon=True)
    soon, _ = run([], [co], [VERDIGRIS])
    both = _score([VERDIGRIS], [lic, *soon])
    only_lic = _score([VERDIGRIS], [lic])
    assert both.p_window == pytest.approx(only_lic.p_window)
    by_type = {c.signal_type: c for c in both.contributions}
    assert by_type["license_pending"].contribution > 0
    assert by_type["opening_soon"].contribution == 0.0
    assert "folded" in by_type["opening_soon"].note
    alone = _score([VERDIGRIS], list(soon))
    assert alone.p_window == pytest.approx(0.30)  # counts when it is the only opening evidence


def test_customer_group_never_becomes_a_cold_prospect_from_these_signals() -> None:
    sigs, _ = run(
        [_job("Verdigris", "General Manager")], [_co("Verdigris", opening_soon=True)], [VERDIGRIS]
    )
    acct = _score([VERDIGRIS], sigs, is_customer=True)
    assert acct.p_window > 0 and acct.is_customer
    assert rank_prospects([acct]) == []
    cold = _score([VERDIGRIS], sigs)
    assert [a.group_id for a in rank_prospects([cold])] == ["g:v:verdigris"]


def test_new_signal_type_and_config_are_backward_compatible() -> None:
    cfg = load_config()
    assert cfg.priors["opening_soon"].family == "opening"
    assert "opening_soon" in cfg.opening_evidence_signals
    assert cfg.culinary_agents.enabled is False  # disabled by default, in the shipped yaml
    assert cfg.budgets["culinary_agents"] == 40
    # a config without the new keys still loads (defaults: disabled)
    assert CulinaryAgentsConfig().enabled is False
    assert Signal.model_validate(make_signal("opening_soon").model_dump()).signal_type == (
        "opening_soon"
    )


# ---- fetching ----


def test_is_fetchable_refuses_users_login_and_foreign_hosts() -> None:
    assert is_fetchable("https://culinaryagents.com/search/jobs?search[location]=New+York")
    assert is_fetchable("https://culinaryagents.com/entities/1-A")
    assert not is_fetchable("https://culinaryagents.com/users/12-Jane-Doe")
    assert not is_fetchable("https://culinaryagents.com/users")
    assert not is_fetchable("https://culinaryagents.com/entities/1-A?intent=job_save&login=true")
    assert not is_fetchable("https://example.com/search/jobs")


def _pages(urls: list[str]):
    def fetch(url: str) -> str | None:
        urls.append(url)
        if "/companies/search" in url:
            return read("company_search_opening_soon.html")
        if "/search/jobs" in url:
            return read("job_search.html")
        return read("company_page.html")

    return fetch


def test_fetch_nyc_collects_jobs_and_companies_and_spends_before_each_fetch() -> None:
    urls: list[str] = []
    spent_at_fetch: list[int] = []
    budget = CallBudget("culinary_agents", 40)
    inner = _pages(urls)

    def fetch(url: str) -> str | None:
        spent_at_fetch.append(budget.used)
        return inner(url)

    cfg = CulinaryAgentsConfig(enabled=True, locations=("New York, NY",), max_company_pages=0)
    js, cs = fetch_nyc(cfg, budget, fetch=fetch, today=TODAY, sleep=lambda s: None)
    assert len(urls) == 3 and budget.used == 3  # jobs, opening-soon jobs, opening-soon companies
    assert spent_at_fetch == [1, 2, 3]  # budget spent before the fetch went out
    assert any("entity_status" in u and "opening_soon" in u for u in urls)
    assert any("open_status" in u for u in urls)
    assert all(is_fetchable(u) for u in urls)
    assert {j.title for j in js} >= {"General Manager", "Sous Chef"}
    assert any(j.opening_soon for j in js)
    names = {c.name for c in cs}
    assert {
        "MARINELLA NYC",
        "Verdigris",
    } <= names  # opening-soon jobs imply an opening-soon company
    assert next(c for c in cs if c.name == "Verdigris").opening_soon


def test_fetch_nyc_budget_hard_stops_before_the_call_over_the_limit() -> None:
    urls: list[str] = []
    budget = CallBudget("culinary_agents", 2)
    cfg = CulinaryAgentsConfig(enabled=True, locations=("New York, NY", "Brooklyn, NY"))
    js, _cs = fetch_nyc(cfg, budget, fetch=_pages(urls), today=TODAY, sleep=lambda s: None)
    assert len(urls) == 2 and budget.used == 2
    assert js  # what was fetched before the stop is kept


def test_fetch_nyc_sleeps_between_requests() -> None:
    sleeps: list[float] = []
    cfg = CulinaryAgentsConfig(
        enabled=True, locations=("New York, NY",), delay_seconds=2.0, max_company_pages=0
    )
    fetch_nyc(cfg, CallBudget("x", 40), fetch=_pages([]), today=TODAY, sleep=sleeps.append)
    assert sleeps == [2.0, 2.0]  # between the three requests, not before the first


def test_fetch_nyc_never_fetches_users_urls() -> None:
    urls: list[str] = []
    bad = _co("Evil", opening_soon=True, url="https://culinaryagents.com/users/1-Jane-Doe")

    def fetch(url: str) -> str | None:
        urls.append(url)
        return read("job_search.html") if "/search/jobs" in url else "<html></html>"

    cfg = CulinaryAgentsConfig(enabled=True, locations=("New York, NY",), max_company_pages=5)
    budget = CallBudget("x", 40)
    ca._enrich_websites([bad], cfg, budget, fetch, lambda: None)
    fetch_nyc(cfg, budget, fetch=fetch, today=TODAY, sleep=lambda s: None)
    assert not any("/users" in u for u in urls)


def test_fetch_failure_is_skipped_not_raised(caplog) -> None:
    cfg = CulinaryAgentsConfig(enabled=True, locations=("New York, NY",), max_company_pages=0)
    with caplog.at_level(logging.WARNING):
        js, cs = fetch_nyc(
            cfg, CallBudget("x", 40), fetch=lambda u: None, today=TODAY, sleep=lambda s: None
        )
    assert js == [] and cs == []
    assert "fetch failed" in caplog.text


def test_enrichment_adds_website_for_opening_soon_companies_within_page_cap() -> None:
    urls: list[str] = []
    cfg = CulinaryAgentsConfig(enabled=True, locations=("New York, NY",), max_company_pages=2)
    _, cs = fetch_nyc(
        cfg, CallBudget("x", 40), fetch=_pages(urls), today=TODAY, sleep=lambda s: None
    )
    entity_fetches = [u for u in urls if "/entities/" in u]
    assert len(entity_fetches) == 2
    assert sum(c.website is not None for c in cs) == 2


class _Resp:
    def __init__(self, text: str, status: int = 200) -> None:
        self.text, self.status_code = text, status


def test_polite_fetcher_honours_robots_and_caches_it(monkeypatch) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /search/blocked\n")
        return httpx.Response(200, text="<html>ok</html>")

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    f = PoliteFetcher(client_factory=client)
    assert f("https://culinaryagents.com/search/jobs?x=1") == "<html>ok</html>"
    assert f("https://culinaryagents.com/entities/1-A") == "<html>ok</html>"
    assert f("https://culinaryagents.com/search/blocked") is None
    assert f("https://culinaryagents.com/users/1-A") is None
    assert sum(u.endswith("/robots.txt") for u in seen) == 1
    assert not any("/users" in u or "blocked" in u for u in seen)


def test_polite_fetcher_returns_none_on_non_200_and_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if "boom" in request.url.path:
            raise httpx.ConnectError("down")
        return httpx.Response(403, text="blocked")

    f = PoliteFetcher(
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    assert f("https://culinaryagents.com/search/jobs") is None
    assert f("https://culinaryagents.com/boom") is None


# ---- CLI ----


def test_cli_refuses_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: load_config())
    with pytest.raises(SystemExit, match="agreement"):
        cli.culinary_agents()


def _enabled_cfg():
    base = load_config()
    return base.model_copy(
        update={
            "culinary_agents": CulinaryAgentsConfig(
                enabled=True, locations=("New York, NY",), max_company_pages=0
            )
        }
    )


def test_cli_end_to_end_saves_signals_evidence_merges_and_rescores(monkeypatch, tmp_path) -> None:
    from scripts.hospitality.store import DocStore

    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    verdigris = make_venue("v:verdigris", name="Verdigris", address="13 EXAMPLE ST")
    marinella = make_venue("v:marinella", name="Marinella", address="149 SAMPLE ST")
    bar = make_venue("v:solano", name="Bar Solano", address="372 MODEL ST")
    casa = make_venue("v:casa", name="Casaverde Hospitality Hub", address="1 X ST")
    store.save("venues", [verdigris, marinella, bar, casa], key=lambda v: v.venue_id)
    store.save(
        "groups",
        [
            Group(
                group_id=f"g:{v.venue_id}",
                name=v.name,
                venue_ids=(v.venue_id,),
                resolution="singleton",
            )
            for v in (verdigris, marinella, bar, casa)
        ],
        key=lambda g: g.group_id,
    )
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    monkeypatch.setattr(cli, "load_config", _enabled_cfg)
    monkeypatch.setattr(cli, "score", lambda: {"scored_groups": 4})
    out = cli.culinary_agents(fetch=_pages([]), today=TODAY, sleep=lambda s: None)
    sigs = store.load("signals", Signal)
    kinds = {(s.entity_id, s.signal_type) for s in sigs}
    assert ("v:verdigris", "new_gm") in kinds
    assert ("v:verdigris", "opening_soon") in kinds
    assert ("v:marinella", "opening_soon") in kinds
    assert all(s.source == "culinary_agents" for s in sigs)
    assert out["pages"] == 3 and out["signals"] == len(sigs) and out["stopped"] == ""
    assert out["scored_groups"] == 4
    assert isinstance(store.load("venues", Venue)[0], Venue)


def test_cli_reports_budget_stop(monkeypatch, tmp_path) -> None:
    from scripts.hospitality.store import DocStore

    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    cfg = _enabled_cfg()
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: cfg.model_copy(update={"budgets": {**cfg.budgets, "culinary_agents": 1}}),
    )
    monkeypatch.setattr(cli, "score", lambda: {"scored_groups": 0})
    out = cli.culinary_agents(fetch=_pages([]), today=TODAY, sleep=lambda s: None)
    assert out["pages"] == 1 and "budget" in out["stopped"]


@pytest.mark.parametrize(
    ("a", "b"),
    [("Major Food Group", "FOOD GROUP"), ("Hotel Chelsea", "GEM HOTEL CHELSEA")],
)
def test_job_board_names_never_match_by_token_subset(a: str, b: str) -> None:
    """C1 residual: a job-board company name merges groups, so a subset must never match."""
    from scripts.hospitality.sources.culinary_agents import _same_name

    assert not _same_name(a, b)


@pytest.mark.parametrize("robots", ["503", "404", "error"])
def test_polite_fetcher_fails_closed_when_robots_cannot_be_read(robots: str) -> None:
    """M8: the source's terms restrict automated collection, so an unreadable robots.txt
    (5xx per RFC 9309, any non-200, or a network error) disallows every page."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/robots.txt":
            if robots == "error":
                raise httpx.ConnectError("down")
            return httpx.Response(int(robots))
        return httpx.Response(200, text="<html>ok</html>")

    f = PoliteFetcher(
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    assert f("https://culinaryagents.com/search/jobs?x=1") is None
    assert seen == ["/robots.txt"]  # no page request goes out


def test_fixtures_are_synthetic_not_captured_pages() -> None:
    """M14: the source's agreement appears to restrict automated collection and this repo is
    open source, so the fixtures mirror the page structure with invented businesses and text."""
    for page in [*FIX.glob("*.html"), *FIX.glob("*.js.txt")]:
        html = page.read_text()
        assert "amazonaws.com" not in html, page.name  # no hot-linked source assets
        assert "SYNTHETIC FIXTURE" in html, page.name


# ---- section 7: title types, hiring burst, fine-dining fit ----


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        # new_chef
        ("Executive Chef", "new_chef"),
        ("Head Chef", "new_chef"),
        ("Chef de Cuisine", "new_chef"),
        ("Culinary Director", "new_chef"),
        ("Corporate Chef", "new_chef"),
        ("Opening Chef", "new_chef"),
        # new_gm
        ("General Manager", "new_gm"),
        ("Opening General Manager", "new_gm"),
        ("Director of Operations", "new_gm"),
        # guest_role_hire
        ("Guest Experience Manager", "guest_role_hire"),
        ("Guest Relations Manager", "guest_role_hire"),
        ("Reservationist", "guest_role_hire"),
        ("Reservations Manager", "guest_role_hire"),
        ("Maitre D'", "guest_role_hire"),
        ("Host Manager", "guest_role_hire"),
        ("Director of Sales", "guest_role_hire"),
        ("Director of Sales and Partnerships", "guest_role_hire"),
        ("Marketing Manager", "guest_role_hire"),
        ("Marketing Director", "guest_role_hire"),
        ("CRM Manager", "guest_role_hire"),
        ("Loyalty Program Lead", "guest_role_hire"),
        ("Guest Data Analyst", "guest_role_hire"),
        # events_role_hire
        ("Events Manager", "events_role_hire"),
        ("Private Dining Director", "events_role_hire"),
        ("Private Events Sales Manager", "events_role_hire"),
        ("Catering Sales", "events_role_hire"),
        ("Director of Events", "events_role_hire"),
        # senior lists still honour exclude_title_words
        ("Assistant General Manager", None),
        ("Executive Chef Intern", None),
        ("Associate Marketing Manager", None),
        # line-level roles emit nothing on their own
        ("Line Cook", None),
        ("Prep Cook", None),
        ("Server", None),
        ("Food Runner", None),
        ("Dishwasher", None),
        ("Porter", None),
        ("Polisher", None),
        ("Barback", None),
        ("Sous Chef", None),
        ("Executive Sous Chef", None),
        # fine-dining service titles are fit evidence, not a people signal
        ("Sommelier", None),
        ("Captain", None),
        ("Service Manager", None),
        ("Beverage Director", None),
    ],
)
def test_classify_title_section_7_table(title: str, expected: str | None) -> None:
    assert classify_title(title, CFG) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Sommelier", True),
        ("Head Sommelier", True),
        ("Wine Director", True),
        ("Beverage Director", True),
        ("Captain", True),
        ("Service Manager", True),
        ("Server", False),
        ("Line Cook", False),
        ("General Manager", False),
        ("Director of Food & Beverage", False),
    ],
)
def test_is_service_title(title: str, expected: bool) -> None:
    assert ca.is_service_title(title, CFG) is expected


def test_new_title_types_emit_their_signals() -> None:
    js = [
        _job("Verdigris", "Executive Chef"),
        _job("Verdigris", "Reservations Manager"),
        _job("Verdigris", "Private Events Manager"),
    ]
    sigs, _ = run(js, [], [VERDIGRIS])
    assert sorted(s.signal_type for s in sigs) == [
        "events_role_hire",
        "guest_role_hire",
        "new_chef",
    ]


def test_service_title_emits_fit_evidence_signal() -> None:
    sigs, _ = run([_job("Verdigris", "Sommelier")], [], [VERDIGRIS])
    assert [s.signal_type for s in sigs] == ["fine_dining_service"]
    assert "Sommelier" in sigs[0].detail


def test_private_listing_is_skipped_and_counted() -> None:
    js = [
        _job("Private Listing", "General Manager", location="New York, NY"),
        _job("Verdigris", "General Manager"),
    ]
    kept, skipped = ca.drop_private_listings(js)
    assert [j.company for j in kept] == ["Verdigris"] and skipped == 1
    private_venue = make_venue("v:p", name="Private Listing", address="1 X ST")
    sigs, _ = run(js, [], [VERDIGRIS, private_venue])
    assert {s.entity_id for s in sigs} == {"v:verdigris"}  # never matched to a venue


def _roles(company: str, titles: list[str], **kw) -> list[CAJob]:
    return [
        _job(company, t, url=f"https://culinaryagents.com/jobs/{i}-x", **kw)
        for i, t in enumerate(titles, start=100)
    ]


def test_hiring_burst_fires_at_five_distinct_roles() -> None:
    five = _roles("Verdigris", ["Line Cook", "Server", "Host", "Porter", "Barback"])
    sigs, _ = run(five, [], [VERDIGRIS])
    burst = [s for s in sigs if s.signal_type == "hiring_burst"]
    assert len(burst) == 1 and burst[0].entity_id == "v:verdigris"
    assert "5 distinct roles" in burst[0].detail
    assert burst[0].source == "culinary_agents"


def test_hiring_burst_needs_five_distinct_roles_within_the_window() -> None:
    four = _roles("Verdigris", ["Line Cook", "Server", "Host", "Porter", "Line Cook"])
    assert not [s for s in run(four, [], [VERDIGRIS])[0] if s.signal_type == "hiring_burst"]
    old = _roles(
        "Verdigris", ["Line Cook", "Server", "Host", "Porter"], posted=date(2026, 11, 14)
    ) + [_job("Verdigris", "Barback", posted=date(2026, 9, 1), url="https://x/jobs/9-b")]
    assert not [s for s in run(old, [], [VERDIGRIS])[0] if s.signal_type == "hiring_burst"]


def test_open_call_posting_is_a_hiring_burst() -> None:
    sigs, _ = run([_job("Verdigris", "Open Call - All Positions")], [], [VERDIGRIS])
    assert [s.signal_type for s in sigs] == ["hiring_burst"]
    assert "open call" in sigs[0].detail.lower()


def test_hiring_burst_folds_with_a_licence_signal_on_the_same_venue() -> None:
    lic = make_signal("license_pending", "v:verdigris")
    burst, _ = run([_job("Verdigris", "Open Call")], [], [VERDIGRIS])
    both = _score([VERDIGRIS], [lic, *burst])
    only_lic = _score([VERDIGRIS], [lic])
    assert both.p_window == pytest.approx(only_lic.p_window)
    by_type = {c.signal_type: c for c in both.contributions}
    assert by_type["hiring_burst"].contribution == 0.0
    assert "folded" in by_type["hiring_burst"].note
    alone = _score([VERDIGRIS], list(burst))
    assert alone.p_window == pytest.approx(0.25)


def test_fine_dining_service_adds_fit_not_window() -> None:
    gm, _ = run([_job("Verdigris", "General Manager")], [], [VERDIGRIS])
    som, _ = run([_job("Verdigris", "Sommelier")], [], [VERDIGRIS])
    base = _score([VERDIGRIS], gm)
    with_service = _score([VERDIGRIS], [*gm, *som])
    assert with_service.p_window == pytest.approx(base.p_window)
    assert with_service.fit == pytest.approx(base.fit + 0.10)
    by_type = {c.signal_type: c for c in with_service.contributions}
    assert by_type["fine_dining_service"].contribution == 0.0
    assert "fit" in by_type["fine_dining_service"].note


def test_new_priors_and_types_load_and_old_role_hire_still_loads() -> None:
    cfg = load_config()
    expected = {
        "new_chef": (0.20, "people"),
        "new_gm": (0.15, "people"),
        "guest_role_hire": (0.20, "people"),
        "events_role_hire": (0.15, "people"),
        "hiring_burst": (0.25, "opening"),
        "role_hire": (0.15, "people"),
    }
    for kind, (precision, family) in expected.items():
        assert cfg.priors[kind].precision == pytest.approx(precision), kind
        assert cfg.priors[kind].family == family, kind
    assert cfg.priors["fine_dining_service"].precision == 0.0
    assert "hiring_burst" in cfg.opening_evidence_signals
    assert cfg.fit_weights["fine_dining_service"] == pytest.approx(0.10)
    for kind in ("role_hire", "new_chef", "hiring_burst", "fine_dining_service"):
        assert Signal.model_validate(make_signal(kind).model_dump()).signal_type == kind
    old = CAJob.model_validate(
        {k: v for k, v in _job("Verdigris", "GM").model_dump().items() if k not in ("job_id",)}
    )
    assert old.sponsored is False


# ---- logged-in mode: UJS extraction, pagination, stops, seen store ----

COOKIE = "remember_user_token=SECRET-COOKIE-VALUE-123; _cagnts_session=SECRET-SESSION-456"
AUTH_CFG = CulinaryAgentsConfig(
    enabled=True,
    authenticated=True,
    locations=("New York, NY",),
    max_company_pages=0,
    daily_stop_after_known=15,
)


def test_extract_ujs_html_unescapes_a_js_string_literal() -> None:
    js = (
        '$("#js-jobs-result").append("<div class=\\"a\\">Chef\\\'s Table<\\/div>\\n'
        '<span>Caf\\u00e9 \u015ctelo \\u2019</span>");\n'
        '$("#load_more_btn").attr("href", "/search/jobs?page=3");'
    )
    html = ca.extract_ujs_html(js)
    assert html == '<div class="a">Chef\'s Table</div>\n<span>Café Ŝtelo ’</span>'


def test_extract_ujs_html_joins_calls_falls_back_to_html_and_rejects_unknown() -> None:
    js = '$("#a").append("<p>one</p>");\n$("#b").html(\'<p>two "q"</p>\');'
    assert ca.extract_ujs_html(js) == '<p>one</p><p>two "q"</p>'
    assert ca.extract_ujs_html("  <div>already html</div>") == "  <div>already html</div>"
    assert ca.extract_ujs_html('window.location = "/users/sign_in";') == ""
    assert ca.extract_ujs_html(read("job_search_xhr_empty.js.txt")) == ""


def test_xhr_fixture_cards_parse_with_sponsored_flag_job_id_and_unicode() -> None:
    parsed = parse_job_search(ca.extract_ujs_html(read("job_search_xhr.js.txt")), TODAY)
    by = {j.company: j for j in parsed}
    assert len(parsed) == 6
    cafe = by["Café Ŝtelo"]  # non-ASCII survives the JS-string decode
    assert cafe.job_id == "9200001" and cafe.title == "Executive Chef"
    assert cafe.group == "Ŝtelo Hospitality"
    assert cafe.posted == date(2026, 11, 10)  # absolute date on a logged-in card
    assert by["Chef's Table at Larkspur"].posted == date(2026, 11, 13)
    assert by["Ambergate"].sponsored and by["Halden Hall"].sponsored
    assert not cafe.sponsored
    assert "ad_id" not in by["Ambergate"].url


def test_session_search_urls_use_exactly_offset_page_and_sj_offset() -> None:
    first = ca.session_search_url("jobs", "New York, NY", 1, 0, AUTH_CFG)
    assert first == (
        "https://culinaryagents.com/search/jobs?search[country]=US"
        "&search[location]=New+York%2C+NY&search[segment_ids][]=13&search[segment_ids][]=9"
        "&search[segment_ids][]=2&search[segment_ids][]=1"
    )
    second = ca.session_search_url("jobs", "New York, NY", 2, 4, AUTH_CFG)
    assert second == (
        "https://culinaryagents.com/search/jobs?offset=20&page=2&search[country]=US"
        "&search[location]=New+York%2C+NY&search[segment_ids][]=13&search[segment_ids][]=9"
        "&search[segment_ids][]=2&search[segment_ids][]=1&sj_offset=4"
    )
    soon = ca.session_search_url("jobs", "New York, NY", 3, 5, AUTH_CFG, opening_soon=True)
    assert "offset=40&page=3" in soon and soon.endswith("&sj_offset=5")
    assert "search[entity_status][]=opening_soon" in soon
    companies = ca.session_search_url("companies", "New York, NY", 2, 0, AUTH_CFG)
    assert companies.startswith("https://culinaryagents.com/companies/search?offset=20&page=2")
    assert "search[open_status][]=opening_soon" in companies and "sj_offset" not in companies
    assert all(is_fetchable(u) for u in (first, second, soon, companies))


class FakeSession:
    """Serves the synthetic logged-in pages: page 1 HTML, page 2 UJS, page 3 empty UJS."""

    def __init__(self, overrides: dict[int, str] | None = None) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.overrides = overrides or {}

    def __call__(self, url: str, xhr: bool) -> str:
        self.calls.append((url, xhr))
        n = len(self.calls)
        if n in self.overrides:
            raise ca.SessionStopped(self.overrides[n], auth="401" in self.overrides[n])
        page = int(re.search(r"[?&]page=(\d+)", url).group(1)) if "page=" in url else 1
        if "/entities/" in url:
            return read("company_page.html")
        if "/companies/search" in url:
            if page == 1:
                return read("company_search_opening_soon.html")
            return read("job_search_xhr_empty.js.txt")
        return {1: read("job_search_logged_in.html"), 2: read("job_search_xhr.js.txt")}.get(
            page, read("job_search_xhr_empty.js.txt")
        )


def test_iter_search_pages_walks_until_an_empty_page_and_tracks_sj_offset() -> None:
    session = FakeSession()
    budget = CallBudget("ca", 50)
    pages = list(
        ca.iter_search_pages(
            "jobs", "New York, NY", session, budget, opening_soon=False, cfg=AUTH_CFG, today=TODAY
        )
    )
    assert [p.page for p in pages] == [1, 2]
    assert budget.used == 3  # the empty page 3 was fetched, then the walk ended
    urls = [u for u, _ in session.calls]
    assert [x for _, x in session.calls] == [False, True, True]  # page 1 is HTML, then XHR
    assert "offset=20&page=2" in urls[1] and urls[1].endswith("sj_offset=1")  # 1 sponsored
    assert "offset=40&page=3" in urls[2] and urls[2].endswith("sj_offset=3")  # 1 + 2


def test_iter_search_pages_respects_max_pages_and_spends_before_each_fetch() -> None:
    budget = CallBudget("ca", 50)
    spent: list[int] = []
    inner = FakeSession()

    def session(url: str, xhr: bool) -> str:
        spent.append(budget.used)
        return inner(url, xhr)

    pages = list(
        ca.iter_search_pages(
            "jobs",
            "New York, NY",
            session,
            budget,
            opening_soon=False,
            cfg=AUTH_CFG,
            today=TODAY,
            max_pages=1,
        )
    )
    assert len(pages) == 1 and spent == [1]


def test_empty_first_page_is_a_stop_not_an_end() -> None:
    with pytest.raises(ca.SessionStopped, match="empty page"):
        list(
            ca.iter_search_pages(
                "jobs",
                "New York, NY",
                lambda u, x: "<html><body>no cards</body></html>",
                CallBudget("ca", 5),
                opening_soon=False,
                cfg=AUTH_CFG,
                today=TODAY,
            )
        )


def test_unrecognised_xhr_response_is_a_stop() -> None:
    def session(url: str, xhr: bool) -> str:
        return read("job_search_logged_in.html") if not xhr else 'window.location="/x";'

    with pytest.raises(ca.SessionStopped, match="unrecognised"):
        list(
            ca.iter_search_pages(
                "jobs",
                "New York, NY",
                session,
                CallBudget("ca", 5),
                opening_soon=False,
                cfg=AUTH_CFG,
                today=TODAY,
            )
        )


def _session_fetcher(handler, cookie: str = COOKIE) -> PoliteFetcher:
    return PoliteFetcher(
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        cookie=cookie,
    )


def _robots_ok(request: httpx.Request) -> httpx.Response | None:
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow: /users\n")
    return None


def test_session_fetcher_sends_cookie_xhr_headers_and_csrf_from_page_one() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if (r := _robots_ok(request)) is not None:
            return r
        if request.url.params.get("page") == "2":
            return httpx.Response(200, text=read("job_search_xhr.js.txt"))
        return httpx.Response(200, text=read("job_search_logged_in.html"))

    f = _session_fetcher(handler)
    page1 = ca.session_search_url("jobs", "New York, NY", 1, 0, AUTH_CFG)
    page2 = ca.session_search_url("jobs", "New York, NY", 2, 1, AUTH_CFG)
    assert "csrf-token" in f.page(page1)
    assert ".append(" in f.page(page2, xhr=True)
    robots, first, second = seen
    assert "cookie" not in robots.headers  # the session never goes to robots.txt
    assert first.headers["cookie"] == COOKIE and "x-csrf-token" not in first.headers
    assert second.headers["cookie"] == COOKIE
    assert second.headers["x-requested-with"] == "XMLHttpRequest"
    assert second.headers["accept"].startswith("text/javascript")
    assert second.headers["x-csrf-token"] == "SYNTHETIC-CSRF-TOKEN-0000"
    assert second.headers["user-agent"] == ca.USER_AGENT  # honest UA, no impersonation


def test_session_fetcher_refuses_xhr_without_a_csrf_token() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return _robots_ok(request) or httpx.Response(200, text="x")

    f = _session_fetcher(handler)
    with pytest.raises(ca.SessionStopped, match="csrf"):
        f.page(ca.session_search_url("jobs", "New York, NY", 2, 0, AUTH_CFG), xhr=True)
    assert seen == []  # nothing went out, not even robots.txt


@pytest.mark.parametrize(
    ("response", "reason", "auth"),
    [
        (httpx.Response(401), "401", True),
        (httpx.Response(403), "403", True),
        (httpx.Response(429), "429", False),
        (
            httpx.Response(302, headers={"location": "https://culinaryagents.com/users/sign_in"}),
            "sign-in redirect",
            True,
        ),
        (httpx.Response(200, text="   \n"), "empty page", False),
    ],
)
def test_session_fetcher_stops_without_retry_and_never_leaks_the_cookie(
    response: httpx.Response, reason: str, auth: bool, caplog
) -> None:
    pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if (r := _robots_ok(request)) is not None:
            return r
        pages.append(str(request.url))
        return response

    f = _session_fetcher(handler)
    with caplog.at_level(logging.DEBUG), pytest.raises(ca.SessionStopped) as info:
        f.page(ca.session_search_url("jobs", "New York, NY", 1, 0, AUTH_CFG))
    assert len(pages) == 1  # stopped, never retried
    assert reason in info.value.reason and info.value.auth is auth
    for text in (str(info.value), repr(info.value), info.value.reason, caplog.text):
        assert "SECRET" not in text
    assert info.value.__cause__ is None and info.value.__context__ is None


def test_session_fetcher_network_error_never_leaks_the_cookie(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if (r := _robots_ok(request)) is not None:
            return r
        raise httpx.ConnectError(f"down; headers were {request.headers.get('cookie')}")

    f = _session_fetcher(handler)
    with caplog.at_level(logging.DEBUG), pytest.raises(ca.SessionStopped) as info:
        f.page(ca.session_search_url("jobs", "New York, NY", 1, 0, AUTH_CFG))
    assert "network error" in info.value.reason
    for text in (str(info.value), caplog.text):
        assert "SECRET" not in text
    assert info.value.__cause__ is None and info.value.__context__ is None


def test_session_fetcher_keeps_the_public_guarantees() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(503)
        return httpx.Response(200, text="<html>ok</html>")

    f = _session_fetcher(handler)
    with pytest.raises(ca.SessionStopped, match="robots"):
        f.page("https://culinaryagents.com/search/jobs?x=1")
    with pytest.raises(ca.SessionStopped, match="refused"):
        f.page("https://culinaryagents.com/users/sign_in")
    assert seen == ["/robots.txt"]  # robots fails closed; /users never requested


def _walk(seen=None, cfg=AUTH_CFG, session=None, backfill=False, budget=None, known=None):
    return ca.walk_nyc(
        cfg,
        budget or CallBudget("ca", 60),
        session or FakeSession(),
        seen or {},
        TODAY,
        backfill=backfill,
        sleep=lambda s: None,
        known_companies=known or {},
    )


def test_walk_collects_new_items_flags_sponsored_and_counts_private_listings() -> None:
    out = _walk()
    assert out.pages == 8  # jobs 3 + opening-soon jobs 3 + companies 2
    assert out.stopped == "" and out.early_exit == ()
    keys = {ca.job_key(j) for j in out.jobs}
    assert len(keys) == len(out.jobs)  # de-duplicated by job id
    assert out.private_skipped >= 1
    assert not any(ca.is_private_listing(j) for j in out.jobs)
    assert out.new_jobs == len(out.jobs)
    assert out.new_companies == sum(c.opening_soon for c in out.companies) > 0
    assert {s.key for s in out.seen} >= keys
    assert all(s.first_seen == TODAY == s.last_seen for s in out.seen)


def test_daily_mode_exits_early_after_n_known_organic_items_ignoring_sponsored() -> None:
    seen = {
        k: CASeen(key=k, first_seen=date(2026, 11, 1), last_seen=date(2026, 11, 15))
        for k in ("job:9100101", "job:9100103")  # page 1's two organic jobs; sponsored is new
    }
    cfg = AUTH_CFG.model_copy(update={"daily_stop_after_known": 2})
    session = FakeSession()
    out = _walk(seen, cfg, session)
    job_pages = [u for u, _ in session.calls if "/search/jobs" in u]
    assert len(job_pages) == 2  # page 1 of each job search, no XHR page
    assert out.early_exit == ("jobs page 1", "opening-soon jobs page 1")
    assert out.new_jobs == 1  # only the sponsored card was new
    kept = next(s for s in out.seen if s.key == "job:9100101")
    assert kept.first_seen == date(2026, 11, 1) and kept.last_seen == TODAY


def test_sponsored_items_alone_never_trigger_the_early_exit() -> None:
    seen = {"job:9100102": CASeen(key="job:9100102", first_seen=TODAY, last_seen=TODAY)}
    cfg = AUTH_CFG.model_copy(update={"daily_stop_after_known": 1})
    out = _walk(seen, cfg)
    assert out.early_exit == ()  # the one known item was sponsored


def test_backfill_ignores_the_early_exit_and_resumes_from_ca_seen() -> None:
    cfg = AUTH_CFG.model_copy(update={"daily_stop_after_known": 1})
    crashed = _walk(cfg=cfg, session=FakeSession({2: "http 429 rate limited"}), backfill=True)
    assert crashed.pages == 2 and "429" in crashed.stopped and not crashed.auth_failure
    assert crashed.jobs  # what was fetched before the stop is kept
    seen = {s.key: s.model_copy(update={"first_seen": date(2026, 11, 2)}) for s in crashed.seen}
    resumed = _walk(seen, cfg, backfill=True)
    assert resumed.early_exit == () and resumed.stopped == ""
    assert resumed.new_jobs == len(resumed.jobs) - len(crashed.jobs)
    for s in resumed.seen:
        if s.key in seen:
            assert s.first_seen == date(2026, 11, 2)  # resumed, not re-dated
        else:
            assert s.first_seen == TODAY


def test_walk_records_auth_stop_and_keeps_what_was_fetched() -> None:
    out = _walk(session=FakeSession({3: "http 401"}))
    assert out.auth_failure and "401" in out.stopped
    assert out.pages == 3 and out.jobs


def test_profiles_fetched_once_and_not_refetched_within_30_days() -> None:
    cfg = AUTH_CFG.model_copy(update={"max_company_pages": 10})
    session = FakeSession()
    first = _walk(cfg=cfg, session=session)
    profiles = [u for u, _ in session.calls if "/entities/" in u]
    assert profiles and all(not x for u, x in session.calls if "/entities/" in u)
    assert all(
        s.profile_fetched_on == TODAY
        for s in first.seen
        if s.key in {ca.company_key(c) for c in first.companies if c.website}
    )
    seen = {
        s.key: s.model_copy(update={"profile_fetched_on": date(2026, 11, 1)}) for s in first.seen
    }
    known = {ca.company_key(c): c for c in first.companies}
    again = FakeSession()
    second = _walk(seen, cfg, again, known=known)
    assert not [u for u, _ in again.calls if "/entities/" in u]  # fetched 15 days ago
    websites = {c.name: c.website for c in second.companies if c.website}
    assert websites == {c.name: c.website for c in first.companies if c.website}
    stale = {
        k: s.model_copy(update={"profile_fetched_on": date(2026, 10, 1)}) for k, s in seen.items()
    }
    third = FakeSession()
    _walk(stale, cfg, third, known=known)
    assert [u for u, _ in third.calls if "/entities/" in u]  # 46 days old: refreshed


def test_first_seen_is_the_signal_date() -> None:
    co = _co("Verdigris", opening_soon=True, locations=("13 Example Street, New York, NY",))
    job = _job("Verdigris", "Executive Chef", posted=None, job_id="77")
    first = {ca.company_key(co): date(2026, 11, 3), ca.job_key(job): date(2026, 11, 5)}
    sigs, _ = to_signals([job], [co], [VERDIGRIS], [], TODAY, CFG, first_seen=first)
    by = {s.signal_type: s for s in sigs}
    assert by["opening_soon"].occurred_at == datetime(2026, 11, 3, tzinfo=UTC)
    assert by["new_chef"].occurred_at == datetime(2026, 11, 5, tzinfo=UTC)
    dated = _job("Verdigris", "Executive Chef", posted=date(2026, 11, 1), job_id="77")
    sigs, _ = to_signals([dated], [], [VERDIGRIS], [], TODAY, CFG, first_seen=first)
    assert sigs[0].occurred_at == datetime(2026, 11, 1, tzinfo=UTC)  # a posting date wins


# ---- logged-in CLI ----


def _auth_cfg(**kw):
    base = load_config()
    ca_cfg = CulinaryAgentsConfig(
        enabled=True, locations=("New York, NY",), max_company_pages=0, **kw
    )
    return base.model_copy(update={"culinary_agents": ca_cfg})


@pytest.mark.parametrize(
    ("authenticated", "cookie", "kwargs"),
    [
        (False, COOKIE, {"backfill": True}),
        (False, COOKIE, {"max_pages": 2}),
        (True, None, {}),
        (True, "", {"backfill": True}),
    ],
)
def test_cli_refuses_logged_in_mode_without_authenticated_or_cookie(
    monkeypatch, authenticated, cookie, kwargs
) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: _auth_cfg(authenticated=authenticated))
    monkeypatch.setattr(cli, "DocStore", lambda: pytest.fail("touched the store"))
    if cookie is None:
        monkeypatch.delenv("CULINARY_AGENTS_COOKIE", raising=False)
    else:
        monkeypatch.setenv("CULINARY_AGENTS_COOKIE", cookie)
    session = FakeSession()
    with pytest.raises(SystemExit) as info:
        cli.culinary_agents(session_fetch=session, today=TODAY, sleep=lambda s: None, **kwargs)
    msg = str(info.value)
    assert "§7" in msg and "risk" in msg
    assert "SECRET" not in msg
    assert session.calls == []


def _auth_store(monkeypatch, tmp_path, **cfg_kw):
    from scripts.hospitality.store import DocStore

    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    venues = [
        make_venue("v:verdigris", name="Verdigris", address="13 EXAMPLE ST"),
        make_venue("v:quillon", name="Quillon", address="44 FIXTURE PL"),
        make_venue("v:marinella", name="Marinella", address="149 SAMPLE ST"),
    ]
    store.save("venues", venues, key=lambda v: v.venue_id)
    store.save(
        "groups",
        [
            Group(
                group_id=f"g:{v.venue_id}",
                name=v.name,
                venue_ids=(v.venue_id,),
                resolution="singleton",
            )
            for v in venues
        ],
        key=lambda g: g.group_id,
    )
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    monkeypatch.setattr(cli, "load_config", lambda: _auth_cfg(authenticated=True, **cfg_kw))
    monkeypatch.setattr(cli, "score", lambda: {"scored_groups": 3})
    monkeypatch.setenv("CULINARY_AGENTS_COOKIE", COOKIE)
    return store


def test_cli_logged_in_daily_run_saves_seen_signals_and_summary(monkeypatch, tmp_path) -> None:
    store = _auth_store(monkeypatch, tmp_path)
    out = cli.culinary_agents(session_fetch=FakeSession(), today=TODAY, sleep=lambda s: None)
    assert out["pages"] == 8 and out["stopped"] == "" and out["early_exit"] == ""
    assert out["new_jobs"] > 0 and out["new_opening_soon_companies"] > 0
    assert out["private_listings_skipped"] >= 1
    seen = store.load("ca_seen", CASeen)
    assert seen and all(s.first_seen == TODAY for s in seen)
    kinds = {(s.entity_id, s.signal_type) for s in store.load("signals", Signal)}
    assert ("v:verdigris", "new_gm") in kinds
    assert ("v:quillon", "guest_role_hire") in kinds
    assert ("v:marinella", "opening_soon") in kinds
    assert "SECRET" not in repr(out)
    # the next morning: everything is known, so both job searches stop after page 1
    later = cli.culinary_agents(
        session_fetch=FakeSession(), today=date(2026, 11, 17), sleep=lambda s: None
    )
    assert later["new_jobs"] == 0
    first = {s.key: s for s in store.load("ca_seen", CASeen)}
    assert all(s.first_seen == TODAY for s in first.values())
    sig = next(s for s in store.load("signals", Signal) if s.signal_type == "opening_soon")
    assert sig.occurred_at == datetime(2026, 11, 16, tzinfo=UTC)  # first seen, not today


def test_cli_max_pages_caps_the_run_and_backfill_uses_its_budget(monkeypatch, tmp_path) -> None:
    _auth_store(monkeypatch, tmp_path)
    session = FakeSession()
    out = cli.culinary_agents(session_fetch=session, today=TODAY, sleep=lambda s: None, max_pages=2)
    assert out["pages"] == 2 and len(session.calls) == 2
    assert "--max-pages 2" in out["stopped"]
    out = cli.culinary_agents(
        session_fetch=FakeSession(), today=TODAY, sleep=lambda s: None, backfill=True
    )
    assert out["mode"] == "backfill" and out["budget"] == 150


def test_cli_auth_stop_says_session_expired(monkeypatch, tmp_path, capsys) -> None:
    _auth_store(monkeypatch, tmp_path)
    out = cli.culinary_agents(
        session_fetch=FakeSession({2: "http 401"}), today=TODAY, sleep=lambda s: None
    )
    assert "session expired — refresh CULINARY_AGENTS_COOKIE" in out["stopped"]
    assert "SECRET" not in repr(out)


# ---- section 8: Culinary Agents articles as opening news ----


def test_parse_article_index_keeps_article_links_only() -> None:
    urls = ca.parse_article_index(read("resources_index.html"))
    assert urls == [
        "https://culinaryagents.com/resources/industry-insights/whats-opening-this-winter-in-nyc",
        "https://culinaryagents.com/resources/featured-articles/a-new-tavern-for-the-west-village",
    ]


def test_article_text_reads_the_article_body_without_scripts() -> None:
    text = ca.article_text(read("article.html"))
    assert "Verdigris, the new tavern" in text
    assert "ignore me" not in text and "Footer links" not in text


def _article_pages(urls: list[str]):
    def fetch(url: str) -> str | None:
        urls.append(url)
        return read("resources_index.html") if url == ca.RESOURCES_URL else read("article.html")

    return fetch


def test_cli_articles_without_anthropic_key_lists_urls_only(monkeypatch, tmp_path) -> None:
    from scripts.hospitality.discover import press

    _auth_store(monkeypatch, tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(press, "structured", lambda *a, **k: pytest.fail("called Claude"))
    urls: list[str] = []
    out = cli.culinary_agents(fetch=_article_pages(urls), today=TODAY, articles=True)
    assert urls == [ca.RESOURCES_URL]  # only the public index; no login, no article bodies
    assert out["articles"] == 2 and out["extracted"] == 0
    assert len(out["urls"]) == 2 and "ANTHROPIC_API_KEY" in out["note"]


def test_cli_articles_route_to_press_extractor_and_drop_names_not_in_text(
    monkeypatch, tmp_path
) -> None:
    from scripts.hospitality.discover import press
    from scripts.hospitality.models import PressFacts, PressPerson, PressVenue

    store = _auth_store(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    facts = PressFacts(
        venues=(
            PressVenue(
                name="Verdigris",
                address_or_area="13 Example Street",
                status="opening_soon",
                expected_open="January",
                group_name=None,
            ),
            PressVenue(
                name="Phantom Bistro",  # not in the article text: a fabrication
                address_or_area="1 Nowhere Lane",
                status="opening_soon",
                expected_open=None,
                group_name=None,
            ),
        ),
        people=(PressPerson(name="Ada Moreau", role="Executive Chef", prior_employers=()),),
        hotel_partner=None,
    )
    calls: list[str] = []

    def fake_structured(*a, **k):
        calls.append(k["user"])
        return facts

    monkeypatch.setattr(press, "structured", fake_structured)
    out = cli.culinary_agents(fetch=_article_pages([]), today=TODAY, articles=True)
    assert len(calls) == 2 and out["extracted"] == 2
    sigs = store.load("signals", Signal)
    assert {s.signal_type for s in sigs} == {"press_opening"}
    assert {s.entity_id for s in sigs} == {"v:verdigris"}
    assert all(s.evidence_ref.startswith(f"{ca.RESOURCES_URL}/") for s in sigs)
    assert not any("Phantom" in s.detail or "Ada Moreau" in s.detail for s in sigs)
    assert not any(v.name == "Phantom Bistro" for v in store.load("venues", Venue))


def test_cli_articles_need_only_the_public_source_enabled(monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: load_config())
    with pytest.raises(SystemExit, match="agreement"):
        cli.culinary_agents(fetch=_article_pages([]), today=TODAY, articles=True)


# ---- live page-2 shape: variable-assigned UJS HTML, unwrapped cards, no silent end ----


def test_extract_ujs_html_reads_html_assigned_to_a_variable_and_appended_by_name() -> None:
    js = (
        "(function() {\n  var result;\n"
        '  result = "<p>one<\\/p>";\n'
        "  $('#js-jobs-result').append(result);\n"
        "  if (!true) {\n    result = \"\";\n    $('#js-jobs-result').append(result);\n  }\n"
        "  $('#js-jobs-result-replace').html(result);\n"
        "}).call(this);"
    )
    # the same HTML injected into a second target is one copy, not two
    assert ca.extract_ujs_html(js) == "<p>one</p>"


def test_extract_ujs_html_keeps_literal_and_variable_injections_in_order() -> None:
    js = '$("#a").append("<p>one</p>");\nx = \'<p>two</p>\';\n$("#b").append(x);'
    assert ca.extract_ujs_html(js) == "<p>one</p><p>two</p>"
    assert ca.extract_ujs_html("$('#a').append(undefinedName);") == ""


def test_live_shape_xhr_fixture_parses_unwrapped_cards() -> None:
    parsed = parse_job_search(ca.extract_ujs_html(read("job_search_xhr_var.js.txt")), TODAY)
    by = {j.company: j for j in parsed}
    assert len(parsed) == 4
    assert [j.job_id for j in parsed] == ["9300001", "9300002", "9300003", "9300004"]
    assert by["Thornfield Tavern"].sponsored and by["Thornfield Tavern"].posted is None
    assert sum(j.sponsored for j in parsed) == 1
    mirelle = by["Mirelle’s Kitchen"]  # non-ASCII survives the variable's JS-string decode
    assert mirelle.group == "Lanternwood Hospitality"
    assert mirelle.location == "34 Sample Avenue, New York, NY"
    assert mirelle.company_url == "https://culinaryagents.com/entities/9400002"
    assert mirelle.posted == TODAY - timedelta(days=1)
    assert by["Chef's Counter at Quillby"].group is None  # four rows: no group row
    assert by["Bramblecote"].posted == TODAY - timedelta(days=7)


def test_wrapped_cards_are_not_double_counted() -> None:
    wrapped = read("job_search_logged_in.html")
    assert len(parse_job_search(wrapped, TODAY)) == 3
    unwrapped = ca.extract_ujs_html(read("job_search_xhr_var.js.txt"))
    both = parse_job_search(wrapped + unwrapped, TODAY)
    assert len(both) == 7 and len({j.url for j in both}) == 7


def _xhr_walk(xhr_bodies: list[str]) -> list[ca.SearchPage]:
    bodies = iter(xhr_bodies)

    def session(url: str, xhr: bool) -> str:
        return next(bodies) if xhr else read("job_search_logged_in.html")

    return list(
        ca.iter_search_pages(
            "jobs",
            "New York, NY",
            session,
            CallBudget("ca", 10),
            opening_soon=False,
            cfg=AUTH_CFG,
            today=TODAY,
        )
    )


def test_page_two_in_the_live_shape_is_read_and_the_walk_continues() -> None:
    pages = _xhr_walk([read("job_search_xhr_var.js.txt"), read("job_search_xhr_empty.js.txt")])
    assert [p.page for p in pages] == [1, 2]
    assert len(pages[1].jobs) == 4


@pytest.mark.parametrize(
    "body",
    [
        # card markup in a shape the extractor cannot read (built by a function call)
        '$(\'#js-jobs-result\').append(build("<a class=\\"ca-single-job-card\\"><\\/a>"));',
        # card markup that is extracted but has no readable card in it
        (
            '$(\'#js-jobs-result\').append("<div class=\\"card new-job-card\\">'
            '<a class=\\"ca-single-job-card\\"><\\/a><\\/div>");'
        ),
    ],
)
def test_job_card_markup_with_zero_cards_is_an_unrecognised_stop(body: str) -> None:
    with pytest.raises(ca.SessionStopped, match="unrecognised"):
        _xhr_walk([body])


def test_company_card_markup_with_zero_cards_is_an_unrecognised_stop() -> None:
    def session(url: str, xhr: bool) -> str:
        if not xhr:
            return read("company_search_opening_soon.html")
        return '$(\'#js-entities-result\').append(build("<div class=\\"company-card\\">"));'

    with pytest.raises(ca.SessionStopped, match="unrecognised"):
        list(
            ca.iter_search_pages(
                "companies",
                "New York, NY",
                session,
                CallBudget("ca", 10),
                opening_soon=True,
                cfg=AUTH_CFG,
                today=TODAY,
            )
        )


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Guest Relations Coordinator", "guest_role_hire"),
        ("Dining Room Manager", "guest_role_hire"),
        ("Restaurant Manager", "guest_role_hire"),
        ("Assistant Restaurant Manager", None),
        ("Bar Manager", None),
        ("Guest Experience Ambassador (Host/Hostess)", None),
        ("Host", None),
        ("Executive Pastry Chef", None),  # fine-dining fit evidence, not new_chef
        ("Pastry Chef", None),
        ("Executive Chef", "new_chef"),
    ],
)
def test_classify_title_live_titles(title: str, expected: str | None) -> None:
    assert classify_title(title, CFG) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Executive Pastry Chef", True),
        ("Pastry Chef", True),
        ("Pastry Sous Chef", False),
        ("Executive Chef", False),
        ("Bar Manager", False),
    ],
)
def test_pastry_chefs_are_fine_dining_service_titles(title: str, expected: bool) -> None:
    assert ca.is_service_title(title, CFG) is expected


def test_example_config_title_lists_match_the_code_defaults() -> None:
    example = load_config().culinary_agents
    default = CulinaryAgentsConfig()
    for field in ("chef_titles", "gm_titles", "events_titles", "guest_titles", "service_titles"):
        assert getattr(example, field) == getattr(default, field), field


# ---- end of results (Partner Jobs block), the saved stop page ----


def test_partner_jobs_are_not_parsed_as_culinary_agents_jobs() -> None:
    html = ca.extract_ujs_html(read("job_search_xhr_end.js.txt"))
    jobs = parse_job_search(html, TODAY)
    assert [(j.company, j.title) for j in jobs] == [("Wrenhaven", "General Manager")]
    assert jobs[0].group == "Wrenhaven Hospitality"


def test_partner_jobs_block_with_no_own_cards_is_a_normal_end() -> None:
    pages = _xhr_walk([read("job_search_xhr_end_empty.js.txt")])
    assert [p.page for p in pages] == [1]  # no stop: the site marked the end of results


def test_partner_jobs_block_after_the_last_cards_ends_the_walk_after_that_page() -> None:
    session = FakeSession()
    bodies = iter([read("job_search_xhr_end.js.txt")])

    def fetch(url: str, xhr: bool) -> str:
        session.calls.append((url, xhr))
        return next(bodies) if xhr else read("job_search_logged_in.html")

    pages = list(
        ca.iter_search_pages(
            "jobs",
            "New York, NY",
            fetch,
            CallBudget("ca", 10),
            opening_soon=True,
            cfg=AUTH_CFG,
            today=TODAY,
        )
    )
    assert [p.page for p in pages] == [1, 2]
    assert [j.company for j in pages[1].jobs] == ["Wrenhaven"]
    assert len(session.calls) == 2  # no page 3 request after the end marker


def test_a_stop_carries_the_body_of_the_page_it_stopped_on() -> None:
    body = '$(\'#js-jobs-result\').append(build("<a class=\\"ca-single-job-card x\\">"));'
    with pytest.raises(ca.SessionStopped) as info:
        _xhr_walk([body])
    assert info.value.body == body
    assert body not in str(info.value)  # the reason stays short


def test_cli_saves_the_stopped_page_under_out_magic(monkeypatch, tmp_path) -> None:
    _auth_store(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "OUT_DIR", tmp_path / "out")
    body = '$(\'#js-jobs-result\').append(build("<a class=\\"ca-single-job-card x\\">"));'

    def session(url: str, xhr: bool) -> str:
        return body if xhr else read("job_search_logged_in.html")

    out = cli.culinary_agents(session_fetch=session, today=TODAY, sleep=lambda s: None)
    assert "unrecognised" in out["stopped"]
    saved = tmp_path / "out" / "culinary_agents_stopped_page.txt"
    assert out["stopped_page"] == str(saved)
    assert saved.read_text().endswith(body)
    assert "/search/jobs" in saved.read_text().splitlines()[0]


def test_cli_redacts_the_cookie_from_a_saved_stopped_page(monkeypatch, tmp_path) -> None:
    _auth_store(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "OUT_DIR", tmp_path / "out")
    body = '<a class="ca-single-job-card x">SECRET-SESSION-456</a>'

    def session(url: str, xhr: bool) -> str:
        return read("job_search_logged_in.html") if not xhr else f"$('#x').append(f({body!r}));"

    out = cli.culinary_agents(session_fetch=session, today=TODAY, sleep=lambda s: None)
    assert "SECRET" not in Path(str(out["stopped_page"])).read_text()


def test_cli_reports_no_stopped_page_when_the_walk_finishes(monkeypatch, tmp_path) -> None:
    _auth_store(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "OUT_DIR", tmp_path / "out")
    out = cli.culinary_agents(session_fetch=FakeSession(), today=TODAY, sleep=lambda s: None)
    assert out["stopped"] == "" and out["stopped_page"] == ""
    assert not (tmp_path / "out" / "culinary_agents_stopped_page.txt").exists()


# ---- hiring burst by venue status: opening evidence vs staffing_change ----

SIX = ["Line Cook", "Server", "Host", "Porter", "Barback", "Dishwasher"]
OPEN_VERDIGRIS = make_venue(
    "v:verdigris", name="Verdigris", address="13 EXAMPLE ST", first_inspection_date=date(2025, 3, 1)
)


def test_open_venue_with_six_roles_gets_staffing_change_not_hiring_burst() -> None:
    sigs, _ = run(_roles("Verdigris", SIX), [], [OPEN_VERDIGRIS])
    kinds = [s.signal_type for s in sigs]
    assert "hiring_burst" not in kinds and kinds.count("staffing_change") == 1
    change = next(s for s in sigs if s.signal_type == "staffing_change")
    assert change.entity_id == "v:verdigris" and "6 distinct roles" in change.detail


def test_open_venue_open_call_is_a_staffing_change() -> None:
    sigs, _ = run([_job("Verdigris", "Open Call - All Positions")], [], [OPEN_VERDIGRIS])
    assert [s.signal_type for s in sigs] == ["staffing_change"]


def test_opening_soon_venue_with_six_roles_gets_hiring_burst() -> None:
    soon = _roles("Verdigris", SIX, opening_soon=True)
    sigs, _ = run(soon, [], [OPEN_VERDIGRIS])  # inspected, but the employer is opening soon
    assert [s.signal_type for s in sigs].count("hiring_burst") == 1
    assert "staffing_change" not in [s.signal_type for s in sigs]
    listed = [_co("Verdigris", opening_soon=True, locations=("13 Example Street",))]
    sigs, _ = run(_roles("Verdigris", SIX), listed, [OPEN_VERDIGRIS])  # a company card says so
    assert "hiring_burst" in [s.signal_type for s in sigs]


def test_never_inspected_venue_with_six_roles_keeps_hiring_burst() -> None:
    sigs, _ = run(_roles("Verdigris", SIX), [], [VERDIGRIS])
    assert "hiring_burst" in [s.signal_type for s in sigs]


def test_open_multi_venue_group_gains_no_window_evidence_from_bursts() -> None:
    quillon = make_venue(
        "v:quillon", name="Quillon", address="44 FIXTURE PL", first_inspection_date=date(2024, 6, 1)
    )
    jobs = [
        *_roles("Verdigris", SIX),
        *(
            _job("Quillon", t, location="44 Fixture Pl, New York, NY", url=f"https://x/jobs/{i}-q")
            for i, t in enumerate(SIX, start=500)
        ),
    ]
    venues = [OPEN_VERDIGRIS, quillon]
    sigs, _ = run(jobs, [], venues)
    assert sorted(s.signal_type for s in sigs) == ["staffing_change", "staffing_change"]
    scored = _score(venues, sigs)
    cfg = load_config()
    opening = [c for c in scored.contributions if cfg.priors[c.signal_type].family == "opening"]
    assert opening == []
    old_style = [s.model_copy(update={"signal_type": "hiring_burst"}) for s in sigs]
    assert scored.p_window < _score(venues, old_style).p_window
    assert all(c.precision == pytest.approx(0.10) for c in scored.contributions)


def test_staffing_change_prior_is_people_family_and_not_folded_with_licences() -> None:
    cfg = load_config()
    prior = cfg.priors["staffing_change"]
    assert prior.precision == pytest.approx(0.10)
    assert prior.family == "people" and prior.half_life_days == 90
    assert "staffing_change" not in cfg.opening_evidence_signals
    lic = make_signal("license_pending", "v:verdigris")
    change, _ = run(_roles("Verdigris", SIX), [], [OPEN_VERDIGRIS])
    both = _score([OPEN_VERDIGRIS], [lic, *change])
    by_type = {c.signal_type: c for c in both.contributions}
    assert by_type["staffing_change"].note == ""  # counted, not folded
    assert Signal.model_validate(make_signal("staffing_change").model_dump())


def test_extract_ujs_html_skips_comments_with_quotes_in_them() -> None:
    js = "// the page's cards\n/* it's \"here\" */\nr = \"<p>one<\\/p>\";\n$('#a').append(r);"
    assert ca.extract_ujs_html(js) == "<p>one</p>"


def test_cli_logged_in_run_replaces_its_earlier_signals_and_job_board_evidence(
    monkeypatch, tmp_path
) -> None:
    store = _auth_store(monkeypatch, tmp_path)
    stale = make_signal("hiring_burst", "v:verdigris").model_copy(
        update={"signal_id": "hiring_burst:v:verdigris:old", "source": "culinary_agents"}
    )
    other = make_signal("license_pending", "v:verdigris").model_copy(
        update={"signal_id": "license_pending:v:verdigris:keep", "source": "sla"}
    )
    store.save("signals", [stale, other], key=lambda s: s.signal_id)
    old_board = GroupEvidence(
        venue_ids=("v:quillon", "v:verdigris"),
        name="Gone Group",
        resolution="job_board",
        evidence_ref="https://culinaryagents.com/entities/1",
    )
    press = old_board.model_copy(update={"name": "Press Group", "resolution": "press"})
    store.save("group_evidence", [old_board, press], key=cli._evidence_key)
    cli.culinary_agents(session_fetch=FakeSession(), today=TODAY, sleep=lambda s: None)
    ids = {s.signal_id for s in store.load("signals", Signal)}
    assert "hiring_burst:v:verdigris:old" not in ids  # recomputed, so the stale one is gone
    assert "license_pending:v:verdigris:keep" in ids  # other sources are untouched
    assert any(i.startswith("new_gm:v:verdigris") for i in ids)
    names = {e.name for e in store.load("group_evidence", GroupEvidence)}
    assert "Gone Group" not in names and "Press Group" in names


# ---- unmatched opening-soon companies become job-board venues ----


def test_unmatched_opening_soon_company_becomes_a_job_board_venue() -> None:
    solano = _co(
        "Bar Solano",
        url="https://culinaryagents.com/entities/9200002",
        locations=("372 Model Street, New York, NY 10012",),
        opening_soon=True,
        website="https://barsolano.example",
    )
    made = ca.job_board_venues([solano], [VERDIGRIS]).venues
    assert len(made) == 1
    v = made[0]
    assert v.venue_id == "v:ca:9200002" and ca.is_job_board_venue(v.venue_id)
    assert v.name == "Bar Solano" and v.address == "372 Model Street, New York, NY 10012"
    assert v.zip_code == "10012" and v.website == "https://barsolano.example"
    assert v.group_id == "g:v:ca:9200002"  # its own group
    assert v.first_inspection_date is None and v.camis is None and v.license_ids == ()
    sigs, _ = run([], [solano], [VERDIGRIS, v])
    assert [(s.signal_type, s.entity_id) for s in sigs] == [("opening_soon", "v:ca:9200002")]


def test_matched_or_not_opening_soon_companies_create_no_venue() -> None:
    matched = _co("Verdigris", locations=("13 Example Street, New York, NY",), opening_soon=True)
    hiring_only = _co("Quillby", url="https://culinaryagents.com/entities/7", opening_soon=False)
    no_entity = _co("Nameless", url="https://culinaryagents.com/companies/x", opening_soon=True)
    assert ca.job_board_venues([matched, hiring_only, no_entity], [VERDIGRIS]).venues == ()


def test_job_board_venue_dedupes_by_strict_name_and_street_number() -> None:
    # same name and street number, street spelled differently: no new venue
    existing = make_venue("v:9", name="Bar Solano", address="372 MODEL AVE")
    solano = _co(
        "Bar Solano",
        url="https://culinaryagents.com/entities/9200002",
        locations=("372 Model Street, New York, NY",),
        opening_soon=True,
    )
    assert ca.job_board_venues([solano], [existing]).venues == ()
    # a different street number is another site of the brand: a new venue
    elsewhere = make_venue("v:9", name="Bar Solano", address="10 OTHER ST")
    assert [v.venue_id for v in ca.job_board_venues([solano], [elsewhere]).venues] == [
        "v:ca:9200002"
    ]


def test_job_board_venues_are_idempotent_across_runs() -> None:
    solano = _co(
        "Bar Solano",
        url="https://culinaryagents.com/entities/9200002",
        locations=("372 Model Street, New York, NY",),
        opening_soon=True,
    )
    first = ca.job_board_venues([solano], [VERDIGRIS]).venues
    assert ca.job_board_venues([solano], [VERDIGRIS, *first]).venues == ()


def test_job_board_group_link_joins_a_new_venue_to_its_group() -> None:
    solano = _co(
        "Bar Solano",
        url="https://culinaryagents.com/entities/9200002",
        locations=("372 Model Street, New York, NY",),
        opening_soon=True,
        group="Casaverde",
    )
    made = ca.job_board_venues([solano], [VERDIGRIS]).venues
    sister = _job("Verdigris", "Server", group="Casaverde")
    _, evidence = run([sister], [solano], [VERDIGRIS, *made])
    assert [set(e.venue_ids) for e in evidence] == [{"v:verdigris", "v:ca:9200002"}]


def test_cli_unmatched_opening_soon_company_enters_the_ranking(monkeypatch, tmp_path) -> None:
    real_score = cli.score
    store = _auth_store(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "OUT_DIR", tmp_path / "out")
    cli.culinary_agents(session_fetch=FakeSession(), today=TODAY, sleep=lambda s: None)
    venues = {v.venue_id: v for v in store.load("venues", Venue)}
    made = sorted(v for v in venues if v.startswith("v:ca:"))
    assert "v:ca:9200002" in made  # Bar Solano: no venue in the universe
    assert "v:ca:9200001" not in made  # MARINELLA NYC matched v:marinella: no duplicate
    assert not [
        v for v in venues.values() if v.venue_id != "v:marinella" and "MARINELLA" in v.name.upper()
    ]
    top = {name for _, name in real_score(datetime(2026, 11, 16, tzinfo=UTC))["top"]}
    assert "Bar Solano" in top
    kinds = {(s.entity_id, s.signal_type) for s in store.load("signals", Signal)}
    assert ("v:ca:9200002", "opening_soon") in kinds


# ---- job-board venue fixes: decorated duplicates, NYC only, ZIP parsing ----

BUKHARA = make_venue("v:bukhara", name="BUKHARA GRILL", address="120 EAST   39 STREET")


def _card(name: str, address: str, ident: int = 881036, **kw):
    return _co(
        name,
        url=f"https://culinaryagents.com/entities/{ident}",
        locations=(address,),
        opening_soon=True,
        **kw,
    )


def test_decorated_card_name_is_the_existing_venue_at_the_same_street_address() -> None:
    card = _card(
        "Bukhara Grill : Indian Spice Rave & Catering (By Raja Jhanjee) - NYC",
        "120 E 39th St, New York, NY 10016, United States",
    )
    assert ca.job_board_venues([card], [BUKHARA]).venues == ()


@pytest.mark.parametrize(
    "name",
    [
        "Bukhara Grill - Midtown",
        "Bukhara Grill (Murray Hill)",
        "Bukhara Grill by Raja Jhanjee",
        "Bukhara Grill: Indian Spice",
    ],
)
def test_each_decoration_separator_is_stripped(name: str) -> None:
    card = _card(name, "120 E 39th St, New York, NY 10016")
    assert ca.job_board_venues([card], [BUKHARA]).venues == ()


def test_leading_name_needs_the_same_street_address() -> None:
    other_street = _card("Bukhara Grill - Uptown", "120 W 58th St, New York, NY 10019")
    assert [v.name for v in ca.job_board_venues([other_street], [BUKHARA]).venues] == [
        "Bukhara Grill - Uptown"
    ]
    # the existing name must lead the card name, not merely appear in it
    not_leading = _card("Royal Bukhara Grill", "120 E 39th St, New York, NY 10016")
    assert len(ca.job_board_venues([not_leading], [BUKHARA]).venues) == 1


@pytest.mark.parametrize(
    "address",
    [
        "120 E Putnam Ave, Greenwich, CT 06830",
        "1300 Peninsula Boulevard, Hewlett, NY",
        "Greenwich, CT",
    ],
)
def test_out_of_area_companies_are_skipped_and_counted(address: str) -> None:
    out = ca.job_board_venues([_card("Sage + Sound Table", address)], [VERDIGRIS])
    assert out.venues == () and out.out_of_area == ("Sage + Sound Table",)


@pytest.mark.parametrize(
    "address",
    [
        "88 Ninth Avenue, New York, NY 10011",
        "Brooklyn, NY",
        "29 Ryerson Street, Brooklyn, NY",
        "West Village, Manhattan, New York, NY",
        "100 Example Ave, Bronx, NY",
        "5 Sample Rd, Staten Island, NY",
        "30-01 Example Blvd, Queens, NY",
        "12 Example St, 11201",  # a NYC ZIP alone is enough
        "New York, NY",
    ],
)
def test_five_borough_addresses_make_job_board_venues(address: str) -> None:
    out = ca.job_board_venues([_card("Quillmoor", address)], [VERDIGRIS])
    assert len(out.venues) == 1 and out.out_of_area == ()


@pytest.mark.parametrize(
    ("address", "zip_code"),
    [
        ("1 W 67th St, New York, NY 10023, United States", "10023"),
        ("120 E 39th St, New York, NY 10016, United States", "10016"),
        ("120 E 39th St, New York, NY 10016, USA", "10016"),
        ("120 E 39th St, New York, NY 10016-1234", "10016"),
        ("301 South End Avenue, New York, NY", ""),
    ],
)
def test_zip_is_parsed_through_a_trailing_country(address: str, zip_code: str) -> None:
    (venue,) = ca.job_board_venues([_card("Quillmoor", address)], [VERDIGRIS]).venues
    assert venue.zip_code == zip_code and venue.address == address


def test_placeholder_projects_and_company_names_are_kept() -> None:
    cards = [
        _card("New Project by Chef Example Person", "West Village, Manhattan, New York, NY", 1),
        _card("Example Street Hospitality", "61 Example Street, New York, NY", 2),
    ]
    assert len(ca.job_board_venues(cards, [VERDIGRIS]).venues) == 2


def test_cli_rerun_deletes_job_board_venues_the_rules_now_reject(monkeypatch, tmp_path) -> None:
    store = _auth_store(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "OUT_DIR", tmp_path / "out")
    stale = make_venue("v:ca:5555", name="Out Of Town", address="9 Example Rd, Greenwich, CT")
    store.save("venues", [*store.load("venues", Venue), stale], key=lambda v: v.venue_id)
    store.save(
        "ca_companies",
        [_card("Out Of Town", "9 Example Rd, Greenwich, CT", 5555)],
        key=ca.company_key,
    )
    out = cli.culinary_agents(session_fetch=FakeSession(), today=TODAY, sleep=lambda s: None)
    ids = {v.venue_id for v in store.load("venues", Venue)}
    assert "v:ca:5555" not in ids  # rejected by the NYC rule now: deleted, not kept
    assert "v:ca:9200002" in ids  # Bar Solano (New York, NY) is still created
    assert out["job_board_out_of_area"] == 1
