"""Unit tests for job scanner AppConfig integration.

Tests that JobPostingScanner reads SERPAPI_KEY from AppConfig instead of
directly from os.environ.

All HTTP calls are mocked — no real network requests.
"""

from unittest.mock import patch
from scripts.config import AppConfig
from scripts.scanners.job_scanner import JobPostingScanner


def test_job_scanner_reads_serpapi_from_app_config():
    """JobPostingScanner must use get_config().serpapi_key, not os.environ directly."""
    fake_config = AppConfig(serpapi_key="demo-key-xyz")
    with patch("scripts.config.get_config", return_value=fake_config):
        scanner = JobPostingScanner(titles=["marketing operations manager"])
        assert scanner._client._api_key == "demo-key-xyz"


def test_job_scanner_explicit_api_key_overrides_config():
    """Explicit api_key parameter should take priority over AppConfig."""
    fake_config = AppConfig(serpapi_key="config-key")
    with patch("scripts.config.get_config", return_value=fake_config):
        scanner = JobPostingScanner(titles=[], api_key="explicit-key")
        assert scanner._client._api_key == "explicit-key"


def test_job_scanner_no_key_returns_empty_results():
    """Without API key, scanner should return empty signals (not crash)."""
    fake_config = AppConfig(serpapi_key=None)
    with patch("scripts.config.get_config", return_value=fake_config):
        scanner = JobPostingScanner(titles=["marketing ops"])
        result = scanner.scan(lookback_days=1)
        assert result.signals_found == []
