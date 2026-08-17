"""Unit tests for FirecrawlClient — all HTTP calls mocked, no real API requests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scripts.api_client import APIError
from scripts.firecrawl_client import FirecrawlClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_mock_response(status: int = 200, json_body: dict | None = None) -> MagicMock:
    """Build a mock requests.Response object."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_body or {}
    resp.headers = {}
    return resp


# ---------------------------------------------------------------------------
# Client initialization
# ---------------------------------------------------------------------------


class TestFirecrawlClientInit:
    def test_requires_api_key(self):
        with pytest.raises(ValueError, match="non-empty api_key"):
            FirecrawlClient(api_key="")

    def test_sets_auth_headers(self):
        client = FirecrawlClient(api_key="fc-test-key")
        assert client._session.headers["Authorization"] == "Bearer fc-test-key"
        assert client._session.headers["Content-Type"] == "application/json"

    def test_base_url(self):
        client = FirecrawlClient(api_key="fc-test-key")
        assert client.base_url == "https://api.firecrawl.dev/v1"


# ---------------------------------------------------------------------------
# scrape()
# ---------------------------------------------------------------------------


class TestScrape:
    @patch("scripts.api_client.requests.Session.request")
    def test_scrape_returns_markdown(self, mock_request):
        mock_request.return_value = make_mock_response(
            200,
            {
                "data": {
                    "markdown": "# Company Page\n\nWe build AI agents.",
                    "metadata": {"title": "Test"},
                }
            },
        )
        client = FirecrawlClient(api_key="fc-test-key")
        result = client.scrape("https://example.com")

        assert result["data"]["markdown"] == "# Company Page\n\nWe build AI agents."
        # Verify POST was called with correct payload
        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"
        payload = call_args[1]["json"]
        assert payload["url"] == "https://example.com"
        assert "markdown" in payload["formats"]

    @patch("scripts.api_client.requests.Session.request")
    def test_scrape_with_html_format(self, mock_request):
        mock_request.return_value = make_mock_response(
            200, {"data": {"markdown": "# Hi", "html": "<h1>Hi</h1>"}}
        )
        client = FirecrawlClient(api_key="fc-test-key")
        client.scrape("https://example.com", formats=["markdown", "html"])

        payload = mock_request.call_args[1]["json"]
        assert "html" in payload["formats"]

    @patch("scripts.api_client.requests.Session.request")
    def test_scrape_raises_on_404(self, mock_request):
        mock_request.return_value = make_mock_response(404, {"error": "Not found"})
        client = FirecrawlClient(api_key="fc-test-key")
        with pytest.raises(APIError):
            client.scrape("https://example.com/nonexistent")


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------


class TestSearch:
    @patch("scripts.api_client.requests.Session.request")
    def test_search_returns_results(self, mock_request):
        mock_request.return_value = make_mock_response(
            200,
            {
                "data": [
                    {
                        "url": "https://ai-company.com",
                        "title": "AI Co",
                        "description": "We build AI",
                    },
                    {
                        "url": "https://ml-startup.io",
                        "title": "ML Startup",
                        "description": "ML platform",
                    },
                ]
            },
        )
        client = FirecrawlClient(api_key="fc-test-key")
        result = client.search("companies building AI agents", limit=5)

        assert len(result["data"]) == 2
        assert result["data"][0]["url"] == "https://ai-company.com"
        payload = mock_request.call_args[1]["json"]
        assert payload["query"] == "companies building AI agents"
        assert payload["limit"] == 5

    @patch("scripts.api_client.requests.Session.request")
    def test_search_raises_on_error(self, mock_request):
        mock_request.return_value = make_mock_response(401, {"error": "Unauthorized"})
        client = FirecrawlClient(api_key="fc-bad-key")
        with pytest.raises(APIError):
            client.search("test query")


# ---------------------------------------------------------------------------
# extract()
# ---------------------------------------------------------------------------


class TestExtract:
    @patch("scripts.api_client.requests.Session.request")
    def test_extract_returns_structured_data(self, mock_request):
        mock_request.return_value = make_mock_response(
            200,
            {
                "data": {
                    "company_name": "TestCo",
                    "tech_stack": ["Python", "PyTorch"],
                    "team_size": "50-200",
                }
            },
        )
        client = FirecrawlClient(api_key="fc-test-key")
        result = client.extract(
            "https://example.com",
            prompt="Extract company tech stack and team size",
        )

        assert result["data"]["company_name"] == "TestCo"
        assert "PyTorch" in result["data"]["tech_stack"]
        payload = mock_request.call_args[1]["json"]
        assert payload["prompt"] == "Extract company tech stack and team size"

    @patch("scripts.api_client.requests.Session.request")
    def test_extract_with_system_prompt(self, mock_request):
        mock_request.return_value = make_mock_response(200, {"data": {}})
        client = FirecrawlClient(api_key="fc-test-key")
        client.extract("https://example.com", prompt="test", system_prompt="You are an analyst")

        payload = mock_request.call_args[1]["json"]
        assert payload["systemPrompt"] == "You are an analyst"


# ---------------------------------------------------------------------------
# map_site()
# ---------------------------------------------------------------------------


class TestMapSite:
    @patch("scripts.api_client.requests.Session.request")
    def test_map_returns_links(self, mock_request):
        mock_request.return_value = make_mock_response(
            200,
            {
                "links": [
                    "https://example.com/",
                    "https://example.com/about",
                    "https://example.com/careers",
                ]
            },
        )
        client = FirecrawlClient(api_key="fc-test-key")
        result = client.map_site("https://example.com")

        assert len(result["links"]) == 3
        payload = mock_request.call_args[1]["json"]
        assert payload["url"] == "https://example.com"
