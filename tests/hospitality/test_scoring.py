from datetime import UTC, date, datetime

import pytest

from scripts.hospitality.config import load_config
from scripts.hospitality.labels import cold_prospects
from scripts.hospitality.models import CustomerLabel, Group
from scripts.hospitality.scoring import (
    ScoreInputs,
    contract_operator_reason,
    fit_score,
    noisy_or,
    operator_names,
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


# --- Task 14b: per-venue dedupe, venue cap, contract-operator disqualification ---


def _multi_inputs(cfg, signals, n_venues: int = 1, **overrides) -> ScoreInputs:
    venues = tuple(make_venue(f"v:{i}", group_id="g:1") for i in range(1, n_venues + 1))
    group = Group(
        group_id="g:1",
        name="Acme",
        venue_ids=tuple(v.venue_id for v in venues),
        resolution="manual",
    )
    return make_score_inputs(cfg, signals, group=group, venues=venues, **overrides)


def test_opening_family_counts_once_per_venue(cfg) -> None:
    sigs = [
        make_signal("license_pending", "v:1"),
        make_signal("license_issued", "v:1"),
        make_signal("not_yet_inspected", "v:1"),
    ]
    scored = score_group(**_multi_inputs(cfg, sigs).kwargs())
    assert scored.p_window == pytest.approx(0.30)  # strongest single contribution only
    by_type = {c.signal_type: c for c in scored.contributions}
    assert len(scored.contributions) == 3  # trace stays complete
    assert by_type["not_yet_inspected"].contribution == 0.0
    assert "folded" in by_type["not_yet_inspected"].note
    assert by_type["license_pending"].contribution == pytest.approx(0.30) or (
        by_type["license_issued"].contribution == pytest.approx(0.30)
    )
    assert by_type["not_yet_inspected"].weight == pytest.approx(1.0)  # raw weight kept


def test_strongest_opening_signal_wins_within_venue(cfg) -> None:
    sigs = [make_signal("not_yet_inspected", "v:1"), make_signal("license_issued", "v:1")]
    scored = score_group(**_multi_inputs(cfg, sigs).kwargs())
    by_type = {c.signal_type: c for c in scored.contributions}
    assert by_type["license_issued"].contribution == pytest.approx(0.30)
    assert by_type["not_yet_inspected"].contribution == 0.0


def test_other_signal_types_on_same_venue_still_combine(cfg) -> None:
    sigs = [
        make_signal("license_issued", "v:1"),
        make_signal("not_yet_inspected", "v:1"),
        make_signal("private_events", "v:1"),
        make_signal("press_opening", "v:1"),
    ]
    scored = score_group(**_multi_inputs(cfg, sigs).kwargs())
    assert scored.p_window == pytest.approx(1 - 0.7 * 0.85 * 0.65)


def test_venue_cap_limits_opening_terms_strongest_first(cfg) -> None:
    sigs = [make_signal("license_issued", f"v:{i}") for i in range(1, 9)]
    scored = score_group(**_multi_inputs(cfg, sigs, n_venues=8).kwargs())
    assert cfg.max_opening_venues_per_group == 3
    assert scored.p_window == pytest.approx(1 - 0.7**3)
    assert sum(c.contribution > 0 for c in scored.contributions) == 3
    assert len(scored.contributions) == 8
    capped = [c for c in scored.contributions if c.contribution == 0.0]
    assert all("cap" in c.note for c in capped)


def test_two_or_three_openings_beat_one_but_dozens_do_not_saturate(cfg) -> None:
    def p(n: int) -> float:
        sigs = [make_signal("license_issued", f"v:{i}") for i in range(1, n + 1)]
        return score_group(**_multi_inputs(cfg, sigs, n_venues=n).kwargs()).p_window

    assert p(1) < p(2) < p(3)
    assert p(30) == pytest.approx(p(3))


def test_venue_cap_keeps_strongest_venues(cfg) -> None:
    est = {
        f"v:{i}": make_estimate(f"v:{i}", estimated_open=date(2030, 1, 1)) for i in range(1, 3)
    }  # far outside the window -> weak
    sigs = [make_signal("license_issued", f"v:{i}") for i in range(1, 6)]
    scored = score_group(**_multi_inputs(cfg, sigs, n_venues=5, estimates=est).kwargs())
    kept = {c.signal_id for c in scored.contributions if c.contribution > 0}
    assert kept == {"license_issued:v:3", "license_issued:v:4", "license_issued:v:5"}


@pytest.mark.parametrize(
    "name",
    [
        "Aramark Services Inc",
        "OTG JFK T5 Venture II, LLC",
        "OTG Management LLC",
        "SSP America, Inc.",
        "HMSHost JFK T5 Partners, LLC",
        "HOST INTERNATIONAL INC",
        "Compass Group USA, Inc.",
        "Sodexo Operations, LLC",
        "Delaware North Companies",
        "Levy Premium Foodservice",
        "Restaurant Associates",
    ],
)
def test_contract_operator_names_disqualified(cfg, name: str) -> None:
    assert contract_operator_reason([name], cfg) == "contract_foodservice"


@pytest.mark.parametrize(
    "name",
    [
        "Compass Rose Bistro LLC",
        "Levy's Deli Corp",
        "Levine Hospitality Group",
        "The Compass Kitchen",
        "Sushi Noz LLC",
        "Host Table LLC",
        "Ssp Pizza Inc",
        "Aramis Restaurant Corp",
        "Delaware Diner LLC",
    ],
)
def test_ordinary_restaurants_not_disqualified(cfg, name: str) -> None:
    assert contract_operator_reason([name], cfg) is None


def test_contract_operator_matches_any_of_the_names(cfg) -> None:
    assert contract_operator_reason(["Nice Place LLC", "x", "SODEXO INC"], cfg) is not None
    assert contract_operator_reason([], cfg) is None


def test_operator_names_include_licensee_legal_and_dba(cfg) -> None:
    from tests.hospitality.factories import make_license

    lic = make_license("sla:1", legal_name="OTG JFK T5 Venture II, LLC", dba="Nom Wah")
    venue = make_venue("v:1", name="Nom Wah", license_ids=("sla:1",))
    group = Group(group_id="g:1", name="Nom Wah Co", venue_ids=("v:1",), resolution="singleton")
    names = operator_names(group, [venue], {"sla:1": lic})
    assert "OTG JFK T5 Venture II, LLC" in names
    assert contract_operator_reason(names, cfg) == "contract_foodservice"
