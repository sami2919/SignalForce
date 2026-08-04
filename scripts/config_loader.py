"""Load and validate SignalForce ICP configuration from YAML.

Distinct from scripts/config.py which handles secrets/API keys from .env.
This module handles domain configuration: what to scan for, how to score, who to target.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from scripts.models import PlaybookEntry

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_DIRNAME = "config"


def config_dir() -> Path:
    """Resolve the active config directory AT CALL TIME.

    Defaults to <repo>/config, which is gitignored. Tests and fresh clones set
    SIGNALFORCE_CONFIG_DIR to point at the committed config.example/ instead.

    Deliberately an explicit override rather than an automatic fallback to
    config.example: a production deploy with a missing config/ must fail
    loudly, not silently run on example data.
    """
    override = os.environ.get("SIGNALFORCE_CONFIG_DIR")
    if override:
        return Path(override)
    return _PROJECT_ROOT / _DEFAULT_CONFIG_DIRNAME


def config_file() -> Path:
    return config_dir() / "config.yaml"


def playbooks_file() -> Path:
    return config_dir() / "playbooks.yaml"


class CompanyConfig(BaseModel):
    """Company identity and product positioning."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    product: str
    category: str
    website: str = ""


class ICPTierConfig(BaseModel):
    """A single ICP tier definition."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    description: str
    signals: list[str] = []


class ICPConfig(BaseModel):
    """Ideal Customer Profile configuration."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    tiers: list[ICPTierConfig]
    maturity_stages: list[str]
    target_titles: list[str]
    disqualifiers: list[str] = []


class ScannerConfig(BaseModel):
    """Configuration for a single scanner module."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    enabled: bool = True
    module: str
    keywords: list[str] = []
    topics: list[str] = []
    libraries: list[str] = []
    queries: list[str] = []
    training_tags: list[str] = []
    card_keywords: list[str] = []
    titles: list[str] = []
    skills: list[str] = []
    lookback_days: int = 7
    custom_params: dict[str, Any] = {}


class ScoringConfig(BaseModel):
    """Scoring engine configuration: weights, half-lives, grade thresholds."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    intent_weights: dict[str, float]
    half_lives_days: dict[str, float]
    icp_weight: float = 0.4
    intent_weight: float = 0.6
    grade_thresholds: dict[str, float] = {"A": 8.0, "B": 5.0, "C": 2.0}


class FiltersConfig(BaseModel):
    """Optional post-scan filters applied before scoring."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    company_blocklist: list[str] = []


class SignalForceConfig(BaseModel):
    """Top-level SignalForce configuration."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    company: CompanyConfig
    icp: ICPConfig
    scanners: dict[str, ScannerConfig]
    scoring: ScoringConfig
    filters: FiltersConfig = FiltersConfig()


def check_config_exists(config_dir_path: Path | None = None) -> None:
    """Check that config/ exists with a config.yaml. Exit with helpful message if not."""
    directory = config_dir_path if config_dir_path is not None else config_dir()
    if not directory.exists() or not (directory / "config.yaml").exists():
        print(
            "\n  SignalForce is not configured yet.\n"
            "\n"
            "  Quick start:\n"
            "    1. Run the /setup skill to auto-generate config for your ICP\n"
            "    2. Or copy an example:  cp -r examples/rl-infrastructure/ config/\n"
            "    3. Or copy the template: cp -r config.example/ config/\n"
            "\n"
            "  See README.md for details.\n"
        )
        raise SystemExit(1)


def load_config(config_path: Path | None = None) -> SignalForceConfig:
    """Load and validate SignalForce configuration.

    Raises:
        FileNotFoundError: config file does not exist.
        yaml.YAMLError: YAML syntax error.
        pydantic.ValidationError: schema validation failure.
    """
    path = config_path if config_path is not None else config_file()
    if not path.exists():
        raise FileNotFoundError(
            f"No config found at {path}. "
            "Run the /setup skill to configure SignalForce for your ICP, "
            "or copy an example: cp -r config.example/ config/"
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SignalForceConfig.model_validate(raw)


def load_playbooks(
    playbooks_path: Path | None = None,
) -> list[PlaybookEntry]:
    """Load and validate signal-to-angle playbook entries from YAML.

    Returns a list of validated PlaybookEntry models.

    Raises:
        FileNotFoundError: playbooks file does not exist.
        yaml.YAMLError: YAML syntax error.
        pydantic.ValidationError: schema validation failure.
    """
    playbooks_path = playbooks_path if playbooks_path is not None else playbooks_file()
    if not playbooks_path.exists():
        raise FileNotFoundError(
            f"No playbooks found at {playbooks_path}. "
            "Copy config.example/playbooks.yaml to config/playbooks.yaml "
            "and customize for your product."
        )
    raw = yaml.safe_load(playbooks_path.read_text(encoding="utf-8"))
    entries = raw.get("playbooks", [])
    return [PlaybookEntry.model_validate(entry) for entry in entries]


def lookup_playbooks_by_signal_type(
    playbooks: list[PlaybookEntry],
    signal_type: str,
) -> list[PlaybookEntry]:
    """Return all playbook entries matching a given signal type."""
    return [p for p in playbooks if p.signal_type == signal_type]
