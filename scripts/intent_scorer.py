"""Intent-weighted scoring engine.

Implements the Gojiberry formula: COMBINED = (ICP_Fit × 0.4) + (Intent × 0.6)

Intent scoring applies:
1. Signal-type-specific weights (papers > code > hiring > funding)
2. Recency decay (fresh signals score higher)
3. Breadth multiplier (multi-source signals score higher)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from scripts.models import ICPScore, Signal, SignalType
from scripts.recency import SignalHalfLife, apply_recency_weight


# Intent weights by signal type — higher = stronger buying intent
INTENT_WEIGHTS: dict[SignalType, float] = {
    SignalType.LINKEDIN_ACTIVITY: 3.0,  # Real-time engagement = highest urgency
    SignalType.ARXIV_PAPER: 3.0,
    SignalType.GITHUB_RL_REPO: 2.5,
    SignalType.HUGGINGFACE_MODEL: 2.5,
    SignalType.JOB_POSTING: 2.0,
    SignalType.FUNDING_EVENT: 1.5,
}

# Map signal types to their decay half-lives (in days)
_HALF_LIVES: dict[SignalType, float] = {
    SignalType.GITHUB_RL_REPO: SignalHalfLife.GITHUB_RL_REPO,
    SignalType.ARXIV_PAPER: SignalHalfLife.ARXIV_PAPER,
    SignalType.JOB_POSTING: SignalHalfLife.JOB_POSTING,
    SignalType.HUGGINGFACE_MODEL: SignalHalfLife.HUGGINGFACE_MODEL,
    SignalType.FUNDING_EVENT: SignalHalfLife.FUNDING_EVENT,
    SignalType.LINKEDIN_ACTIVITY: SignalHalfLife.LINKEDIN_ACTIVITY,
}

# Breadth multiplier keyed on number of unique source types;
# values beyond 3 use _BREADTH_FALLBACK.
_BREADTH_MULTIPLIER: dict[int, float] = {1: 1.0, 2: 1.5, 3: 2.0}
_BREADTH_FALLBACK = 3.0

# Grade thresholds: first matching threshold wins (list is ordered descending)
_GRADE_THRESHOLDS: list[tuple[float, ICPScore]] = [
    (8.0, ICPScore.A),
    (5.0, ICPScore.B),
    (2.0, ICPScore.C),
]


@dataclass(frozen=True)
class ScoringResult:
    """Result of scoring a company's signals."""

    intent_score: float
    combined_score: float
    icp_score: ICPScore
    signal_count: int
    source_types: int


def calculate_intent_score(signals: list[Signal], now: datetime | None = None) -> float:
    """Calculate intent score from a list of signals.

    For each signal:
        weighted_value = strength × intent_weight × recency_decay

    The sum is then scaled by a breadth multiplier based on the number of
    unique signal source types present.
    """
    if not signals:
        return 0.0
    if now is None:
        now = datetime.now(UTC)

    total = 0.0
    for signal in signals:
        intent_weight = INTENT_WEIGHTS.get(signal.signal_type, 1.0)
        half_life = _HALF_LIVES.get(signal.signal_type, 7.0)
        recency_weighted = apply_recency_weight(
            signal_strength=int(signal.signal_strength),
            signal_time=signal.detected_at,
            now=now,
            half_life_days=half_life,
        )
        total += recency_weighted * intent_weight

    unique_types = len({s.signal_type for s in signals})
    multiplier = _BREADTH_MULTIPLIER.get(unique_types, _BREADTH_FALLBACK)
    return total * multiplier


def calculate_combined_score(icp_fit: float, intent_score: float) -> float:
    """Apply the Gojiberry formula: COMBINED = (ICP_Fit × 0.4) + (Intent × 0.6).

    Intent receives 60% weight because timing beats targeting.
    """
    return (icp_fit * 0.4) + (intent_score * 0.6)


def _determine_grade(combined_score: float) -> ICPScore:
    """Map a combined score to an ICP grade (A/B/C/D)."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if combined_score >= threshold:
            return grade
    return ICPScore.D


class IntentScorer:
    """Intent-weighted scoring engine for company signals."""

    def score_signals(
        self,
        signals: list[Signal],
        icp_fit: float,
        now: datetime | None = None,
    ) -> ScoringResult:
        """Score a company's signals and return a ScoringResult.

        Args:
            signals:   All detected signals for the company.
            icp_fit:   ICP fit score (0–10 scale recommended).
            now:       Reference time for decay calculations (defaults to UTC now).

        Returns:
            Frozen ScoringResult with intent, combined score, grade, and metadata.
        """
        intent = calculate_intent_score(signals, now)
        combined = calculate_combined_score(icp_fit, intent)
        grade = _determine_grade(combined)
        return ScoringResult(
            intent_score=intent,
            combined_score=combined,
            icp_score=grade,
            signal_count=len(signals),
            source_types=len({s.signal_type for s in signals}),
        )


if __name__ == "__main__":  # pragma: no cover
    import sys

    print("IntentScorer — Gojiberry formula demo")
    print("COMBINED = (ICP_Fit × 0.4) + (Intent × 0.6)")
    print()
    print("Intent weights:")
    for st, w in INTENT_WEIGHTS.items():
        print(f"  {st.value:<25} {w}")
    sys.exit(0)
