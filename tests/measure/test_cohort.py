"""Tests for scripts/measure/cohort.py.

ADR-0021 is the spec. Expected z-score/p-value figures are hand-computed
(via a standalone Python script using the same math.erf-based normal CDF,
independently traced by hand, not copied from the implementation) before
being embedded here as assertions.
"""

from __future__ import annotations

import pytest

from scripts.measure.cohort import CohortResult, compute_lift


def _cohort(replied: int, total: int) -> CohortResult:
    return CohortResult(replied=replied, total=total)


# ---------------------------------------------------------------------------
# Core statistics -- hand-verified values
# ---------------------------------------------------------------------------


def test_basic_lift_reports_correct_rates_and_z_score():
    # cohort_a: 20/100 = 20%, cohort_b: 10/100 = 10%.
    # Hand-computed: pooled=0.15, SE=0.050498, z=1.98030, p=0.04767.
    report = compute_lift(_cohort(20, 100), _cohort(10, 100))

    assert report.insufficient_data is False
    assert report.cohort_a_rate == pytest.approx(0.2)
    assert report.cohort_b_rate == pytest.approx(0.1)
    assert report.z_score == pytest.approx(1.98030, abs=1e-4)
    assert report.p_value == pytest.approx(0.04767, abs=1e-4)


def test_absolute_and_relative_lift_are_both_reported():
    report = compute_lift(_cohort(20, 100), _cohort(10, 100))

    assert report.absolute_lift == pytest.approx(0.1)  # 20% - 10% = +10 points
    assert report.relative_lift == pytest.approx(1.0)  # 0.2/0.1 - 1 = +100%


def test_cohort_a_higher_than_b_gives_a_positive_z_score():
    report = compute_lift(_cohort(20, 100), _cohort(10, 100))
    assert report.z_score > 0


def test_cohort_a_lower_than_b_gives_a_negative_z_score():
    # Mirror of the basic test's cohorts (a/b swapped) -- p-value must be
    # the SAME magnitude as the positive-z case (two-tailed test is
    # symmetric), catching a missing abs() around z_score in the p-value
    # calculation that a bare `z_score < 0` check alone would miss.
    report = compute_lift(_cohort(10, 100), _cohort(20, 100))
    assert report.z_score == pytest.approx(-1.98030, abs=1e-4)
    assert report.p_value == pytest.approx(0.04767, abs=1e-4)


def test_sample_sizes_are_reported():
    report = compute_lift(_cohort(20, 100), _cohort(10, 200))
    assert report.cohort_a_n == 100
    assert report.cohort_b_n == 200


# ---------------------------------------------------------------------------
# ADR-0021 Decision 1: the plan's n>=30 guard alone is not enough -- the
# success-failure condition (n*p>=5 and n*(1-p)>=5) must ALSO hold.
# ---------------------------------------------------------------------------


def test_below_30_per_arm_is_insufficient_data():
    report = compute_lift(_cohort(5, 20), _cohort(50, 200))
    assert report.insufficient_data is True
    assert report.z_score is None
    assert report.p_value is None


def test_n_at_least_30_but_success_failure_condition_violated_is_still_insufficient():
    """The exact gap ADR-0021 Decision 1 exists to close: n=50 clears the
    plan's literal n>=30 floor, but with only 1 success, n*p=1 < 5 -- the
    normal approximation isn't valid even though n>=30 alone would pass."""
    report = compute_lift(_cohort(1, 50), _cohort(50, 200))
    assert report.insufficient_data is True
    assert report.z_score is None


def test_n_at_least_30_and_success_failure_condition_satisfied_is_sufficient():
    # n=30, p=0.5 -> n*p=15, n*(1-p)=15, both comfortably >= 5.
    # Identical rates at a VALID sample size give a real, defined z=0.0
    # (hand-verified: pooled=0.5, SE=0.12909944487358055, z=0.0) -- see
    # ADR-0021 Decision 5, which corrects an earlier draft that wrongly
    # treated identical rates as an "undefined" case.
    report = compute_lift(_cohort(15, 30), _cohort(15, 30))
    assert report.insufficient_data is False
    assert report.z_score == pytest.approx(0.0, abs=1e-9)
    assert report.p_value == pytest.approx(1.0, abs=1e-9)


def test_success_failure_condition_at_the_exact_boundary_of_5_is_sufficient():
    # n*p_hat == 5 exactly (5 replies out of 100) must PASS the guard --
    # it's stated as >=5, not >5. Catches an off-by-one that tightens the
    # boundary to a strict >.
    report = compute_lift(_cohort(5, 100), _cohort(50, 200))
    assert report.insufficient_data is False


def test_rates_and_ns_are_still_reported_even_when_insufficient_for_a_z_test():
    """Withholding the z-test doesn't mean withholding the real counts --
    there's no reason to hide what was actually observed."""
    report = compute_lift(_cohort(5, 20), _cohort(50, 200))
    assert report.cohort_a_rate == pytest.approx(0.25)
    assert report.cohort_b_rate == pytest.approx(0.25)
    assert report.cohort_a_n == 20
    assert report.cohort_b_n == 200


# ---------------------------------------------------------------------------
# ADR-0021 Decision 5: SE == 0 is unreachable once Decision 1's
# success-failure guard is applied -- it always requires an arm's success or
# failure count to be exactly 0, which the guard already rejects. These
# cases are therefore insufficient_data, not a distinct "undefined" case.
# ---------------------------------------------------------------------------


def test_identical_rates_at_a_valid_sample_size_yield_a_real_zero_z_score():
    # Same case as test_n_at_least_30_and_success_failure_condition_satisfied_is_sufficient
    # at a different n, confirming z=0 is defined (not None) generally, not
    # just at n=30.
    report = compute_lift(_cohort(30, 100), _cohort(30, 100))
    assert report.insufficient_data is False
    assert report.z_score == pytest.approx(0.0, abs=1e-9)
    assert report.p_value == pytest.approx(1.0, abs=1e-9)
    assert report.absolute_lift == pytest.approx(0.0)


def test_both_cohorts_at_zero_percent_fails_the_success_failure_guard():
    # x=0 for both arms means n*p=0 < 5 for both -- Decision 1's guard
    # rejects this before a z-test is ever attempted, regardless of n.
    report = compute_lift(_cohort(0, 50), _cohort(0, 50))
    assert report.insufficient_data is True
    assert report.z_score is None


def test_both_cohorts_at_one_hundred_percent_fails_the_success_failure_guard():
    # x=n for both arms means n*(1-p)=0 < 5 for both -- same guard, the
    # other tail.
    report = compute_lift(_cohort(50, 50), _cohort(50, 50))
    assert report.insufficient_data is True
    assert report.z_score is None


def test_relative_lift_is_none_when_baseline_rate_is_zero():
    report = compute_lift(_cohort(10, 50), _cohort(0, 50))
    assert report.relative_lift is None
    assert report.absolute_lift == pytest.approx(0.2)
