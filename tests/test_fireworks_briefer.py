"""Tests for the Fireworks-based MarOps briefer.

Tests verify:
- The briefer correctly builds the agent instructions
- JSON parsing from the agent output works
- Markdown fence stripping works
- The LifecycleBrief is constructed with correct metadata
- Error handling for invalid JSON

Network calls are NOT made — the Fireworks agent runner is mocked.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.marops.fireworks_briefer import generate_brief
from scripts.marops.models import MarOpsCampaignConfig


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_config() -> MarOpsCampaignConfig:
    return MarOpsCampaignConfig(
        prospect="TestCorp",
        prospect_url="https://testcorp.com",
        vertical="B2B SaaS",
        campaign_name="TestCorp Q3 Expansion",
        lifecycle_stage="renewal",
        objective="Drive renewal expansion via executive engagement",
        segment_description="Enterprise accounts with Marketo usage",
        num_touches=4,
        why_now_signals=[
            {
                "signal_type": "g2_review_velocity",
                "description": "3 negative G2 reviews about Marketo in 30 days",
                "days_ago": 5,
                "source": "G2",
            }
        ],
    )


@pytest.fixture
def sample_brief_json() -> str:
    """Valid brief JSON matching the LifecycleBrief schema."""
    return json.dumps(
        {
            "segment": {
                "name": "Marketo Pain - Enterprise",
                "salesforce_filters": [
                    "Account.Marketing_Platform__c = 'Marketo'",
                    "Account.AnnualRevenue > 50000000",
                ],
                "warehouse_traits": [
                    "marketo_logins:gt:100",
                    "email_volume:gt:50000",
                ],
                "exclusions": [
                    "Account.Status = 'Churned'",
                    "Contact.Role = 'Inactive'",
                ],
                "estimated_size": "~350 accounts",
            },
            "touches": [
                {
                    "step": 1,
                    "channel": "email",
                    "agent": "execution",
                    "timing": "Day 0, 9am local",
                    "subject": "Your Marketo pain is showing",
                    "body_brief": "Reference the G2 reviews and offer a 15-min assessment call.",
                    "personalization_tokens": ["{{first_name}}", "{{g2_review_count}}"],
                    "qa_rules": ["Suppress if contacted in last 14 days"],
                    "success_metric": "25% open rate, 5% reply rate",
                },
                {
                    "step": 2,
                    "channel": "ae_task",
                    "agent": "optimization",
                    "timing": "Day 3, if no reply",
                    "subject": "Follow-up: Marketo alternatives",
                    "body_brief": "AE calls with a tailored migration ROI deck.",
                    "personalization_tokens": ["{{first_name}}", "{{renewal_date}}"],
                    "qa_rules": ["Only if account is in renewal window"],
                    "success_metric": "20% meeting booking rate",
                },
                {
                    "step": 3,
                    "channel": "linkedin",
                    "agent": "execution",
                    "timing": "Day 7",
                    "subject": "Connecting on Marketo migration",
                    "body_brief": "LinkedIn connect with a soft touch referencing industry trends.",
                    "personalization_tokens": ["{{first_name}}", "{{company}}"],
                    "qa_rules": ["Suppress if already connected"],
                    "success_metric": "30% accept rate",
                },
            ],
            "optimization_triggers": [
                {
                    "condition": "G2 review velocity > 3/week",
                    "action": "Accelerate touch 1 by 2 days",
                },
                {
                    "condition": "No reply after touch 2",
                    "action": "Add executive sponsor touch",
                },
            ],
            "pipeline_projection": {
                "expected_renewals": "12-18 renewals in Q3",
                "ae_efficiency": "4 hours per renewal vs 12 baseline",
                "campaign_runtime": "21 days per cohort",
                "downside": "If G2 signals decay, revert to nurture queue. Risk: 60% of accounts go cold.",
            },
            "meta": {"confidence": "high"},
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerateBrief:
    """Test the generate_brief function with mocked Fireworks agent."""

    @patch("scripts.marops.fireworks_briefer.run_agent_sync")
    @patch("scripts.marops.fireworks_briefer.build_fireworks_agent")
    def test_generate_brief_success(
        self,
        mock_build_agent: MagicMock,
        mock_run: MagicMock,
        sample_config: MarOpsCampaignConfig,
        sample_brief_json: str,
    ) -> None:
        mock_agent = MagicMock()
        mock_build_agent.return_value = mock_agent
        mock_run.return_value = sample_brief_json

        brief = generate_brief(sample_config)

        assert brief.prospect == "TestCorp"
        assert brief.vertical == "B2B SaaS"
        assert brief.campaign_name == "TestCorp Q3 Expansion"
        assert brief.segment.name == "Marketo Pain - Enterprise"
        assert len(brief.touches) == 3
        assert brief.touches[0].channel == "email"
        assert brief.touches[0].agent == "execution"
        assert len(brief.optimization_triggers) == 2
        assert "downside" in brief.pipeline_projection.model_fields
        assert brief.meta["backend"] == "fireworks"
        assert brief.meta["model"] == "fireworks"
        assert brief.why_now is not None
        assert brief.why_now.timing_score == "HIGH"  # 5 days ago = HIGH

    @patch("scripts.marops.fireworks_briefer.run_agent_sync")
    @patch("scripts.marops.fireworks_briefer.build_fireworks_agent")
    def test_generate_brief_strips_markdown_fences(
        self,
        mock_build_agent: MagicMock,
        mock_run: MagicMock,
        sample_config: MarOpsCampaignConfig,
        sample_brief_json: str,
    ) -> None:
        """The agent might wrap JSON in markdown fences — ensure we strip them."""
        fenced = f"```json\n{sample_brief_json}\n```"
        mock_run.return_value = fenced

        brief = generate_brief(sample_config)
        assert brief.prospect == "TestCorp"

    @patch("scripts.marops.fireworks_briefer.run_agent_sync")
    @patch("scripts.marops.fireworks_briefer.build_fireworks_agent")
    def test_generate_brief_invalid_json_raises(
        self,
        mock_build_agent: MagicMock,
        mock_run: MagicMock,
        sample_config: MarOpsCampaignConfig,
    ) -> None:
        mock_run.return_value = "This is not JSON at all."
        with pytest.raises(RuntimeError, match="did not return valid JSON"):
            generate_brief(sample_config)

    @patch("scripts.marops.fireworks_briefer.run_agent_sync")
    @patch("scripts.marops.fireworks_briefer.build_fireworks_agent")
    def test_generate_brief_includes_why_now_context(
        self,
        mock_build_agent: MagicMock,
        mock_run: MagicMock,
        sample_config: MarOpsCampaignConfig,
        sample_brief_json: str,
    ) -> None:
        mock_run.return_value = sample_brief_json
        generate_brief(sample_config)

        # Verify the prompt passed to run_agent_sync includes why-now signals
        call_args = mock_run.call_args
        prompt = call_args[0][1]  # second positional arg
        assert "Why Now" in prompt
        assert "G2" in prompt
        assert "g2_review_velocity" in prompt.lower() or "G2_REVIEW_VELOCITY" in prompt

    @patch("scripts.marops.fireworks_briefer.run_agent_sync")
    @patch("scripts.marops.fireworks_briefer.build_fireworks_agent")
    def test_generate_brief_no_why_now_signals(
        self,
        mock_build_agent: MagicMock,
        mock_run: MagicMock,
        sample_config: MarOpsCampaignConfig,
        sample_brief_json: str,
    ) -> None:
        """Brief should still generate when there are no why-now signals."""
        sample_config = sample_config.model_copy(update={"why_now_signals": []})
        mock_run.return_value = sample_brief_json

        brief = generate_brief(sample_config)
        assert brief.why_now is None

    @patch("scripts.marops.fireworks_briefer.run_agent_sync")
    @patch("scripts.marops.fireworks_briefer.build_fireworks_agent")
    def test_generate_brief_agent_name(
        self,
        mock_build_agent: MagicMock,
        mock_run: MagicMock,
        sample_config: MarOpsCampaignConfig,
        sample_brief_json: str,
    ) -> None:
        mock_run.return_value = sample_brief_json
        generate_brief(sample_config)

        # Verify the agent was built with the correct name
        call_kwargs = mock_build_agent.call_args[1]
        assert call_kwargs["name"] == "MarOpsBriefer"


class TestCLIBackendFlag:
    """Test that the CLI --backend flag works."""

    def test_cli_accepts_fireworks_backend(self) -> None:
        from scripts.marops.cli import run

        # Just verify the function signature accepts backend
        import inspect

        sig = inspect.signature(run)
        assert "backend" in sig.parameters
        assert sig.parameters["backend"].default == "claude"
