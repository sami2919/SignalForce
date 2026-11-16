from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from scripts.hospitality import cli, llm
from scripts.hospitality.benchmark.baseline import (
    BASELINE_PROMPT,
    BaselineList,
    match_items,
    run_baseline,
)
from scripts.hospitality.benchmark.compare import compare
from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.models import BaselineItem, BaselineRun, BenchmarkResult
from tests.hospitality.factories import make_scored, make_venue


@pytest.fixture(autouse=True)
def _fresh_budget() -> None:
    llm.reset_budget()


def item(name: str, location: str = "", group: str | None = None) -> BaselineItem:
    return BaselineItem(name=name, location=location, group=group, expected_opening=None)


def run_of(*items: BaselineItem, index: int = 0) -> BaselineRun:
    return BaselineRun(run_index=index, items=items, searches_used=5)


def _response(text: str = "Oriana opens soon", stop: str = "end_turn", searches: int = 2):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop,
        usage=SimpleNamespace(server_tool_use=SimpleNamespace(web_search_requests=searches)),
    )


def fake_client(responses: list | None = None, items: tuple[BaselineItem, ...] = ()) -> MagicMock:
    client = MagicMock()
    client.messages.create.side_effect = responses or [_response()]
    parsed = client.beta.messages.parse.return_value
    parsed.parsed_output = BaselineList(items=items or (item("Oriana"),))
    parsed.stop_reason = "end_turn"
    return client


# --- compare -------------------------------------------------------------------------------


def test_compare_counts_hits_dupes_and_unmatched() -> None:
    truth = [make_venue("v:1", name="Oriana"), make_venue("v:2", name="Massara")]
    universe = truth + [make_venue("v:3", name="Other")]
    runs = [
        BaselineRun(
            run_index=0,
            searches_used=5,
            items=(item("Oriana"), item("Oriana NYC"), item("Made Up Place")),
        )
    ]
    sf_top = [make_scored("g:v:1"), make_scored("g:v:2")]
    r = compare(sf_top, {"g:v:1": ("v:1",), "g:v:2": ("v:2",)}, runs, truth, universe, k=50)
    assert r.sf_hits == 2 and r.claude_hits == (1,)
    assert r.claude_duplicates == (1,) and r.claude_unmatched == (1,)
    assert r.truth_total == 2
    assert r.claude_precision_at_k == (pytest.approx(1 / 3),)
    assert r.sf_precision_at_k == pytest.approx(1.0)


def test_compare_always_notes_hindsight_leak() -> None:
    r = compare([], {}, [], [], [], k=5)
    assert any("Hindsight leak favors the Claude baseline" in n for n in r.notes)
    assert any("a SignalForce win is conservative" in n for n in r.notes)


def test_hallucinated_venue_is_unmatched_deterministically() -> None:
    """A venue named by the LLM that is not in the universe is counted as a non-venue."""
    truth = [make_venue("v:1", name="Oriana")]
    runs = [run_of(item("Zzyzx Quantum Bistro"))]
    r = compare([], {}, runs, truth, truth, k=10)
    assert r.claude_unmatched == (1,) and r.claude_hits == (0,)


def test_existing_non_opening_venue_is_neither_hit_nor_unmatched() -> None:
    truth = [make_venue("v:1", name="Oriana")]
    universe = [*truth, make_venue("v:9", name="Old Standby")]
    r = compare([], {}, [run_of(item("Old Standby"))], truth, universe, k=10)
    assert r.claude_hits == (0,) and r.claude_unmatched == (0,) and r.claude_duplicates == (0,)


def test_compare_run_jaccard_measures_variance() -> None:
    truth = [make_venue("v:1", name="Oriana"), make_venue("v:2", name="Massara")]
    same = compare([], {}, [run_of(item("Oriana")), run_of(item("Oriana"), index=1)], truth, truth)
    diff = compare([], {}, [run_of(item("Oriana")), run_of(item("Massara"), index=1)], truth, truth)
    assert same.claude_run_jaccard == 1.0
    assert diff.claude_run_jaccard == 0.0


def test_sf_precision_uses_top_k_only() -> None:
    truth = [make_venue("v:1", name="Oriana")]
    sf_top = [make_scored("g:a"), make_scored("g:b"), make_scored("g:c")]
    by_group = {"g:a": ("v:x",), "g:b": ("v:1",), "g:c": ("v:1",)}
    r = compare(sf_top, by_group, [], truth, truth, k=2)
    assert r.sf_hits == 1 and r.sf_precision_at_k == pytest.approx(0.5)


# --- match_items ---------------------------------------------------------------------------


def test_match_items_requires_name_similarity() -> None:
    universe = [make_venue("v:1", name="Oriana")]
    out = match_items([item("Oriana"), item("Random Cafe")], universe)
    assert out == {0: "v:1", 1: None}


def test_match_items_location_zip_must_agree() -> None:
    universe = [make_venue("v:1", name="Oriana", zip_code="10001")]
    assert match_items([item("Oriana", "12 W 20th St, 10001")], universe) == {0: "v:1"}
    assert match_items([item("Oriana", "5 Main St, 11201")], universe) == {0: None}


def test_match_items_location_borough_must_agree() -> None:
    universe = [make_venue("v:1", name="Oriana", zip_code="11201")]
    assert match_items([item("Oriana", "Brooklyn")], universe) == {0: "v:1"}
    assert match_items([item("Oriana", "Manhattan")], universe) == {0: None}


# --- run_baseline --------------------------------------------------------------------------


def test_run_baseline_uses_current_web_search_tool() -> None:
    client = fake_client()
    runs = run_baseline(client, date(2026, 9, 21), runs=1)
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tools"][0]["type"] == "web_search_20260209"
    assert kwargs["tools"][0]["name"] == "web_search"
    assert kwargs["tools"][0]["max_uses"] == 20
    assert "Today is 2026-09-21." in kwargs["messages"][0]["content"]
    assert len(runs) == 1 and runs[0].items == (item("Oriana"),) and runs[0].searches_used == 2


def test_baseline_prompt_exact_text() -> None:
    assert BASELINE_PROMPT.startswith("Today is {cutoff}. List as many New York City")
    assert BASELINE_PROMPT.endswith("expected opening timing. Use web search.")


def test_run_baseline_continues_on_pause_turn_and_caps_searches() -> None:
    client = fake_client([_response("a", "pause_turn", 3), _response("b", "end_turn", 4)])
    runs = run_baseline(client, date(2026, 9, 21), runs=1, max_searches=5)
    assert client.messages.create.call_count == 2
    second = client.messages.create.call_args.kwargs
    assert second["tools"][0]["max_uses"] == 2  # 5 - 3 already used
    assert second["messages"][-1]["role"] == "assistant"
    assert runs[0].searches_used == 7
    structured_user = client.beta.messages.parse.call_args.kwargs["messages"][0]["content"]
    assert "a" in structured_user and "b" in structured_user


def test_run_baseline_stops_when_search_budget_spent() -> None:
    client = fake_client([_response("a", "pause_turn", 5), _response("b", "pause_turn", 5)])
    run_baseline(client, date(2026, 9, 21), runs=1, max_searches=5)
    assert client.messages.create.call_count == 1  # no continuation with zero searches left


def test_run_baseline_hard_stops_on_claude_call_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "_CALL_BUDGET", CallBudget("claude_calls", 3))
    client = fake_client([_response() for _ in range(3)])
    with pytest.raises(BudgetExceeded):
        run_baseline(client, date(2026, 9, 21), runs=3)
    assert client.messages.create.call_count + client.beta.messages.parse.call_count == 3


# --- CLI -----------------------------------------------------------------------------------


def test_benchmark_command_fails_fast_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(["benchmark", "--cutoff-weeks", "8", "--yes"])
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_benchmark_command_requires_yes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    ran = MagicMock()
    monkeypatch.setattr(cli, "benchmark", ran)
    with pytest.raises(SystemExit) as exc:
        cli.main(["benchmark", "--cutoff-weeks", "8"])
    assert "--yes" in str(exc.value)
    ran.assert_not_called()
    assert "maximum" in capsys.readouterr().out.lower()


def test_benchmark_result_is_frozen() -> None:
    r = BenchmarkResult(
        k=1,
        sf_hits=0,
        sf_precision_at_k=0.0,
        claude_hits=(),
        claude_precision_at_k=(),
        claude_duplicates=(),
        claude_unmatched=(),
        claude_run_jaccard=1.0,
        truth_total=0,
        notes=(),
    )
    with pytest.raises(ValidationError):
        r.k = 2  # type: ignore[misc]


def test_benchmark_replays_as_of_cutoff_without_touching_live_scores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from scripts.hospitality.models import Group, ScoredAccount
    from scripts.hospitality.store import DocStore
    from tests.hospitality.factories import make_license

    store = DocStore(f"sqlite:///{tmp_path}/b.db")
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    monkeypatch.setattr(cli, "Anthropic", MagicMock)
    today = date(2026, 11, 16)
    lic = make_license("sla:1", received_date=date(2026, 8, 1))
    venue = make_venue(
        "v:1",
        name="Zephyr Hall",
        license_ids=("sla:1",),
        group_id="g:v:1",
        license_description="Restaurant",
        first_inspection_date=date(2026, 10, 20),  # after the 8-week cutoff (2026-09-21)
    )
    group = Group(
        group_id="g:v:1",
        name="Zephyr Hall",
        venue_ids=("v:1",),
        resolution="singleton",
        evidence_ref="",
    )
    store.save("venues", [venue], key=lambda v: v.venue_id)
    store.save("groups", [group], key=lambda g: g.group_id)
    store.save("licenses", [lic], key=lambda r: r.record_id)
    captured: dict[str, object] = {}

    def fake_runs(client: object, cutoff: date, runs: int, max_searches: int) -> list[BaselineRun]:
        captured["cutoff"] = cutoff
        return [run_of(item("Zephyr Hall"))]

    monkeypatch.setattr(cli, "run_baseline", fake_runs)
    result = cli.benchmark(8, today=today)
    assert captured["cutoff"] == date(2026, 9, 21)
    assert result.truth_total == 1 and result.claude_hits == (1,)
    assert result.sf_hits == 1  # pending license predates the cutoff; inspection must not leak
    assert store.load("scores", ScoredAccount) == []  # live scores untouched


def test_benchmark_replay_counts_inactive_license_issued_before_cutoff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from scripts.hospitality.models import Group
    from scripts.hospitality.store import DocStore
    from tests.hospitality.factories import make_license

    store = DocStore(f"sqlite:///{tmp_path}/b.db")
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    monkeypatch.setattr(cli, "Anthropic", MagicMock)
    lic = make_license(
        "i1", source="sla_inactive", received_date=None, original_issue_date=date(2026, 8, 1)
    )
    venue = make_venue(
        "v:1",
        name="Zephyr Hall",
        license_ids=("i1",),
        group_id="g:v:1",
        camis="9",
        license_description="Restaurant",
        first_inspection_date=date(2026, 10, 20),
    )
    group = Group(
        group_id="g:v:1",
        name="Zephyr Hall",
        venue_ids=("v:1",),
        resolution="singleton",
        evidence_ref="",
    )
    store.save("venues", [venue], key=lambda v: v.venue_id)
    store.save("groups", [group], key=lambda g: g.group_id)
    store.save("licenses", [lic], key=lambda r: r.record_id)
    monkeypatch.setattr(cli, "run_baseline", lambda *a, **k: [run_of(item("Zephyr Hall"))])
    result = cli.benchmark(8, today=date(2026, 11, 16))
    assert result.truth_total == 1 and result.sf_hits == 1
