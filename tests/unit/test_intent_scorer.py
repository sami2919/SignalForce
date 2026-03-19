"""Tests for the intent-weighted scoring engine.

TDD: These tests are written FIRST. They define the expected behavior
before any implementation exists.
"""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from pathlib import Path

import pytest

from scripts.models import ICPScore, Signal, SignalStrength
from scripts.config_loader import load_config
from scripts.intent_scorer import (
    IntentScorer,
)

_CONFIG = load_config(Path(__file__).parent.parent / "fixtures" / "sample_config.yaml")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_signal(
    signal_type: str = "github",
    strength: SignalStrength = SignalStrength.MODERATE,
    age_days: float = 0,
    company_name: str = "TestCo",
    company_domain: str | None = "testco.com",
) -> Signal:
    metadata: dict = {}
    if signal_type == "github":
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
    """Intent weights from config follow expected ordering."""

    def test_arxiv_weight_is_configured(self):
        assert _CONFIG.scoring.intent_weights["arxiv"] == 3.0

    def test_github_weight_is_configured(self):
        assert _CONFIG.scoring.intent_weights["github"] == 2.5

    def test_all_configured_weights_are_positive(self):
        for st, w in _CONFIG.scoring.intent_weights.items():
            assert w > 0, f"Weight for {st} must be positive"

    def test_arxiv_has_highest_configured_weight(self):
        assert _CONFIG.scoring.intent_weights["arxiv"] == max(
            _CONFIG.scoring.intent_weights.values()
        )

    def test_github_weight_lower_than_arxiv(self):
        assert _CONFIG.scoring.intent_weights["github"] < _CONFIG.scoring.intent_weights["arxiv"]

    def test_unknown_signal_type_uses_fallback_weight(self):
        scorer = IntentScorer(_CONFIG)
        now = datetime.now(UTC)
        signal = make_signal(
            signal_type="unknown_type", strength=SignalStrength.MODERATE, age_days=0
        )
        score = scorer.calculate_intent_score([signal], now=now)
        # fallback weight = 1.0, MODERATE=2, decay≈1, breadth=1 → 2.0
        assert score == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# TestCalculateIntentScore
# ---------------------------------------------------------------------------


class TestCalculateIntentScore:
    """calculate_intent_score computes intent from a list of signals."""

    def setup_method(self):
        self.scorer = IntentScorer(_CONFIG)

    def test_empty_signals_returns_zero(self):
        assert self.scorer.calculate_intent_score([]) == 0.0

    def test_fresh_strong_signal_scores_high(self):
        now = datetime.now(UTC)
        signal = make_signal(
            signal_type="arxiv",
            strength=SignalStrength.STRONG,
            age_days=0,
        )
        score = self.scorer.calculate_intent_score([signal], now=now)
        # STRONG=3 × arxiv_weight=3.0 × decay≈1.0 × breadth_multiplier=1.0 ≈ 9.0
        assert score > 8.0

    def test_stale_signal_scores_lower_than_fresh(self):
        now = datetime.now(UTC)
        fresh = make_signal(signal_type="github", strength=SignalStrength.STRONG, age_days=0)
        stale = make_signal(signal_type="github", strength=SignalStrength.STRONG, age_days=30)

        fresh_score = self.scorer.calculate_intent_score([fresh], now=now)
        stale_score = self.scorer.calculate_intent_score([stale], now=now)

        assert fresh_score > stale_score

    def test_stale_signal_decay_significant(self):
        """Signal at 6× half-life should be < 2% of original strength."""
        now = datetime.now(UTC)
        # github half-life = 5 days (from sample_config); 30 days = 6 half-lives → decay ≈ 2^-6 ≈ 0.0156
        signal = make_signal(signal_type="github", strength=SignalStrength.STRONG, age_days=30)
        score = self.scorer.calculate_intent_score([signal], now=now)
        max_possible = (
            int(SignalStrength.STRONG) * _CONFIG.scoring.intent_weights["github"] * 1.0
        )  # no breadth bonus
        assert score < max_possible * 0.02

    def test_multi_source_gets_breadth_bonus(self):
        """Two different signal types should score higher than two identical types."""
        now = datetime.now(UTC)
        signal_a = make_signal(signal_type="github", strength=SignalStrength.MODERATE, age_days=0)
        signal_b = make_signal(signal_type="arxiv", strength=SignalStrength.MODERATE, age_days=0)
        signal_dup = make_signal(signal_type="github", strength=SignalStrength.MODERATE, age_days=0)

        multi_source_score = self.scorer.calculate_intent_score([signal_a, signal_b], now=now)
        single_source_score = self.scorer.calculate_intent_score([signal_a, signal_dup], now=now)

        assert multi_source_score > single_source_score

    def test_three_source_types_higher_than_two(self):
        now = datetime.now(UTC)
        s1 = make_signal(signal_type="github", strength=SignalStrength.MODERATE, age_days=0)
        s2 = make_signal(signal_type="arxiv", strength=SignalStrength.MODERATE, age_days=0)
        s3 = make_signal(signal_type="job_posting", strength=SignalStrength.MODERATE, age_days=0)

        three_type_score = self.scorer.calculate_intent_score([s1, s2, s3], now=now)
        two_type_score = self.scorer.calculate_intent_score([s1, s2], now=now)

        assert three_type_score > two_type_score

    def test_now_defaults_to_utc_current_time(self):
        """Calling without now= should not raise and should return a plausible value."""
        signal = make_signal(age_days=1)
        score = self.scorer.calculate_intent_score([signal])
        assert score >= 0.0

    def test_breadth_multiplier_4_plus_types_uses_fallback(self):
        """4 unique source types should use the 3.0 fallback multiplier."""
        now = datetime.now(UTC)
        signals = [
            make_signal(signal_type="github", strength=SignalStrength.WEAK, age_days=0),
            make_signal(signal_type="arxiv", strength=SignalStrength.WEAK, age_days=0),
            make_signal(signal_type="job_posting", strength=SignalStrength.WEAK, age_days=0),
            make_signal(signal_type="funding_event", strength=SignalStrength.WEAK, age_days=0),
        ]
        # 4 types → fallback multiplier 3.0
        score_4 = self.scorer.calculate_intent_score(signals, now=now)

        # 3 of the same 4 signals (3 unique types → multiplier 2.0)
        score_3 = self.scorer.calculate_intent_score(signals[:3], now=now)

        # Fallback 3.0 > standard 2.0 after accounting for the extra signal
        # The 4th signal adds funding weight=1.0(fallback) × WEAK=1 × decay≈1 = 1.0, then ×3.0
        # Verify 4-type score is strictly positive and higher breadth-corrected
        assert score_4 > 0.0
        # Raw sum for 4 types with fallback 3.0 vs 3 types with multiplier 2.0:
        # score_4 = (raw_3 + funding_contribution) * 3.0
        # score_3 = raw_3 * 2.0
        # Since 3.0 > 2.0 and raw_4 > raw_3, score_4 > score_3
        assert score_4 > score_3


# ---------------------------------------------------------------------------
# TestCalculateCombinedScore
# ---------------------------------------------------------------------------


class TestCalculateCombinedScore:
    """calculate_combined_score applies Gojiberry formula: 60% intent + 40% ICP."""

    def setup_method(self):
        self.scorer = IntentScorer(_CONFIG)

    def test_zero_inputs_return_zero(self):
        assert self.scorer.calculate_combined_score(0.0, 0.0) == 0.0

    def test_intent_weight_is_60_percent(self):
        # Only intent, no ICP fit
        score = self.scorer.calculate_combined_score(icp_fit=0.0, intent_score=10.0)
        assert score == pytest.approx(6.0)

    def test_icp_weight_is_40_percent(self):
        # Only ICP fit, no intent
        score = self.scorer.calculate_combined_score(icp_fit=10.0, intent_score=0.0)
        assert score == pytest.approx(4.0)

    def test_both_components_combined(self):
        score = self.scorer.calculate_combined_score(icp_fit=5.0, intent_score=5.0)
        assert score == pytest.approx(5.0)

    def test_intent_dominates_over_icp(self):
        """High intent + low ICP should outscore high ICP + low intent."""
        high_intent = self.scorer.calculate_combined_score(icp_fit=2.0, intent_score=10.0)
        high_icp = self.scorer.calculate_combined_score(icp_fit=10.0, intent_score=2.0)
        assert high_intent > high_icp

    def test_formula_gojiberry(self):
        """Explicitly validate formula: COMBINED = (ICP × 0.4) + (Intent × 0.6)."""
        icp_fit = 7.5
        intent_score = 4.2
        expected = (icp_fit * 0.4) + (intent_score * 0.6)
        assert self.scorer.calculate_combined_score(icp_fit, intent_score) == pytest.approx(
            expected
        )


# ---------------------------------------------------------------------------
# TestIntentScorer
# ---------------------------------------------------------------------------


class TestIntentScorer:
    """IntentScorer.score_signals returns correct ScoringResult objects."""

    def test_fresh_multi_source_yields_a_tier(self):
        now = datetime.now(UTC)
        signals = [
            make_signal(signal_type="arxiv", strength=SignalStrength.STRONG, age_days=0),
            make_signal(signal_type="github", strength=SignalStrength.STRONG, age_days=0),
            make_signal(signal_type="job_posting", strength=SignalStrength.STRONG, age_days=0),
        ]
        scorer = IntentScorer(_CONFIG)
        result = scorer.score_signals(signals, icp_fit=10.0, now=now)
        assert result.icp_score == ICPScore.A

    def test_stale_single_source_yields_c_or_d_tier(self):
        now = datetime.now(UTC)
        signals = [
            make_signal(signal_type="funding_event", strength=SignalStrength.WEAK, age_days=90),
        ]
        scorer = IntentScorer(_CONFIG)
        result = scorer.score_signals(signals, icp_fit=1.0, now=now)
        assert result.icp_score in (ICPScore.C, ICPScore.D)

    def test_result_has_intent_score(self):
        now = datetime.now(UTC)
        signal = make_signal(age_days=0)
        scorer = IntentScorer(_CONFIG)
        result = scorer.score_signals([signal], icp_fit=5.0, now=now)
        assert isinstance(result.intent_score, float)
        assert result.intent_score >= 0.0

    def test_result_has_combined_score(self):
        now = datetime.now(UTC)
        signal = make_signal(age_days=0)
        scorer = IntentScorer(_CONFIG)
        result = scorer.score_signals([signal], icp_fit=5.0, now=now)
        assert isinstance(result.combined_score, float)
        assert result.combined_score >= 0.0

    def test_result_is_frozen_dataclass(self):
        scorer = IntentScorer(_CONFIG)
        result = scorer.score_signals([], icp_fit=0.0)
        with pytest.raises((AttributeError, TypeError)):
            result.intent_score = 99.0  # type: ignore[misc]

    def test_signal_count_matches_input(self):
        now = datetime.now(UTC)
        signals = [make_signal(age_days=i) for i in range(4)]
        scorer = IntentScorer(_CONFIG)
        result = scorer.score_signals(signals, icp_fit=5.0, now=now)
        assert result.signal_count == 4

    def test_source_types_counts_unique_types(self):
        now = datetime.now(UTC)
        signals = [
            make_signal(signal_type="github", age_days=0),
            make_signal(signal_type="github", age_days=1),
            make_signal(signal_type="arxiv", age_days=0),
        ]
        scorer = IntentScorer(_CONFIG)
        result = scorer.score_signals(signals, icp_fit=5.0, now=now)
        assert result.source_types == 2

    def test_empty_signals_returns_d_grade(self):
        scorer = IntentScorer(_CONFIG)
        result = scorer.score_signals([], icp_fit=0.0)
        assert result.icp_score == ICPScore.D
        assert result.combined_score == 0.0

    def test_b_tier_threshold(self):
        """combined_score >= 5.0 and < 8.0 should yield B."""
        scorer = IntentScorer(_CONFIG)
        assert scorer._determine_grade(7.9) == ICPScore.B
        assert scorer._determine_grade(8.0) == ICPScore.A
        assert scorer._determine_grade(4.9) == ICPScore.C
        assert scorer._determine_grade(5.0) == ICPScore.B

    def test_now_parameter_propagated_to_intent(self):
        """Passing a fixed `now` should give deterministic results."""
        fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        signal = make_signal(
            signal_type="github",
            strength=SignalStrength.MODERATE,
            age_days=0,
        )
        # Override detected_at to fixed time
        signal = signal.model_copy(update={"detected_at": fixed_now})
        scorer = IntentScorer(_CONFIG)
        r1 = scorer.score_signals([signal], icp_fit=5.0, now=fixed_now)
        r2 = scorer.score_signals([signal], icp_fit=5.0, now=fixed_now)
        assert r1.intent_score == r2.intent_score
