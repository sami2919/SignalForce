"""Core Pydantic data models for the SignalForce GTM pipeline.

These models define the shape of data flowing between all pipeline components:
    scanners → researcher → contact finder → email writer → pipeline tracker

All models are immutable (frozen=True) to prevent hidden side effects.
"""

from __future__ import annotations

from datetime import datetime, UTC
from enum import Enum, IntEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, field_validator, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SignalStrength(IntEnum):
    WEAK = 1
    MODERATE = 2
    STRONG = 3


class ICPScore(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class EnrichmentSource(str, Enum):
    APOLLO = "APOLLO"
    HUNTER = "HUNTER"
    PROSPEO = "PROSPEO"
    PEOPLE_DATA_LABS = "PEOPLE_DATA_LABS"
    MANUAL = "MANUAL"


class EmailVariant(str, Enum):
    PROBLEM_FOCUSED = "PROBLEM_FOCUSED"
    OUTCOME_FOCUSED = "OUTCOME_FOCUSED"
    SOCIAL_PROOF_FOCUSED = "SOCIAL_PROOF_FOCUSED"


class OutreachChannel(str, Enum):
    EMAIL = "EMAIL"
    LINKEDIN = "LINKEDIN"
    LINKEDIN_INMAIL = "LINKEDIN_INMAIL"


class DealStage(str, Enum):
    SIGNAL_DETECTED = "SIGNAL_DETECTED"
    RESEARCHED = "RESEARCHED"
    ENRICHED = "ENRICHED"
    SEQUENCED = "SEQUENCED"
    ENGAGED = "ENGAGED"
    RESPONDED = "RESPONDED"
    MEETING_SCHEDULED = "MEETING_SCHEDULED"
    MEETING_COMPLETED = "MEETING_COMPLETED"
    PROPOSAL_SENT = "PROPOSAL_SENT"
    DISQUALIFIED = "DISQUALIFIED"


# ---------------------------------------------------------------------------
# Sequence step model
# ---------------------------------------------------------------------------


class SequenceStep(BaseModel):
    """A single step in a multi-channel outreach sequence."""

    model_config = ConfigDict(frozen=True)

    day: int
    channel: OutreachChannel
    action: str  # "send_email", "connection_request", "follow_up_message"
    template_name: str
    variant: str | None = None


# ---------------------------------------------------------------------------
# Signal model
# ---------------------------------------------------------------------------


class Signal(BaseModel):
    """A detected market signal indicating buyer intent or activity."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    signal_type: str
    company_name: str
    company_domain: str | None = None
    signal_strength: SignalStrength
    source_url: str
    raw_data: dict
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Company profile model
# ---------------------------------------------------------------------------


class CompanyProfile(BaseModel):
    """Enriched profile of a target company."""

    model_config = ConfigDict(frozen=True)

    company_name: str
    domain: str
    icp_tier: str | None = None
    icp_score: ICPScore | None = None
    maturity_stage: str | None = None
    employee_count: int | None = None
    funding_stage: str | None = None
    founded_year: int | None = None
    hq_location: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)
    composite_signal_score: float = 0.0
    researched_at: datetime | None = None
    notes: str = ""


# ---------------------------------------------------------------------------
# Contact model
# ---------------------------------------------------------------------------


class Contact(BaseModel):
    """A target contact at a prospect company."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    full_name: str
    title: str
    title_category: str
    email: str | None = None
    email_verified: bool = False
    email_verification_source: str | None = None
    linkedin_url: str | None = None
    enrichment_source: EnrichmentSource | None = None
    company_domain: str
    confidence_score: float = 0.0
    found_at: datetime | None = None

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence_score(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence_score must be between 0.0 and 1.0, got {v}")
        return v


# ---------------------------------------------------------------------------
# Generated email model
# ---------------------------------------------------------------------------


class GeneratedEmail(BaseModel):
    """A personalized outbound email generated for a contact."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    contact_id: str
    signal_type: str
    signal_reference: str
    subject_line: str
    body: str
    cta: str
    variant: EmailVariant
    template_name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Deal model
# ---------------------------------------------------------------------------


class Deal(BaseModel):
    """Tracks a prospect through the GTM pipeline."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    company_profile: CompanyProfile
    contacts: list[Contact] = Field(default_factory=list)
    emails_sent: list[GeneratedEmail] = Field(default_factory=list)
    stage: DealStage = DealStage.SIGNAL_DETECTED
    hubspot_deal_id: str | None = None
    instantly_campaign_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str = ""


# ---------------------------------------------------------------------------
# Scan result model
# ---------------------------------------------------------------------------


class ScanResult(BaseModel):
    """Summary of a completed scanner run."""

    model_config = ConfigDict(frozen=True)

    scan_id: str = Field(default_factory=lambda: str(uuid4()))
    scan_type: str
    started_at: datetime
    completed_at: datetime
    signals_found: list[Signal]
    total_raw_results: int
    total_after_dedup: int
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Meeting outcome model
# ---------------------------------------------------------------------------


class MeetingOutcome(BaseModel):
    """Structured output from a discovery/demo meeting."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    deal_id: str
    meeting_date: datetime
    attendees: list[str]
    outcome: str  # "positive", "neutral", "negative", "no_show"
    objections: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    decision_timeline: str | None = None
    stakeholders_needed: list[str] = Field(default_factory=list)
    follow_up_resources: list[str] = Field(default_factory=list)
    notes: str = ""
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Playbook entry model
# ---------------------------------------------------------------------------


class PlaybookEntry(BaseModel):
    """A signal-to-angle mapping that drives outreach personalization.

    Each entry connects a signal type + trigger pattern to a specific outreach
    angle, complete with email opener and proof point templates.
    """

    model_config = ConfigDict(frozen=True)

    signal_type: str
    trigger_pattern: str
    angle_name: str
    angle_description: str
    email_opener: str
    proof_point_template: str
