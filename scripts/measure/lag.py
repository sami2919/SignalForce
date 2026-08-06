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
detected.

Fixed by grouping both sides by key and matching by NEAREST-NEIGHBOR
proximity in time rather than a naive positional `zip` (corrected twice on
review, 2026-08-06 -- see below): each watch event in a key's group is
assigned to its closest deep event in the same group; each deep event then
takes whichever assigned watch event is closest to it as its match, and any
other watch events assigned to that same deep event are recorded as
EXTRANEOUS -- the watch layer reporting more than ground truth confirms
happened, surfaced separately rather than silently discarded, since it is
itself a signal about watch-layer precision (e.g. confirm-on-change letting
a cosmetic flip through). A deep event with no watch events assigned to it
is a genuine MISS.

**Correction, 2026-08-06 (first pass):** an initial version of this fix
used a plain positional `zip(deep_group, watch_group)` after sorting each
side independently. That resolves the ADR's original multi-change-per-key
defect but not a second instance of the same failure class: an early false-
positive watch detection would consume the "first" position and get paired
with the real deep event, while the GENUINE watch detection (later, matched
correctly to the real change) was pushed to "extraneous." Reproduced:
deep=[h100] (one real change), watch=[h0 false positive, h104 genuine
catch] -> positional zip paired h100 with h0, producing `+100h` -- a
physically implausible lag -- while the genuine h104 detection was flagged
as the extraneous one.

**Correction, 2026-08-06 (second pass):** the first pass's fix was a
two-pointer merge that rejected pairing a deep event with any watch event
chronologically BEFORE it, on the theory that deep -- ground truth, more
frequent -- can never be beaten to a detection. That theory is false: more
frequent makes deep *usually* faster, not *always*, and watch legitimately
beating deep to a real change is a real, expected case (see
`test_lag_is_positive_when_watch_was_faster`). The two-pointer version
turned that legitimate case into a phantom miss. The property that actually
distinguishes a genuine catch from a false positive is PROXIMITY, not
chronological order -- h104 is close to h100, h0 is far from it, and that
distinction survives regardless of which side of h100 either watch event
falls on. Nearest-neighbor assignment (`_match_one_key`) fixes both the
original defect and the two-pointer regression at once.
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
    """Nearest-rank percentile: p95 is meant to surface the WORST 5% of
    `values`, so this always sorts so that badness increases with index —
    callers must pass a "badness" list (bigger = worse), never the raw
    signed lag directly. See `_tail_percentiles` for why: with `lag`'s sign
    convention (positive = watch won), sorting `lag` ascending and taking a
    high-percentile index does the OPPOSITE of what "p95 lag" means — it
    surfaces the fastest detection, not the slowest.
    """
    if not values:
        return None
    ordered = sorted(values)
    idx = min(int(len(ordered) * pct), len(ordered) - 1)
    return ordered[idx]


def _tail_percentiles(lags: list[float]) -> tuple[float | None, float | None]:
    """p50/p95 of `lag` (positive = watch won), tail-correct.

    Fixed on review, 2026-08-06: the first version called
    `_percentile(lags, 0.50/0.95)` directly. Verified with 10 lags
    representing watch lateness of 1..24 hours (lag = -lateness, so mostly
    negative): the buggy version reported p50=-8.0, p95=-1.0 -- the SINGLE
    BEST detection in the batch (1h late), while the worst case (24h late)
    was invisible. p95 exists to answer "how bad does it get," and this
    reported "how good does it get" instead -- for the exact regime
    (deep hourly, watch daily -> lag predominantly negative) this project is
    designed to run in.

    Fix: percentiles are computed over "badness" (`-lag`, so positive =
    worse), which sorts correctly for the tail, then negated back to `lag`
    units so the returned value stays in the sign convention the rest of
    this module and its callers use. Re-run on the same 10-value scenario:
    p50=-10.0, p95=-24.0 -- p95 now correctly reports the worst case.
    """
    badness = [-lag for lag in lags]
    p50_badness = _percentile(badness, 0.50)
    p95_badness = _percentile(badness, 0.95)
    p50 = -p50_badness if p50_badness is not None else None
    p95 = -p95_badness if p95_badness is not None else None
    return p50, p95


def _group_sorted_by_key(
    changes: list[DetectedChange],
) -> dict[tuple[int, str], list[DetectedChange]]:
    grouped: dict[tuple[int, str], list[DetectedChange]] = defaultdict(list)
    for change in changes:
        grouped[change.key].append(change)
    for group in grouped.values():
        group.sort(key=lambda c: c.detected_at)
    return grouped


def _match_one_key(
    deep_group: list[DetectedChange], watch_group: list[DetectedChange]
) -> tuple[list[float], list[DetectedChange], list[DetectedChange]]:
    """Nearest-neighbor assignment over one (account_id, source_type)'s deep
    and watch events. Returns (lags, missed, extraneous).

    Superseded on review, 2026-08-06 (second pass): a first fix used a
    two-pointer merge that rejected any watch event chronologically BEFORE
    the deep event it would pair with, on the theory that deep (ground
    truth, more frequent) can never be beaten to a detection. That theory is
    false -- deep running more often makes it *usually* faster, not
    *always*; watch legitimately beating deep to a real change is the exact
    scenario `test_lag_is_positive_when_watch_was_faster` exercises, and the
    two-pointer version turned that into a phantom miss (`p50_lag_hours`
    came back `None`).

    The property that actually distinguishes a genuine catch from a false
    positive isn't chronological order, it's PROXIMITY: in the IMPORTANT-2
    scenario (deep=[h100], watch=[h0 false positive, h104 genuine catch]),
    h104 is close to h100 and h0 is far from it -- order alone can't tell
    them apart (both watch events technically straddle differently), but
    distance can. So each watch event is assigned to its nearest deep event
    in this group (ties break toward the earlier deep event); each deep
    event then takes the CLOSEST watch event assigned to it as its match,
    and any others assigned to the same deep event are extraneous. A deep
    event with no watch events assigned to it at all is a miss. This
    reproduces the correct answer for every scenario the two-pointer
    version was built for (h100/h104/h0 -> matches h100<->h104, h0
    extraneous) while also fixing the watch-was-faster regression the
    two-pointer version introduced.
    """
    lags: list[float] = []
    missed: list[DetectedChange] = []
    extraneous: list[DetectedChange] = []

    if not deep_group:
        return lags, missed, list(watch_group)

    def _hours(a: DetectedChange, b: DetectedChange) -> float:
        return (a.detected_at - b.detected_at).total_seconds() / 3600.0

    assigned: dict[int, list[DetectedChange]] = defaultdict(list)
    for watch_event in watch_group:
        nearest_idx = min(
            range(len(deep_group)),
            key=lambda i: abs(_hours(deep_group[i], watch_event)),
        )
        assigned[nearest_idx].append(watch_event)

    for idx, deep_event in enumerate(deep_group):
        candidates = assigned.get(idx, [])
        if not candidates:
            missed.append(deep_event)
            continue
        best = min(candidates, key=lambda w: abs(_hours(deep_event, w)))
        lags.append(_hours(deep_event, best))
        extraneous.extend(w for w in candidates if w is not best)

    return lags, missed, extraneous


def compute_recall(
    deep_changes: list[DetectedChange], watch_changes: list[DetectedChange]
) -> RecallReport:
    """Compare ground truth (deep scan) against what the watch layer caught.

    See module docstring for the two-pointer per-key matching this
    implements and the two distinct defect shapes it fixes relative to the
    plan's original one-entry-per-key design.
    """
    deep_by_key = _group_sorted_by_key(deep_changes)
    watch_by_key = _group_sorted_by_key(watch_changes)

    lags: list[float] = []
    missed: list[DetectedChange] = []
    extraneous: list[DetectedChange] = []

    all_keys = set(deep_by_key) | set(watch_by_key)
    for key in all_keys:
        key_lags, key_missed, key_extraneous = _match_one_key(
            deep_by_key.get(key, []), watch_by_key.get(key, [])
        )
        lags.extend(key_lags)
        missed.extend(key_missed)
        extraneous.extend(key_extraneous)

    deep_count = len(deep_changes)
    caught_count = len(lags)

    # Deterministic ordering, same rationale as scripts/verify/differ.py:
    # a replayed report should produce byte-identical output.
    missed.sort(key=lambda c: (c.account_id, c.source_type, c.detected_at))
    extraneous.sort(key=lambda c: (c.account_id, c.source_type, c.detected_at))

    p50_lag_hours, p95_lag_hours = _tail_percentiles(lags)

    return RecallReport(
        recall=(caught_count / deep_count) if deep_count else None,
        deep_count=deep_count,
        caught_count=caught_count,
        missed_count=len(missed),
        p50_lag_hours=p50_lag_hours,
        p95_lag_hours=p95_lag_hours,
        missed=tuple(missed),
        extraneous_watch_count=len(extraneous),
        extraneous_watch=tuple(extraneous),
    )
