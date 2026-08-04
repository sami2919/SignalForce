"""Unit tests for MAP Frustration Scanner (formerly G2 Review Scanner).

Detects companies expressing MAP frustration on LinkedIn and blogs.
All HTTP calls are mocked — no real network requests.
"""

from unittest.mock import MagicMock, patch
from scripts.scanners.g2_scanner import MAPFrustrationScanner, G2ReviewScanner, scan
from scripts.config_loader import ScannerConfig
from scripts.models import SignalStrength


SAMPLE_LINKEDIN_RESULT = {
    "title": "PDL Replaces Marketo with Conversion",
    "url": "https://www.linkedin.com/posts/neiltewari_in-under-4-weeks-people-data-labs-replaced-activ",
    "snippet": "I'm the marketing operations manager at PDL. Yeah. So here at PDL we just finished "
    "replacing Marketo with a unified AI-powered Conversion stack. It took 4 weeks.",
}

SAMPLE_HUBSPOT_RESULT = {
    "title": "Why We Left HubSpot Enterprise",
    "url": "https://www.linkedin.com/posts/jsmith_why-we-left-hubspot-activity-12345",
    "snippet": "HubSpot Enterprise was too expensive and the ceiling on custom SQL audiences "
    "was something we hit at Beta Inc every single week.",
}

NON_EXTRACTABLE_RESULT = {
    "title": "Generic Blog Post About Marketing",
    "url": "https://www.capterra.com/marketing-software/",
    "snippet": "Compare marketing automation tools.",
}


def test_g2_scanner_creates_signals_from_results():
    """MAP frustration scanner should convert results with company names into signals."""
    scanner = MAPFrustrationScanner(api_key="fake-key")
    with patch.object(scanner._client, "search_jobs", return_value=[SAMPLE_LINKEDIN_RESULT]):
        result = scanner.scan(lookback_days=7)
    assert len(result.signals_found) > 0
    assert all(s.signal_type == "map_frustration" for s in result.signals_found)


def test_g2_scanner_filters_non_extractable_results():
    """Scanner must skip results where no company name can be extracted."""
    scanner = MAPFrustrationScanner(api_key="fake-key")
    with patch.object(scanner._client, "search_jobs", return_value=[NON_EXTRACTABLE_RESULT]):
        result = scanner.scan(lookback_days=7)
    assert len(result.signals_found) == 0


def test_g2_scanner_marks_migration_language_as_strong():
    """Result containing 'replacing' should produce STRONG signal."""
    scanner = MAPFrustrationScanner(api_key="fake-key")
    with patch.object(scanner._client, "search_jobs", return_value=[SAMPLE_LINKEDIN_RESULT]):
        result = scanner.scan(lookback_days=7)
    assert any(s.signal_strength == SignalStrength.STRONG for s in result.signals_found)


def test_g2_scanner_no_api_key_returns_empty_with_no_crash():
    """Without API key, scanner should return 0 signals without crashing."""
    from scripts.config import AppConfig

    fake_config = AppConfig(_env_file=None, serpapi_key=None)
    with patch("scripts.config.get_config", return_value=fake_config):
        scanner = MAPFrustrationScanner(api_key=None)
        result = scanner.scan(lookback_days=7)
    assert result.scan_type == "map_frustration"
    assert len(result.signals_found) == 0


def test_scan_module_function_uses_config():
    """Module-level scan() should accept ScannerConfig and return correct scan_type."""
    cfg = ScannerConfig(
        enabled=True,
        module="scripts.scanners.g2_scanner",
        keywords=["Marketo", "HubSpot"],
        lookback_days=7,
    )
    mock_result = MagicMock(scan_type="map_frustration")
    with patch("scripts.scanners.g2_scanner.MAPFrustrationScanner.scan", return_value=mock_result):
        result = scan(cfg)
    assert result.scan_type == "map_frustration"


def test_g2_review_scanner_alias():
    """G2ReviewScanner should be an alias for MAPFrustrationScanner."""
    assert G2ReviewScanner is MAPFrustrationScanner
