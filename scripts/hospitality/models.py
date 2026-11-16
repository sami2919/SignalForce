"""Frozen Pydantic domain models shared by every hospitality pipeline step."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LicenseSource = Literal["sla_pending", "sla_active", "sla_inactive"]
GroupResolution = Literal[
    "singleton",
    "shared_legal_name",
    "shared_domain",
    "website_locations",
    "press",
    "agent",
    "manual",
]
SignalType = Literal[
    "license_pending",
    "license_issued",
    "not_yet_inspected",
    "press_opening",
    "stack_fragmented",
    "private_events",
    "tripleseat_resy",
    "hotel_partnership",
    "role_hire",
    "new_gm",
    "platform_switch",
    "alumni_edge",
    "lookalike",
]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class LicenseRecord(_Frozen):
    source: LicenseSource
    record_id: str
    legal_name: str
    dba: str
    address: str
    city: str
    zip_code: str
    county: str
    license_class: str
    description: str
    received_date: date | None
    original_issue_date: date | None
    lat: float | None
    lon: float | None


class InspectionVenue(_Frozen):
    camis: str
    dba: str
    boro: str
    address: str
    zip_code: str
    cuisine: str
    phone: str
    lat: float | None
    lon: float | None
    first_inspection_date: date | None
    first_inspection_type: str | None


class Venue(_Frozen):
    venue_id: str
    name: str
    address: str
    zip_code: str
    lat: float | None
    lon: float | None
    camis: str | None
    license_ids: tuple[str, ...]
    license_class: str | None
    license_description: str | None
    first_inspection_date: date | None
    website: str | None
    group_id: str


class Group(_Frozen):
    group_id: str
    name: str
    venue_ids: tuple[str, ...]
    resolution: GroupResolution


class GroupEvidence(_Frozen):
    venue_ids: tuple[str, ...]
    name: str
    resolution: GroupResolution
    evidence_ref: str


class EntityLink(_Frozen):
    left_id: str
    right_id: str
    kind: Literal["possibly_same"]
    probability: float = Field(ge=0, le=1)
    method: str


class Signal(_Frozen):
    signal_id: str
    signal_type: SignalType
    entity_id: str  # a venue_id or group_id
    observed_at: datetime
    occurred_at: datetime | None
    source: str
    evidence_ref: str
    detail: str  # short human-readable string


class StackObservation(_Frozen):
    venue_id: str
    url: str
    observed_at: datetime
    platforms: tuple[str, ...]
    evidence: tuple[str, ...]
    fetched_via: Literal["fetcher", "firecrawl"]


class PlaceMatch(_Frozen):
    place_id: str
    display_name: str
    address: str
    website: str | None
    lat: float
    lon: float


class WindowEstimate(_Frozen):
    venue_id: str
    estimated_open: date
    p_open_90d: float = Field(ge=0, le=1)
    p_open_180d: float = Field(ge=0, le=1)
    basis: str


class CustomerLabel(_Frozen):
    name: str
    website_domain: str | None
    first_public_date: date | None
    source: Literal["public_list", "embed"]
    evidence_ref: str


class Contribution(_Frozen):
    signal_id: str
    signal_type: str
    precision: float
    weight: float
    contribution: float
    note: str = ""  # why a zero contribution was folded / capped (empty when it counted)


class ScoredAccount(_Frozen):
    group_id: str
    p_window: float = Field(ge=0, le=1)
    fit: float = Field(ge=0, le=1)
    relationship: float
    priority: float
    contributions: tuple[Contribution, ...]
    disqualified_reason: str | None
    is_customer: bool


class Contact(_Frozen):
    contact_id: str
    group_id: str
    name: str
    role: str
    email: str | None
    email_confidence: float | None
    instagram: str | None
    phone: str | None
    source: str
    evidence_ref: str


class PendingSnapshot(_Frozen):
    taken_on: date
    record_id: str


class MatchPair(_Frozen):
    license_id: str
    camis: str
    probability: float
    method: str


class MatchResult(_Frozen):
    pairs: tuple[MatchPair, ...]
    links: tuple[EntityLink, ...]
    unmatched_licenses: tuple[str, ...]
    unmatched_camis: tuple[str, ...]


class CurveRecord(_Frozen):
    stratum: str
    n: int
    steps: tuple[tuple[float, float], ...]


class RecallReport(_Frozen):
    start: date
    end: date
    total: int
    caught: int
    recall: float
    median_lead_days: float | None
    lead_days: tuple[int, ...]
    misses: tuple[str, ...]


class BaselineItem(_Frozen):
    name: str
    location: str
    group: str | None
    expected_opening: str | None


class BaselineRun(_Frozen):
    run_index: int
    items: tuple[BaselineItem, ...]
    searches_used: int


class BenchmarkResult(_Frozen):
    k: int
    sf_hits: int
    sf_precision_at_k: float
    claude_hits: tuple[int, ...]
    claude_precision_at_k: tuple[float, ...]
    claude_duplicates: tuple[int, ...]
    claude_unmatched: tuple[int, ...]
    claude_run_jaccard: float
    truth_total: int
    notes: tuple[str, ...]


class CaseReplay(_Frozen):
    group_id: str
    customer: str
    anchor_date: date  # upper bound: the customer was live on or before this date
    new_venue_id: str | None
    first_signal_date: date | None
    lead_days: int | None
    signal_types: tuple[str, ...]
