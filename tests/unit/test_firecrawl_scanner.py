"""Unit tests for firecrawl_scanner (website enrichment) — all HTTP mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from scripts.config_loader import ScannerConfig
from scripts.models import SignalStrength
from scripts.scanners.firecrawl_scanner import (
    _normalize_domain,
    _extract_domain,
    _score_content,
    _extract_tech_stack,
    _extract_hiring_language,
    _extract_product_description,
    _scrape_company,
    scan,
)


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


def make_scanner_config(
    keywords: list[str] | None = None,
    topics: list[str] | None = None,
    custom_params: dict | None = None,
) -> ScannerConfig:
    return ScannerConfig(
        module="scripts.scanners.firecrawl_scanner",
        keywords=keywords or [],
        topics=topics or ["reinforcement learning", "rlhf", "agent"],
        custom_params=custom_params or {},
    )


def make_scrape_response(markdown: str) -> dict:
    return {"data": {"markdown": markdown, "metadata": {"title": "Test"}}}


# ---------------------------------------------------------------------------
# Utility function tests
# ---------------------------------------------------------------------------


class TestNormalizeDomain:
    def test_adds_https(self):
        assert _normalize_domain("example.com") == "https://example.com"

    def test_preserves_https(self):
        assert _normalize_domain("https://example.com") == "https://example.com"

    def test_preserves_http(self):
        assert _normalize_domain("http://example.com") == "http://example.com"

    def test_strips_whitespace(self):
        assert _normalize_domain("  example.com  ") == "https://example.com"

    def test_lowercases(self):
        assert _normalize_domain("Example.COM") == "https://example.com"


class TestExtractDomain:
    def test_simple_domain(self):
        assert _extract_domain("https://example.com/about") == "example.com"

    def test_http(self):
        assert _extract_domain("http://example.com") == "example.com"

    def test_with_port(self):
        assert _extract_domain("https://example.com:8080/path") == "example.com"


class TestScoreContent:
    def test_strong_with_multiple_matches(self):
        markdown = "We use reinforcement learning and RLHF for training agents with PyTorch"
        result = _score_content(markdown, ["rlhf"])
        assert result == SignalStrength.STRONG

    def test_moderate_with_one_match(self):
        markdown = "We work with AI and machine learning"
        result = _score_content(markdown, [])
        assert result == SignalStrength.MODERATE

    def test_weak_no_matches(self):
        markdown = "Welcome to our bakery. We make great bread."
        result = _score_content(markdown, [])
        assert result == SignalStrength.WEAK

    def test_config_keywords_contribute(self):
        markdown = "We specialize in reward modeling and fine-tuning"
        result = _score_content(markdown, ["reward modeling", "fine-tuning"])
        assert result == SignalStrength.STRONG


class TestExtractTechStack:
    def test_finds_common_tech(self):
        md = "Our stack includes Python, PyTorch, Kubernetes, and AWS"
        stack = _extract_tech_stack(md)
        assert "PyTorch" in stack
        assert "Python" in stack
        assert "Kubernetes" in stack
        assert "AWS" in stack

    def test_empty_content(self):
        assert _extract_tech_stack("nothing here") == []

    def test_dedup_not_needed(self):
        md = "We use PyTorch and PyTorch everywhere"
        stack = _extract_tech_stack(md)
        # "pytorch" appears once in the list
        assert stack.count("PyTorch") == 1


class TestExtractHiringLanguage:
    def test_finds_hiring_indicators(self):
        md = "We're hiring! Senior ML Engineer. Join our team."
        result = _extract_hiring_language(md)
        assert "we're hiring" in result
        assert any("engineer" in r.lower() for r in result)

    def test_no_hiring_content(self):
        md = "Our product is great. No jobs here."
        result = _extract_hiring_language(md)
        assert result == []


class TestExtractProductDescription:
    def test_finds_first_paragraph(self):
        md = "# Home\n\nWe build AI infrastructure for training large language models at scale."
        desc = _extract_product_description(md)
        assert "AI infrastructure" in desc

    def test_skips_headers(self):
        md = "# Welcome\n## About Us\nWe are a great company building innovative AI products at scale."
        desc = _extract_product_description(md)
        assert "innovative AI products" in desc

    def test_empty_markdown(self):
        assert _extract_product_description("") == ""


# ---------------------------------------------------------------------------
# _scrape_company tests
# ---------------------------------------------------------------------------


class TestScrapeCompany:
    @patch("scripts.scanners.firecrawl_scanner.FirecrawlClient")
    def test_successful_scrape(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.scrape.side_effect = [
            make_scrape_response("# OpenAI\n\nWe build AI and reinforcement learning systems."),
            make_scrape_response("# About\n\nWe do RLHF research."),
            make_scrape_response("# Careers\n\nWe're hiring ML Engineers."),
            # Remaining key pages return empty/fail
        ]
        # Pad side_effect for remaining key pages
        mock_client.scrape.side_effect = [
            make_scrape_response("# OpenAI\n\nWe build AI and reinforcement learning systems."),
            make_scrape_response("# About\n\nWe do RLHF research."),
            make_scrape_response("# Careers\n\nWe're hiring ML Engineers."),
        ] + [Exception("404")] * 3  # /product, /team, /pricing fail

        signal = _scrape_company(mock_client, "openai.com", ["rlhf", "agent"])

        assert signal is not None
        assert signal.signal_type == "website_enrichment"
        assert signal.company_domain == "openai.com"
        assert signal.signal_strength == SignalStrength.STRONG
        assert "rlhf" in signal.raw_data["markdown"].lower()

    @patch("scripts.scanners.firecrawl_scanner.FirecrawlClient")
    def test_homepage_failure_returns_none(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.scrape.side_effect = Exception("Connection refused")

        signal = _scrape_company(mock_client, "example.com", [])
        assert signal is None


# ---------------------------------------------------------------------------
# scan() integration tests
# ---------------------------------------------------------------------------


class TestScan:
    @patch("scripts.scanners.firecrawl_scanner.get_config")
    @patch("scripts.scanners.firecrawl_scanner.FirecrawlClient")
    def test_scan_with_domains(self, MockClient, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        mock_client = MockClient.return_value
        mock_client.scrape.side_effect = [
            make_scrape_response("# AI Co\n\nWe build RLHF training platforms with PyTorch."),
            Exception("404"),
            Exception("404"),
            Exception("404"),
            Exception("404"),
            Exception("404"),
            make_scrape_response("# ML Startup\n\nWe do machine learning and fine-tuning."),
            Exception("404"),
            Exception("404"),
            Exception("404"),
            Exception("404"),
            Exception("404"),
        ]

        config = make_scanner_config(
            keywords=["ai-co.com", "ml-startup.io"],
            topics=["rlhf", "machine learning"],
        )
        result = scan(config)

        assert result.scan_type == "website_enrichment"
        assert len(result.signals_found) == 2
        assert result.total_raw_results == 2

    @patch("scripts.scanners.firecrawl_scanner.get_config")
    def test_scan_no_api_key(self, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = None
        mock_get_config.return_value = mock_config

        config = make_scanner_config(keywords=["example.com"])
        result = scan(config)

        assert len(result.signals_found) == 0
        assert any("FIRECRAWL_API_KEY" in e for e in result.errors)

    @patch("scripts.scanners.firecrawl_scanner.get_config")
    @patch("scripts.scanners.firecrawl_scanner.FirecrawlClient")
    def test_scan_no_domains(self, MockClient, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        config = make_scanner_config(keywords=[], topics=["rlhf"])
        result = scan(config)

        assert len(result.signals_found) == 0
        assert result.total_raw_results == 0

    @patch("scripts.scanners.firecrawl_scanner.get_config")
    @patch("scripts.scanners.firecrawl_scanner.FirecrawlClient")
    def test_scan_deduplicates_domains(self, MockClient, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        mock_client = MockClient.return_value
        mock_client.scrape.side_effect = [
            make_scrape_response("# AI Co\n\nWe build AI agents."),
            Exception("404"),
            Exception("404"),
            Exception("404"),
            Exception("404"),
            Exception("404"),
        ]

        config = make_scanner_config(
            keywords=["ai-co.com", "https://ai-co.com", "AI-CO.COM"],
            topics=["agent"],
        )
        result = scan(config)

        assert len(result.signals_found) == 1
        assert result.total_raw_results == 1
