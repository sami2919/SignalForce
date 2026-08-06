"""Tests for scripts/measure/lag.py.

ADR-0010 (docs/decisions/0010-holdout-deep-scan-and-recall.md) Decision 4 is
the spec. The plan's reference `compute_recall` keeps ONE watch timestamp per
(account_id, source_type) key and matches every deep-scan event against it --
which silently mispairs a source's SECOND real change in a window against the
FIRST change's watch timestamp, producing a plausible-looking multi-day "lag"
for a change the watch layer never detected at all. This is fixed here by
matching deep and watch events per-key, in chronological order, position by
position -- the i-th real change against the i-th watch detection for that
same key.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.measure.lag import DetectedChange, compute_recall

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _dc(account_id: int, source_type: str, offset_hours: float) -> DetectedChange:
    return DetectedChange(
        account_id=account_id,
        source_type=source_type,
        detected_at=NOW + timedelta(hours=offset_hours),
    )


# ---------------------------------------------------------------------------
# From the plan — kept as regression tests for what did not change.
# ---------------------------------------------------------------------------


def test_perfect_recall_when_watch_caught_everything():
    deep = [_dc(1, "careers", 0)]
    watch = [_dc(1, "careers", 6)]
    report = compute_recall(deep, watch)
    assert report.recall == 1.0
    assert report.missed_count == 0


def test_missed_change_lowers_recall():
    deep = [_dc(1, "careers", 0), _dc(2, "careers", 0)]
    watch = [_dc(1, "careers", 0)]
    report = compute_recall(deep, watch)
    assert report.recall == 0.5
    assert report.missed_count == 1


def test_lag_is_positive_when_watch_was_faster():
    # deep detected at hour 12, watch detected at hour 0 -> watch was faster
    # (smaller timestamp) -> lag = deep - watch = +12 ("positive = watch won").
    deep = [_dc(1, "careers", 12)]
    watch = [_dc(1, "careers", 0)]
    assert compute_recall(deep, watch).p50_lag_hours == 12.0


def test_no_deep_changes_yields_undefined_recall_not_crash():
    report = compute_recall([], [])
    assert report.recall is None
    assert report.deep_count == 0


# ---------------------------------------------------------------------------
# ADR-0010 Decision 4 — the real fix: per-key sequential matching.
# ---------------------------------------------------------------------------


def test_second_real_change_on_the_same_key_is_not_mispaired_against_the_first_watch_timestamp():
    """The measured defect: source changes at hour 0 and again at hour 168
    (day 7). Watch catches the FIRST change 6 hours late. The plan's
    one-entry-per-key design would compute the SECOND deep event's lag
    against the FIRST watch timestamp: 168 - 6 = +162h, a nonsense number
    reported as if watch caught the day-7 change 162 hours "late" when watch
    never detected it at all. The fix must report it as a genuine miss.
    """
    deep = [_dc(1, "careers", 0), _dc(1, "careers", 168)]
    watch = [_dc(1, "careers", 6)]  # only ever caught the FIRST change

    report = compute_recall(deep, watch)

    assert report.deep_count == 2
    assert report.caught_count == 1
    assert report.missed_count == 1
    # The caught lag is the FIRST change's real lag: deep detected at hour 0,
    # watch 6h later at hour 6 -> lag = 0 - 6 = -6h (deep won; watch was
    # slow). Must not be corrupted by the second, unmatched deep event.
    assert report.p50_lag_hours == -6.0
    # No lag value anywhere near the nonsense +162h the old (one-entry-per-
    # key) design would have produced by pairing the day-7 event against
    # this same hour-6 watch timestamp.
    assert all(
        abs(v - 162.0) > 1.0 for v in [report.p50_lag_hours, report.p95_lag_hours] if v is not None
    )


def test_two_real_changes_both_caught_are_matched_to_the_correct_watch_event_each():
    deep = [_dc(1, "careers", 0), _dc(1, "careers", 100)]
    watch = [_dc(1, "careers", 4), _dc(1, "careers", 106)]  # watch 4h and 6h slow, respectively

    report = compute_recall(deep, watch)

    assert report.caught_count == 2
    assert report.missed_count == 0
    # lags: (0-4)=-4h, (100-106)=-6h. Nearest-rank percentile over
    # sorted([-6.0, -4.0]) at pct=0.5: idx=min(int(2*0.5),1)=1 -> -4.0.
    assert report.p50_lag_hours == -4.0
    assert report.p95_lag_hours == -4.0


def test_matching_is_chronological_not_input_order():
    """Deep events are supplied in REVERSE chronological order (list
    position does not match time order); watch events are supplied in
    forward order. If matching used list position (zip on the input order)
    instead of sorting each side by detected_at first, event 100 would pair
    against watch@4 and event 0 would pair against watch@106 -- a ~96h
    "lag" -- instead of the correct small pairings (0<->4, 100<->106).
    Mutation-confirmed: removing the sort produces p50=96.0 here; this test
    failed to catch that the first time because an earlier version of it
    used input orderings that accidentally stayed pairwise-aligned even
    without sorting.
    """
    deep = [_dc(1, "careers", 100), _dc(1, "careers", 0)]  # reverse chronological order
    watch = [_dc(1, "careers", 4), _dc(1, "careers", 106)]  # forward chronological order

    report = compute_recall(deep, watch)

    assert report.caught_count == 2
    assert report.missed_count == 0
    # Correct (sorted) pairing: (0,4)->-4h, (100,106)->-6h -- both small.
    assert all(v is not None and abs(v) < 24 for v in [report.p50_lag_hours, report.p95_lag_hours])


def test_watch_detection_with_no_corresponding_deep_change_is_extraneous_not_discarded():
    """The watch layer 'detecting' more changes than ground truth confirms
    happened (e.g. a cosmetic hash flip that confirm-on-change let through)
    is itself a signal about watch-layer precision and must be visible, not
    silently dropped."""
    deep = [_dc(1, "careers", 0)]
    watch = [_dc(1, "careers", 6), _dc(1, "careers", 50)]  # second has no deep match

    report = compute_recall(deep, watch)

    assert report.caught_count == 1
    assert report.missed_count == 0
    assert report.extraneous_watch_count == 1


def test_key_present_only_in_watch_is_fully_extraneous():
    deep = [_dc(1, "careers", 0)]
    watch = [_dc(1, "careers", 6), _dc(2, "careers", 6)]  # account 2 has no deep changes at all

    report = compute_recall(deep, watch)

    assert report.extraneous_watch_count == 1


def test_different_keys_do_not_interfere_with_each_other():
    deep = [_dc(1, "careers", 0), _dc(2, "pricing", 0)]
    watch = [_dc(1, "careers", 6)]  # account 2's change is missed entirely

    report = compute_recall(deep, watch)

    assert report.deep_count == 2
    assert report.caught_count == 1
    assert report.missed_count == 1


# ---------------------------------------------------------------------------
# Percentiles and recall math
# ---------------------------------------------------------------------------


def test_recall_is_none_when_deep_count_is_zero_but_watch_has_extraneous_entries():
    report = compute_recall([], [_dc(1, "careers", 0)])
    assert report.recall is None
    assert report.deep_count == 0
    assert report.extraneous_watch_count == 1


def test_recall_is_zero_when_nothing_was_caught():
    deep = [_dc(1, "careers", 0)]
    watch: list[DetectedChange] = []
    report = compute_recall(deep, watch)
    assert report.recall == 0.0
    assert report.missed_count == 1


# ---------------------------------------------------------------------------
# Deterministic output ordering -- a replayed report must be byte-identical
# regardless of input order, same rationale as scripts/verify/differ.py.
# ---------------------------------------------------------------------------


def test_missed_events_are_ordered_deterministically():
    # Two misses, deliberately supplied in an order that is NOT the expected
    # sorted output order, to prove ordering is enforced, not incidental.
    deep = [_dc(9, "careers", 0), _dc(2, "careers", 0), _dc(2, "blog", 0)]
    watch: list[DetectedChange] = []
    report = compute_recall(deep, watch)

    assert [(m.account_id, m.source_type) for m in report.missed] == [
        (2, "blog"),
        (2, "careers"),
        (9, "careers"),
    ]


def test_extraneous_watch_events_are_ordered_deterministically():
    deep: list[DetectedChange] = []
    watch = [_dc(9, "careers", 0), _dc(2, "careers", 0), _dc(2, "blog", 0)]
    report = compute_recall(deep, watch)

    assert [(e.account_id, e.source_type) for e in report.extraneous_watch] == [
        (2, "blog"),
        (2, "careers"),
        (9, "careers"),
    ]
