"""Tests for cli.py — the live demo entry point."""

from unittest.mock import MagicMock, patch

import pytest


def _make_brief_mock() -> MagicMock:
    from scripts.marops.models import (
        LifecycleBrief,
        OptimizationTrigger,
        PipelineProjection,
        SegmentDefinition,
        Touch,
        AgentRole,
        TouchChannel,
    )

    return LifecycleBrief(
        prospect="Meridian Analytics",
        prospect_url="https://www.meridian-analytics.example",
        vertical="Supplier compliance SaaS",
        campaign_name="Tier-2 Re-Engagement",
        objective="Reactivate lapsed accounts.",
        lifecycle_stage="Customer · Re-engagement",
        segment=SegmentDefinition(
            name="Lapsed Tier-2",
            salesforce_filters=["Account.Tier__c = 'Tier 2'"],
            warehouse_traits=["product.last_login_at < now() - interval '90 days'"],
            exclusions=["Account.OptOut_AllMarketing__c = TRUE"],
            estimated_size="~2,400 contacts",
        ),
        touches=[
            Touch(
                step=1,
                channel=TouchChannel.EMAIL,
                agent=AgentRole.EXECUTION,
                timing="T+0",
                subject="Your clients require verified suppliers",
                body_brief="Re-engagement email.",
                personalization_tokens=["Contact.FirstName"],
                qa_rules=["Reject if null token"],
                success_metric="Open rate >38%",
            )
        ],
        optimization_triggers=[
            OptimizationTrigger(condition="intent spike detected", action="accelerate to step 4")
        ],
        pipeline_projection=PipelineProjection(
            expected_renewals="~$1.4M ARR",
            ae_efficiency="70% task acceptance",
            campaign_runtime="21 days",
            downside="Pipeline drops 30% if legal fails",
        ),
        meta={
            "model": "claude-sonnet-4-6",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "cache_read_input_tokens": 800,
            "cache_creation_input_tokens": 200,
            "input_tokens": 1000,
            "output_tokens": 500,
        },
    )


def test_run_config_not_found(tmp_path):
    from scripts.marops import cli

    with patch.object(cli, "EXAMPLES", tmp_path):
        with pytest.raises(SystemExit) as exc_info:
            cli.run("nonexistent")
    assert exc_info.value.code == 1


def test_run_api_key_not_set(tmp_path):
    import yaml
    from scripts.marops import cli

    config_path = tmp_path / "meridian.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "prospect": "Meridian Analytics",
                "prospect_url": "https://www.meridian-analytics.example",
                "vertical": "SaaS",
                "campaign_name": "Re-engagement",
                "lifecycle_stage": "Customer",
                "objective": "Reactivate",
                "segment_description": "Lapsed accounts",
            }
        )
    )

    with (
        patch.object(cli, "EXAMPLES", tmp_path),
        patch.dict("os.environ", {}, clear=True),
        patch("scripts.marops.briefer.os.environ.get", return_value=None),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cli.run("meridian")
    assert exc_info.value.code == 1


def test_run_api_timeout(tmp_path):
    import anthropic
    import yaml
    from scripts.marops import cli

    config_path = tmp_path / "meridian.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "prospect": "Meridian Analytics",
                "prospect_url": "https://www.meridian-analytics.example",
                "vertical": "SaaS",
                "campaign_name": "Re-engagement",
                "lifecycle_stage": "Customer",
                "objective": "Reactivate",
                "segment_description": "Lapsed accounts",
            }
        )
    )

    with (
        patch.object(cli, "EXAMPLES", tmp_path),
        patch(
            "scripts.marops.cli.generate_brief",
            side_effect=anthropic.APITimeoutError(request=MagicMock()),
        ),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cli.run("meridian")
    assert exc_info.value.code == 1


def test_run_happy_path(tmp_path):
    import yaml
    from scripts.marops import cli

    config_path = tmp_path / "meridian.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "prospect": "Meridian Analytics",
                "prospect_url": "https://www.meridian-analytics.example",
                "vertical": "SaaS",
                "campaign_name": "Re-engagement",
                "lifecycle_stage": "Customer",
                "objective": "Reactivate",
                "segment_description": "Lapsed accounts",
            }
        )
    )

    brief = _make_brief_mock()

    with (
        patch.object(cli, "EXAMPLES", tmp_path),
        patch.object(cli, "OUT", tmp_path),
        patch("scripts.marops.cli.generate_brief", return_value=brief),
        patch("scripts.marops.cli.render_html") as mock_render,
    ):
        result = cli.run("meridian")

    assert result == tmp_path / "meridian.html"
    mock_render.assert_called_once()
    json_out = tmp_path / "meridian.json"
    assert json_out.exists()
