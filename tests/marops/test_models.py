"""Tests for MarOps Pydantic models."""
import pytest

from scripts.marops.models import (
    AgentRole,
    LifecycleBrief,
    MarOpsCampaignConfig,
    PipelineProjection,
    SegmentDefinition,
    Touch,
    TouchChannel,
)


def _make_segment() -> SegmentDefinition:
    return SegmentDefinition(
        name="Lapsed Tier-2",
        salesforce_filters=["Account.Tier__c = 'Tier 2'"],
        warehouse_traits=["product.last_login_at < now() - interval '90 days'"],
        exclusions=["Account.OptOut_AllMarketing__c = TRUE"],
        estimated_size="~2,400 contacts",
    )


def _make_touch() -> Touch:
    return Touch(
        step=1,
        channel=TouchChannel.EMAIL,
        agent=AgentRole.EXECUTION,
        timing="T+0",
        subject="Your clients require verified suppliers",
        body_brief="Plain-text re-engagement.",
        personalization_tokens=["Contact.FirstName"],
        qa_rules=["Reject if token is null"],
        success_metric="Open rate >38%",
    )


def test_touch_is_immutable():
    touch = _make_touch()
    with pytest.raises(Exception):
        touch.step = 2  # type: ignore


def test_segment_is_immutable():
    seg = _make_segment()
    with pytest.raises(Exception):
        seg.name = "mutated"  # type: ignore


def test_lifecycle_brief_round_trips_json():
    brief = LifecycleBrief(
        prospect="Veriforce",
        prospect_url="https://www.veriforce.com",
        vertical="Supplier compliance SaaS",
        campaign_name="Tier-2 Re-Engagement",
        objective="Reactivate lapsed accounts.",
        lifecycle_stage="Customer · Re-engagement",
        segment=_make_segment(),
        touches=[_make_touch()],
        optimization_triggers=["Intent spike: accelerate to step 4"],
        pipeline_projection=PipelineProjection(
            expected_renewals="~$1.4M ARR",
            ae_efficiency="70% task acceptance",
            campaign_runtime="21 days",
            downside="Pipeline drops 30% if legal fails",
        ),
        meta={},
    )
    data = brief.model_dump()
    assert data["prospect"] == "Veriforce"
    assert data["segment"]["name"] == "Lapsed Tier-2"
    assert data["touches"][0]["channel"] == "email"


def test_campaign_config_validates():
    config = MarOpsCampaignConfig(
        prospect="Veriforce",
        prospect_url="https://www.veriforce.com",
        vertical="SaaS",
        campaign_name="Re-engagement",
        lifecycle_stage="Customer",
        objective="Reactivate",
        segment_description="Lapsed accounts",
    )
    assert config.num_touches == 5
