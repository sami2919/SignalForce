from datetime import date

import pytest

from scripts.hospitality.window.survival import (
    build_curves,
    kaplan_meier,
    opening_durations,
    quantile_time,
    survival_at,
)
from tests.hospitality.factories import make_license, make_venue

TODAY = date(2026, 11, 16)


def test_kaplan_meier_hand_computed():
    curve = kaplan_meier([10, 20, 20, 30], [True, True, False, True])
    assert curve[0] == (0.0, 1.0)
    assert survival_at(curve, 9) == 1.0
    assert survival_at(curve, 10) == pytest.approx(0.75)
    assert survival_at(curve, 20) == pytest.approx(0.50)
    assert survival_at(curve, 30) == pytest.approx(0.0)


def test_quantile_time_median():
    curve = kaplan_meier([10, 20, 20, 30], [True, True, False, True])
    assert quantile_time(curve, 0.5) == 20


def test_quantile_none_when_curve_never_reaches_level():
    curve = kaplan_meier([10, 20], [True, False])
    assert quantile_time(curve, 0.9) is None


def test_negative_duration_excluded_as_not_new_opening():
    v = make_venue("v:1", first_inspection_date=date(2025, 1, 1), license_ids=("a",))
    lic = make_license("a", source="sla_active", original_issue_date=date(2026, 1, 1))
    assert opening_durations([v], [lic], TODAY) == []


def test_observed_and_censored_durations():
    opened = make_venue("v:1", first_inspection_date=date(2026, 3, 1), license_ids=("a",))
    waiting = make_venue("v:2", license_ids=("b",))
    noisy = make_venue("v:3", first_inspection_date=date(2026, 6, 1), license_ids=("c",))
    lics = [
        make_license("a", source="sla_active", original_issue_date=date(2026, 1, 1)),
        make_license("b", source="sla_active", original_issue_date=date(2026, 10, 17)),
        make_license("c", source="sla_active", original_issue_date=date(2023, 1, 1)),
    ]
    out = opening_durations([opened, waiting, noisy], lics, TODAY)
    assert out == [("Restaurant|New York", 59.0, True), ("Restaurant|New York", 30.0, False)]


def test_pending_license_is_not_a_duration():
    v = make_venue("v:1", license_ids=("p",))
    assert opening_durations([v], [make_license("p")], TODAY) == []


def test_build_curves_drops_small_strata_keeps_all():
    d = [("a|x", float(i + 1), True) for i in range(5)] + [("b|y", 3.0, True)]
    curves = build_curves(d, min_n=5)
    assert set(curves) == {"all", "a|x"}
