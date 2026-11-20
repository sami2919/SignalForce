"""Hospitality pipeline configuration: priors, thresholds, budgets and model names as data."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "examples/magic-loyalist/hospitality.yaml"
)

# "fit" signals feed a fit criterion (fit_score), never p_window.
SignalFamily = Literal["opening", "stack", "people", "relationship", "events", "discovery", "fit"]


class SignalPrior(BaseModel):
    model_config = ConfigDict(frozen=True)

    precision: float
    half_life_days: float | None
    family: SignalFamily


class CulinaryAgentsConfig(BaseModel):
    """Culinary Agents job-board source. Off by default: its user agreement restricts scraping."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    # Logged-in mode (the operator's own session cookie in CULINARY_AGENTS_COOKIE): paginates
    # past page 1 through the site's XHR endpoint. The agreement (section 7) bans robots and
    # scrapers without written permission; the operator accepts the risk by turning this on.
    authenticated: bool = False
    # Logged-in mode: pages walked per search at most (20 items a page), and the daily run's
    # early exit after this many consecutive already-seen organic (non-sponsored) items.
    max_pages_per_search: int = 50
    daily_stop_after_known: int = 15
    # Search segment filter ids sent as search[segment_ids][] (captured defaults; confirm the
    # labels during the first supervised run).
    segment_ids: tuple[str, ...] = ("13", "9", "2", "1")
    # A company profile fetched less than this many days ago is not fetched again.
    profile_refresh_days: int = 30
    # Search locations; each costs 3 pages: jobs, opening-soon jobs, opening-soon companies.
    locations: tuple[str, ...] = ("New York, NY",)
    delay_seconds: float = 2.0
    # Opening-soon company profile pages fetched for a website (domain matching), at most.
    max_company_pages: int = 10
    # Title regexes over the folded, lowercased title, one list per signal type (section 7 of
    # the logged-in plan). Checked in this order; the first list that matches wins.
    chef_titles: tuple[str, ...] = (
        r"\b(executive|head|corporate|opening) chef\b",
        r"\bchef de cuisine\b",
        r"\bculinary director\b",
        r"\bdirector of culinary\b",
    )
    gm_titles: tuple[str, ...] = (
        r"\bgeneral manager\b",
        r"^gm$",
        r"\bopening gm\b",
        r"\bdirector of operations\b",
    )
    events_titles: tuple[str, ...] = (
        (
            r"\b(events?|private dining|private events?|catering) (sales )?"
            r"(manager|director|coordinator|sales)\b"
        ),
        r"\bdirector of (private )?(events?|dining|catering)\b",
    )
    guest_titles: tuple[str, ...] = (
        r"\bguest (relations|experience) (manager|director)\b",
        r"\breservations? (manager|director|supervisor)\b",
        r"\breservationists?\b",
        r"\bmaitre d\b",
        r"\bhost manager\b",
        r"\bdirector of (sales|partnerships)\b",
        r"\b(marketing (manager|director)|director of marketing)\b",
        r"\bcrm\b",
        r"\bloyalty\b",
        r"\bguest data\b",
    )
    # Senior roles left over for the older `role_hire` type.
    leadership_titles: tuple[str, ...] = (
        r"\bdirector of (hospitality|food (and|&) beverage)\b",
        r"\b(pre-?opening|opening) (team|manager)\b",
    )
    # A title containing any of these words is never senior-leadership evidence.
    exclude_title_words: tuple[str, ...] = ("assistant", "associate", "intern", "trainee")
    # Fine-dining service roles: evidence for the `fine_dining_service` fit criterion only.
    service_titles: tuple[str, ...] = (
        r"\bsommeliers?\b",
        r"\b(wine|beverage) director\b",
        r"\bdirector of (wine|beverage)\b",
        r"\bcaptains?\b",
        r"\bservice manager\b",
    )
    # A posting like this is a whole venue staffing at once (`hiring_burst`).
    open_call_titles: tuple[str, ...] = (r"\bopen call\b",)
    # `hiring_burst` also fires at this many distinct roles from one employer in the window.
    burst_min_roles: int = 5
    burst_window_days: int = 30


class PremisesRule(BaseModel):
    """Data-driven non-restaurant premises (I8). A venue is non-restaurant when its zip code is
    listed, or when every one of its licenses has a listed description. A group is disqualified
    only when every venue is (one airport outpost does not disqualify a restaurant group), and a
    venue with no premises evidence (no license, unlisted zip) never counts as non-restaurant.
    """

    model_config = ConfigDict(frozen=True)

    zip_codes: dict[str, str]  # zip -> label, e.g. "11430": airport
    license_descriptions: dict[str, str]  # SLA description -> label


class EventsConfig(BaseModel):
    """Event ranking priors (starting assumptions, not measured) and the in-window threshold."""

    model_config = ConfigDict(frozen=True)

    attend_prior: dict[str, float]  # role -> P(the person attends)
    meeting_rate_prior: dict[str, float]  # event type -> P(a qualified meeting | attends)
    unmatched_priority: float  # priority of a person whose restaurant matches no venue
    # A meeting target is "in window" at p_window >= this (M1).
    in_window_p: float


class BenchmarkConfig(BaseModel):
    """Head-to-head size and the spend shown before it runs."""

    model_config = ConfigDict(frozen=True)

    runs: int
    max_searches: int  # web searches per Claude run, at most
    k: int  # list length scored on each side
    web_search_usd_each: float  # list price, for the spend warning only


class WebsitesConfig(BaseModel):
    """Website lookup: provider choice and the search-and-verify rules (lists are data)."""

    model_config = ConfigDict(frozen=True)

    # `search`: Exa (primary) / Firecrawl search (fallback) + deterministic page verification.
    # `places`: the Google Places provider (needs GOOGLE_PLACES_API_KEY).
    provider: Literal["search", "places"] = "search"
    # Search results requested per query, and distinct candidate domains verified at most.
    search_results: int = 8
    max_candidates: int = 5
    # Extra pages fetched per candidate after its home page (the first of `verify_paths`).
    max_verify_pages: int = 3
    verify_paths: tuple[str, ...] = (
        "/contact",
        "/contact-us",
        "/locations",
        "/location",
        "/visit",
        "/about",
    )
    # A candidate must show the street address, then one of these terms (or the zip) within
    # this many tokens after it.
    address_context_tokens: int = 10
    address_context_terms: tuple[str, ...] = (
        "new york",
        "ny",
        "manhattan",
        "brooklyn",
        "queens",
        "bronx",
        "staten island",
    )
    # A provider that errors this many times in a row is switched off for the run.
    max_provider_errors: int = 3
    # Registrable domains that are never a venue's own site (directories, social, marketplaces,
    # delivery, reservation platforms, government, news). Matched on the registrable domain.
    excluded_domains: tuple[str, ...]


class HospitalityConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasets: dict[str, str]
    nyc_counties: tuple[str, ...]
    on_premise_descriptions: tuple[str, ...]
    priors: dict[str, SignalPrior]
    window_pre_days: int
    window_post_days: int
    window_outside_half_life_days: float
    pending_to_issue_prior_days: int
    window_unmatched_censor_max_age_days: int
    # Longest issue-to-first-inspection time that counts as an opening (the curve drops longer
    # durations); a not_yet_inspected venue licensed longer ago than the cap is stale.
    max_opening_days: float
    not_yet_inspected_max_age_days: float
    # license_issued fires only for licenses issued within this many days.
    issued_lookback_days: int
    # Recall audit: a lead longer than this is reported as stale and kept out of the median.
    recall_lead_cap_days: int
    events: EventsConfig
    benchmark: BenchmarkConfig
    # A judged draft passes at or above this LLM rubric score (and only with no violations).
    judge_pass_score: float
    # A Hunter email is used only at or above this confidence (0-100).
    min_email_confidence: float
    # Paid-spend caps per group: Hunter email lookups, and drafted angles (one Claude draft and
    # one judge call each).
    max_email_lookups_per_group: int
    draft_angles_per_group: int
    # The demo report's recall audit looks back this many weeks.
    report_recall_weeks: int
    # Google Places candidate acceptance for a venue's website.
    website_match_max_distance_m: float
    website_match_min_name_similarity: float
    websites: WebsitesConfig
    fit_weights: dict[str, float]
    relationship_boost: float
    budgets: dict[str, int]
    models: dict[str, str]
    match_max_distance_m: float
    match_auto_threshold: float
    match_link_threshold: float
    # Registrable domains shared by unrelated businesses (social profiles, booking pages, site
    # builders): a venue "website" on one of these never merges groups by shared domain.
    shared_host_domains: tuple[str, ...]
    # A website lookup that found nothing is retried only after this many days (a venue that
    # has not opened often has no listing yet); a found website is never looked up again.
    website_miss_retry_days: int
    # Accolade names (Michelin, JBF) or group ids; names match group and venue names strictly.
    accolades: tuple[str, ...] = ()
    # Opening evidence is one underlying fact per venue: only the strongest of these counts.
    opening_evidence_signals: tuple[str, ...] = (
        "license_pending",
        "license_issued",
        "not_yet_inspected",
        "opening_soon",
        "hiring_burst",
    )
    # At most this many venues' opening terms enter a group's p_window (strongest first).
    max_opening_venues_per_group: int = 3
    # Case-insensitive regexes over normalized group / venue / licensee names (contract
    # and institutional food-service operators are not Magic's buyer). Required: a config that
    # omits a disqualifier list must fail to load, not silently disqualify nothing (M2).
    disqualify_name_patterns: tuple[str, ...]
    disqualify_reason: str = "contract_foodservice"
    # Premises that are not a restaurant, read from the data (zip code, license class).
    non_restaurant_premises: PremisesRule
    # reason -> regexes, for non-buyers the data cannot express (zoos, caterers, hotel chains);
    # checked in order, the first matching reason wins.
    non_restaurant_name_patterns: dict[str, tuple[str, ...]]
    culinary_agents: CulinaryAgentsConfig = CulinaryAgentsConfig()
    # Employers whose alumni are a warm-intro edge (Loyalist's founders / champions' pedigree).
    alumni_employers: tuple[str, ...] = (
        "Eleven Madison Park",
        "Make It Nice",
        "Union Square Hospitality Group",
        "Major Food Group",
        "Momofuku",
        "The Corner Store",
        "Thomas Keller Restaurant Group",
    )


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> HospitalityConfig:
    """Load and validate the hospitality YAML config."""
    with Path(path).open() as fh:
        raw = yaml.safe_load(fh)
    return HospitalityConfig.model_validate(raw)
