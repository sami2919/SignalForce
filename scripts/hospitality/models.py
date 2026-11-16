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
    "job_board",
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
    "opening_soon",
]


Angle = Literal["opening", "people_change", "platform_switch", "relationship", "private_events"]


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


class WebsiteLookup(_Frozen):
    """One paid website lookup for a venue (hit or miss), kept apart from the rebuilt venues.

    `resolve` rebuilds venue rows from public data; it re-applies these, so a website already
    bought is never looked up again. A miss (`website=None`) is retried only after
    `website_miss_retry_days`: a not-yet-open venue often has no listing yet.
    """

    venue_id: str
    website: str | None
    looked_up_on: date
    source: str = "google_places"


class VenueAlias(_Frozen):
    """A venue id that a re-resolve replaced (a licensed venue that got its DOHMH site)."""

    old_venue_id: str
    new_venue_id: str


class GroupEvidence(_Frozen):
    venue_ids: tuple[str, ...]
    name: str
    resolution: GroupResolution
    evidence_ref: str


class CAJob(_Frozen):
    """One job card from a Culinary Agents search page (employer-side facts only)."""

    company: str
    company_url: str
    title: str
    location: str  # the card's address line, e.g. "149 Grand Street, New York, NY"
    group: str | None  # the card's parent / group line, when it shows one
    posted: date | None  # derived from "Posted N days ago" relative to the fetch date
    url: str  # job URL without tracking parameters
    opening_soon: bool = False  # the card came from a search filtered to opening-soon employers


class CACompany(_Frozen):
    """A Culinary Agents company (entity) card or profile page."""

    name: str
    url: str
    description: str
    locations: tuple[str, ...]  # addresses the page shows for this entity
    group: str | None  # "Part of <group>" on the card, when present
    opening_soon: bool
    hiring: bool  # the "Hiring Now" tag
    website: str | None


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


class ExaResult(_Frozen):
    url: str
    title: str
    published_date: date | None
    text: str | None


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
    # The customer's other venues (seed data): a venue matching any of them is the customer's.
    # A name ending in "*" is a brand prefix ("Momofuku*" covers "MOMOFUKU NOODLE BAR").
    venue_names: tuple[str, ...] = ()
    venue_domains: tuple[str, ...] = ()
    venue_id: str | None = None  # embed labels: the venue the embed was observed on


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
    # Tie-break facts (I8), shown in the report: equal priorities are ordered by the opening
    # nearest today (estimated open, or first inspection if already open), then signal recency.
    opening_date: date | None = None
    opening_gap_days: int | None = None  # |opening_date - scoring date|
    latest_signal_on: date | None = None  # newest signal that contributed


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
    """License-signal timeliness among license-matched openings, with its coverage denominator.

    `total` is the truth set (venues first inspected in the window that we could tie to an
    on-premise license and that are not a transfer); `recall` is caught / total. It is NOT the
    share of NYC openings found: `coverage` is caught / `first_inspections` (every venue first
    inspected in the window, matched to a license or not).
    """

    start: date
    end: date
    total: int
    caught: int
    recall: float
    first_inspections: int  # every venue first inspected in the window
    license_matched: int  # of those, venues tied to at least one license record
    coverage: float  # caught / first_inspections
    median_lead_days: float | None  # all leads, including stale ones
    lead_cap_days: int
    median_lead_days_within_cap: float | None  # leads over the cap excluded
    leads_over_cap: int
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
    # Upper bound: live on or before this date. The venue's own seed date when it has its own
    # entry, else the customer's; None when undated (then the case is not evaluable).
    anchor_date: date | None
    new_venue_id: str | None
    first_signal_date: date | None
    lead_days: int | None
    signal_types: tuple[str, ...]
    status: Literal["replayed", "not_evaluable"]
    anchor_basis: Literal["venue", "customer"] | None = None
    reason: str = ""  # why a case is not evaluable; empty when replayed


class BacktestResult(_Frozen):
    cases: tuple[CaseReplay, ...]
    undated: int  # customers with no public date
    fit_auc: float
    fit_distinct: int
    n_customers: int
    n_others: int


class PressPerson(_Frozen):
    name: str
    role: str
    prior_employers: tuple[str, ...]


class PressVenue(_Frozen):
    name: str
    address_or_area: str
    status: Literal["announced", "opening_soon", "opened"]
    expected_open: str | None
    group_name: str | None


class PressFacts(_Frozen):
    venues: tuple[PressVenue, ...]
    people: tuple[PressPerson, ...]
    hotel_partner: str | None


class TeamPerson(_Frozen):
    name: str
    role: str


class TeamFacts(_Frozen):
    people: tuple[TeamPerson, ...]


class TeamPage(_Frozen):
    url: str
    html: str
    text: str
    members: tuple[TeamPerson, ...]


class DraftSentence(_Frozen):
    text: str
    evidence_ids: tuple[str, ...]  # signal_ids of stored evidence
    is_claim: bool  # a factual claim about them; must cite evidence


class Draft(_Frozen):
    draft_id: str
    group_id: str
    contact_id: str | None
    angle: Angle
    subject: str
    sentences: tuple[DraftSentence, ...]


class Judgement(_Frozen):
    score: float
    hyper_specific: bool
    factually_grounded: bool
    non_obvious: bool
    deletion_reason: str
    what_would_make_me_reply: str
    grounding_violations: tuple[str, ...]
    passed: bool


EventType = Literal[
    "trade_show", "curated_conference", "festival", "awards", "local_meetup", "magic_dinner"
]
Role = Literal[
    "speaker",
    "panelist",
    "festival_chef",
    "award_nominee",
    "exhibitor_staff",
    "sponsor",
    "past_recap",
]


class Event(_Frozen):
    event_id: str
    name: str
    start: date | None  # None = date not verified; excluded from ranking
    end: date | None
    city: str
    event_type: EventType
    cost_usd: float
    lineup_urls: tuple[str, ...]
    lineup_gated: bool = False  # lineup only in a gated app: never fetched


class EventAppearance(_Frozen):
    event_id: str
    person: str
    restaurant: str
    role: Role
    source_url: str


class LineupEntry(_Frozen):
    person: str
    restaurant: str
    role: Role


class LineupFacts(_Frozen):
    entries: tuple[LineupEntry, ...]


class EventScore(_Frozen):
    event_id: str
    expected_meetings: float
    score_per_dollar: float  # 0.0 when the event's cost is unknown (never "infinitely efficient")
    matched_people: int


class MeetingTarget(_Frozen):
    event_id: str
    person: str
    group_id: str | None
    p_attend: float
    priority: float
    in_window: bool
    is_customer: bool  # True: warm intro / co-host only, never a cold target
    reason: str
