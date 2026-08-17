"""Tests for the Fireworks ICP demo assets.

Tests cover:
- Fireworks ICP config exists and has required fields
- Positive signal categories exist
- Scoring weights exist
- Outbound angles exist
- Seed demo accounts load and have required fields
- FireworksICPBrief schema validates a mocked response
- Schema validators reject invalid data (fit_score range, linkedin_message length, empty lists)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.marops.fireworks_icp_schema import FireworksICPBrief

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


def test_fireworks_icp_config_exists() -> None:
    path = ROOT / "configs" / "icps" / "fireworks_ai.yaml"
    assert path.exists()


def test_fireworks_icp_config_has_required_fields() -> None:
    path = ROOT / "configs" / "icps" / "fireworks_ai.yaml"
    config = yaml.safe_load(path.read_text())

    assert config["name"] == "fireworks_ai"
    assert "company_profile" in config
    assert "buyer_personas" in config
    assert "positive_signals" in config
    assert "negative_signals" in config
    assert "scoring" in config
    assert "outbound_angles" in config


def test_fireworks_icp_positive_signal_categories() -> None:
    path = ROOT / "configs" / "icps" / "fireworks_ai.yaml"
    config = yaml.safe_load(path.read_text())

    positive_signals = config["positive_signals"]

    assert "hiring" in positive_signals
    assert "github" in positive_signals
    assert "website" in positive_signals
    assert "funding" in positive_signals


def test_fireworks_icp_scoring_weights() -> None:
    path = ROOT / "configs" / "icps" / "fireworks_ai.yaml"
    config = yaml.safe_load(path.read_text())

    scoring = config["scoring"]
    assert "weights" in scoring
    assert "thresholds" in scoring

    weights = scoring["weights"]
    assert "ai_product_signal" in weights
    assert "inference_or_latency_signal" in weights
    assert "hiring_signal" in weights
    assert "open_source_model_signal" in weights
    assert "funding_or_growth_signal" in weights


def test_fireworks_icp_outbound_angles() -> None:
    path = ROOT / "configs" / "icps" / "fireworks_ai.yaml"
    config = yaml.safe_load(path.read_text())

    angles = config["outbound_angles"]
    assert "latency" in angles
    assert "cost" in angles
    assert "model_flexibility" in angles
    assert "scale" in angles

    for angle_key in ("latency", "cost", "model_flexibility", "scale"):
        angle = angles[angle_key]
        assert "trigger_keywords" in angle
        assert "angle" in angle
        assert isinstance(angle["trigger_keywords"], list)
        assert len(angle["trigger_keywords"]) > 0


# ---------------------------------------------------------------------------
# Seed accounts tests
# ---------------------------------------------------------------------------


def test_fireworks_demo_accounts_load() -> None:
    path = ROOT / "examples" / "fireworks-demo" / "accounts.json"
    accounts = json.loads(path.read_text())

    assert len(accounts) >= 3

    for account in accounts:
        assert "account_name" in account
        assert "industry" in account
        assert "signals" in account
        assert "hypothesis" in account
        assert account["signals"]


def test_fireworks_demo_accounts_content() -> None:
    """Verify the seeded accounts cover diverse AI inference use cases."""
    path = ROOT / "examples" / "fireworks-demo" / "accounts.json"
    accounts = json.loads(path.read_text())

    industries = [a["industry"] for a in accounts]
    # Ensure we have diverse segments, not all the same
    assert len(set(industries)) >= 3


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def _make_valid_brief() -> FireworksICPBrief:
    return FireworksICPBrief(
        account_name="Voice AI Support Startup",
        fit_score=94,
        intent_level="Urgent",
        matched_signals=[
            "Hiring real-time AI engineers",
            "Needs sub-second latency for customer conversations",
        ],
        why_now="Real-time voice workflows make inference latency a product bottleneck.",
        fireworks_relevance="Fireworks can support low-latency inference for production AI workloads.",
        likely_pain_points=[
            "Sub-second latency",
            "High token volume",
            "Inference cost at scale",
        ],
        recommended_persona="Head of AI Infrastructure",
        outbound_angle="Low-latency inference for production voice AI",
        linkedin_message=(
            "Saw your team is hiring around real-time AI and streaming responses. "
            "Curious if inference latency has become a bottleneck as usage grows."
        ),
        cold_email_subject="Scaling real-time AI inference",
        cold_email_body=(
            "Saw your team is building around real-time AI workflows. "
            "Thought Fireworks could be relevant if latency, model flexibility, "
            "or inference cost is becoming a bottleneck."
        ),
    )


def test_fireworks_icp_brief_schema_validates() -> None:
    brief = _make_valid_brief()

    assert brief.fit_score == 94
    assert brief.intent_level == "Urgent"
    assert len(brief.matched_signals) == 2
    assert len(brief.likely_pain_points) == 3


def test_fireworks_icp_brief_fit_score_too_high() -> None:
    with pytest.raises(ValueError, match="fit_score must be between 0 and 100"):
        FireworksICPBrief(
            account_name="Test",
            fit_score=101,
            intent_level="High",
            matched_signals=["signal"],
            why_now="Test",
            fireworks_relevance="Test",
            likely_pain_points=["pain"],
            recommended_persona="CTO",
            outbound_angle="Test",
            linkedin_message="Hi",
            cold_email_subject="Test",
            cold_email_body="Test body",
        )


def test_fireworks_icp_brief_fit_score_negative() -> None:
    with pytest.raises(ValueError, match="fit_score must be between 0 and 100"):
        FireworksICPBrief(
            account_name="Test",
            fit_score=-1,
            intent_level="Low",
            matched_signals=["signal"],
            why_now="Test",
            fireworks_relevance="Test",
            likely_pain_points=["pain"],
            recommended_persona="CTO",
            outbound_angle="Test",
            linkedin_message="Hi",
            cold_email_subject="Test",
            cold_email_body="Test body",
        )


def test_fireworks_icp_brief_linkedin_message_too_long() -> None:
    with pytest.raises(ValueError, match="linkedin_message must be under 500 characters"):
        FireworksICPBrief(
            account_name="Test",
            fit_score=50,
            intent_level="Medium",
            matched_signals=["signal"],
            why_now="Test",
            fireworks_relevance="Test",
            likely_pain_points=["pain"],
            recommended_persona="CTO",
            outbound_angle="Test",
            linkedin_message="x" * 501,
            cold_email_subject="Test",
            cold_email_body="Test body",
        )


def test_fireworks_icp_brief_empty_matched_signals() -> None:
    with pytest.raises(ValueError, match="matched_signals must not be empty"):
        FireworksICPBrief(
            account_name="Test",
            fit_score=50,
            intent_level="Medium",
            matched_signals=[],
            why_now="Test",
            fireworks_relevance="Test",
            likely_pain_points=["pain"],
            recommended_persona="CTO",
            outbound_angle="Test",
            linkedin_message="Hi",
            cold_email_subject="Test",
            cold_email_body="Test body",
        )


def test_fireworks_icp_brief_empty_pain_points() -> None:
    with pytest.raises(ValueError, match="likely_pain_points must not be empty"):
        FireworksICPBrief(
            account_name="Test",
            fit_score=50,
            intent_level="Medium",
            matched_signals=["signal"],
            why_now="Test",
            fireworks_relevance="Test",
            likely_pain_points=[],
            recommended_persona="CTO",
            outbound_angle="Test",
            linkedin_message="Hi",
            cold_email_subject="Test",
            cold_email_body="Test body",
        )


def test_fireworks_icp_brief_intent_level_values() -> None:
    """All four intent levels should be valid."""
    for level in ("Low", "Medium", "High", "Urgent"):
        brief = FireworksICPBrief(
            account_name="Test",
            fit_score=50,
            intent_level=level,
            matched_signals=["signal"],
            why_now="Test",
            fireworks_relevance="Test",
            likely_pain_points=["pain"],
            recommended_persona="CTO",
            outbound_angle="Test",
            linkedin_message="Hi",
            cold_email_subject="Test",
            cold_email_body="Test body",
        )
        assert brief.intent_level == level


def test_fireworks_icp_brief_invalid_intent_level() -> None:
    with pytest.raises(Exception):
        FireworksICPBrief(
            account_name="Test",
            fit_score=50,
            intent_level="Critical",  # Not a valid Literal value
            matched_signals=["signal"],
            why_now="Test",
            fireworks_relevance="Test",
            likely_pain_points=["pain"],
            recommended_persona="CTO",
            outbound_angle="Test",
            linkedin_message="Hi",
            cold_email_subject="Test",
            cold_email_body="Test body",
        )


# ---------------------------------------------------------------------------
# Demo script tests (mocked)
# ---------------------------------------------------------------------------


def test_demo_script_loaders() -> None:
    """Test that the demo script's load functions work."""
    from scripts.demo_fireworks_icp import load_json, load_yaml

    icp = load_yaml(ROOT / "configs" / "icps" / "fireworks_ai.yaml")
    assert icp["name"] == "fireworks_ai"

    accounts = load_json(ROOT / "examples" / "fireworks-demo" / "accounts.json")
    assert len(accounts) >= 3


def test_demo_script_build_prompt() -> None:
    """Test that the prompt builder includes key elements."""
    from scripts.demo_fireworks_icp import build_prompt

    account = {
        "account_name": "Test Co",
        "industry": "AI",
        "signals": ["signal1"],
        "hypothesis": "test",
    }
    icp = {"name": "fireworks_ai", "scoring": {"weights": {}}}
    prompt = build_prompt(account, icp)

    assert "SignalForce" in prompt
    assert "Fireworks" in prompt
    assert "JSON" in prompt
    assert "Test Co" in prompt
