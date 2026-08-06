"""Per-source health metrics and silent-breakage detection.

ADR-0011 (docs/decisions/0011-source-health-and-anomaly-detection.md) is the spec. Sami
(Rippling, 17:07): "you can't really tell real quiet from a broken scanner." Three rates
would answer this in full -- fetch_success_rate (network/ban failures), parse_success_rate
(extraction failures), zero_result_rate (structural drift: the page loads fine but the
parser now finds nothing, the dangerous one, since nothing errors).

**Scope, per Decision 1: only fetch_success_rate is computed from real data today.**
parse_success_rate and zero_result_rate require the verify layer's per-fetch extraction
outcome (scripts/verify/extractor.py), which is fully built and reviewed but has no caller
anywhere in this codebase -- it has never run against a real snapshot. They stay `None`
until a future wiring task gives them real data. Faking them from a proxy was considered
and rejected: raw `bytes` is already measured (Task 1.3a) to not correlate with parsed
content size on JS-heavy sites, and `changed` would be actively wrong in the other
direction -- Phase 1's own exit-criterion data showed ~83-97% of daily probes are
`changed=False` BY DESIGN, so treating "unchanged" as "zero result" would fire almost
every day and train whoever reads it to ignore the alert.
"""

from __future__ import annotations

import statistics
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

_MIN_HISTORY = 7
_SIGMA_THRESHOLD = 3.0
# Flat-baseline guard: when the trailing history has zero variance, a plain
# sigma comparison divides by zero. This is the flat-baseline equivalent of
# the 3-sigma threshold, expressed as an absolute departure from the mean.
_FLAT_BASELINE_DEPARTURE = 0.25


class ProbeOutcome(BaseModel):
    """A minimal, DB-decoupled view of one fetch, for pure aggregation.

    Deliberately not the ORM `Probe` row (ADR-0011 Decision 4) -- matches the
    established pattern (`DetectedChange` in scripts/measure/lag.py,
    `FactChange` in scripts/verify/differ.py): callers map ORM rows to this
    shape, so the computation itself needs no DB session to test.
    """

    model_config = ConfigDict(frozen=True)

    source_type: str
    fetched_at: datetime
    succeeded: bool


class SourceHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_type: str
    run_date: date
    # None when there is no data for this (source_type, run_date) at all --
    # distinct from a real 0.0, the same "undefined vs zero" distinction
    # RecallReport.recall makes in scripts/measure/lag.py.
    fetch_success_rate: float | None
    # ADR-0011 Decision 1: not yet computable from any data this codebase
    # produces. Never populate these with a proxy -- see module docstring.
    parse_success_rate: float | None
    zero_result_rate: float | None
    sample_size: int


class Anomaly(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_type: str
    metric: str
    current: float
    baseline_mean: float
    sigma: float
    message: str


def compute_health(
    outcomes: list[ProbeOutcome], *, source_type: str, run_date: date
) -> SourceHealth:
    """Aggregate fetch outcomes for one (source_type, run_date) into a SourceHealth.

    Filters `outcomes` to the given source_type and date itself, rather than
    requiring the caller to pre-filter -- callers pass one day's full outcome
    list and this does the grouping, matching compute_recall's shape in
    lag.py (caller loads, pure function groups and computes).
    """
    matching = [
        o for o in outcomes if o.source_type == source_type and o.fetched_at.date() == run_date
    ]
    sample_size = len(matching)
    fetch_success_rate = (
        sum(1 for o in matching if o.succeeded) / sample_size if sample_size else None
    )

    return SourceHealth(
        source_type=source_type,
        run_date=run_date,
        fetch_success_rate=fetch_success_rate,
        parse_success_rate=None,
        zero_result_rate=None,
        sample_size=sample_size,
    )


def detect_anomaly(
    current: float,
    trailing: list[float],
    *,
    metric_name: str,
    source_type: str,
    direction: Literal["high_is_bad", "low_is_bad"],
) -> Anomaly | None:
    """Flag `current` as anomalous against the trailing baseline, direction-aware.

    ADR-0011 Decision 2: generalized over metric name and direction rather
    than hardcoded to zero_result_rate/"a rise is bad", because
    fetch_success_rate's bad direction is the OPPOSITE (a drop is the
    failure) -- the statistics (mean, stdev, flat-baseline guard) are
    identical either way, only the comparison and message text change.
    """
    if len(trailing) < _MIN_HISTORY:
        return None

    mean = statistics.mean(trailing)
    stdev = statistics.stdev(trailing) if len(trailing) > 1 else 0.0
    departure = current - mean if direction == "high_is_bad" else mean - current

    if stdev == 0.0:
        if departure > _FLAT_BASELINE_DEPARTURE:
            return Anomaly(
                source_type=source_type,
                metric=metric_name,
                current=current,
                baseline_mean=mean,
                sigma=float("inf"),
                message=(
                    f"{source_type}: {metric_name} {current:.0%} vs flat baseline "
                    f"{mean:.0%} -- likely a real departure, not normal variation"
                ),
            )
        return None

    sigma = departure / stdev
    if sigma < _SIGMA_THRESHOLD:
        return None

    return Anomaly(
        source_type=source_type,
        metric=metric_name,
        current=current,
        baseline_mean=mean,
        sigma=sigma,
        message=(
            f"{source_type}: {metric_name} {current:.0%} is {sigma:.1f}sigma "
            f"from the {mean:.0%} baseline -- investigate before assuming it's a quiet day"
        ),
    )
