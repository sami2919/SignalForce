"""Intent-weighted scoring engine.

Implements the Gojiberry formula: COMBINED = (ICP_Fit × icp_weight) + (Intent × intent_weight)

Intent scoring applies:
1. Signal-type-specific weights (configured per deployment)
2. Recency decay (fresh signals score higher)
3. Breadth multiplier (multi-source signals score higher)

Weights, half-lives, and grade thresholds are loaded from SignalForceConfig.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from scripts.models import ICPScore, Signal
from scripts.recency import apply_recency_weight
from scripts.config_loader import SignalForceConfig


# Breadth multiplier keyed on number of unique source types;
# values beyond 3 use _BREADTH_FALLBACK.
_BREADTH_MULTIPLIER: dict[int, float] = {1: 1.0, 2: 1.5, 3: 2.0}
_BREADTH_FALLBACK = 3.0


@dataclass(frozen=True)
class ScoringResult:
    """Result of scoring a company's signals."""

    intent_score: float
    combined_score: float
    icp_score: ICPScore
    signal_count: int
    source_types: int


class IntentScorer:
    """Intent-weighted scoring engine for company signals."""

    def __init__(self, config: SignalForceConfig) -> None:
        self._weights = config.scoring.intent_weights
        self._half_lives = config.scoring.half_lives_days
        self._icp_weight = config.scoring.icp_weight
        self._intent_weight = config.scoring.intent_weight
        thresholds = config.scoring.grade_thresholds
        # Build sorted list of (threshold, grade) for descending comparison
        self._grade_thresholds: list[tuple[float, ICPScore]] = sorted(
            ((v, ICPScore(k)) for k, v in thresholds.items()),
            key=lambda t: t[0],
            reverse=True,
        )

    def calculate_intent_score(self, signals: list[Signal], now: datetime | None = None) -> float:
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
            intent_weight = self._weights.get(signal.signal_type, 1.0)
            half_life = self._half_lives.get(signal.signal_type, 7.0)
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

    def calculate_combined_score(self, icp_fit: float, intent_score: float) -> float:
        """Apply the Gojiberry formula: COMBINED = (ICP_Fit × icp_weight) + (Intent × intent_weight).

        Intent receives higher weight because timing beats targeting.
        """
        return (icp_fit * self._icp_weight) + (intent_score * self._intent_weight)

    def _determine_grade(self, combined_score: float) -> ICPScore:
        """Map a combined score to an ICP grade (A/B/C/D)."""
        for threshold, grade in self._grade_thresholds:
            if combined_score >= threshold:
                return grade
        return ICPScore.D

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
        intent = self.calculate_intent_score(signals, now)
        combined = self.calculate_combined_score(icp_fit, intent)
        grade = self._determine_grade(combined)
        return ScoringResult(
            intent_score=intent,
            combined_score=combined,
            icp_score=grade,
            signal_count=len(signals),
            source_types=len({s.signal_type for s in signals}),
        )


if __name__ == "__main__":  # pragma: no cover
    import sys
    from scripts.config_loader import load_config

    config = load_config()
    scorer = IntentScorer(config)
    print("IntentScorer — Gojiberry formula demo")
    print(
        f"COMBINED = (ICP_Fit × {config.scoring.icp_weight}) + (Intent × {config.scoring.intent_weight})"
    )
    print()
    print("Intent weights:")
    for st, w in config.scoring.intent_weights.items():
        print(f"  {st:<25} {w}")
    sys.exit(0)
