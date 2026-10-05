"""Tests for scripts/scoring/engine.py.

ADR-0015 is the spec for the scaffold (everything except `_combine`, which is the
user's own contribution per the plan's Task 4.1 -- see docs/superpowers/plans/
2026-08-04-signalforce-production.md, "Your Contribution"). These tests exercise the
scaffold's own behavior (recency decay, trace recording, zero_out, clamping) plus the
product-level tests `_combine` itself must satisfy once written (recency ordering,
breadth-beats-one-strong-signal, empty-is-zero) -- those will fail with
NotImplementedError until `_combine` is filled in.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.scoring.engine import (
    HALF_LIFE_DAYS,
    ScoreComponent,
    SignalInput,
    recency_decay,
    score_account,
    zero_out,
)

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _sig(kind, days_ago, weight=1.0, is_icp=False) -> SignalInput:
    return SignalInput(
        signal_type=kind,
        detected_at=NOW - timedelta(days=days_ago),
        base_weight=weight,
        is_icp=is_icp,
    )


# ---------------------------------------------------------------------------
# recency_decay -- pure, scaffolded, no dependency on _combine
# ---------------------------------------------------------------------------


def test_recency_decay_is_one_at_zero_age():
    assert recency_decay(NOW, NOW) == pytest.approx(1.0)


def test_recency_decay_is_half_at_the_half_life():
    decayed_at = NOW - timedelta(days=HALF_LIFE_DAYS)
    assert recency_decay(decayed_at, NOW) == pytest.approx(0.5)


def test_recency_decay_never_goes_negative_for_a_future_timestamp():
    """detected_at slightly after `now` (clock skew) must not decay to a value
    greater than 1.0 or produce a negative age."""
    future = NOW + timedelta(hours=1)
    assert recency_decay(future, NOW) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# score_account / _combine -- the product-level contract _combine must satisfy.
# These are the plan's own acceptance tests for the user's contribution.
# ---------------------------------------------------------------------------


def test_empty_signals_score_zero():
    assert score_account([], now=NOW).score == 0.0


def test_recent_signal_outscores_old_signal():
    recent = score_account([_sig("hiring", 1)], now=NOW)
    old = score_account([_sig("hiring", 60)], now=NOW)
    assert recent.score > old.score


def test_breadth_beats_a_single_strong_signal():
    """Sami's stated philosophy: three weak converging > one flashy."""
    three_weak = score_account(
        [_sig("hiring", 3, 0.4), _sig("funding", 5, 0.4), _sig("stack", 4, 0.4)],
        now=NOW,
    )
    one_strong = score_account([_sig("hiring", 3, 1.0)], now=NOW)
    assert three_weak.score > one_strong.score


def test_trace_records_every_contribution():
    result = score_account([_sig("hiring", 1), _sig("funding", 2)], now=NOW)
    assert len(result.trace["components"]) == 2
    assert all("decayed_weight" in c for c in result.trace["components"])


def test_zero_out_isolates_a_signals_contribution():
    signals = [_sig("hiring", 1), _sig("funding", 2)]
    full = score_account(signals, now=NOW)
    without = zero_out(signals, "hiring", now=NOW)
    assert without.score < full.score


# ---------------------------------------------------------------------------
# ADR-0015 Decision 2: score_account clamps _combine's output to [0, 100],
# visibly. These tests don't depend on the user's real _combine -- they
# monkeypatch it directly, so they can be run and trusted independently of
# whatever weighting logic eventually lands.
# ---------------------------------------------------------------------------


def test_score_is_clamped_to_100_and_logs_a_warning(monkeypatch, caplog):
    import scripts.scoring.engine as engine_module

    monkeypatch.setattr(engine_module, "_combine", lambda components: 340.0)

    with caplog.at_level("WARNING", logger="scripts.scoring.engine"):
        result = score_account([_sig("hiring", 1)], now=NOW)

    assert result.score == 100.0
    assert any("clamp" in r.message.lower() for r in caplog.records)


def test_score_is_clamped_to_0_and_logs_a_warning(monkeypatch, caplog):
    import scripts.scoring.engine as engine_module

    monkeypatch.setattr(engine_module, "_combine", lambda components: -12.0)

    with caplog.at_level("WARNING", logger="scripts.scoring.engine"):
        result = score_account([_sig("hiring", 1)], now=NOW)

    assert result.score == 0.0
    assert any("clamp" in r.message.lower() for r in caplog.records)


def test_a_score_already_in_range_is_not_flagged_as_clamped(monkeypatch, caplog):
    import scripts.scoring.engine as engine_module

    monkeypatch.setattr(engine_module, "_combine", lambda components: 42.0)

    with caplog.at_level("WARNING", logger="scripts.scoring.engine"):
        result = score_account([_sig("hiring", 1)], now=NOW)

    assert result.score == 42.0
    assert not any("clamp" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# _combine's actual formula, pinned. The tests above only check relative
# orderings (recent > old, breadth > single) -- robust to almost any
# monotonic transformation, so they don't catch a mutation that just rescales
# everything uniformly. Mutation-confirmed: removing the is_icp split, the
# sqrt dampening, or the distinct-vs-total-count breadth check all survived
# the ordering-only tests above. These pin exact values by hand.
# ---------------------------------------------------------------------------


def test_icp_and_intent_signals_are_weighted_differently():
    """ICP_WEIGHT=0.4, INTENT_WEIGHT=0.6 must actually apply -- an is_icp
    signal and an otherwise-identical intent signal must score differently,
    not just both count the same."""
    icp_only = score_account([_sig("stack", 0, weight=1.0, is_icp=True)], now=NOW)
    intent_only = score_account([_sig("hiring", 0, weight=1.0, is_icp=False)], now=NOW)

    assert icp_only.score == pytest.approx(12.65, abs=1e-2)
    assert intent_only.score == pytest.approx(15.49, abs=1e-2)
    assert intent_only.score > icp_only.score  # 0.6 > 0.4


def test_three_signals_of_the_same_type_get_no_breadth_bonus():
    """Breadth is rewarded per DISTINCT signal_type, not per signal count --
    three "hiring" signals must score as one undifferentiated pool, not get
    the same breadth credit as three different signal types."""
    same_type = score_account(
        [_sig("hiring", 0, 0.3), _sig("hiring", 0, 0.3), _sig("hiring", 0, 0.3)], now=NOW
    )
    assert same_type.score == pytest.approx(14.70, abs=1e-2)


def test_three_distinct_types_score_higher_than_three_of_the_same_type():
    """Isolates the breadth multiplier specifically: identical total weight,
    only signal_type diversity differs."""
    same_type = score_account(
        [_sig("hiring", 0, 0.3), _sig("hiring", 0, 0.3), _sig("hiring", 0, 0.3)], now=NOW
    )
    distinct_types = score_account(
        [_sig("hiring", 0, 0.3), _sig("funding", 0, 0.3), _sig("stack", 0, 0.3)], now=NOW
    )
    assert distinct_types.score > same_type.score


# ---------------------------------------------------------------------------
# ADR-0015 Decision 1: _combine receives typed ScoreComponent objects.
# ---------------------------------------------------------------------------


def test_combine_receives_typed_score_components(monkeypatch):
    import scripts.scoring.engine as engine_module

    seen: list[object] = []

    def _spy(components):
        seen.extend(components)
        return 0.0

    monkeypatch.setattr(engine_module, "_combine", _spy)
    score_account([_sig("hiring", 1, 0.7, is_icp=True)], now=NOW)

    assert len(seen) == 1
    assert isinstance(seen[0], ScoreComponent)
    assert seen[0].signal_type == "hiring"
    assert seen[0].base_weight == 0.7
    assert seen[0].is_icp is True


def test_trace_components_are_plain_dicts_not_score_component_objects():
    """The persisted/logged trace shape must stay a plain dict (JSON-serializable
    for the eventual Score.trace column), regardless of ScoreComponent being used
    internally for _combine's input."""
    result = score_account([_sig("hiring", 1)], now=NOW)
    assert isinstance(result.trace["components"][0], dict)
