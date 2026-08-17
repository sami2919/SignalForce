"""Firecrawl API client — website scraping, search, and structured extraction.

Extends BaseAPIClient for retry/backoff/rate-limit handling.

Three core capabilities:
1. scrape(url)     — clean markdown of any page (homepage, /about, /careers, G2 reviews)
2. search(query)   — discover companies matching natural-language patterns
3. extract(url)    — structured data extraction via natural-language prompt

API docs: https://docs.firecrawl.dev
"""

from __future__ import annotations

import logging

from scripts.api_client import BaseAPIClient

logger = logging.getLogger(__name__)


class FirecrawlClient(BaseAPIClient):
    """Firecrawl REST API client.

    All endpoints accept JSON POST bodies with the API key in the Authorization header.
    """

    BASE_URL = "https://api.firecrawl.dev/v1"

    def __init__(self, api_key: str, timeout: int = 60) -> None:
        if not api_key:
            raise ValueError("FirecrawlClient requires a non-empty api_key")
        auth_headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        super().__init__(base_url=self.BASE_URL, auth_headers=auth_headers, timeout=timeout)

    # ------------------------------------------------------------------
    # scrape — clean markdown of any URL
    # ------------------------------------------------------------------

    def scrape(
        self,
        url: str,
        formats: list[str] | None = None,
        only_main_content: bool = True,
        max_age: int = 14,
    ) -> dict:
        """Scrape a single URL and return clean markdown + metadata.

        Args:
            url:             The URL to scrape.
            formats:         Output formats — ["markdown"] (default), ["html"], or both.
            only_main_content: Strip nav/footer/ads, return main content only.
            max_age:         Return cached result if younger than this many days (0 = force fresh).

        Returns:
            Firecrawl scrape response dict with keys:
                - "markdown":  clean markdown of the page
                - "html":      raw HTML (if requested)
                - "metadata":  page metadata (title, description, og tags, etc.)
                - "links":     links found on the page (if requested)

        Raises:
            APIError: on non-retryable failures.
            RateLimitError: if rate limits exhausted.
        """
        if formats is None:
            formats = ["markdown"]

        payload = {
            "url": url,
            "formats": formats,
            "onlyMainContent": only_main_content,
            "maxAge": max_age,
        }
        return self.post("/scrape", json_data=payload)

    # ------------------------------------------------------------------
    # search — discover pages/companies matching a query
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 10,
        scrape_options: dict | None = None,
    ) -> dict:
        """Search the web and return matching pages with optional scraped content.

        Args:
            query:         Natural-language or search-operator query
                           (e.g. "companies building AI agents", "site:github.com RLHF").
            limit:         Max number of results (1–100).
            scrape_options: Optional dict of scrape options applied to each result
                           (e.g. {"formats": ["markdown"]}).

        Returns:
            Firecrawl search response dict with "data" key containing a list of
            result objects, each with url, title, description, and optionally markdown.

        Raises:
            APIError: on non-retryable failures.
        """
        if scrape_options is None:
            scrape_options = {"formats": ["markdown"]}

        payload = {
            "query": query,
            "limit": limit,
            "scrapeOptions": scrape_options,
        }
        return self.post("/search", json_data=payload)

    # ------------------------------------------------------------------
    # extract — structured data extraction from a URL via natural-language prompt
    # ------------------------------------------------------------------

    def extract(
        self,
        url: str,
        prompt: str,
        system_prompt: str | None = None,
    ) -> dict:
        """Extract structured data from a URL using a natural-language prompt.

        Uses Firecrawl's LLM extraction endpoint. The prompt describes what to
        extract and Firecrawl returns a structured JSON object.

        Args:
            url:           The URL to extract data from.
            prompt:        Natural-language description of what to extract
                           (e.g. "Extract the company's tech stack, team size,
                            funding stage, and product category").
            system_prompt: Optional system prompt for additional context.

        Returns:
            Firecrawl extract response dict with "data" key containing the
            LLM-extracted structured object.

        Raises:
            APIError: on non-retryable failures.
        """
        payload: dict = {
            "url": url,
            "prompt": prompt,
            "enableWebSearch": True,
        }
        if system_prompt:
            payload["systemPrompt"] = system_prompt

        return self.post("/scrape", json_data={**payload, "formats": ["extract"]})

    # ------------------------------------------------------------------
    # map — discover all crawlable URLs on a domain
    # ------------------------------------------------------------------

    def map_site(self, url: str, limit: int = 50) -> dict:
        """Map all URLs on a site for systematic crawling.

        Args:
            url:   Root URL of the site to map.
            limit: Max number of URLs to return.

        Returns:
            Firecrawl map response with "links" key containing URL list.

        Raises:
            APIError: on non-retryable failures.
        """
        payload = {"url": url, "limit": limit}
        return self.post("/map", json_data=payload)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json
    import sys

    from scripts.config import get_config

    parser = argparse.ArgumentParser(
        description="Firecrawl API client — scrape, search, extract.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scrape_p = sub.add_parser("scrape", help="Scrape a URL into clean markdown")
    scrape_p.add_argument("url", help="URL to scrape")
    scrape_p.add_argument("--html", action="store_true", help="Also return HTML")

    search_p = sub.add_parser("search", help="Search the web via Firecrawl")
    search_p.add_argument("query", help="Search query")
    search_p.add_argument("--limit", type=int, default=10)

    extract_p = sub.add_parser("extract", help="Extract structured data from a URL")
    extract_p.add_argument("url", help="URL to extract from")
    extract_p.add_argument("prompt", help="What to extract (natural language)")

    map_p = sub.add_parser("map", help="Map all URLs on a site")
    map_p.add_argument("url", help="Root URL")
    map_p.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()
    cfg = get_config()
    if not cfg.firecrawl_api_key:
        print("FIRECRAWL_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    client = FirecrawlClient(api_key=cfg.firecrawl_api_key)

    if args.command == "scrape":
        formats = ["markdown", "html"] if args.html else ["markdown"]
        result = client.scrape(args.url, formats=formats)
    elif args.command == "search":
        result = client.search(args.query, limit=args.limit)
    elif args.command == "extract":
        result = client.extract(args.url, args.prompt)
    elif args.command == "map":
        result = client.map_site(args.url, limit=args.limit)

    print(json.dumps(result, indent=2, default=str))
