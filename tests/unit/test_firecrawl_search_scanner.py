"""Unit tests for firecrawl_search_scanner — all HTTP mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from scripts.config_loader import ScannerConfig
from scripts.models import SignalStrength
from scripts.scanners.firecrawl_search_scanner import (
    _extract_domain,
    _score_result,
    _result_to_signal,
    scan,
)


def make_scanner_config(
    queries: list[str] | None = None,
    keywords: list[str] | None = None,
    topics: list[str] | None = None,
    custom_params: dict | None = None,
) -> ScannerConfig:
    return ScannerConfig(
        module="scripts.scanners.firecrawl_search_scanner",
        queries=queries or [],
        keywords=keywords or [],
        topics=topics or ["reinforcement learning", "rlhf"],
        custom_params=custom_params or {},
    )


class TestExtractDomain:
    def test_simple(self):
        assert _extract_domain("https://example.com/page") == "example.com"

    def test_with_subdomain(self):
        assert _extract_domain("https://app.example.com") == "app.example.com"


class TestScoreResult:
    def test_strong(self):
        markdown = "We use reinforcement learning and RLHF for agent training with PyTorch"
        assert _score_result(markdown, ["rlhf"]) == SignalStrength.STRONG

    def test_moderate(self):
        markdown = "We do AI and machine learning"
        assert _score_result(markdown, []) == SignalStrength.MODERATE

    def test_weak(self):
        markdown = "Welcome to our bakery"
        assert _score_result(markdown, []) == SignalStrength.WEAK


class TestResultToSignal:
    def test_builds_signal(self):
        result = {
            "url": "https://ai-company.com",
            "title": "AI Company",
            "description": "We build RLHF training platforms",
            "markdown": "# AI Company\n\nWe build RLHF training platforms",
        }
        signal = _result_to_signal(result, "RLHF companies", ["rlhf"])
        assert signal is not None
        assert signal.signal_type == "firecrawl_search"
        assert signal.company_domain == "ai-company.com"
        assert signal.signal_strength == SignalStrength.STRONG

    def test_no_url_returns_none(self):
        result = {"title": "No URL", "description": "test"}
        signal = _result_to_signal(result, "test", [])
        assert signal is None


class TestScan:
    @patch("scripts.scanners.firecrawl_search_scanner.get_config")
    @patch("scripts.scanners.firecrawl_search_scanner.FirecrawlClient")
    def test_scan_with_queries(self, MockClient, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        mock_client = MockClient.return_value
        mock_client.search.return_value = {
            "data": [
                {
                    "url": "https://ai-co.com",
                    "title": "AI Co",
                    "description": "RLHF platform",
                    "markdown": "We build RLHF",
                },
                {
                    "url": "https://ml-io.io",
                    "title": "ML IO",
                    "description": "ML infra",
                    "markdown": "Machine learning at scale",
                },
            ]
        }

        config = make_scanner_config(queries=["companies building RLHF"])
        result = scan(config)

        assert result.scan_type == "firecrawl_search"
        assert len(result.signals_found) == 2
        assert result.total_raw_results == 2

    @patch("scripts.scanners.firecrawl_search_scanner.get_config")
    def test_scan_no_api_key(self, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = None
        mock_get_config.return_value = mock_config

        config = make_scanner_config(queries=["test"])
        result = scan(config)

        assert len(result.signals_found) == 0
        assert any("FIRECRAWL_API_KEY" in e for e in result.errors)

    @patch("scripts.scanners.firecrawl_search_scanner.get_config")
    @patch("scripts.scanners.firecrawl_search_scanner.FirecrawlClient")
    def test_scan_deduplicates(self, MockClient, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        mock_client = MockClient.return_value
        mock_client.search.return_value = {
            "data": [
                {"url": "https://same-company.com", "title": "Same", "description": "AI"},
                {
                    "url": "https://same-company.com/about",
                    "title": "Same About",
                    "description": "AI",
                },
            ]
        }

        config = make_scanner_config(queries=["query1", "query2"])
        result = scan(config)

        assert len(result.signals_found) == 1  # deduped by domain

    @patch("scripts.scanners.firecrawl_search_scanner.get_config")
    @patch("scripts.scanners.firecrawl_search_scanner.FirecrawlClient")
    def test_scan_handles_search_error(self, MockClient, mock_get_config):
        mock_config = MagicMock()
        mock_config.firecrawl_api_key = "fc-test-key"
        mock_get_config.return_value = mock_config

        mock_client = MockClient.return_value
        mock_client.search.side_effect = Exception("API down")

        config = make_scanner_config(queries=["test query"])
        result = scan(config)

        assert len(result.signals_found) == 0
        assert len(result.errors) > 0
