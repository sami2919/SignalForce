"""Tests for briefer.py — Claude API call mocked."""
from unittest.mock import MagicMock, patch

import pytest

from scripts.marops.briefer import generate_brief
from scripts.marops.models import LifecycleBrief, MarOpsCampaignConfig

_CONFIG = MarOpsCampaignConfig(
    prospect="Veriforce",
    prospect_url="https://www.veriforce.com",
    vertical="Supplier compliance SaaS",
    campaign_name="Tier-2 Re-Engagement",
    lifecycle_stage="Customer · Re-engagement",
    objective="Reactivate lapsed accounts.",
    segment_description="Lapsed Tier-2 suppliers, 90+ days no login.",
)

_TOOL_INPUT = {
    "segment": {
        "name": "Lapsed Tier-2",
        "salesforce_filters": ["Account.Tier__c = 'Tier 2'"],
        "warehouse_traits": ["product.last_login_at < now() - interval '90 days'"],
        "exclusions": ["Account.OptOut_AllMarketing__c = TRUE"],
        "estimated_size": "~2,400 contacts",
    },
    "touches": [
        {
            "step": 1,
            "channel": "email",
            "agent": "execution",
            "timing": "T+0",
            "subject": "Your clients require verified suppliers",
            "body_brief": "Re-engagement email.",
            "personalization_tokens": ["Contact.FirstName"],
            "qa_rules": ["Reject if null token"],
            "success_metric": "Open rate >38%",
        }
    ],
    "optimization_triggers": ["Intent spike → accelerate to step 4"],
    "pipeline_projection": {
        "expected_renewals": "~$1.4M ARR",
        "ae_efficiency": "70% task acceptance",
        "campaign_runtime": "21 days",
        "downside": "Pipeline drops 30% if legal fails",
    },
    "meta": {"platform_fit": "Salesforce + warehouse sync"},
}


def _mock_response(tool_input: dict) -> MagicMock:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = tool_input

    usage = MagicMock()
    usage.input_tokens = 1000
    usage.output_tokens = 500
    usage.cache_read_input_tokens = 800
    usage.cache_creation_input_tokens = 200

    response = MagicMock()
    response.content = [tool_block]
    response.usage = usage
    return response


def test_generate_brief_returns_lifecycle_brief():
    with patch("scripts.marops.briefer.anthropic.Anthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create.return_value = _mock_response(_TOOL_INPUT)
        brief = generate_brief(_CONFIG)

    assert isinstance(brief, LifecycleBrief)
    assert brief.prospect == "Veriforce"
    assert brief.segment.name == "Lapsed Tier-2"
    assert len(brief.touches) == 1
    assert brief.meta["input_tokens"] == 1000


def test_generate_brief_raises_when_no_tool_use():
    with patch("scripts.marops.briefer.anthropic.Anthropic") as mock_client_cls:
        response = MagicMock()
        response.content = []  # no tool_use block
        mock_client_cls.return_value.messages.create.return_value = response

        with pytest.raises(RuntimeError, match="did not invoke"):
            generate_brief(_CONFIG)
