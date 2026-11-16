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
    fit_weights: dict[str, float]
    relationship_boost: float
    budgets: dict[str, int]
    models: dict[str, str]
    match_max_distance_m: float
    match_auto_threshold: float
    match_link_threshold: float


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> HospitalityConfig:
    """Load and validate the hospitality YAML config."""
    with Path(path).open() as fh:
        raw = yaml.safe_load(fh)
    return HospitalityConfig.model_validate(raw)
