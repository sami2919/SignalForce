"""Unit tests for configuration management.

Tests are written first (TDD RED phase) before implementation.
"""

import pytest
from unittest.mock import patch
from pydantic import ValidationError

from scripts.config import AppConfig, get_config, validate_keys_for_scanner


# ---------------------------------------------------------------------------
# AppConfig tests
# ---------------------------------------------------------------------------


def test_config_loads_defaults():
    """With no env vars, all keys are None and numeric defaults are correct."""
    with patch.dict("os.environ", {}, clear=True):
        config = AppConfig()
        assert config.github_token is None
        assert config.semantic_scholar_key is None
        assert config.apollo_api_key is None
        assert config.hunter_api_key is None
        assert config.prospeo_api_key is None
        assert config.instantly_api_key is None
        assert config.hubspot_api_key is None
        assert config.openai_api_key is None
        assert config.clay_api_key is None
        assert config.zerobounce_api_key is None
        assert config.scan_lookback_days == 7
        assert config.min_signal_strength == 1
        assert config.log_level == "INFO"


def test_config_loads_from_env():
    """Env vars are picked up and populate config fields correctly."""
    env_vars = {
        "GITHUB_TOKEN": "gh-token-123",
        "SEMANTIC_SCHOLAR_KEY": "ss-key-456",
        "APOLLO_API_KEY": "apollo-key",
        "HUNTER_API_KEY": "hunter-key",
        "PROSPEO_API_KEY": "prospeo-key",
        "INSTANTLY_API_KEY": "instantly-key",
        "HUBSPOT_API_KEY": "hubspot-key",
        "OPENAI_API_KEY": "openai-key",
        "CLAY_API_KEY": "clay-key",
        "ZEROBOUNCE_API_KEY": "zb-key",
        "SCAN_LOOKBACK_DAYS": "14",
        "MIN_SIGNAL_STRENGTH": "2",
        "LOG_LEVEL": "DEBUG",
    }
    with patch.dict("os.environ", env_vars, clear=True):
        config = AppConfig()
        assert config.github_token == "gh-token-123"
        assert config.semantic_scholar_key == "ss-key-456"
        assert config.apollo_api_key == "apollo-key"
        assert config.hunter_api_key == "hunter-key"
        assert config.prospeo_api_key == "prospeo-key"
        assert config.instantly_api_key == "instantly-key"
        assert config.hubspot_api_key == "hubspot-key"
        assert config.openai_api_key == "openai-key"
        assert config.clay_api_key == "clay-key"
        assert config.zerobounce_api_key == "zb-key"
        assert config.scan_lookback_days == 14
        assert config.min_signal_strength == 2
        assert config.log_level == "DEBUG"


def test_config_is_frozen():
    """AppConfig is immutable — attempting to mutate raises an error."""
    with patch.dict("os.environ", {}, clear=True):
        config = AppConfig()
        with pytest.raises((ValidationError, TypeError)):
            config.github_token = "should-fail"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# validate_keys_for_scanner tests
# ---------------------------------------------------------------------------


def test_validate_github_scanner_missing_key():
    """validate_keys_for_scanner('github') raises ValueError when token is absent."""
    with patch.dict("os.environ", {}, clear=True):
        config = AppConfig()
        with pytest.raises(ValueError, match="github_token"):
            validate_keys_for_scanner("github", config)


def test_validate_github_scanner_has_key():
    """validate_keys_for_scanner('github') succeeds when token is present."""
    with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_abc"}, clear=True):
        config = AppConfig()
        validate_keys_for_scanner("github", config)  # must not raise


def test_validate_huggingface_no_key_needed():
    """huggingface scanner requires no API key — passes with empty config."""
    with patch.dict("os.environ", {}, clear=True):
        config = AppConfig()
        validate_keys_for_scanner("huggingface", config)  # must not raise


def test_validate_arxiv_no_key_needed():
    """arxiv scanner works without a key (semantic_scholar_key is optional)."""
    with patch.dict("os.environ", {}, clear=True):
        config = AppConfig()
        validate_keys_for_scanner("arxiv", config)  # must not raise


def test_validate_enrichment_needs_at_least_one():
    """enrichment scanner raises ValueError when none of the three keys are set."""
    with patch.dict("os.environ", {}, clear=True):
        config = AppConfig()
        with pytest.raises(ValueError, match="apollo|hunter|prospeo"):
            validate_keys_for_scanner("enrichment", config)


def test_validate_enrichment_has_apollo():
    """enrichment scanner passes when apollo_api_key is configured."""
    with patch.dict("os.environ", {"APOLLO_API_KEY": "ap-key"}, clear=True):
        config = AppConfig()
        validate_keys_for_scanner("enrichment", config)  # must not raise


def test_validate_job_posting_no_key_needed():
    """job_posting scanner requires no API key."""
    with patch.dict("os.environ", {}, clear=True):
        config = AppConfig()
        validate_keys_for_scanner("job_posting", config)  # must not raise


def test_validate_funding_no_key_needed():
    """funding scanner requires no API key."""
    with patch.dict("os.environ", {}, clear=True):
        config = AppConfig()
        validate_keys_for_scanner("funding", config)  # must not raise


# ---------------------------------------------------------------------------
# get_config singleton tests
# ---------------------------------------------------------------------------


def test_get_config_returns_same_instance():
    """get_config() returns the same cached AppConfig object on repeated calls."""
    instance_a = get_config()
    instance_b = get_config()
    assert instance_a is instance_b
