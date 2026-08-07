"""Cohort lift analysis: two-proportion z-test between a treatment cohort
(cohort_a) and a baseline cohort (cohort_b) (ADR-0021).

Validity guard is stronger than the plan's stated "n>=30 per arm": both
`n>=30` AND the success-failure condition (`n*p_hat>=5` and
`n*(1-p_hat)>=5` per arm) must hold before a z-test is computed (ADR-0021
Decision 1). Either failing sets `insufficient_data=True` and nulls the
statistical fields -- rates and sample sizes are still reported regardless.

The normal CDF is computed via stdlib `math.erf`, no scipy/numpy dependency
(ADR-0021 Decision 3).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict

_MIN_N = 30
_MIN_SUCCESS_FAILURE = 5


class CohortResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    replied: int
    total: int


class LiftReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    cohort_a_rate: float
    cohort_b_rate: float
    cohort_a_n: int
    cohort_b_n: int
    absolute_lift: float
    relative_lift: float | None
    insufficient_data: bool
    z_score: float | None
    p_value: float | None


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _passes_success_failure_condition(replied: int, total: int) -> bool:
    return replied >= _MIN_SUCCESS_FAILURE and (total - replied) >= _MIN_SUCCESS_FAILURE


def _is_valid_for_z_test(cohort: CohortResult) -> bool:
    return cohort.total >= _MIN_N and _passes_success_failure_condition(
        cohort.replied, cohort.total
    )


def compute_lift(cohort_a: CohortResult, cohort_b: CohortResult) -> LiftReport:
    rate_a = cohort_a.replied / cohort_a.total
    rate_b = cohort_b.replied / cohort_b.total

    absolute_lift = rate_a - rate_b
    relative_lift = (rate_a / rate_b - 1.0) if rate_b > 0 else None

    insufficient_data = not (_is_valid_for_z_test(cohort_a) and _is_valid_for_z_test(cohort_b))

    z_score: float | None = None
    p_value: float | None = None

    if not insufficient_data:
        pooled = (cohort_a.replied + cohort_b.replied) / (cohort_a.total + cohort_b.total)
        se = math.sqrt(pooled * (1.0 - pooled) * (1.0 / cohort_a.total + 1.0 / cohort_b.total))
        # Defensive only: SE=0 requires pooled in {0, 1}, which requires an
        # arm's replied count to be exactly 0 or equal to its total -- both
        # already fail _passes_success_failure_condition above, so this
        # branch is unreachable through compute_lift. Kept as a guard
        # against a future change to the guard order (ADR-0021 Decision 5).
        if se > 0:
            z_score = (rate_a - rate_b) / se
            p_value = 2.0 * (1.0 - _normal_cdf(abs(z_score)))

    return LiftReport(
        cohort_a_rate=rate_a,
        cohort_b_rate=rate_b,
        cohort_a_n=cohort_a.total,
        cohort_b_n=cohort_b.total,
        absolute_lift=absolute_lift,
        relative_lift=relative_lift,
        insufficient_data=insufficient_data,
        z_score=z_score,
        p_value=p_value,
    )
