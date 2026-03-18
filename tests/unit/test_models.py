"""Unit tests for core GTM pipeline data models.

Tests are written first (TDD RED phase) before implementation.
"""

import pytest
from datetime import datetime, UTC
from pydantic import ValidationError

from scripts.models import (
    SignalType,
    SignalStrength,
    Signal,
    ICPTier,
    ICPScore,
    RLMaturityStage,
    CompanyProfile,
    ContactTitle,
    EnrichmentSource,
    Contact,
    EmailVariant,
    DealStage,
    Deal,
    ScanResult,
    OutreachChannel,
    SequenceStep,
)


# ---------------------------------------------------------------------------
# Signal tests
# ---------------------------------------------------------------------------


def test_signal_creation_with_valid_data():
    signal = Signal(
        signal_type=SignalType.ARXIV_PAPER,
        company_name="DeepMind",
        signal_strength=SignalStrength.STRONG,
        source_url="https://arxiv.org/abs/1234.5678",
        raw_data={"title": "PPO paper"},
    )
    assert signal.company_name == "DeepMind"
    assert signal.signal_type == SignalType.ARXIV_PAPER
    assert signal.signal_strength == SignalStrength.STRONG
    assert signal.raw_data == {"title": "PPO paper"}


def test_signal_frozen_prevents_mutation():
    signal = Signal(
        signal_type=SignalType.ARXIV_PAPER,
        company_name="DeepMind",
        signal_strength=SignalStrength.STRONG,
        source_url="https://arxiv.org/abs/1234.5678",
        raw_data={},
    )
    with pytest.raises((TypeError, ValidationError)):
        signal.company_name = "OpenAI"  # type: ignore[misc]


def test_signal_github_requires_repo_name_in_metadata():
    signal = Signal(
        signal_type=SignalType.GITHUB_RL_REPO,
        company_name="OpenAI",
        signal_strength=SignalStrength.STRONG,
        source_url="https://github.com/openai/gym",
        raw_data={"stars": 1000},
        metadata={"repo_name": "openai/gym"},
    )
    assert signal.metadata["repo_name"] == "openai/gym"


def test_signal_github_without_repo_name_raises():
    with pytest.raises(ValidationError):
        Signal(
            signal_type=SignalType.GITHUB_RL_REPO,
            company_name="OpenAI",
            signal_strength=SignalStrength.STRONG,
            source_url="https://github.com/openai/gym",
            raw_data={"stars": 1000},
            metadata={},  # missing repo_name
        )


def test_signal_non_github_doesnt_require_repo_name():
    # Should not raise even without repo_name in metadata
    signal = Signal(
        signal_type=SignalType.FUNDING_EVENT,
        company_name="Cohere",
        signal_strength=SignalStrength.MODERATE,
        source_url="https://techcrunch.com/cohere-funding",
        raw_data={"amount": "270M"},
    )
    assert signal.signal_type == SignalType.FUNDING_EVENT


def test_signal_auto_generates_uuid():
    signal1 = Signal(
        signal_type=SignalType.JOB_POSTING,
        company_name="Anthropic",
        signal_strength=SignalStrength.WEAK,
        source_url="https://jobs.anthropic.com/123",
        raw_data={},
    )
    signal2 = Signal(
        signal_type=SignalType.JOB_POSTING,
        company_name="Anthropic",
        signal_strength=SignalStrength.WEAK,
        source_url="https://jobs.anthropic.com/456",
        raw_data={},
    )
    assert signal1.id != signal2.id
    assert len(signal1.id) == 36  # UUID4 format


def test_signal_default_detected_at():
    before = datetime.now(UTC)
    signal = Signal(
        signal_type=SignalType.ARXIV_PAPER,
        company_name="MIT",
        signal_strength=SignalStrength.MODERATE,
        source_url="https://arxiv.org/abs/9999.0000",
        raw_data={},
    )
    after = datetime.now(UTC)
    assert before <= signal.detected_at <= after


# ---------------------------------------------------------------------------
# Enum value tests
# ---------------------------------------------------------------------------


def test_enum_values_correct():
    # SignalType
    assert SignalType.GITHUB_RL_REPO == "GITHUB_RL_REPO"
    assert SignalType.ARXIV_PAPER == "ARXIV_PAPER"
    assert SignalType.JOB_POSTING == "JOB_POSTING"
    assert SignalType.HUGGINGFACE_MODEL == "HUGGINGFACE_MODEL"
    assert SignalType.FUNDING_EVENT == "FUNDING_EVENT"
    assert SignalType.LINKEDIN_ACTIVITY == "LINKEDIN_ACTIVITY"

    # SignalStrength
    assert SignalStrength.WEAK == 1
    assert SignalStrength.MODERATE == 2
    assert SignalStrength.STRONG == 3

    # ICPTier
    assert ICPTier.TIER_1_AI_LAB == "TIER_1_AI_LAB"
    assert ICPTier.TIER_2_AGENT_BUILDER == "TIER_2_AGENT_BUILDER"
    assert ICPTier.TIER_3_ROBOTICS == "TIER_3_ROBOTICS"
    assert ICPTier.TIER_4_INDUSTRY == "TIER_4_INDUSTRY"

    # ICPScore
    assert ICPScore.A == "A"
    assert ICPScore.B == "B"
    assert ICPScore.C == "C"
    assert ICPScore.D == "D"

    # RLMaturityStage
    assert RLMaturityStage.EXPLORING == "EXPLORING"
    assert RLMaturityStage.BUILDING == "BUILDING"
    assert RLMaturityStage.SCALING == "SCALING"
    assert RLMaturityStage.PRODUCTIONIZING == "PRODUCTIONIZING"

    # DealStage
    assert DealStage.SIGNAL_DETECTED == "SIGNAL_DETECTED"
    assert DealStage.MEETING_SCHEDULED == "MEETING_SCHEDULED"
    assert DealStage.DISQUALIFIED == "DISQUALIFIED"

    # EmailVariant
    assert EmailVariant.PROBLEM_FOCUSED == "PROBLEM_FOCUSED"
    assert EmailVariant.OUTCOME_FOCUSED == "OUTCOME_FOCUSED"
    assert EmailVariant.SOCIAL_PROOF_FOCUSED == "SOCIAL_PROOF_FOCUSED"

    # ContactTitle
    assert ContactTitle.CTO == "CTO"
    assert ContactTitle.OTHER == "OTHER"

    # EnrichmentSource
    assert EnrichmentSource.APOLLO == "APOLLO"
    assert EnrichmentSource.MANUAL == "MANUAL"


# ---------------------------------------------------------------------------
# Contact tests
# ---------------------------------------------------------------------------


def test_contact_confidence_score_valid_range():
    contact = Contact(
        full_name="Jane Smith",
        title="Head of ML",
        title_category=ContactTitle.HEAD_OF_ML,
        company_domain="deepmind.com",
        confidence_score=0.85,
    )
    assert contact.confidence_score == 0.85


def test_contact_confidence_score_over_1_raises():
    with pytest.raises(ValidationError):
        Contact(
            full_name="Jane Smith",
            title="Head of ML",
            title_category=ContactTitle.HEAD_OF_ML,
            company_domain="deepmind.com",
            confidence_score=1.5,
        )


def test_contact_confidence_score_negative_raises():
    with pytest.raises(ValidationError):
        Contact(
            full_name="Jane Smith",
            title="Head of ML",
            title_category=ContactTitle.HEAD_OF_ML,
            company_domain="deepmind.com",
            confidence_score=-0.1,
        )


# ---------------------------------------------------------------------------
# CompanyProfile tests
# ---------------------------------------------------------------------------


def test_company_profile_optional_fields_accept_none():
    profile = CompanyProfile(
        company_name="Acme RL",
        domain="acmerl.com",
    )
    assert profile.icp_tier is None
    assert profile.icp_score is None
    assert profile.rl_maturity is None
    assert profile.employee_count is None
    assert profile.funding_stage is None
    assert profile.founded_year is None
    assert profile.hq_location is None
    assert profile.tech_stack == []
    assert profile.signals == []
    assert profile.composite_signal_score == 0.0
    assert profile.researched_at is None
    assert profile.notes == ""


def test_company_profile_with_signals():
    signal = Signal(
        signal_type=SignalType.JOB_POSTING,
        company_name="Acme RL",
        company_domain="acmerl.com",
        signal_strength=SignalStrength.STRONG,
        source_url="https://jobs.acmerl.com/rl-engineer",
        raw_data={"title": "RL Engineer"},
    )
    profile = CompanyProfile(
        company_name="Acme RL",
        domain="acmerl.com",
        icp_tier=ICPTier.TIER_2_AGENT_BUILDER,
        icp_score=ICPScore.B,
        signals=[signal],
        composite_signal_score=2.5,
    )
    assert len(profile.signals) == 1
    assert profile.signals[0].company_name == "Acme RL"
    assert profile.composite_signal_score == 2.5


# ---------------------------------------------------------------------------
# Deal tests
# ---------------------------------------------------------------------------


def test_deal_default_stage_is_signal_detected():
    profile = CompanyProfile(company_name="RoboAI", domain="roboai.io")
    deal = Deal(company_profile=profile)
    assert deal.stage == DealStage.SIGNAL_DETECTED
    assert deal.contacts == []
    assert deal.emails_sent == []
    assert deal.hubspot_deal_id is None
    assert deal.instantly_campaign_id is None
    assert deal.notes == ""


# ---------------------------------------------------------------------------
# ScanResult tests
# ---------------------------------------------------------------------------


def test_scan_result_creation():
    now = datetime.now(UTC)
    signal = Signal(
        signal_type=SignalType.ARXIV_PAPER,
        company_name="Stanford",
        signal_strength=SignalStrength.MODERATE,
        source_url="https://arxiv.org/abs/0001.0001",
        raw_data={"abstract": "RL paper"},
    )
    scan = ScanResult(
        scan_type=SignalType.ARXIV_PAPER,
        started_at=now,
        completed_at=now,
        signals_found=[signal],
        total_raw_results=50,
        total_after_dedup=45,
    )
    assert scan.scan_type == SignalType.ARXIV_PAPER
    assert len(scan.signals_found) == 1
    assert scan.total_raw_results == 50
    assert scan.total_after_dedup == 45
    assert scan.errors == []


# ---------------------------------------------------------------------------
# OutreachChannel enum tests
# ---------------------------------------------------------------------------


def test_outreach_channel_email_value():
    assert OutreachChannel.EMAIL == "EMAIL"


def test_outreach_channel_linkedin_value():
    assert OutreachChannel.LINKEDIN == "LINKEDIN"


def test_outreach_channel_linkedin_inmail_value():
    assert OutreachChannel.LINKEDIN_INMAIL == "LINKEDIN_INMAIL"


def test_outreach_channel_is_str_enum():
    assert isinstance(OutreachChannel.EMAIL, str)
    assert isinstance(OutreachChannel.LINKEDIN, str)


def test_outreach_channel_all_members():
    members = {m.value for m in OutreachChannel}
    assert members == {"EMAIL", "LINKEDIN", "LINKEDIN_INMAIL"}


# ---------------------------------------------------------------------------
# SequenceStep model tests
# ---------------------------------------------------------------------------


def test_sequence_step_creation_minimal():
    step = SequenceStep(
        day=0,
        channel=OutreachChannel.EMAIL,
        action="send_email",
        template_name="github-rl-signal",
    )
    assert step.day == 0
    assert step.channel == OutreachChannel.EMAIL
    assert step.action == "send_email"
    assert step.template_name == "github-rl-signal"
    assert step.variant is None


def test_sequence_step_with_variant():
    step = SequenceStep(
        day=1,
        channel=OutreachChannel.LINKEDIN,
        action="connection_request",
        template_name="hiring-signal",
        variant="signal_reference",
    )
    assert step.variant == "signal_reference"


def test_sequence_step_frozen_prevents_mutation():
    step = SequenceStep(
        day=0,
        channel=OutreachChannel.EMAIL,
        action="send_email",
        template_name="general-signal",
    )
    with pytest.raises((TypeError, ValidationError)):
        step.day = 5  # type: ignore[misc]


def test_sequence_step_json_roundtrip():
    step = SequenceStep(
        day=3,
        channel=OutreachChannel.LINKEDIN,
        action="follow_up_message",
        template_name="arxiv-paper-signal",
        variant=None,
    )
    json_str = step.model_dump_json()
    restored = SequenceStep.model_validate_json(json_str)
    assert restored.day == step.day
    assert restored.channel == step.channel
    assert restored.action == step.action
    assert restored.template_name == step.template_name
    assert restored.variant == step.variant


def test_sequence_step_linkedin_inmail_channel():
    step = SequenceStep(
        day=2,
        channel=OutreachChannel.LINKEDIN_INMAIL,
        action="send_inmail",
        template_name="general-signal",
    )
    assert step.channel == OutreachChannel.LINKEDIN_INMAIL


# ---------------------------------------------------------------------------
# JSON roundtrip test
# ---------------------------------------------------------------------------


def test_signal_json_roundtrip():
    signal = Signal(
        signal_type=SignalType.HUGGINGFACE_MODEL,
        company_name="HuggingFace",
        company_domain="huggingface.co",
        signal_strength=SignalStrength.STRONG,
        source_url="https://huggingface.co/models/rl-zoo",
        raw_data={"model_id": "rl-zoo", "downloads": 9999},
        metadata={"framework": "stable-baselines3"},
    )
    json_str = signal.model_dump_json()
    restored = Signal.model_validate_json(json_str)
    assert restored.id == signal.id
    assert restored.signal_type == signal.signal_type
    assert restored.company_name == signal.company_name
    assert restored.raw_data == signal.raw_data
    assert restored.metadata == signal.metadata
    assert restored.detected_at == signal.detected_at
