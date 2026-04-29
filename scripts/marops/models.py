"""Immutable Pydantic models for MarOps lifecycle campaign briefs.

Shape mirrors what Conversion's platform consumes: segment (Salesforce + warehouse
filters) → touch sequence with agent assignments → optimization triggers → pipeline
projection.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class AgentRole(str, Enum):
    EXECUTION = "execution"
    QA = "qa"
    OPTIMIZATION = "optimization"


class TouchChannel(str, Enum):
    EMAIL = "email"
    IN_APP_BANNER = "in_app_banner"
    AE_TASK = "ae_task"
    SMS = "sms"
    LINKEDIN = "linkedin"


class Touch(BaseModel):
    model_config = ConfigDict(frozen=True)

    step: int
    channel: TouchChannel
    agent: AgentRole
    timing: str
    subject: str
    body_brief: str
    personalization_tokens: list[str]
    qa_rules: list[str]
    success_metric: str


class SegmentDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    salesforce_filters: list[str]
    warehouse_traits: list[str]
    exclusions: list[str]
    estimated_size: str


class OptimizationTrigger(BaseModel):
    model_config = ConfigDict(frozen=True)

    condition: str
    action: str


class PipelineProjection(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_renewals: str
    ae_efficiency: str
    campaign_runtime: str
    downside: str


class LifecycleBrief(BaseModel):
    model_config = ConfigDict(frozen=True)

    prospect: str
    prospect_url: str
    vertical: str
    campaign_name: str
    objective: str
    lifecycle_stage: str
    segment: SegmentDefinition
    touches: list[Touch]
    optimization_triggers: list[str]
    pipeline_projection: PipelineProjection
    meta: dict[str, Any]


class MarOpsCampaignConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    prospect: str
    prospect_url: str
    vertical: str
    campaign_name: str
    lifecycle_stage: str
    objective: str
    segment_description: str
    num_touches: int = 5
