import json
import math
from datetime import date

import pytest
from pydantic import ValidationError

from scripts.hospitality.measure.backtest import auc, case_replay, fit_auc
from scripts.hospitality.models import CaseReplay, CustomerLabel
from tests.hospitality.factories import make_scored, make_signal, make_venue


def _label(name: str = "The Noortwyck", when: date | None = date(2026, 5, 1)) -> CustomerLabel:
    return CustomerLabel(
        name=name,
        website_domain=None,
        first_public_date=when,
        source="public_list",
        evidence_ref="x",
    )


def test_auc_hand_computed():
    assert auc([0.9, 0.4], [0.5, 0.1]) == pytest.approx(0.75)
    assert auc([0.5], [0.5]) == pytest.approx(0.5)


def test_auc_empty_side_is_nan():
    assert math.isnan(auc([], [0.1]))
    assert math.isnan(auc([0.1], []))


def test_case_replay_lead_days():
    labels = {"g:1": _label()}
    venues = [make_venue("v:o", name="Oriana", group_id="g:1")]
    sigs = [make_signal("license_issued", "v:o", observed=date(2026, 2, 1))]
    [r] = case_replay(labels, venues, sigs, {"g:1": "Oriana"})
    assert r.lead_days == 89 and r.signal_types == ("license_issued",)
    assert r.new_venue_id == "v:o" and r.first_signal_date == date(2026, 2, 1)


def test_case_replay_no_signal_and_no_venue():
    labels = {"g:1": _label(), "g:2": _label("Momofuku")}
    venues = [make_venue("v:o", name="Oriana", group_id="g:1")]
    out = {r.group_id: r for r in case_replay(labels, venues, [], {"g:1": "Oriana", "g:2": "Zzz"})}
    assert out["g:1"].new_venue_id == "v:o" and out["g:1"].lead_days is None
    assert out["g:2"].new_venue_id is None and out["g:2"].signal_types == ()


def test_case_replay_ignores_non_opening_and_post_anchor_signals():
    labels = {"g:1": _label()}
    venues = [make_venue("v:o", name="Oriana", group_id="g:1")]
    sigs = [
        make_signal("stack_fragmented", "v:o", observed=date(2026, 1, 1)),
        make_signal("license_issued", "v:o", observed=date(2026, 6, 1)),  # after the anchor
    ]
    [r] = case_replay(labels, venues, sigs, {"g:1": "Oriana"})
    assert r.lead_days is None and r.signal_types == ()


def test_case_replay_skips_undated_labels():
    labels = {"g:1": _label(when=None)}
    venues = [make_venue("v:o", name="Oriana", group_id="g:1")]
    assert case_replay(labels, venues, [], {"g:1": "Oriana"}) == []


def test_case_replay_finds_venue_in_universe_outside_group():
    labels = {"g:1": _label()}
    venues = [
        make_venue("v:a", name="Other Place", group_id="g:1"),
        make_venue("v:o", name="Oriana", group_id="g:9"),
    ]
    [r] = case_replay(labels, venues, [], {"g:1": "Oriana"})
    assert r.new_venue_id == "v:o"


def test_case_replay_model_frozen():
    r = CaseReplay(
        group_id="g:1",
        customer="c",
        anchor_date=date(2026, 1, 1),
        new_venue_id=None,
        first_signal_date=None,
        lead_days=None,
        signal_types=(),
    )
    with pytest.raises(ValidationError):
        r.lead_days = 3  # type: ignore[misc]


def test_fit_auc_customers_vs_rest():
    accounts = [
        make_scored("g:1", fit=0.9, is_customer=True),
        make_scored("g:2", fit=0.2, is_customer=True),
        make_scored("g:3", fit=0.5),
        make_scored("g:4", fit=0.1),
    ]
    assert fit_auc(accounts) == pytest.approx(0.75)


def test_fit_auc_constant_fit_is_chance():
    accounts = [make_scored("g:1", is_customer=True), make_scored("g:2")]
    assert fit_auc(accounts) == pytest.approx(0.5)


def test_backtest_command_prints_indicative_with_n(tmp_path, monkeypatch, capsys):
    from scripts.hospitality import cli

    monkeypatch.setattr(
        cli,
        "backtest",
        lambda: {
            "cases": [
                CaseReplay(
                    group_id="g:1",
                    customer="Dinex Group",
                    anchor_date=date(2025, 10, 20),
                    new_venue_id="v:1",
                    first_signal_date=date(2025, 1, 1),
                    lead_days=292,
                    signal_types=("license_issued",),
                )
            ],
            "undated": 3,
            "fit_auc": 0.5,
            "fit_distinct": 1,
            "n_customers": 2,
            "n_others": 100,
        },
    )
    assert cli.main(["backtest"]) == 0
    text = capsys.readouterr().out
    assert "indicative" in text.lower() and "n=2" in text and "n=100" in text
    assert "degenerate" in text.lower()
    json.dumps(text)


def test_run_p0_chains_steps_in_order(monkeypatch):
    from scripts.hospitality import cli

    calls: list[str] = []
    real_main = cli.main

    def fake(argv=None):
        if argv == ["run-p0"]:
            return real_main(argv)
        calls.append(argv[0])
        return 0

    monkeypatch.setattr(cli, "main", fake)
    assert cli.main(["run-p0"]) == 0
    assert calls == [
        "ingest-sla", "snapshot-pending", "ingest-dohmh", "resolve", "window",
        "websites", "crawl", "labels", "score", "recall", "backtest",
    ]  # fmt: skip
