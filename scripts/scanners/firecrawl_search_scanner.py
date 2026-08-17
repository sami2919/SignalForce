"""Firecrawl Search Scanner — company discovery via web search.

Uses Firecrawl's /search endpoint to discover companies matching ICP patterns.
Unlike other scanners that monitor specific platforms (GitHub, ArXiv, HF),
this scanner searches the entire web for companies matching natural-language
or search-operator queries, then scrapes the results for enrichment.

Signal type: "firecrawl_search"
Strength:
  - STRONG:   Company found with ICP keywords in scraped page content
  - MODERATE: Company found with partial ICP match
  - WEAK:     Company found but no ICP keyword match in content
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone

from scripts.config import get_config
from scripts.firecrawl_client import FirecrawlClient
from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)


# Generic ICP indicators for scoring scraped search results
_ICP_INDICATOR_KEYWORDS: set[str] = {
    "reinforcement learning",
    "rlhf",
    "grpo",
    "reward model",
    "policy gradient",
    "sim-to-real",
    "agent",
    "llm",
    "ai",
    "machine learning",
    "ml",
    "training",
    "fine-tuning",
    "inference",
    "gpu",
    "cuda",
    "pytorch",
    "tensorflow",
    "jax",
}


def _extract_domain(url: str) -> str:
    """Extract bare domain from a URL."""
    clean = url.replace("https://", "").replace("http://", "")
    return clean.split("/")[0].split(":")[0]


def _score_result(markdown: str, config_keywords: list[str]) -> SignalStrength:
    """Score a search result based on ICP keyword presence in scraped content."""
    lower = markdown.lower()
    config_matches = [kw for kw in config_keywords if kw.lower() in lower]
    icp_matches = [kw for kw in _ICP_INDICATOR_KEYWORDS if kw in lower]
    total = len(config_matches) + len(icp_matches)

    if total >= 3:
        return SignalStrength.STRONG
    if total >= 1:
        return SignalStrength.MODERATE
    return SignalStrength.WEAK


def _result_to_signal(
    result: dict,
    query: str,
    config_keywords: list[str],
) -> Signal | None:
    """Convert a Firecrawl search result into a Signal.

    Args:
        result:          Single result from Firecrawl search response.
        query:           The search query that found this result.
        config_keywords: ICP keywords for scoring.

    Returns:
        Signal or None if no domain can be extracted.
    """
    url = result.get("url", "")
    if not url:
        return None

    domain = _extract_domain(url)
    if not domain or domain in ("github.com", "linkedin.com", "twitter.com", "x.com"):
        # Skip social/profile pages — we want company sites
        if not any(domain.endswith(tld) for tld in (".io", ".ai", ".com", ".dev", ".co")):
            return None

    title = result.get("title", "")
    description = result.get("description", "")
    markdown = result.get("markdown", "") or description

    strength = _score_result(markdown + " " + title, config_keywords)

    # Derive company name from domain
    company_name = domain.split(".")[0].capitalize()

    return Signal(
        signal_type="firecrawl_search",
        company_name=company_name,
        company_domain=domain,
        signal_strength=strength,
        source_url=url,
        raw_data={
            "title": title,
            "description": description,
            "markdown": markdown[:3000],
            "query": query,
        },
        metadata={
            "domain": domain,
            "search_query": query,
            "title": title,
        },
    )


def scan(config: ScannerConfig) -> ScanResult:
    """Run the Firecrawl search scanner.

    Uses config.queries as search queries (natural language or search operators).
    Also uses config.keywords as additional search terms.

    Args:
        config: ScannerConfig with queries and/or keywords for searching.

    Returns:
        ScanResult with Signal objects for each discovered company.
    """
    started_at = datetime.now(timezone.utc)

    app_config = get_config()
    if not app_config.firecrawl_api_key:
        return ScanResult(
            scan_type="firecrawl_search",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
            errors=["FIRECRAWL_API_KEY not configured — see .env.example"],
        )

    client = FirecrawlClient(api_key=app_config.firecrawl_api_key)

    # Build search queries from config
    queries: list[str] = list(config.queries)
    for kw in config.keywords:
        queries.append(f"companies building {kw}")

    if not queries:
        logger.warning("Firecrawl search scanner enabled but no queries configured")
        return ScanResult(
            scan_type="firecrawl_search",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
        )

    # ICP keywords for scoring
    scoring_keywords = list(config.topics) + list(config.libraries) + list(config.keywords)

    signals: list[Signal] = []
    seen_domains: set[str] = set()
    total_raw = 0
    errors: list[str] = []

    for query in queries:
        try:
            # Use search without scraping individual results (faster, cheaper)
            # scrape_options with empty formats = just search results
            resp = client.search(
                query,
                limit=config.custom_params.get("search_limit", 10),
                scrape_options={"formats": ["markdown"]},
            )
        except Exception as exc:
            msg = f"Firecrawl search failed for '{query[:60]}': {exc}"
            logger.warning(msg)
            errors.append(msg)
            continue

        results = resp.get("data", [])
        if not results:
            # Some responses use top-level list
            results = resp if isinstance(resp, list) else []

        for result in results:
            if not isinstance(result, dict):
                continue
            total_raw += 1

            domain = _extract_domain(result.get("url", ""))
            if domain in seen_domains:
                continue
            seen_domains.add(domain)

            signal = _result_to_signal(result, query, scoring_keywords)
            if signal:
                signals.append(signal)

    return ScanResult(
        scan_type="firecrawl_search",
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        signals_found=signals,
        total_raw_results=total_raw,
        total_after_dedup=len(signals),
        errors=errors,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover companies via Firecrawl web search.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--queries",
        nargs="+",
        required=True,
        help='Search queries (e.g. "companies building AI agents" "site:github.com RLHF")',
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max results per query.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to write results as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the Firecrawl search scanner."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    from scripts.config_loader import ScannerConfig

    scanner_cfg = ScannerConfig(
        module="scripts.scanners.firecrawl_search_scanner",
        queries=args.queries,
        lookback_days=7,
        custom_params={"search_limit": args.limit},
    )

    result = scan(scanner_cfg)

    print(f"Search complete — {len(result.signals_found)} signals")
    print(f"  Raw results:  {result.total_raw_results}")
    print(f"  After dedup:  {result.total_after_dedup}")
    if result.errors:
        print(f"  Errors:       {len(result.errors)}")

    for signal in sorted(result.signals_found, key=lambda s: s.signal_strength, reverse=True):
        strength = SignalStrength(signal.signal_strength).name
        print(f"  [{strength:8s}] {signal.company_name} — {signal.company_domain}")
        print(f"    URL: {signal.source_url}")

    if args.output:
        output_data = result.model_dump(mode="json")
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
