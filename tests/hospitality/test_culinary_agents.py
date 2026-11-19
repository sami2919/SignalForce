import logging
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from scripts.hospitality import cli
from scripts.hospitality.budget import CallBudget
from scripts.hospitality.config import CulinaryAgentsConfig, load_config
from scripts.hospitality.models import CAJob, Group, Signal, Venue
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
    for page in FIX.glob("*.html"):
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
