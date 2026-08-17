"""Unit tests for g2_firecrawl_scanner — all HTTP mocked, no real API calls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from scripts.config_loader import ScannerConfig
from scripts.models import SignalStrength
from scripts.scanners.g2_firecrawl_scanner import (
    G2FirecrawlScanner,
    _AT_COMPANY_RE,
    _STRONG_KEYWORDS,
    _MODERATE_KEYWORDS,
    scan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_scanner_config(custom_params: dict | None = None) -> ScannerConfig:
    return ScannerConfig(
        module="scripts.scanners.g2_firecrawl_scanner",
        lookback_days=30,
        custom_params=custom_params or {"use_extraction": True},
    )


def make_extract_response(reviews: list[dict]) -> dict:
    return {"data": {"reviews": reviews}}


def make_scrape_response(markdown: str) -> dict:
    return {"data": {"markdown": markdown}}


# ---------------------------------------------------------------------------
# Regex / keyword tests
# ---------------------------------------------------------------------------


class TestRegexAndKeywords:
    def test_at_company_regex_matches(self):
        text = "VP Marketing at Acme Corp | 2 years"
        m = _AT_COMPANY_RE.search(text)
        assert m is not None
        assert "Acme" in m.group(1)

    def test_at_company_regex_no_match(self):
        text = "Just a regular sentence without company"
        assert _AT_COMPANY_RE.search(text) is None

    def test_strong_keywords_present(self):
        assert "migration" in _STRONG_KEYWORDS
        assert "replacing" in _STRONG_KEYWORDS
        assert "switching" in _STRONG_KEYWORDS

    def test_moderate_keywords_present(self):
        assert "expensive" in _MODERATE_KEYWORDS
        assert "complex" in _MODERATE_KEYWORDS


# ---------------------------------------------------------------------------
# Scanner init tests
# ---------------------------------------------------------------------------


class TestScannerInit:
    @patch("scripts.scanners.g2_firecrawl_scanner.get_config")
    def test_init_with_api_key(self, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        scanner = G2FirecrawlScanner()
        assert scanner._api_key == "fc-test-key"

    @patch("scripts.scanners.g2_firecrawl_scanner.get_config")
    def test_init_no_api_key(self, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = None
        mock_get_config.return_value = mock_config

        scanner = G2FirecrawlScanner()
        assert scanner._api_key is None


# ---------------------------------------------------------------------------
# Extraction-based scanning
# ---------------------------------------------------------------------------


class TestExtractionScanning:
    @patch("scripts.scanners.g2_firecrawl_scanner.get_config")
    @patch("scripts.scanners.g2_firecrawl_scanner.FirecrawlClient")
    def test_scan_with_extraction(self, MockClient, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        mock_client = MockClient.return_value
        mock_client.extract.return_value = make_extract_response(
            [
                {
                    "reviewer_company": "Acme Corp",
                    "star_rating": 2,
                    "review_snippet": "We're migrating away from Marketo, it's too expensive",
                    "frustration_keywords": ["migrating", "expensive"],
                    "vendor_name": "Marketo",
                },
                {
                    "reviewer_company": "TechStart Inc",
                    "star_rating": 1,
                    "review_snippet": "Switching to a Marketo alternative — too complex",
                    "frustration_keywords": ["switching", "alternative", "complex"],
                    "vendor_name": "Marketo",
                },
            ]
        )

        scanner = G2FirecrawlScanner()
        result = scanner.scan(use_extraction=True)

        assert result.scan_type == "g2_review"
        assert len(result.signals_found) == 2
        assert result.signals_found[0].company_name == "Acme Corp"
        assert result.signals_found[0].signal_strength == SignalStrength.STRONG
        assert result.signals_found[0].metadata["star_rating"] == 2
        assert result.signals_found[0].metadata["product_mentioned"] == "Marketo"

    @patch("scripts.scanners.g2_firecrawl_scanner.get_config")
    @patch("scripts.scanners.g2_firecrawl_scanner.FirecrawlClient")
    def test_extraction_filters_non_companies(self, MockClient, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        mock_client = MockClient.return_value
        mock_client.extract.return_value = make_extract_response(
            [
                {"reviewer_company": "Acme Corp", "star_rating": 2, "review_snippet": "bad"},
                {"reviewer_company": "g2", "star_rating": 1, "review_snippet": "bad"},
                {"reviewer_company": "", "star_rating": 3, "review_snippet": "ok"},
            ]
        )

        scanner = G2FirecrawlScanner()
        result = scanner.scan(use_extraction=True)

        assert len(result.signals_found) == 1
        assert result.signals_found[0].company_name == "Acme Corp"

    @patch("scripts.scanners.g2_firecrawl_scanner.get_config")
    def test_no_api_key_returns_empty(self, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = None
        mock_get_config.return_value = mock_config

        scanner = G2FirecrawlScanner()
        result = scanner.scan()

        assert len(result.signals_found) == 0
        assert any("FIRECRAWL_API_KEY" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Markdown fallback scanning
# ---------------------------------------------------------------------------


class TestMarkdownScanning:
    @patch("scripts.scanners.g2_firecrawl_scanner.get_config")
    @patch("scripts.scanners.g2_firecrawl_scanner.FirecrawlClient")
    def test_markdown_fallback(self, MockClient, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        mock_client = MockClient.return_value
        markdown = """
        VP Marketing at Acme Corp
        2.0 star rating
        "We're migrating away from Marketo, it's too expensive and complex"
        """
        mock_client.scrape.return_value = make_scrape_response(markdown)

        scanner = G2FirecrawlScanner()
        result = scanner.scan(use_extraction=False)

        assert result.scan_type == "g2_review"
        # Should find at least one signal from "at Acme Corp"
        assert len(result.signals_found) >= 1
        assert result.signals_found[0].company_name == "Acme Corp"


# ---------------------------------------------------------------------------
# Scoring tests
# ---------------------------------------------------------------------------


class TestScoring:
    @patch("scripts.scanners.g2_firecrawl_scanner.get_config")
    def test_strong_migration_keyword(self, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        scanner = G2FirecrawlScanner()
        assert scanner._score("we are migrating from marketo", 3.0) == SignalStrength.STRONG

    @patch("scripts.scanners.g2_firecrawl_scanner.get_config")
    def test_strong_low_rating_with_frustration(self, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        scanner = G2FirecrawlScanner()
        assert scanner._score("it's too complex and slow", 1.0) == SignalStrength.STRONG

    @patch("scripts.scanners.g2_firecrawl_scanner.get_config")
    def test_moderate_frustration_only(self, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        scanner = G2FirecrawlScanner()
        assert scanner._score("it's expensive and complex", 4.0) == SignalStrength.MODERATE

    @patch("scripts.scanners.g2_firecrawl_scanner.get_config")
    def test_weak_no_keywords(self, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        scanner = G2FirecrawlScanner()
        assert scanner._score("it's a good product", 4.0) == SignalStrength.WEAK


# ---------------------------------------------------------------------------
# scan() entry point
# ---------------------------------------------------------------------------


class TestScanEntryPoint:
    @patch("scripts.scanners.g2_firecrawl_scanner.get_config")
    @patch("scripts.scanners.g2_firecrawl_scanner.FirecrawlClient")
    def test_scan_function(self, MockClient, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        mock_client = MockClient.return_value
        mock_client.extract.return_value = make_extract_response(
            [
                {
                    "reviewer_company": "TestCo",
                    "star_rating": 2,
                    "review_snippet": "migrating from Marketo",
                },
            ]
        )

        config = make_scanner_config()
        result = scan(config)

        assert result.scan_type == "g2_review"
        assert len(result.signals_found) == 1
        assert result.signals_found[0].company_name == "TestCo"
        assert result.signals_found[0].signal_strength == SignalStrength.STRONG
