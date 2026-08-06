"""Deterministic, traceable account scoring.

Every score carries a trace so it can be replayed and so individual signals can
be zeroed out to isolate their contribution. Sami (Rippling, 20:24): "zero out
which signal one by one and see which one was actually doing the work."

Deterministic, not learned, on purpose: when a rep says "this account was
terrible," you need to explain WHY it scored 87, not shrug at a model.

ADR-0015 is the spec for everything in this file EXCEPT `_combine` — that
function is deliberately left unimplemented. It's the one place this module
encodes a product opinion (how decayed signal contributions turn into a single
0-100 number) rather than mechanism, and per the plan's Task 4.1 it's meant to
be written by hand, not scaffolded. See its docstring below for the contract
it must satisfy.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

HALF_LIFE_DAYS = 14.0
ICP_WEIGHT = 0.4
INTENT_WEIGHT = 0.6

_SCORE_MIN = 0.0
_SCORE_MAX = 100.0


class SignalInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_type: str
    detected_at: datetime
    base_weight: float
    is_icp: bool = False


class ScoreComponent(BaseModel):
    """One signal's decayed contribution, typed (ADR-0015 Decision 1) rather
    than a raw dict -- matches every other pure function in this codebase
    (DetectedChange, ProbeOutcome, FactChange)."""

    model_config = ConfigDict(frozen=True)

    signal_type: str
    base_weight: float
    age_days: float
    decay: float
    decayed_weight: float
    is_icp: bool


class ScoreResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: float
    trace: dict


def recency_decay(
    detected_at: datetime, now: datetime, half_life_days: float = HALF_LIFE_DAYS
) -> float:
    """Exponential decay. A 48h-old signal is worth far more than a 6-week-old one.

    Clamped at age >= 0: a `detected_at` slightly after `now` (clock skew
    between whatever recorded the signal and whatever is scoring it) must not
    produce a decay > 1.0 or a negative age feeding into `math.pow`.
    """
    age_days = max((now - detected_at).total_seconds() / 86400.0, 0.0)
    return math.pow(0.5, age_days / half_life_days)


def _combine(components: list[ScoreComponent]) -> float:
    """Combine decayed signal contributions into a 0-100 account score.

    Each `ScoreComponent` has:
        signal_type: str
        base_weight: float      (0-1, per-signal-type importance)
        age_days: float
        decay: float            (0-1, exponential, 14-day half-life)
        decayed_weight: float   (base_weight * decay)
        is_icp: bool            (True = fit signal, False = intent signal)

    Must satisfy the tests in tests/scoring/test_engine.py:
      - recent > old for identical signals
      - three weak converging signals > one strong signal
      - empty list returns 0.0
      - output bounded 0-100 (score_account clamps as a safety net -- ADR-0015
        Decision 2 -- but _combine should still aim to stay in range on its own)

    Consider: how do you express breadth? A multiplier on distinct signal_type
    count? Diminishing returns via sqrt or log on the sum? A convergence bonus
    that only fires at 3+ distinct types? Each choice says something different
    about what you believe a "buying window" is.
    """
    # TODO(sami): ~10 lines. This is the opinion at the center of the product.
    raise NotImplementedError("_combine is Task 4.1's one hand-written piece — see its docstring")


def score_account(signals: list[SignalInput], now: datetime) -> ScoreResult:
    """Score an account, recording every contribution in the trace."""
    components: list[ScoreComponent] = []
    for sig in signals:
        decay = recency_decay(sig.detected_at, now)
        components.append(
            ScoreComponent(
                signal_type=sig.signal_type,
                base_weight=sig.base_weight,
                age_days=round((now - sig.detected_at).total_seconds() / 86400.0, 2),
                decay=round(decay, 4),
                decayed_weight=round(sig.base_weight * decay, 4),
                is_icp=sig.is_icp,
            )
        )

    raw_score = _combine(components)

    score = min(max(raw_score, _SCORE_MIN), _SCORE_MAX)
    if score != raw_score:
        logger.warning(
            "score_account: _combine returned %.4f, outside [%.0f, %.0f] -- clamped to %.2f",
            raw_score,
            _SCORE_MIN,
            _SCORE_MAX,
            score,
        )

    return ScoreResult(
        score=round(score, 2),
        trace={
            "components": [c.model_dump(mode="json") for c in components],
            "half_life_days": HALF_LIFE_DAYS,
            "icp_weight": ICP_WEIGHT,
            "intent_weight": INTENT_WEIGHT,
            "computed_at": now.isoformat(),
        },
    )


def zero_out(signals: list[SignalInput], signal_type: str, now: datetime) -> ScoreResult:
    """Rescore with one signal type removed. Isolates its real contribution."""
    return score_account([s for s in signals if s.signal_type != signal_type], now=now)
