from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from scripts.hospitality import cli
from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.events import extract
from scripts.hospitality.events.extract import extract_appearances
from scripts.hospitality.events.registry import load_events
from scripts.hospitality.models import Event, LineupEntry, LineupFacts

URL = "https://example.org/lineup"
PAGE = (
    "<html><body><script>var x='Zed Ghost';</script><h1>Speakers</h1>"
    "<p>Ana Reyes, chef at Ghost Bird, speaks on hospitality. Bo Lin of Ember Hall is a "
    "panelist. Cy Park is cooking at the festival. " + "x " * 200 + "</p></body></html>"
)


def event(**kw) -> Event:
    base = {
        "event_id": "e:test",
        "name": "Test Event",
        "start": date(2027, 5, 22),
        "end": date(2027, 5, 25),
        "city": "New York",
        "event_type": "curated_conference",
        "cost_usd": 100.0,
        "lineup_urls": (URL,),
    }
    base.update(kw)
    return Event(**base)


def facts(*rows: tuple[str, str, str]) -> LineupFacts:
    return LineupFacts(
        entries=tuple(LineupEntry(person=p, restaurant=r, role=ro) for p, r, ro in rows)
    )


def run(ev: Event, parsed: LineupFacts, html: str | None = PAGE, fc: Mock | None = None):
    fc = fc or Mock()
    budget = CallBudget("firecrawl", 5)
    with (
        patch.object(extract, "_fetch_page", return_value=html) as fetch,
        patch.object(extract, "structured", return_value=parsed) as llm,
    ):
        out = extract_appearances(ev, fc, budget)
    return out, fetch, llm, fc, budget


def test_load_events_yaml_excludes_unverified(tmp_path: Path) -> None:
    p = tmp_path / "events.yaml"
    p.write_text(
        "events:\n"
        "  - {event_id: e:a, name: A, start: 2027-05-22, end: 2027-05-25, city: Chicago,\n"
        "     event_type: trade_show, cost_usd: 500, lineup_urls: [https://a.example]}\n"
        "  - {event_id: e:b, name: B, start: null, end: null, city: New York,\n"
        "     event_type: festival, cost_usd: 0, lineup_urls: [], verify: check the date}\n"
    )
    assert [e.event_id for e in load_events(p)] == ["e:a"]
    both = load_events(p, include_unverified=True)
    assert [e.event_id for e in both] == ["e:a", "e:b"]
    assert both[0].start == date(2027, 5, 22) and both[1].start is None


def test_load_events_rejects_missing_list(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("foo: 1\n")
    with pytest.raises(ValueError, match="events"):
        load_events(p)


def test_shipped_registry_loads_and_has_no_invented_dates() -> None:
    path = Path("examples/magic-loyalist/events.yaml")
    all_events = load_events(path, include_unverified=True)
    nra = next(e for e in all_events if e.event_id == "e:nra-show-2027")
    assert (nra.start, nra.end, nra.city) == (date(2027, 5, 22), date(2027, 5, 25), "Chicago")
    assert nra.event_type == "trade_show"
    assert [e.event_id for e in load_events(path)] == ["e:nra-show-2027"]


def test_extraction_maps_roles_and_carries_page_url() -> None:
    parsed = facts(
        ("Ana Reyes", "Ghost Bird", "speaker"),
        ("Bo Lin", "Ember Hall", "panelist"),
        ("Cy Park", "", "festival_chef"),
    )
    out, *_ = run(event(), parsed)
    assert [(a.person, a.restaurant, a.role) for a in out] == [
        ("Ana Reyes", "Ghost Bird", "speaker"),
        ("Bo Lin", "Ember Hall", "panelist"),
        ("Cy Park", "", "festival_chef"),
    ]
    assert {a.source_url for a in out} == {URL} and {a.event_id for a in out} == {"e:test"}


def test_fabricated_person_or_restaurant_is_dropped() -> None:
    parsed = facts(
        ("Zed Ghost", "Ghost Bird", "speaker"),  # name only inside a <script>
        ("Ana Reyes", "Phantom Grill", "speaker"),  # restaurant not on the page
        ("Ana Reyes", "Ghost Bird", "speaker"),
    )
    out, *_ = run(event(), parsed)
    assert [(a.person, a.restaurant) for a in out] == [("Ana Reyes", "Ghost Bird")]


def test_duplicates_collapse() -> None:
    row = ("Ana Reyes", "Ghost Bird", "speaker")
    out, *_ = run(event(), facts(row, row))
    assert len(out) == 1


def test_gated_event_and_gated_hosts_are_never_fetched() -> None:
    out, fetch, llm, _fc, _ = run(event(lineup_gated=True), facts())
    assert out == [] and not fetch.called and not llm.called
    gated = event(
        lineup_urls=(
            "https://app.swapcard.com/x",
            "https://whova.com/e",
            "https://www.linkedin.com/events/1",
        )
    )
    out, fetch, llm, *_ = run(gated, facts())
    assert out == [] and not fetch.called and not llm.called


def test_unreadable_page_yields_nothing_without_llm_call() -> None:
    out, _, llm, fc, budget = run(event(), facts(), html=None)
    assert out == [] and not llm.called and not fc.scrape.called and budget.used == 0


def test_thin_js_page_falls_back_to_firecrawl_and_spends_budget() -> None:
    fc = Mock()
    fc.scrape.return_value = {"markdown": "Ana Reyes of Ghost Bird speaks. " + "y " * 200}
    out, _, _llm, fc, budget = run(
        event(),
        facts(("Ana Reyes", "Ghost Bird", "speaker")),
        html="<html><body>app</body></html>",
        fc=fc,
    )
    assert len(out) == 1 and fc.scrape.call_count == 1 and budget.used == 1


def test_firecrawl_budget_hard_stops_fallback() -> None:
    fc = Mock()
    budget = CallBudget("firecrawl", 0)
    with (
        patch.object(extract, "_fetch_page", return_value="<html><body>app</body></html>"),
        patch.object(extract, "structured") as llm,
        pytest.raises(BudgetExceeded),
    ):
        extract_appearances(event(), fc, budget)
    assert not fc.scrape.called and not llm.called


def test_cli_events_extract_fails_fast_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    with pytest.raises(SystemExit, match="FIRECRAWL_API_KEY"):
        cli.events_extract()
    monkeypatch.setenv("FIRECRAWL_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        cli.events_extract()


def test_cli_events_extract_end_to_end_mocked(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from scripts.hospitality.models import EventAppearance
    from scripts.hospitality.store import DocStore

    monkeypatch.setenv("FIRECRAWL_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    reg = tmp_path / "events.yaml"
    reg.write_text(
        "events:\n"
        f"  - {{event_id: e:a, name: A, start: 2027-05-22, end: 2027-05-25, city: Chicago,\n"
        f"     event_type: trade_show, cost_usd: 500, lineup_urls: ['{URL}']}}\n"
        "  - {event_id: e:b, name: B, start: null, end: null, city: New York,\n"
        "     event_type: festival, cost_usd: 0, lineup_urls: ['https://b.example']}\n"
    )
    with (
        patch.object(extract, "_fetch_page", return_value=PAGE),
        patch.object(
            extract, "structured", return_value=facts(("Ana Reyes", "Ghost Bird", "speaker"))
        ),
        patch.object(cli, "FirecrawlClient"),
    ):
        out = cli.events_extract(reg)
    assert out["events"] == 1 and out["appearances"] == 1
    saved = store.load("event_appearances", EventAppearance)
    assert [a.person for a in saved] == ["Ana Reyes"]
