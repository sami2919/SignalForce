from datetime import date, timedelta

import pytest

from scripts.hospitality.config import load_config
from scripts.hospitality.window.estimate import estimate_window
from scripts.hospitality.window.survival import kaplan_meier
from tests.hospitality.factories import make_license, make_venue

TODAY = date(2026, 11, 16)


@pytest.fixture
def cfg():
    return load_config()


def test_pending_estimate_records_prior_in_basis(cfg):
    curves = {"all": kaplan_meier([60] * 40, [True] * 40)}
    v = make_venue("v:lic:p", first_inspection_date=None)
    lic = make_license("p", source="sla_pending", received_date=date(2026, 11, 1))
    est = estimate_window(v, lic, curves, cfg, today=TODAY)
    assert est.estimated_open == date(2026, 11, 1) + timedelta(days=75 + 60)
    assert "prior:pending_to_issue=75d" in est.basis


def test_issued_estimate_uses_issue_plus_median(cfg):
    curves = {"all": kaplan_meier([60] * 40, [True] * 40)}
    v = make_venue("v:1")
    lic = make_license("a", source="sla_active", original_issue_date=date(2026, 11, 1))
    est = estimate_window(v, lic, curves, cfg, today=TODAY)
    assert est.estimated_open == date(2026, 12, 31)
    # age 15, everyone opens at day 60 -> certain within 90d
    assert est.p_open_90d == 1.0
    assert est.p_open_180d == 1.0


def test_overdue_issued_uses_conditional_remaining(cfg):
    durations = [30.0] * 10 + [100.0] * 10 + [200.0] * 5 + [250.0] * 5
    curves = {"all": kaplan_meier(durations, [True] * 30)}
    v = make_venue("v:1", camis="1")  # DOHMH record awaiting inspection: past the unmatched cap
    lic = make_license("a", source="sla_active", original_issue_date=TODAY - timedelta(days=120))
    est = estimate_window(v, lic, curves, cfg, today=TODAY)
    # median 100 is already past; S(120)=1/3, remaining median: S(t)<=1/6 first at t=200 -> +80d
    assert est.estimated_open == TODAY + timedelta(days=80)
    # P(open by 210 | alive at 120) = 1 - S(210)/S(120) = 1 - (1/6)/(1/3)
    assert est.p_open_90d == pytest.approx(0.5)
    # by 300: S=0 -> certain
    assert est.p_open_180d == pytest.approx(1.0)


def test_stratum_curve_preferred_then_all_fallback(cfg):
    curves = {
        "all": kaplan_meier([60] * 40, [True] * 40),
        "Restaurant|New York": kaplan_meier([20] * 40, [True] * 40),
    }
    lic = make_license("a", source="sla_active", original_issue_date=date(2026, 11, 10))
    est = estimate_window(make_venue("v:1"), lic, curves, cfg, today=TODAY)
    assert est.estimated_open == date(2026, 11, 30)
    other = make_license(
        "b", source="sla_active", original_issue_date=date(2026, 11, 10), county="Kings"
    )
    est2 = estimate_window(make_venue("v:2"), other, curves, cfg, today=TODAY)
    assert est2.estimated_open == date(2027, 1, 9)


def test_already_inspected_venue_has_no_estimate(cfg):
    curves = {"all": kaplan_meier([60] * 40, [True] * 40)}
    v = make_venue("v:1", first_inspection_date=date(2026, 1, 1))
    lic = make_license("a", source="sla_active", original_issue_date=date(2025, 12, 1))
    assert estimate_window(v, lic, curves, cfg, today=TODAY) is None


def test_estimate_all_prefers_issued_and_skips_opened(cfg):
    from scripts.hospitality.window.estimate import estimate_all

    curves = {"all": kaplan_meier([60] * 40, [True] * 40)}
    issued = make_license("a", source="sla_active", original_issue_date=date(2026, 11, 1))
    pend = make_license("p", received_date=date(2026, 11, 1))
    waiting = make_venue("v:1", license_ids=("a", "p"))
    opened = make_venue("v:2", license_ids=("a",), first_inspection_date=date(2026, 11, 5))
    out = estimate_all([waiting, opened], [issued, pend], curves, cfg, TODAY)
    assert [e.venue_id for e in out] == ["v:1"]
    assert out[0].estimated_open == date(2026, 12, 31)


# --- Task 9b: likely-already-open venues get no "opening soon" estimate --------------------


def _link(license_id: str, camis: str):
    from scripts.hospitality.models import EntityLink

    return EntityLink(
        left_id=license_id, right_id=camis, kind="possibly_same", probability=0.7, method="geo"
    )


def test_over_age_license_with_no_dohmh_record_gets_no_estimate(cfg):
    curves = {"all": kaplan_meier([60] * 40, [True] * 40)}
    lic = make_license("a", source="sla_active", original_issue_date=TODAY - timedelta(days=200))
    assert estimate_window(make_venue("v:lic:a"), lic, curves, cfg, today=TODAY) is None


def test_over_age_dohmh_pending_venue_still_gets_estimate(cfg):
    curves = {"all": kaplan_meier([60] * 40, [True] * 40)}
    lic = make_license("a", source="sla_active", original_issue_date=TODAY - timedelta(days=200))
    est = estimate_window(make_venue("v:5", camis="5"), lic, curves, cfg, today=TODAY)
    assert est is not None


def test_estimate_all_skips_license_linked_to_inspected_venue(cfg):
    from scripts.hospitality.window.estimate import estimate_all

    curves = {"all": kaplan_meier([60] * 40, [True] * 40)}
    inspected = make_venue("v:9", camis="9", first_inspection_date=date(2024, 1, 1))
    issued = make_license("a", source="sla_active", original_issue_date=date(2026, 11, 1))
    pend = make_license("p", received_date=date(2026, 11, 1))
    linked = make_venue("v:lic:a", license_ids=("a",))
    linked_pending = make_venue("v:lic:p", license_ids=("p",))
    fresh = make_venue("v:lic:c", license_ids=("c",))
    other = make_license("c", source="sla_active", original_issue_date=date(2026, 11, 1))
    out = estimate_all(
        [inspected, linked, linked_pending, fresh],
        [issued, pend, other],
        curves,
        cfg,
        TODAY,
        links=[_link("a", "9"), _link("p", "9")],
    )
    assert [e.venue_id for e in out] == ["v:lic:c"]


def test_renewed_licence_gives_no_opening_estimate(cfg):
    from scripts.hospitality.window.estimate import estimate_all

    curve = {"all": kaplan_meier([100.0, 200.0, 300.0], [True, True, True])}

    def run(rid: str):
        lic = make_license(rid, source="sla_active", received_date=None,
                           original_issue_date=date(2026, 9, 3))  # fmt: skip
        venue = make_venue("v:1", license_ids=(rid,), camis="9")
        return estimate_all([venue], [lic], curve, cfg, date(2026, 11, 16))

    assert len(run("sla_active:0340-26-119590")) == 1
    assert run("sla_active:0340-21-119590") == []
