from datetime import UTC, date, datetime

import pytest

from scripts.hospitality.config import load_config
from scripts.hospitality.labels import cold_prospects
from scripts.hospitality.models import CustomerLabel, Group
from scripts.hospitality.scoring import (
    ScoreInputs,
    fit_score,
    noisy_or,
    rank_prospects,
    score_group,
    window_weight,
    zero_out,
)
from tests.hospitality.factories import (
    make_estimate,
    make_observation,
    make_scored,
    make_signal,
    make_venue,
)

NOW = datetime(2026, 11, 16, tzinfo=UTC)


@pytest.fixture
def cfg():
    return load_config()


def make_score_inputs(cfg, signals, **overrides) -> ScoreInputs:
    venue = make_venue("v:1", group_id="g:1")
    base = {
        "group": Group(group_id="g:1", name="Acme", venue_ids=("v:1",), resolution="singleton"),
        "signals": tuple(signals),
        "estimates": {},
        "venues": (venue,),
        "observations": (),
        "cfg": cfg,
        "now": NOW,
        "is_customer": False,
        "disqualified_reason": None,
    }
    base.update(overrides)
    return ScoreInputs(**base)


def test_noisy_or() -> None:
    assert noisy_or([0.5, 0.5]) == pytest.approx(0.75)
    assert noisy_or([]) == 0.0


def test_window_weight_inside_is_one(cfg) -> None:
    est = make_estimate("v:1", estimated_open=date(2027, 2, 1))
    sig = make_signal("license_pending", "v:1")
    assert window_weight(sig, cfg.priors["license_pending"], est, NOW, cfg) == 1.0


def test_window_weight_decays_outside(cfg) -> None:
    est = make_estimate("v:1", estimated_open=date(2027, 11, 16))  # 365d ahead -> 182d outside
    w = window_weight(
        make_signal("license_pending", "v:1"), cfg.priors["license_pending"], est, NOW, cfg
    )
    assert w == pytest.approx(0.5 ** (182 / 60), rel=1e-3)


def test_window_weight_decays_after_post_window(cfg) -> None:
    est = make_estimate("v:1", estimated_open=date(2025, 11, 16))  # 365d ago -> inside (post=365)
    sig = make_signal("license_pending", "v:1")
    assert window_weight(sig, cfg.priors["license_pending"], est, NOW, cfg) == 1.0
    est2 = make_estimate("v:1", estimated_open=date(2025, 5, 18))  # 547d ago -> 182 outside
    w = window_weight(sig, cfg.priors["license_pending"], est2, NOW, cfg)
    assert w == pytest.approx(0.5 ** (182 / 60), rel=1e-3)


def test_window_weight_state_signal_without_half_life_is_one(cfg) -> None:
    sig = make_signal("stack_fragmented", "g:1", observed_at=datetime(2020, 1, 1, tzinfo=UTC))
    assert window_weight(sig, cfg.priors["stack_fragmented"], None, NOW, cfg) == 1.0


def test_window_weight_half_life_decay(cfg) -> None:
    sig = make_signal("private_events", "v:1", observed_at=datetime(2026, 7, 18, tzinfo=UTC))
    # 121 days old, half-life 120
    w = window_weight(sig, cfg.priors["private_events"], None, NOW, cfg)
    assert w == pytest.approx(0.5 ** (121 / 120), rel=1e-3)


def test_opening_signal_without_estimate_is_one(cfg) -> None:
    sig = make_signal("license_pending", "v:1")
    assert window_weight(sig, cfg.priors["license_pending"], None, NOW, cfg) == 1.0


def test_customer_excluded_from_prospects() -> None:
    a = make_scored("g:1", priority=0.9, is_customer=True)
    b = make_scored("g:2", priority=0.1)
    assert [x.group_id for x in rank_prospects([a, b])] == ["g:2"]


def test_rank_prospects_excludes_disqualified_and_orders_ties_by_group_id() -> None:
    accounts = [
        make_scored("g:3", priority=0.5),
        make_scored("g:1", priority=0.5),
        make_scored("g:2", priority=0.7),
        make_scored("g:9", priority=0.0, disqualified_reason="qsr_loyalty:punchh"),
    ]
    assert [a.group_id for a in rank_prospects(accounts)] == ["g:2", "g:1", "g:3"]


def test_customer_group_flagged_and_never_a_cold_target(cfg) -> None:
    inputs = make_score_inputs(cfg, [make_signal("license_pending", "v:1")], is_customer=True)
    scored = score_group(**inputs.kwargs())
    assert scored.is_customer is True
    customers = {
        "g:1": CustomerLabel(
            name="Acme",
            website_domain=None,
            first_public_date=None,
            source="public_list",
            evidence_ref="x",
        )
    }
    assert cold_prospects(["g:1", "g:2"], customers) == ["g:2"]
    assert rank_prospects([scored]) == []


def test_disqualified_priority_zero_reason_kept(cfg) -> None:
    inputs = make_score_inputs(
        cfg, [make_signal("license_pending", "v:1")], disqualified_reason="qsr_loyalty:punchh"
    )
    scored = score_group(**inputs.kwargs())
    assert scored.priority == 0.0
    assert scored.disqualified_reason == "qsr_loyalty:punchh"
    assert scored.p_window > 0
    assert rank_prospects([scored]) == []


def test_score_group_math_and_trace(cfg) -> None:
    sigs = [make_signal("license_pending", "v:1"), make_signal("stack_fragmented", "g:1")]
    scored = score_group(**make_score_inputs(cfg, sigs).kwargs())
    assert scored.p_window == pytest.approx(1 - 0.7 * 0.75)
    # fit: single venue, no obs, no accolade, no license description -> 0
    assert scored.fit == 0.0
    assert scored.priority == pytest.approx(scored.p_window * 0.5)
    assert {c.signal_type: c.contribution for c in scored.contributions} == {
        "license_pending": pytest.approx(0.30),
        "stack_fragmented": pytest.approx(0.25),
    }


def test_signals_of_other_groups_ignored_and_venue_signals_attributed(cfg) -> None:
    sigs = [make_signal("license_pending", "v:1"), make_signal("license_pending", "v:99")]
    scored = score_group(**make_score_inputs(cfg, sigs).kwargs())
    assert len(scored.contributions) == 1


def test_estimate_of_venue_drives_weight(cfg) -> None:
    est = {"v:1": make_estimate("v:1", estimated_open=date(2027, 11, 16))}
    inputs = make_score_inputs(cfg, [make_signal("license_pending", "v:1")], estimates=est)
    scored = score_group(**inputs.kwargs())
    assert scored.contributions[0].weight == pytest.approx(0.5 ** (182 / 60), rel=1e-3)


def test_alumni_edge_boosts_relationship_but_not_p_window(cfg) -> None:
    sigs = [make_signal("license_pending", "v:1"), make_signal("alumni_edge", "g:1")]
    scored = score_group(**make_score_inputs(cfg, sigs).kwargs())
    assert scored.relationship == pytest.approx(1.5)
    assert scored.p_window == pytest.approx(0.30)
    assert scored.priority == pytest.approx(0.30 * 0.5 * 1.5)


def test_fit_score_components(cfg) -> None:
    group = Group(group_id="g:1", name="Acme", venue_ids=("v:1", "v:2"), resolution="manual")
    venues = [
        make_venue("v:1", group_id="g:1", license_description="Restaurant"),
        make_venue("v:2", group_id="g:1"),
    ]
    assert fit_score(group, venues, [], cfg) == pytest.approx(0.30 + 0.10)
    obs = [make_observation("v:2", ("resy", "tripleseat"))]
    assert fit_score(group, venues, obs, cfg) == pytest.approx(0.30 + 0.10 + 0.30 + 0.15)


def test_fit_score_uses_latest_observation_and_accolades(cfg) -> None:
    cfg2 = cfg.model_copy(update={"accolades": ("g:1",)})
    group = Group(group_id="g:1", name="Acme", venue_ids=("v:1",), resolution="singleton")
    venues = [make_venue("v:1", group_id="g:1")]
    old = make_observation("v:1", ("resy",), observed_at=datetime(2026, 1, 1, tzinfo=UTC))
    new = make_observation("v:1", (), observed_at=datetime(2026, 6, 1, tzinfo=UTC))
    assert fit_score(group, venues, [old, new], cfg2) == pytest.approx(0.15)


def test_zero_out_removes_contribution(cfg) -> None:
    inputs = make_score_inputs(
        cfg, [make_signal("license_pending", "v:1"), make_signal("private_events", "v:1")]
    )
    full = score_group(**inputs.kwargs())
    without = zero_out(inputs, "license_pending")
    assert without.p_window < full.p_window
    assert [c.signal_type for c in without.contributions] == ["private_events"]
