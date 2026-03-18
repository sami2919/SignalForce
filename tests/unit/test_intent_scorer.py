"""Tests for the intent-weighted scoring engine.

TDD: These tests are written FIRST. They define the expected behavior
before any implementation exists.
"""

from __future__ import annotations

from datetime import datetime, timedelta, UTC

import pytest

from scripts.models import ICPScore, Signal, SignalStrength, SignalType
from scripts.intent_scorer import (
    INTENT_WEIGHTS,
    IntentScorer,
    calculate_combined_score,
    calculate_intent_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_signal(
    signal_type: SignalType = SignalType.GITHUB_RL_REPO,
    strength: SignalStrength = SignalStrength.MODERATE,
    age_days: float = 0,
    company_name: str = "TestCo",
    company_domain: str | None = "testco.com",
) -> Signal:
    metadata: dict = {}
    if signal_type == SignalType.GITHUB_RL_REPO:
        metadata["repo_name"] = "test-repo"
    return Signal(
        signal_type=signal_type,
        company_name=company_name,
        company_domain=company_domain,
        signal_strength=strength,
        source_url="https://example.com",
        raw_data={},
        detected_at=datetime.now(UTC) - timedelta(days=age_days),
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# TestIntentWeights
# ---------------------------------------------------------------------------


class TestIntentWeights:
    """INTENT_WEIGHTS constants follow the ordering: papers > code > hiring > funding."""

    def test_arxiv_has_highest_weight(self):
        assert INTENT_WEIGHTS[SignalType.ARXIV_PAPER] == max(INTENT_WEIGHTS.values())

    def test_github_weight_is_high(self):
        # GitHub and HuggingFace should both be tied at 2.5 (code-level signals)
        assert INTENT_WEIGHTS[SignalType.GITHUB_RL_REPO] == 2.5
        assert INTENT_WEIGHTS[SignalType.HUGGINGFACE_MODEL] == 2.5

    def test_job_posting_weight_is_middle(self):
        assert INTENT_WEIGHTS[SignalType.JOB_POSTING] == 2.0

    def test_funding_has_lowest_weight(self):
        assert INTENT_WEIGHTS[SignalType.FUNDING_EVENT] == min(INTENT_WEIGHTS.values())

    def test_all_signal_types_have_weights(self):
        for signal_type in SignalType:
            assert signal_type in INTENT_WEIGHTS, f"Missing weight for {signal_type}"

    def test_all_weights_are_positive(self):
        for st, w in INTENT_WEIGHTS.items():
            assert w > 0, f"Weight for {st} must be positive"


# ---------------------------------------------------------------------------
# TestCalculateIntentScore
# ---------------------------------------------------------------------------


class TestCalculateIntentScore:
    """calculate_intent_score computes intent from a list of signals."""

    def test_empty_signals_returns_zero(self):
        assert calculate_intent_score([]) == 0.0

    def test_fresh_strong_signal_scores_high(self):
        now = datetime.now(UTC)
        signal = make_signal(
            signal_type=SignalType.ARXIV_PAPER,
            strength=SignalStrength.STRONG,
            age_days=0,
        )
        score = calculate_intent_score([signal], now=now)
        # STRONG=3 × arxiv_weight=3.0 × decay≈1.0 × breadth_multiplier=1.0 ≈ 9.0
        assert score > 8.0

    def test_stale_signal_scores_lower_than_fresh(self):
        now = datetime.now(UTC)
        fresh = make_signal(
            signal_type=SignalType.GITHUB_RL_REPO, strength=SignalStrength.STRONG, age_days=0
        )
        stale = make_signal(
            signal_type=SignalType.GITHUB_RL_REPO, strength=SignalStrength.STRONG, age_days=30
        )

        fresh_score = calculate_intent_score([fresh], now=now)
        stale_score = calculate_intent_score([stale], now=now)

        assert fresh_score > stale_score

    def test_stale_signal_decay_significant(self):
        """Signal at 6× half-life should be < 2% of original strength."""
        now = datetime.now(UTC)
        # GitHub half-life = 5 days; 30 days = 6 half-lives → decay ≈ 2^-6 ≈ 0.0156
        signal = make_signal(
            signal_type=SignalType.GITHUB_RL_REPO, strength=SignalStrength.STRONG, age_days=30
        )
        score = calculate_intent_score([signal], now=now)
        max_possible = (
            int(SignalStrength.STRONG) * INTENT_WEIGHTS[SignalType.GITHUB_RL_REPO] * 1.0
        )  # no breadth bonus
        assert score < max_possible * 0.02

    def test_multi_source_gets_breadth_bonus(self):
        """Two different signal types should score higher than two identical types."""
        now = datetime.now(UTC)
        signal_a = make_signal(
            signal_type=SignalType.GITHUB_RL_REPO, strength=SignalStrength.MODERATE, age_days=0
        )
        signal_b = make_signal(
            signal_type=SignalType.ARXIV_PAPER, strength=SignalStrength.MODERATE, age_days=0
        )
        signal_dup = make_signal(
            signal_type=SignalType.GITHUB_RL_REPO, strength=SignalStrength.MODERATE, age_days=0
        )

        multi_source_score = calculate_intent_score([signal_a, signal_b], now=now)
        single_source_score = calculate_intent_score([signal_a, signal_dup], now=now)

        assert multi_source_score > single_source_score

    def test_three_source_types_higher_than_two(self):
        now = datetime.now(UTC)
        s1 = make_signal(
            signal_type=SignalType.GITHUB_RL_REPO, strength=SignalStrength.MODERATE, age_days=0
        )
        s2 = make_signal(
            signal_type=SignalType.ARXIV_PAPER, strength=SignalStrength.MODERATE, age_days=0
        )
        s3 = make_signal(
            signal_type=SignalType.JOB_POSTING, strength=SignalStrength.MODERATE, age_days=0
        )

        three_type_score = calculate_intent_score([s1, s2, s3], now=now)
        two_type_score = calculate_intent_score([s1, s2], now=now)

        assert three_type_score > two_type_score

    def test_now_defaults_to_utc_current_time(self):
        """Calling without now= should not raise and should return a plausible value."""
        signal = make_signal(age_days=1)
        score = calculate_intent_score([signal])
        assert score >= 0.0

    def test_breadth_multiplier_4_plus_types_uses_fallback(self):
        """4 unique source types should use the 3.0 fallback multiplier."""
        now = datetime.now(UTC)
        signals = [
            make_signal(
                signal_type=SignalType.GITHUB_RL_REPO, strength=SignalStrength.WEAK, age_days=0
            ),
            make_signal(
                signal_type=SignalType.ARXIV_PAPER, strength=SignalStrength.WEAK, age_days=0
            ),
            make_signal(
                signal_type=SignalType.JOB_POSTING, strength=SignalStrength.WEAK, age_days=0
            ),
            make_signal(
                signal_type=SignalType.FUNDING_EVENT, strength=SignalStrength.WEAK, age_days=0
            ),
        ]
        # 4 types → fallback multiplier 3.0
        score_4 = calculate_intent_score(signals, now=now)

        # 3 of the same 4 signals (3 unique types → multiplier 2.0)
        score_3 = calculate_intent_score(signals[:3], now=now)

        # Fallback 3.0 > standard 2.0 after accounting for the extra signal
        # The 4th signal adds funding weight=1.5 × WEAK=1 × decay≈1 = 1.5, then ×3.0
        # Verify 4-type score is strictly positive and higher breadth-corrected
        assert score_4 > 0.0
        # Raw sum for 4 types with fallback 3.0 vs 3 types with multiplier 2.0:
        # Let raw_4 = raw_3 + funding_contribution
        # score_4 = (raw_3 + funding_contribution) * 3.0
        # score_3 = raw_3 * 2.0
        # Since 3.0 > 2.0 and raw_4 > raw_3, score_4 > score_3
        assert score_4 > score_3


# ---------------------------------------------------------------------------
# TestCalculateCombinedScore
# ---------------------------------------------------------------------------


class TestCalculateCombinedScore:
    """calculate_combined_score applies Gojiberry formula: 60% intent + 40% ICP."""

    def test_zero_inputs_return_zero(self):
        assert calculate_combined_score(0.0, 0.0) == 0.0

    def test_intent_weight_is_60_percent(self):
        # Only intent, no ICP fit
        score = calculate_combined_score(icp_fit=0.0, intent_score=10.0)
        assert score == pytest.approx(6.0)

    def test_icp_weight_is_40_percent(self):
        # Only ICP fit, no intent
        score = calculate_combined_score(icp_fit=10.0, intent_score=0.0)
        assert score == pytest.approx(4.0)

    def test_both_components_combined(self):
        score = calculate_combined_score(icp_fit=5.0, intent_score=5.0)
        assert score == pytest.approx(5.0)

    def test_intent_dominates_over_icp(self):
        """High intent + low ICP should outscore high ICP + low intent."""
        high_intent = calculate_combined_score(icp_fit=2.0, intent_score=10.0)
        high_icp = calculate_combined_score(icp_fit=10.0, intent_score=2.0)
        assert high_intent > high_icp

    def test_formula_gojiberry(self):
        """Explicitly validate formula: COMBINED = (ICP × 0.4) + (Intent × 0.6)."""
        icp_fit = 7.5
        intent_score = 4.2
        expected = (icp_fit * 0.4) + (intent_score * 0.6)
        assert calculate_combined_score(icp_fit, intent_score) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# TestIntentScorer
# ---------------------------------------------------------------------------


class TestIntentScorer:
    """IntentScorer.score_signals returns correct ScoringResult objects."""

    def test_fresh_multi_source_yields_a_tier(self):
        now = datetime.now(UTC)
        signals = [
            make_signal(
                signal_type=SignalType.ARXIV_PAPER, strength=SignalStrength.STRONG, age_days=0
            ),
            make_signal(
                signal_type=SignalType.GITHUB_RL_REPO, strength=SignalStrength.STRONG, age_days=0
            ),
            make_signal(
                signal_type=SignalType.JOB_POSTING, strength=SignalStrength.STRONG, age_days=0
            ),
        ]
        scorer = IntentScorer()
        result = scorer.score_signals(signals, icp_fit=10.0, now=now)
        assert result.icp_score == ICPScore.A

    def test_stale_single_source_yields_c_or_d_tier(self):
        now = datetime.now(UTC)
        signals = [
            make_signal(
                signal_type=SignalType.FUNDING_EVENT, strength=SignalStrength.WEAK, age_days=90
            ),
        ]
        scorer = IntentScorer()
        result = scorer.score_signals(signals, icp_fit=1.0, now=now)
        assert result.icp_score in (ICPScore.C, ICPScore.D)

    def test_result_has_intent_score(self):
        now = datetime.now(UTC)
        signal = make_signal(age_days=0)
        scorer = IntentScorer()
        result = scorer.score_signals([signal], icp_fit=5.0, now=now)
        assert isinstance(result.intent_score, float)
        assert result.intent_score >= 0.0

    def test_result_has_combined_score(self):
        now = datetime.now(UTC)
        signal = make_signal(age_days=0)
        scorer = IntentScorer()
        result = scorer.score_signals([signal], icp_fit=5.0, now=now)
        assert isinstance(result.combined_score, float)
        assert result.combined_score >= 0.0

    def test_result_is_frozen_dataclass(self):
        scorer = IntentScorer()
        result = scorer.score_signals([], icp_fit=0.0)
        with pytest.raises((AttributeError, TypeError)):
            result.intent_score = 99.0  # type: ignore[misc]

    def test_signal_count_matches_input(self):
        now = datetime.now(UTC)
        signals = [make_signal(age_days=i) for i in range(4)]
        scorer = IntentScorer()
        result = scorer.score_signals(signals, icp_fit=5.0, now=now)
        assert result.signal_count == 4

    def test_source_types_counts_unique_types(self):
        now = datetime.now(UTC)
        signals = [
            make_signal(signal_type=SignalType.GITHUB_RL_REPO, age_days=0),
            make_signal(signal_type=SignalType.GITHUB_RL_REPO, age_days=1),
            make_signal(signal_type=SignalType.ARXIV_PAPER, age_days=0),
        ]
        scorer = IntentScorer()
        result = scorer.score_signals(signals, icp_fit=5.0, now=now)
        assert result.source_types == 2

    def test_empty_signals_returns_d_grade(self):
        scorer = IntentScorer()
        result = scorer.score_signals([], icp_fit=0.0)
        assert result.icp_score == ICPScore.D
        assert result.combined_score == 0.0

    def test_b_tier_threshold(self):
        """combined_score >= 5.0 and < 8.0 should yield B."""
        from scripts.intent_scorer import _determine_grade

        assert _determine_grade(7.9) == ICPScore.B
        assert _determine_grade(8.0) == ICPScore.A
        assert _determine_grade(4.9) == ICPScore.C
        assert _determine_grade(5.0) == ICPScore.B

    def test_now_parameter_propagated_to_intent(self):
        """Passing a fixed `now` should give deterministic results."""
        fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        signal = make_signal(
            signal_type=SignalType.GITHUB_RL_REPO,
            strength=SignalStrength.MODERATE,
            age_days=0,
        )
        # Override detected_at to fixed time
        signal = signal.model_copy(update={"detected_at": fixed_now})
        scorer = IntentScorer()
        r1 = scorer.score_signals([signal], icp_fit=5.0, now=fixed_now)
        r2 = scorer.score_signals([signal], icp_fit=5.0, now=fixed_now)
        assert r1.intent_score == r2.intent_score
