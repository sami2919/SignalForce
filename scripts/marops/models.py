"""Immutable Pydantic models for MarOps lifecycle campaign briefs.

Shape mirrors what an AI-native, warehouse-native MAP consumes: segment (Salesforce + warehouse
filters) → touch sequence with agent assignments → optimization triggers → pipeline
projection.

Signal decay: WhyNowBlock is computed from YAML-declared signals using a simple
recency decay. 0-7 days = HIGH, 8-30 days = MEDIUM, 31+ days = LOW. Shelf life is
(14 - days_ago) clamped to 0, representing days remaining in the buying window.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class SignalTimingTier(str, Enum):
    HIGH = "HIGH"  # 0-7 days old
    MEDIUM = "MEDIUM"  # 8-30 days old
    LOW = "LOW"  # 31+ days old


def _timing_tier(days_ago: int) -> SignalTimingTier:
    if days_ago <= 7:
        return SignalTimingTier.HIGH
    if days_ago <= 30:
        return SignalTimingTier.MEDIUM
    return SignalTimingTier.LOW


def _shelf_life(days_ago: int, window_days: int = 14) -> int:
    """Days remaining before this signal expires from the buying window."""
    return max(0, window_days - days_ago)


class WhyNowSignal(BaseModel):
    model_config = ConfigDict(frozen=True, use_enum_values=True)

    signal_type: str  # e.g. "g2_review_velocity", "hiring", "conference", "funding"
    description: str
    days_ago: int
    source: str  # e.g. "G2", "LinkedIn", "Crunchbase", "Eventbrite"
    timing_tier: SignalTimingTier = SignalTimingTier.MEDIUM
    shelf_life_days: int = 0

    @model_validator(mode="before")
    @classmethod
    def compute_decay(cls, values: dict) -> dict:
        days = values.get("days_ago", 30)
        values.setdefault("timing_tier", _timing_tier(days).value)
        values.setdefault("shelf_life_days", _shelf_life(days))
        return values


class WhyNowBlock(BaseModel):
    model_config = ConfigDict(frozen=True, use_enum_values=True)

    timing_score: SignalTimingTier
    signals: list[WhyNowSignal]
    shelf_life_days: int  # minimum shelf life across all signals
    rationale: str


def compute_why_now(raw_signals: list[dict]) -> WhyNowBlock | None:
    """Build a WhyNowBlock from a list of raw signal dicts (from YAML)."""
    if not raw_signals:
        return None
    signals = [WhyNowSignal(**s) for s in raw_signals]
    min_shelf = min(s.shelf_life_days for s in signals)
    # Aggregate timing: any HIGH → HIGH, else any MEDIUM → MEDIUM, else LOW
    tiers = {s.timing_tier for s in signals}
    if SignalTimingTier.HIGH in tiers:
        agg = SignalTimingTier.HIGH
    elif SignalTimingTier.MEDIUM in tiers:
        agg = SignalTimingTier.MEDIUM
    else:
        agg = SignalTimingTier.LOW
    rationale = (
        f"{len(signals)} signal{'s' if len(signals) != 1 else ''} detected in the last "
        f"{max(s.days_ago for s in signals)} days. "
        f"Buying window closes in ~{min_shelf} days."
    )
    return WhyNowBlock(
        timing_score=agg,
        signals=signals,
        shelf_life_days=min_shelf,
        rationale=rationale,
    )


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
    optimization_triggers: list[OptimizationTrigger]
    pipeline_projection: PipelineProjection
    meta: dict[str, Any]
    why_now: WhyNowBlock | None = None


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
    why_now_signals: list[dict[str, Any]] = []
