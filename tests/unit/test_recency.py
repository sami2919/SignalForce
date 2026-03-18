"""Tests for recency decay functions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scripts.recency import (
    SignalHalfLife,
    apply_recency_weight,
    calculate_decay_factor,
)


class TestCalculateDecayFactor:
    def test_zero_age_returns_1(self):
        now = datetime.now(UTC)
        assert calculate_decay_factor(now, now, half_life_days=5) == pytest.approx(1.0)

    def test_one_half_life_returns_0_5(self):
        now = datetime.now(UTC)
        signal_time = now - timedelta(days=5)
        assert calculate_decay_factor(signal_time, now, half_life_days=5) == pytest.approx(0.5)

    def test_two_half_lives_returns_0_25(self):
        now = datetime.now(UTC)
        signal_time = now - timedelta(days=10)
        assert calculate_decay_factor(signal_time, now, half_life_days=5) == pytest.approx(0.25)

    def test_48_hours_fast_decay(self):
        now = datetime.now(UTC)
        signal_time = now - timedelta(hours=48)
        factor = calculate_decay_factor(signal_time, now, half_life_days=5)
        assert 0.7 < factor < 0.8

    def test_14_day_slow_decay(self):
        now = datetime.now(UTC)
        signal_time = now - timedelta(days=14)
        assert calculate_decay_factor(signal_time, now, half_life_days=14) == pytest.approx(0.5)

    def test_negative_age_clamps_to_1(self):
        now = datetime.now(UTC)
        future = now + timedelta(hours=1)
        assert calculate_decay_factor(future, now, half_life_days=5) == pytest.approx(1.0)

    def test_very_old_signal_near_zero(self):
        now = datetime.now(UTC)
        signal_time = now - timedelta(days=30)
        factor = calculate_decay_factor(signal_time, now, half_life_days=5)
        assert factor < 0.02


class TestApplyRecencyWeight:
    def test_applies_decay_to_strength(self):
        now = datetime.now(UTC)
        signal_time = now - timedelta(days=5)
        result = apply_recency_weight(
            signal_strength=3, signal_time=signal_time, now=now, half_life_days=5
        )
        assert result == pytest.approx(1.5)

    def test_fresh_signal_full_strength(self):
        now = datetime.now(UTC)
        result = apply_recency_weight(signal_strength=2, signal_time=now, now=now, half_life_days=5)
        assert result == pytest.approx(2.0)


class TestSignalHalfLife:
    def test_github_fast_decay(self):
        assert SignalHalfLife.GITHUB_RL_REPO == 5

    def test_arxiv_medium_decay(self):
        assert SignalHalfLife.ARXIV_PAPER == 10

    def test_funding_slow_decay(self):
        assert SignalHalfLife.FUNDING_EVENT == 21

    def test_job_posting_medium_decay(self):
        assert SignalHalfLife.JOB_POSTING == 10

    def test_huggingface_fast_decay(self):
        assert SignalHalfLife.HUGGINGFACE_MODEL == 7

    def test_linkedin_fastest_decay(self):
        assert SignalHalfLife.LINKEDIN_ACTIVITY == 2
