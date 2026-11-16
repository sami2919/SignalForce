import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from scripts.hospitality import cli
from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.stack.crawl import crawl_stacks
from scripts.hospitality.store import DocStore
from scripts.watch.fetcher import ProbeResult
from tests.hospitality.factories import make_venue

NOW = datetime(2026, 11, 16, tzinfo=UTC)
RESY = '<a href="https://resy.com/x">'
EMPTY = "<div id=app></div>"


def ok(i: int, body: str) -> ProbeResult:
    return ProbeResult(source_id=i, status_code=200, body=body)


def two_venues():
    return [make_venue("v:1", website="https://a.com"), make_venue("v:2", website="https://b.com")]


async def run(venues, results, fc, budget):
    with patch("scripts.hospitality.stack.crawl.fetch_all", AsyncMock(return_value=results)):
        return await crawl_stacks(venues, NOW, firecrawl=fc, firecrawl_budget=budget)


@pytest.mark.asyncio
async def test_firecrawl_only_when_no_reservation() -> None:
    fc = Mock()
    fc.scrape.return_value = {"data": {"html": '<a href="https://exploretock.com/b">'}}
    obs = await run(two_venues(), [ok(0, RESY), ok(1, EMPTY)], fc, CallBudget("fc", 5))
    assert fc.scrape.call_count == 1
    by_id = {o.venue_id: o for o in obs}
    assert by_id["v:2"].platforms == ("tock",) and by_id["v:2"].fetched_via == "firecrawl"
    assert by_id["v:1"].platforms == ("resy",) and by_id["v:1"].fetched_via == "fetcher"


@pytest.mark.asyncio
async def test_firecrawl_reads_raw_html_key() -> None:
    fc = Mock()
    fc.scrape.return_value = {"data": {"rawHtml": RESY}}
    obs = await run(two_venues()[1:], [ok(0, EMPTY)], fc, CallBudget("fc", 5))
    assert obs[0].platforms == ("resy",)


@pytest.mark.asyncio
async def test_budget_hard_stops_before_the_call() -> None:
    fc = Mock()
    fc.scrape.return_value = {"data": {"html": RESY}}
    budget = CallBudget("fc", 1)
    obs = await run(two_venues(), [ok(0, EMPTY), ok(1, EMPTY)], fc, budget)
    assert fc.scrape.call_count == 1  # the second call never went out
    assert budget.used == 1
    assert {o.venue_id: o.platforms for o in obs} == {"v:1": ("resy",), "v:2": ()}
    with pytest.raises(BudgetExceeded):
        budget.spend()


@pytest.mark.asyncio
async def test_failed_fetch_yields_no_observation_and_no_firecrawl() -> None:
    fc = Mock()
    results = [
        ProbeResult(source_id=0, error="boom"),
        ProbeResult(source_id=1, robots_blocked=True),
    ]
    obs = await run(two_venues(), results, fc, CallBudget("fc", 5))
    assert obs == [] and fc.scrape.call_count == 0


@pytest.mark.asyncio
async def test_firecrawl_error_keeps_fetcher_observation() -> None:
    fc = Mock()
    fc.scrape.side_effect = RuntimeError("down")
    obs = await run(two_venues()[1:], [ok(0, EMPTY)], fc, CallBudget("fc", 5))
    assert [(o.venue_id, o.platforms, o.fetched_via) for o in obs] == [("v:2", (), "fetcher")]


@pytest.mark.asyncio
async def test_no_firecrawl_client_and_skips_sites_without_website_or_loyalist_for() -> None:
    venues = [
        make_venue("v:1", website="https://a.com"),
        make_venue("v:2"),
        make_venue("v:3", website="https://www.loyalist.com/for/acme"),
    ]
    fetch = AsyncMock(return_value=[ok(0, RESY)])
    with patch("scripts.hospitality.stack.crawl.fetch_all", fetch):
        obs = await crawl_stacks(venues, NOW, firecrawl=None, firecrawl_budget=CallBudget("fc", 1))
    assert [r.url for r in fetch.call_args.args[0]] == ["https://a.com"]
    assert [o.venue_id for o in obs] == ["v:1"]


def test_crawl_command_fails_fast_without_key(monkeypatch) -> None:
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(["crawl"])
    assert "FIRECRAWL_API_KEY" in str(exc.value)


def test_crawl_command_saves_observations_and_signals(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    store.save(
        "venues",
        [make_venue("v:1", website="https://a.com", group_id="g:1")],
        key=lambda v: v.venue_id,  # type: ignore[attr-defined]
    )
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    body = '<a href="https://resy.com/x"></a><a href="https://tripleseat.com/y"></a>'
    with patch("scripts.hospitality.stack.crawl.fetch_all", AsyncMock(return_value=[ok(0, body)])):
        out = cli.crawl(NOW)
        cli.crawl(NOW)  # rerun: observations append, signals stay idempotent
    assert out["observations"] == 1 and out["platforms"] == {"resy": 1, "tripleseat": 1}
    from scripts.hospitality.models import Signal, StackObservation

    assert len(store.load("stack_observations", StackObservation)) == 1  # same timestamp key
    types = {s.signal_type for s in store.load("signals", Signal)}
    assert types == {"tripleseat_resy", "private_events"}
    json.dumps(out)
