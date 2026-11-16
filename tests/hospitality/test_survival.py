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


# --- Task 9b: only plausibly-unopened licenses count as censored ---------------------------


def _link(license_id: str, camis: str):
    from scripts.hospitality.models import EntityLink

    return EntityLink(
        left_id=license_id, right_id=camis, kind="possibly_same", probability=0.7, method="geo"
    )


def test_license_linked_to_inspected_venue_is_not_censored():
    inspected = make_venue("v:9", camis="9", first_inspection_date=date(2024, 1, 1))
    lic_only = make_venue("v:lic:b", license_ids=("b",))
    lic = make_license("b", source="sla_active", original_issue_date=date(2026, 10, 17))
    out = opening_durations(
        [inspected, lic_only], [lic], TODAY, links=[_link("b", "9")], max_unmatched_age_days=90
    )
    assert out == []


def test_license_linked_to_uninspected_venue_is_still_censored():
    pending_site = make_venue("v:9", camis="9")
    lic_only = make_venue("v:lic:b", license_ids=("b",))
    lic = make_license("b", source="sla_active", original_issue_date=date(2026, 10, 17))
    out = opening_durations(
        [pending_site, lic_only], [lic], TODAY, links=[_link("b", "9")], max_unmatched_age_days=90
    )
    assert out == [("Restaurant|New York", 30.0, False)]


def test_over_age_license_with_no_dohmh_record_is_not_censored():
    v = make_venue("v:lic:b", license_ids=("b",))
    lic = make_license("b", source="sla_active", original_issue_date=date(2026, 5, 1))
    assert opening_durations([v], [lic], TODAY, max_unmatched_age_days=90) == []


def test_recent_license_with_no_dohmh_record_is_censored():
    v = make_venue("v:lic:b", license_ids=("b",))
    lic = make_license("b", source="sla_active", original_issue_date=date(2026, 10, 17))
    out = opening_durations([v], [lic], TODAY, max_unmatched_age_days=90)
    assert out == [("Restaurant|New York", 30.0, False)]


def test_dohmh_pending_venue_is_censored_beyond_unmatched_age_cap():
    # A DOHMH record awaiting first inspection is positive evidence the site is not yet open.
    v = make_venue("v:5", camis="5", license_ids=("b",))
    lic = make_license("b", source="sla_active", original_issue_date=date(2025, 10, 12))
    out = opening_durations([v], [lic], TODAY, max_unmatched_age_days=90)
    assert out == [("Restaurant|New York", 400.0, False)]


def test_config_has_unmatched_censor_age_cap():
    from scripts.hospitality.config import load_config

    assert load_config().window_unmatched_censor_max_age_days == 90


def test_max_opening_days_is_a_parameter():
    """M2: the duration cap comes from config (`max_opening_days`), not only MAX_DAYS."""
    v = make_venue("v:1", first_inspection_date=date(2026, 3, 1), license_ids=("a",))
    lic = make_license("a", source="sla_active", original_issue_date=date(2025, 3, 1))  # 365d
    assert len(opening_durations([v], [lic], TODAY)) == 1
    assert opening_durations([v], [lic], TODAY, max_days=300) == []
