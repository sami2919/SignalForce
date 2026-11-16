"""Hospitality pipeline configuration: priors, thresholds, budgets and model names as data."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "examples/magic-loyalist/hospitality.yaml"
)

SignalFamily = Literal["opening", "stack", "people", "relationship", "events", "discovery"]


class SignalPrior(BaseModel):
    model_config = ConfigDict(frozen=True)

    precision: float
    half_life_days: float | None
    family: SignalFamily


class CulinaryAgentsConfig(BaseModel):
    """Culinary Agents job-board source. Off by default: its user agreement restricts scraping."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    # Search locations; each costs 3 pages: jobs, opening-soon jobs, opening-soon companies.
    locations: tuple[str, ...] = ("New York, NY",)
    delay_seconds: float = 2.0
    # Opening-soon company profile pages fetched for a website (domain matching), at most.
    max_company_pages: int = 10
    # Senior roles that emit `new_gm` / `role_hire`; line-level roles emit nothing.
    gm_titles: tuple[str, ...] = (r"\bgeneral manager\b", r"^gm$")
    leadership_titles: tuple[str, ...] = (
        r"\bdirector of (operations|hospitality|food (and|&) beverage)\b",
        r"\b(events?|private dining|private events?|catering) (manager|director|coordinator)\b",
        r"\b(pre-?opening|opening) (team|manager|gm|general manager)\b",
        r"\bmaitre d\b",
        r"\bguest (relations|experience) manager\b",
        r"\breservations? manager\b",
    )
    # A title containing any of these words is never senior-leadership evidence.
    exclude_title_words: tuple[str, ...] = ("assistant", "associate", "intern", "trainee")


class PremisesRule(BaseModel):
    """Data-driven non-restaurant premises (I8). A venue is non-restaurant when its zip code is
    listed, or when every one of its licenses has a listed description. A group is disqualified
    only when every venue is (one airport outpost does not disqualify a restaurant group), and a
    venue with no premises evidence (no license, unlisted zip) never counts as non-restaurant.
    """

    model_config = ConfigDict(frozen=True)

    zip_codes: dict[str, str]  # zip -> label, e.g. "11430": airport
    license_descriptions: dict[str, str]  # SLA description -> label


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
    # Google Places candidate acceptance for a venue's website.
    website_match_max_distance_m: float
    website_match_min_name_similarity: float
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
    # Manually flagged accolade groups (Michelin / JBF): group ids or names. Empty for the demo.
    accolades: tuple[str, ...] = ()
    # Opening evidence is one underlying fact per venue: only the strongest of these counts.
    opening_evidence_signals: tuple[str, ...] = (
        "license_pending",
        "license_issued",
        "not_yet_inspected",
        "opening_soon",
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
