"""Unit tests for the signal stacking and composite scoring engine.

TDD: Tests written before implementation.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, UTC
from pathlib import Path

import pytest

from scripts.config_loader import load_config
from scripts.models import (
    ICPScore,
    ScanResult,
    Signal,
    SignalStrength,
)
from scripts.signal_stacker import SignalStacker, stack_from_files

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_SAMPLE_CONFIG = _FIXTURES / "sample_config.yaml"


# ---------------------------------------------------------------------------
# Helpers / Factories
# ---------------------------------------------------------------------------


def make_signal(
    company_name: str = "Acme Corp",
    company_domain: str | None = None,
    signal_type: str = "arxiv_paper",
    signal_strength: SignalStrength = SignalStrength.MODERATE,
    source_url: str = "https://example.com",
    metadata: dict | None = None,
) -> Signal:
    """Factory for Signal objects with sensible defaults.

    github_repo signals require 'repo_name' in metadata — pass it explicitly
    or use a non-GitHub type (default is arxiv_paper).
    """
    if metadata is None:
        if signal_type == "github_repo":
            metadata = {"repo_name": "acme/repo"}
        else:
            metadata = {}

    return Signal(
        signal_type=signal_type,
        company_name=company_name,
        company_domain=company_domain,
        signal_strength=signal_strength,
        source_url=source_url,
        raw_data={},
        metadata=metadata,
    )


def make_scan_result(signals: list[Signal], scan_type: str = "arxiv_paper") -> ScanResult:
    """Factory for ScanResult objects."""
    now = datetime.now(UTC)
    return ScanResult(
        scan_type=scan_type,
        started_at=now,
        completed_at=now,
        signals_found=signals,
        total_raw_results=len(signals),
        total_after_dedup=len(signals),
    )


# ---------------------------------------------------------------------------
# Composite score calculation
# ---------------------------------------------------------------------------


class TestCalculateCompositeScore:
    def test_single_signal_no_multiplier(self):
        """1 MODERATE signal (strength=2) × 1 unique type (multiplier=1.0) = 2.0"""
        stacker = SignalStacker()
        signals = [make_signal(signal_strength=SignalStrength.MODERATE)]
        score = stacker._calculate_composite_score(signals)
        assert score == 2.0

    def test_two_source_types_multiplier(self):
        """2 different source types → multiplier = 1.5"""
        stacker = SignalStacker()
        signals = [
            make_signal(signal_type="arxiv_paper", signal_strength=SignalStrength.WEAK),
            make_signal(signal_type="job_posting", signal_strength=SignalStrength.WEAK),
        ]
        # base = 1 + 1 = 2, multiplier = 1.5
        score = stacker._calculate_composite_score(signals)
        assert score == pytest.approx(3.0)

    def test_three_source_types_multiplier(self):
        """3 different source types → multiplier = 2.0"""
        stacker = SignalStacker()
        signals = [
            make_signal(signal_type="arxiv_paper", signal_strength=SignalStrength.WEAK),
            make_signal(signal_type="job_posting", signal_strength=SignalStrength.WEAK),
            make_signal(signal_type="funding_event", signal_strength=SignalStrength.WEAK),
        ]
        # base = 1 + 1 + 1 = 3, multiplier = 2.0
        score = stacker._calculate_composite_score(signals)
        assert score == pytest.approx(6.0)

    def test_four_plus_source_types_multiplier(self):
        """4+ different source types → multiplier = 3.0"""
        stacker = SignalStacker()
        signals = [
            make_signal(signal_type="arxiv_paper", signal_strength=SignalStrength.WEAK),
            make_signal(signal_type="job_posting", signal_strength=SignalStrength.WEAK),
            make_signal(signal_type="funding_event", signal_strength=SignalStrength.WEAK),
            make_signal(
                signal_type="github_repo",
                signal_strength=SignalStrength.WEAK,
                metadata={"repo_name": "acme/rl"},
            ),
        ]
        # base = 4 × 1 = 4, multiplier = 3.0
        score = stacker._calculate_composite_score(signals)
        assert score == pytest.approx(12.0)

    def test_same_source_type_no_extra_multiplier(self):
        """2 GITHUB_RL_REPO signals = 1 unique type → multiplier = 1.0"""
        stacker = SignalStacker()
        signals = [
            make_signal(
                signal_type="github_repo",
                signal_strength=SignalStrength.STRONG,
                metadata={"repo_name": "acme/rl-1"},
            ),
            make_signal(
                signal_type="github_repo",
                signal_strength=SignalStrength.STRONG,
                metadata={"repo_name": "acme/rl-2"},
            ),
        ]
        # base = 3 + 3 = 6, multiplier = 1.0
        score = stacker._calculate_composite_score(signals)
        assert score == pytest.approx(6.0)


# ---------------------------------------------------------------------------
# ICP score determination
# ---------------------------------------------------------------------------


class TestDetermineICPScore:
    def test_icp_score_a(self):
        stacker = SignalStacker()
        assert stacker._determine_icp_score(9.0) == ICPScore.A
        assert stacker._determine_icp_score(15.0) == ICPScore.A

    def test_icp_score_b(self):
        stacker = SignalStacker()
        assert stacker._determine_icp_score(5.0) == ICPScore.B
        assert stacker._determine_icp_score(8.9) == ICPScore.B

    def test_icp_score_c(self):
        stacker = SignalStacker()
        assert stacker._determine_icp_score(2.0) == ICPScore.C
        assert stacker._determine_icp_score(4.9) == ICPScore.C

    def test_icp_score_d(self):
        stacker = SignalStacker()
        assert stacker._determine_icp_score(1.9) == ICPScore.D
        assert stacker._determine_icp_score(0.0) == ICPScore.D


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------


class TestNormalizeName:
    def test_normalize_strips_suffixes(self):
        stacker = SignalStacker()
        assert stacker._normalize_name("Acme Inc") == "acme"

    def test_normalize_strips_ltd(self):
        stacker = SignalStacker()
        assert stacker._normalize_name("Acme Ltd") == "acme"

    def test_normalize_strips_corp(self):
        stacker = SignalStacker()
        assert stacker._normalize_name("Acme Corp") == "acme"

    def test_normalize_strips_llc(self):
        stacker = SignalStacker()
        assert stacker._normalize_name("Acme LLC") == "acme"

    def test_normalize_strips_ai_suffix(self):
        stacker = SignalStacker()
        assert stacker._normalize_name("Acme AI") == "acme"

    def test_normalize_strips_labs(self):
        stacker = SignalStacker()
        assert stacker._normalize_name("Acme Labs") == "acme"

    def test_normalize_lowercases(self):
        stacker = SignalStacker()
        assert stacker._normalize_name("DeepMind") == "deepmind"

    def test_normalize_strips_trailing_punctuation(self):
        stacker = SignalStacker()
        assert stacker._normalize_name("Acme, Inc.") == "acme"


# ---------------------------------------------------------------------------
# Company matching
# ---------------------------------------------------------------------------


class TestMatchCompany:
    def test_matches_by_domain(self):
        """Same domain, different name → should match."""
        stacker = SignalStacker()
        assert stacker._match_company("DeepMind", "deepmind.com", "Google DeepMind", "deepmind.com")

    def test_does_not_match_different_domains(self):
        """Different domains → no match even if names are similar."""
        stacker = SignalStacker()
        assert not stacker._match_company("Acme AI", "acme.com", "Acme Corp", "acme-corp.com")

    def test_matches_by_name_exact_normalized(self):
        """Same name after normalization → match."""
        stacker = SignalStacker()
        assert stacker._match_company("OpenAI Inc", None, "OpenAI", None)

    def test_matches_by_name_substring(self):
        """'DeepMind' is a substring of 'Google DeepMind' → match."""
        stacker = SignalStacker()
        assert stacker._match_company("DeepMind", None, "Google DeepMind", None)

    def test_no_match_different_companies(self):
        """'OpenAI' and 'Anthropic' share no relationship → no match."""
        stacker = SignalStacker()
        assert not stacker._match_company("OpenAI", None, "Anthropic", None)

    def test_domain_takes_priority_over_name(self):
        """If both have domains, domain match is definitive (no name fallback)."""
        stacker = SignalStacker()
        # Same name but different domains → no match
        assert not stacker._match_company("Acme", "acme-us.com", "Acme", "acme-eu.com")

    def test_no_domain_falls_back_to_name(self):
        """No domains → fall back to name comparison."""
        stacker = SignalStacker()
        assert stacker._match_company("Acme Inc", None, "Acme", None)


# ---------------------------------------------------------------------------
# Signal grouping
# ---------------------------------------------------------------------------


class TestGroupSignalsByCompany:
    def test_groups_same_company(self):
        """Two signals for the same company → one group."""
        stacker = SignalStacker()
        signals = [
            make_signal(company_name="OpenAI", company_domain="openai.com"),
            make_signal(company_name="OpenAI Inc", company_domain="openai.com"),
        ]
        groups = stacker._group_signals_by_company(signals)
        assert len(groups) == 1

    def test_separates_different_companies(self):
        """Two signals for different companies → two groups."""
        stacker = SignalStacker()
        signals = [
            make_signal(company_name="OpenAI", company_domain="openai.com"),
            make_signal(company_name="Anthropic", company_domain="anthropic.com"),
        ]
        groups = stacker._group_signals_by_company(signals)
        assert len(groups) == 2

    def test_group_key_prefers_domain(self):
        """Group key should be the domain when available."""
        stacker = SignalStacker()
        signals = [
            make_signal(company_name="OpenAI", company_domain="openai.com"),
        ]
        groups = stacker._group_signals_by_company(signals)
        assert "openai.com" in groups

    def test_group_key_falls_back_to_name(self):
        """Group key is normalized name when no domain."""
        stacker = SignalStacker()
        signals = [
            make_signal(company_name="Acme Corp", company_domain=None),
        ]
        groups = stacker._group_signals_by_company(signals)
        assert "acme" in groups


# ---------------------------------------------------------------------------
# Full stack_signals pipeline
# ---------------------------------------------------------------------------


class TestStackSignals:
    def test_empty_input_returns_empty(self):
        stacker = SignalStacker()
        result = stacker.stack_signals([])
        assert result == []

    def test_output_sorted_by_score(self):
        """Company with higher composite score should appear first."""
        stacker = SignalStacker()
        # Company A: 1 WEAK signal (score = 1.0)
        # Company B: 3 signals from 3 different types (score = 3 * 2.0 = 6.0)
        signals_low = [
            make_signal(
                company_name="Low Score Co",
                company_domain="low.com",
                signal_strength=SignalStrength.WEAK,
            )
        ]
        signals_high = [
            make_signal(
                company_name="High Score Co",
                company_domain="high.com",
                signal_type="arxiv_paper",
                signal_strength=SignalStrength.WEAK,
            ),
            make_signal(
                company_name="High Score Co",
                company_domain="high.com",
                signal_type="job_posting",
                signal_strength=SignalStrength.WEAK,
            ),
            make_signal(
                company_name="High Score Co",
                company_domain="high.com",
                signal_type="funding_event",
                signal_strength=SignalStrength.WEAK,
            ),
        ]
        scan_low = make_scan_result(signals_low, "arxiv_paper")
        scan_high = make_scan_result(signals_high, "arxiv_paper")
        results = stacker.stack_signals([scan_low, scan_high])
        assert len(results) == 2
        assert results[0].domain == "high.com"
        assert results[1].domain == "low.com"

    def test_dedup_preserves_all_signals(self):
        """Grouped company profile must contain all signals from all sources."""
        stacker = SignalStacker()
        signals = [
            make_signal(
                company_name="OpenAI",
                company_domain="openai.com",
                signal_type="arxiv_paper",
                source_url="https://arxiv.org/paper1",
            ),
            make_signal(
                company_name="OpenAI Inc",
                company_domain="openai.com",
                signal_type="job_posting",
                source_url="https://jobs.example.com/1",
            ),
        ]
        scan = make_scan_result(signals)
        results = stacker.stack_signals([scan])
        assert len(results) == 1
        assert len(results[0].signals) == 2

    def test_company_profile_has_icp_score(self):
        """Each CompanyProfile must have an icp_score set."""
        stacker = SignalStacker()
        signals = [make_signal(company_name="Acme", company_domain="acme.com")]
        scan = make_scan_result(signals)
        results = stacker.stack_signals([scan])
        assert results[0].icp_score is not None

    def test_company_profile_domain_set(self):
        """CompanyProfile domain should come from the signal's company_domain."""
        stacker = SignalStacker()
        signals = [make_signal(company_name="Acme", company_domain="acme.com")]
        scan = make_scan_result(signals)
        results = stacker.stack_signals([scan])
        assert results[0].domain == "acme.com"

    def test_company_profile_domain_fallback_normalized_name(self):
        """When no domain present, domain field falls back to normalized company name."""
        stacker = SignalStacker()
        signals = [make_signal(company_name="Acme Corp", company_domain=None)]
        scan = make_scan_result(signals)
        results = stacker.stack_signals([scan])
        assert results[0].domain == "acme"

    def test_known_domains_used_for_matching(self):
        """known_domains mapping improves matching across signals without domains."""
        stacker = SignalStacker(known_domains={"deepmind": "deepmind.com"})
        signals = [
            make_signal(company_name="DeepMind", company_domain=None),
            make_signal(company_name="Google DeepMind", company_domain=None),
        ]
        scan = make_scan_result(signals)
        results = stacker.stack_signals([scan])
        # Should be grouped into one company
        assert len(results) == 1

    def test_multiple_scan_results_merged(self):
        """Signals from multiple ScanResult objects are combined correctly."""
        stacker = SignalStacker()
        scan1 = make_scan_result(
            [
                make_signal(
                    company_name="Acme",
                    company_domain="acme.com",
                    signal_type="arxiv_paper",
                )
            ],
            "arxiv_paper",
        )
        scan2 = make_scan_result(
            [
                make_signal(
                    company_name="Acme",
                    company_domain="acme.com",
                    signal_type="job_posting",
                )
            ],
            "job_posting",
        )
        results = stacker.stack_signals([scan1, scan2])
        assert len(results) == 1
        assert len(results[0].signals) == 2


# ---------------------------------------------------------------------------
# stack_from_files
# ---------------------------------------------------------------------------


class TestStackFromFiles:
    def test_loads_and_stacks_from_json_files(self):
        """stack_from_files should deserialize ScanResult JSON and run stacking."""
        SignalStacker()
        signals = [
            make_signal(company_name="Acme", company_domain="acme.com", signal_type="arxiv_paper"),
            make_signal(company_name="Acme", company_domain="acme.com", signal_type="job_posting"),
        ]
        scan = make_scan_result(signals)

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "scan.json"
            filepath.write_text(scan.model_dump_json())
            results = stack_from_files([str(filepath)])

        assert len(results) == 1
        assert results[0].domain == "acme.com"

    def test_empty_file_list_returns_empty(self):
        results = stack_from_files([])
        assert results == []


# ---------------------------------------------------------------------------
# Intent scoring integration
# ---------------------------------------------------------------------------


class TestIntentScoringIntegration:
    def test_intent_scoring_disabled_by_default(self):
        stacker = SignalStacker()
        assert stacker.use_intent_scoring is False

    def test_intent_scoring_opt_in(self):
        stacker = SignalStacker(use_intent_scoring=True)
        assert stacker.use_intent_scoring is True

    def test_intent_scoring_produces_different_scores(self):
        """Intent-weighted scores differ from legacy."""
        config = load_config(_SAMPLE_CONFIG)
        signals = [
            make_signal(company_name="IntentCo", signal_type="arxiv_paper"),
            make_signal(company_name="IntentCo", signal_type="github_repo"),
        ]
        scan_result = ScanResult(
            scan_type="arxiv_paper",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=signals,
            total_raw_results=2,
            total_after_dedup=2,
        )
        intent_stacker = SignalStacker(use_intent_scoring=True, config=config)
        legacy_stacker = SignalStacker(use_intent_scoring=False)
        intent_profiles = intent_stacker.stack_signals([scan_result])
        legacy_profiles = legacy_stacker.stack_signals([scan_result])
        assert (
            intent_profiles[0].composite_signal_score != legacy_profiles[0].composite_signal_score
        )

    def test_legacy_mode_matches_original_behavior(self):
        """Legacy mode = same scores as before."""
        stacker = SignalStacker(use_intent_scoring=False)
        signals = [make_signal(company_name="LegacyCo", signal_type="github_repo")]
        scan_result = ScanResult(
            scan_type="github_repo",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=signals,
            total_raw_results=1,
            total_after_dedup=1,
        )
        profiles = stacker.stack_signals([scan_result])
        # Legacy: sum(strength=2) × multiplier(1 type=1.0) = 2.0
        assert profiles[0].composite_signal_score == pytest.approx(2.0)
