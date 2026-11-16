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
    v = make_venue("v:1")
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
