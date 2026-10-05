"""Tests for scripts/measure/health.py.

ADR-0011 (docs/decisions/0011-source-health-and-anomaly-detection.md) is the spec.
Scope, per Decision 1: fetch_success_rate is real, computed from actual Probe outcomes.
parse_success_rate and zero_result_rate are left None -- they require the verify layer's
extraction output, which has no caller anywhere in this codebase yet. Faking them from a
proxy (bytes, changed) was considered and rejected: both are already disproven signals for
"content found nothing" (Task 1.3a measured raw bytes doesn't correlate with parsed content
size; Phase 1's own exit-criterion data showed unchanged=83-97% of probes by design, so
"changed" as a zero-result proxy would fire almost every day).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from scripts.measure.health import (
    ProbeOutcome,
    SourceHealth,
    compute_health,
    detect_anomaly,
)

RUN_DATE = date(2026, 8, 15)


def _outcome(source_type: str, succeeded: bool, day: int = 15) -> ProbeOutcome:
    return ProbeOutcome(
        source_type=source_type,
        fetched_at=datetime(2026, 8, day, 12, tzinfo=timezone.utc),
        succeeded=succeeded,
    )


def _health(rate: float, day: int = 1) -> SourceHealth:
    return SourceHealth(
        source_type="careers",
        run_date=date(2026, 8, day),
        fetch_success_rate=rate,
        parse_success_rate=None,
        zero_result_rate=None,
        sample_size=100,
    )


# ---------------------------------------------------------------------------
# compute_health
# ---------------------------------------------------------------------------


def test_all_succeeded_gives_perfect_fetch_success_rate():
    outcomes = [_outcome("careers", True) for _ in range(10)]
    health = compute_health(outcomes, source_type="careers", run_date=RUN_DATE)
    assert health.fetch_success_rate == 1.0
    assert health.sample_size == 10


def test_mixed_outcomes_compute_correct_rate():
    outcomes = [_outcome("careers", True) for _ in range(3)] + [
        _outcome("careers", False) for _ in range(1)
    ]
    health = compute_health(outcomes, source_type="careers", run_date=RUN_DATE)
    assert health.fetch_success_rate == 0.75
    assert health.sample_size == 4


def test_no_outcomes_yields_none_rate_not_a_divide_by_zero():
    health = compute_health([], source_type="careers", run_date=RUN_DATE)
    assert health.fetch_success_rate is None
    assert health.sample_size == 0


def test_parse_and_zero_result_rate_are_none_not_faked():
    outcomes = [_outcome("careers", True)]
    health = compute_health(outcomes, source_type="careers", run_date=RUN_DATE)
    assert health.parse_success_rate is None
    assert health.zero_result_rate is None


def test_only_matching_source_type_counted():
    outcomes = [_outcome("careers", True), _outcome("careers", False), _outcome("pricing", True)]
    health = compute_health(outcomes, source_type="careers", run_date=RUN_DATE)
    assert health.sample_size == 2
    assert health.fetch_success_rate == 0.5


def test_only_matching_run_date_counted():
    same_day = _outcome("careers", True, day=15)
    other_day = _outcome("careers", False, day=14)
    health = compute_health([same_day, other_day], source_type="careers", run_date=RUN_DATE)
    assert health.sample_size == 1
    assert health.fetch_success_rate == 1.0


def test_run_date_and_source_type_are_carried_through_even_with_no_data():
    health = compute_health([], source_type="pricing", run_date=RUN_DATE)
    assert health.source_type == "pricing"
    assert health.run_date == RUN_DATE


# ---------------------------------------------------------------------------
# detect_anomaly -- direction-aware (ADR-0011 Decision 2)
# ---------------------------------------------------------------------------


def test_low_is_bad_flags_a_success_rate_drop():
    trailing = [h.fetch_success_rate for h in [_health(0.97, d) for d in range(1, 15)]]
    anomaly = detect_anomaly(
        0.10,
        trailing,
        metric_name="fetch_success_rate",
        source_type="careers",
        direction="low_is_bad",
    )
    assert anomaly is not None
    assert anomaly.metric == "fetch_success_rate"
    assert anomaly.current == 0.10


def test_low_is_bad_does_not_flag_normal_variation():
    trailing = [0.95 + (i % 3) * 0.01 for i in range(14)]
    anomaly = detect_anomaly(
        0.96,
        trailing,
        metric_name="fetch_success_rate",
        source_type="careers",
        direction="low_is_bad",
    )
    assert anomaly is None


def test_low_is_bad_does_not_flag_an_improvement():
    """A success rate going UP is never bad -- the low_is_bad direction must not
    fire on the opposite tail."""
    trailing = [0.5 for _ in range(14)]
    anomaly = detect_anomaly(
        1.0,
        trailing,
        metric_name="fetch_success_rate",
        source_type="careers",
        direction="low_is_bad",
    )
    assert anomaly is None


def test_high_is_bad_flags_a_spike():
    trailing = [0.12 for _ in range(14)]
    anomaly = detect_anomaly(
        1.0,
        trailing,
        metric_name="zero_result_rate",
        source_type="careers",
        direction="high_is_bad",
    )
    assert anomaly is not None


def test_high_is_bad_does_not_flag_a_drop():
    trailing = [0.5 for _ in range(14)]
    anomaly = detect_anomaly(
        0.0,
        trailing,
        metric_name="zero_result_rate",
        source_type="careers",
        direction="high_is_bad",
    )
    assert anomaly is None


def test_no_alert_without_enough_history():
    anomaly = detect_anomaly(
        0.10,
        [0.9, 0.9],
        metric_name="fetch_success_rate",
        source_type="careers",
        direction="low_is_bad",
    )
    assert anomaly is None


def test_flat_baseline_guard_still_flags_a_real_departure():
    """stdev=0 across trailing history must not divide by zero, and a real
    departure from a perfectly flat baseline must still be caught."""
    trailing = [1.0 for _ in range(14)]
    anomaly = detect_anomaly(
        0.5,
        trailing,
        metric_name="fetch_success_rate",
        source_type="careers",
        direction="low_is_bad",
    )
    assert anomaly is not None


def test_flat_baseline_guard_does_not_flag_a_tiny_departure():
    trailing = [1.0 for _ in range(14)]
    anomaly = detect_anomaly(
        0.99,
        trailing,
        metric_name="fetch_success_rate",
        source_type="careers",
        direction="low_is_bad",
    )
    assert anomaly is None


def test_low_is_bad_flags_a_real_drop_against_a_genuinely_varying_baseline():
    """Trailing data has real variance (stdev != 0) here, unlike every other
    anomaly-triggering fixture in this file, which all happen to use flat
    (stdev=0) trailing history and so never exercise the non-flat sigma
    branch. Mutation-confirmed: negating `sigma` after computing it survives
    every other test in this file but fails this one, since mean=0.90,
    stdev=0.017, and a genuine drop to 0.5 needs the SIGN of departure/stdev
    to come out positive (worse than baseline) to be flagged.
    """
    trailing = [0.90, 0.92, 0.88, 0.91, 0.89, 0.93, 0.87, 0.90, 0.92, 0.88, 0.91, 0.89, 0.90, 0.91]
    anomaly = detect_anomaly(
        0.5,
        trailing,
        metric_name="fetch_success_rate",
        source_type="careers",
        direction="low_is_bad",
    )
    assert anomaly is not None
    assert anomaly.sigma > 0


def test_high_is_bad_flags_a_real_spike_against_a_genuinely_varying_baseline():
    trailing = [0.10, 0.12, 0.08, 0.11, 0.09, 0.13, 0.07, 0.10, 0.12, 0.08, 0.11, 0.09, 0.10, 0.11]
    anomaly = detect_anomaly(
        0.9,
        trailing,
        metric_name="zero_result_rate",
        source_type="careers",
        direction="high_is_bad",
    )
    assert anomaly is not None
    assert anomaly.sigma > 0
