"""Recall and detection lag for the watch layer, measured against the holdout.

ADR-0010 (docs/decisions/0010-holdout-deep-scan-and-recall.md) Decision 4 is
the spec. This is the function that answers the question this whole project
exists to answer: "if you don't know something changed at all, how would you
know if you captured it fast enough?"

    recall        = |matched deep changes| / |deep changes|
    detection_lag = deep_detected_at - watch_detected_at   (positive = watch won)

Deep scan (Task 3.1) is ground truth by construction: it bypasses
confirm-on-change and re-fetches every holdout source on its own cadence, so
anything it finds real is real. Anything it finds that the watch layer did
not is a MISS, and misses are the number that actually matters.

The plan's original reference implementation kept ONE watch timestamp per
`(account_id, source_type)` key and matched every deep-scan event for that
key against it. Measured defect: a source that changes twice in one window
-- day 0 and day 7, with watch catching only the day-0 change 6 hours late
-- would have its day-7 event paired against the day-0 watch timestamp,
producing a nonsense "+162 hour lag" for a change the watch layer never
detected. Fixed here: group both sides by key, sort each group
chronologically, and match position-by-position -- the i-th real change
against the i-th watch detection for that same key. A deep change beyond the
number of watch detections for its key is a genuine miss. A watch detection
beyond the number of deep changes for its key is an EXTRANEOUS watch
detection -- the watch layer reporting more than ground truth confirms
happened -- surfaced separately rather than silently discarded, since it is
itself a signal about watch-layer precision (e.g. confirm-on-change letting
a cosmetic flip through).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DetectedChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: int
    source_type: str
    detected_at: datetime

    @property
    def key(self) -> tuple[int, str]:
        return (self.account_id, self.source_type)


class RecallReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    # None when deep_count is 0 -- recall is undefined without ground truth
    # to measure against, not zero (zero would falsely read as "watch missed
    # everything" when really there was nothing to catch).
    recall: float | None
    deep_count: int
    caught_count: int
    missed_count: int
    p50_lag_hours: float | None
    p95_lag_hours: float | None
    # The actual missed deep-scan events, not just their keys -- richer than
    # the plan's `missed_keys: list[tuple[int, str]]`, and necessary now that
    # per-key sequential matching allows more than one miss per key.
    missed: tuple[DetectedChange, ...]
    extraneous_watch_count: int
    extraneous_watch: tuple[DetectedChange, ...]


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(int(len(ordered) * pct), len(ordered) - 1)
    return ordered[idx]


def _group_sorted_by_key(
    changes: list[DetectedChange],
) -> dict[tuple[int, str], list[DetectedChange]]:
    grouped: dict[tuple[int, str], list[DetectedChange]] = defaultdict(list)
    for change in changes:
        grouped[change.key].append(change)
    for group in grouped.values():
        group.sort(key=lambda c: c.detected_at)
    return grouped


def compute_recall(
    deep_changes: list[DetectedChange], watch_changes: list[DetectedChange]
) -> RecallReport:
    """Compare ground truth (deep scan) against what the watch layer caught.

    See module docstring for the per-key sequential matching this implements
    and why the plan's simpler one-entry-per-key design was wrong.
    """
    deep_by_key = _group_sorted_by_key(deep_changes)
    watch_by_key = _group_sorted_by_key(watch_changes)

    lags: list[float] = []
    missed: list[DetectedChange] = []
    extraneous: list[DetectedChange] = []

    all_keys = set(deep_by_key) | set(watch_by_key)
    for key in all_keys:
        deep_group = deep_by_key.get(key, [])
        watch_group = watch_by_key.get(key, [])

        for deep_event, watch_event in zip(deep_group, watch_group):
            lag_hours = (deep_event.detected_at - watch_event.detected_at).total_seconds() / 3600.0
            lags.append(lag_hours)

        matched = min(len(deep_group), len(watch_group))
        missed.extend(deep_group[matched:])
        extraneous.extend(watch_group[matched:])

    deep_count = len(deep_changes)
    caught_count = len(lags)

    # Deterministic ordering, same rationale as scripts/verify/differ.py:
    # a replayed report should produce byte-identical output.
    missed.sort(key=lambda c: (c.account_id, c.source_type, c.detected_at))
    extraneous.sort(key=lambda c: (c.account_id, c.source_type, c.detected_at))

    return RecallReport(
        recall=(caught_count / deep_count) if deep_count else None,
        deep_count=deep_count,
        caught_count=caught_count,
        missed_count=len(missed),
        p50_lag_hours=_percentile(lags, 0.50),
        p95_lag_hours=_percentile(lags, 0.95),
        missed=tuple(missed),
        extraneous_watch_count=len(extraneous),
        extraneous_watch=tuple(extraneous),
    )
