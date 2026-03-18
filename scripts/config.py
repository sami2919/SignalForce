"""Configuration management for the RL GTM pipeline.

Loads environment variables from .env file and exposes them via a validated,
immutable Pydantic Settings model. A cached singleton is provided via get_config().
"""

from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env at import time so os.environ is populated before any model is created.
load_dotenv()


# ---------------------------------------------------------------------------
# Settings model
# ---------------------------------------------------------------------------


class AppConfig(BaseSettings):
    """Validated, immutable application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", frozen=True)

    # External API keys
    github_token: str | None = None
    semantic_scholar_key: str | None = None
    apollo_api_key: str | None = None
    hunter_api_key: str | None = None
    prospeo_api_key: str | None = None
    instantly_api_key: str | None = None
    hubspot_api_key: str | None = None
    openai_api_key: str | None = None
    clay_api_key: str | None = None
    zerobounce_api_key: str | None = None

    # Pipeline behaviour
    scan_lookback_days: int = 7
    min_signal_strength: int = 1
    log_level: str = "INFO"


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Return a cached singleton AppConfig instance."""
    return AppConfig()


# ---------------------------------------------------------------------------
# Key validation helper
# ---------------------------------------------------------------------------

_SCANNER_REQUIREMENTS: dict[str, list[str]] = {
    "github": ["github_token"],
    "arxiv": [],  # semantic_scholar_key is optional
    "huggingface": [],
    "enrichment": [],  # custom logic: at least one of three keys
    "job_posting": [],
    "funding": [],
}


def validate_keys_for_scanner(scanner_name: str, config: AppConfig | None = None) -> None:
    """Verify that required API keys are configured for the given scanner.

    Args:
        scanner_name: One of "github", "arxiv", "huggingface", "enrichment",
                      "job_posting", "funding".
        config: AppConfig instance to validate against. Defaults to get_config().

    Raises:
        ValueError: If a required key is missing.
    """
    cfg = config if config is not None else get_config()

    if scanner_name == "github":
        if not cfg.github_token:
            raise ValueError(
                "Scanner 'github' requires github_token to be set. "
                "Add GITHUB_TOKEN to your .env file."
            )

    elif scanner_name == "enrichment":
        has_key = any([cfg.apollo_api_key, cfg.hunter_api_key, cfg.prospeo_api_key])
        if not has_key:
            raise ValueError(
                "Scanner 'enrichment' requires at least one of: "
                "apollo_api_key, hunter_api_key, prospeo_api_key. "
                "Add APOLLO_API_KEY, HUNTER_API_KEY, or PROSPEO_API_KEY to your .env file."
            )

    # "arxiv", "huggingface", "job_posting", "funding" require no mandatory keys.
