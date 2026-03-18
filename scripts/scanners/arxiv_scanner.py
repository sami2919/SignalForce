"""ArXiv Paper Scanner.

Detects companies publishing research by querying the Semantic Scholar API
for relevant papers, extracting author affiliations, and normalizing them
to company names.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, UTC
from typing import Any

from scripts.api_client import BaseAPIClient
from scripts.config import get_config
from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Semantic Scholar API client
# ---------------------------------------------------------------------------


class SemanticScholarClient(BaseAPIClient):
    """Semantic Scholar Graph API client with optional API key authentication."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, api_key: str | None = None, timeout: int = 30) -> None:
        auth_headers: dict[str, str] | None = None
        if api_key:
            auth_headers = {"x-api-key": api_key}
        super().__init__(base_url=self.BASE_URL, auth_headers=auth_headers, timeout=timeout)

    def search_papers(
        self,
        query: str,
        year: str | None = None,
        limit: int = 100,
        fields: str = "title,authors,year,externalIds,abstract",
    ) -> dict:
        """Search for papers via the Semantic Scholar /paper/search endpoint.

        Args:
            query: Search query string (e.g. "reinforcement learning").
            year: Optional year filter (e.g. "2024" or "2023-2024").
            limit: Maximum number of results to return (default 100).
            fields: Comma-separated list of fields to return.

        Returns:
            Dict with "total", "offset", and "data" keys.
        """
        params: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "fields": fields,
        }
        if year:
            params["year"] = year

        return self.get("/paper/search", params=params)


# ---------------------------------------------------------------------------
# Monitor class (internal implementation)
# ---------------------------------------------------------------------------


# Known affiliation → canonical company name (case-insensitive lookup)
_KNOWN_AFFILIATIONS: dict[str, str] = {
    "google deepmind": "Google",
    "meta ai": "Meta",
    "meta ai research": "Meta",
    "microsoft research": "Microsoft",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "deepmind": "Google",
    "google brain": "Google",
    "google research": "Google",
    "facebook ai research": "Meta",
    "fair": "Meta",
}

# Terms that indicate an academic/non-company affiliation
_ACADEMIC_KEYWORDS = [
    "university",
    "institute",
    "college",
    "school",
    "department of",
]

# Suffixes to strip from unknown company names (order matters: longest first)
_STRIP_SUFFIXES = [
    r"\s+ai\s+lab$",
    r"\s+labs?$",
    r"\s+research$",
    r"\s+inc\.?$",
    r"\s+ltd\.?$",
    r"\s+corp\.?$",
]


class ArxivMonitor:
    """Monitor that detects companies publishing research via Semantic Scholar.

    Queries are driven by ScannerConfig.queries rather than hardcoded constants.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._client = SemanticScholarClient(api_key=api_key)

    # Preserve class attribute for test patching compatibility
    @property
    def RL_SEARCH_QUERIES(self) -> list[str]:  # noqa: N802  (kept for backward compat)
        return []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def scan_with_queries(self, queries: list[str], lookback_days: int = 7) -> ScanResult:
        """Run a full Semantic Scholar scan with the provided queries.

        Args:
            queries: List of search query strings.
            lookback_days: How many days back to scan for new papers.

        Returns:
            ScanResult with Signal objects for each qualifying company.
        """
        started_at = datetime.now(UTC)

        # company_name → set of paper dicts (deduped by paperId)
        company_papers: dict[str, dict[str, dict]] = defaultdict(dict)
        total_raw = 0
        errors: list[str] = []

        for query in queries:
            try:
                response = self._client.search_papers(query)
            except Exception as exc:
                msg = f"Search query failed: '{query}' — {exc}"
                logger.warning(msg)
                errors.append(msg)
                continue

            papers: list[dict] = response.get("data", [])
            for paper in papers:
                if not self._is_recent(paper, lookback_days):
                    continue

                paper_id = paper.get("paperId", "")
                companies = self._extract_companies(paper)
                for company in companies:
                    if paper_id not in company_papers[company]:
                        company_papers[company][paper_id] = paper
                        total_raw += 1

        signals: list[Signal] = []
        for company, papers_by_id in company_papers.items():
            papers_list = list(papers_by_id.values())
            score = self._score_company(len(papers_list))
            signal = self._create_signal(company, papers_list, score)
            signals.append(signal)

        completed_at = datetime.now(UTC)

        return ScanResult(
            scan_type="arxiv_paper",
            started_at=started_at,
            completed_at=completed_at,
            signals_found=signals,
            total_raw_results=total_raw,
            total_after_dedup=len(signals),
            errors=errors,
        )

    def scan(self, lookback_days: int = 7) -> ScanResult:
        """Run scan using RL_SEARCH_QUERIES (for backward compatibility with tests)."""
        return self.scan_with_queries(self.RL_SEARCH_QUERIES, lookback_days)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_recent(self, paper: dict, lookback_days: int) -> bool:
        """Return True if the paper's publication year is within lookback_days."""
        year = paper.get("year")
        if year is None:
            return False
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        paper_date = datetime(year, 1, 1, tzinfo=UTC)
        return paper_date >= cutoff

    def _extract_companies(self, paper: dict) -> list[str]:
        """Extract normalized company names from a paper's author affiliations."""
        companies: set[str] = set()
        for author in paper.get("authors", []):
            for affiliation in author.get("affiliations", []):
                normalized = self._normalize_affiliation(affiliation)
                if normalized:
                    companies.add(normalized)
        return list(companies)

    def _normalize_affiliation(self, affiliation: str) -> str | None:
        """Normalize an affiliation string to a company name."""
        stripped = affiliation.strip()
        lower = stripped.lower()

        if lower in _KNOWN_AFFILIATIONS:
            return _KNOWN_AFFILIATIONS[lower]

        for keyword in _ACADEMIC_KEYWORDS:
            if keyword in lower:
                return None

        cleaned = stripped
        for suffix_pattern in _STRIP_SUFFIXES:
            cleaned = re.sub(suffix_pattern, "", cleaned, flags=re.IGNORECASE).strip()

        return cleaned if cleaned else None

    def _score_company(self, paper_count: int) -> SignalStrength:
        """Score a company's investment level by paper count."""
        if paper_count >= 4:
            return SignalStrength.STRONG
        if paper_count >= 2:
            return SignalStrength.MODERATE
        return SignalStrength.WEAK

    def _create_signal(
        self,
        company: str,
        papers: list[dict],
        score: SignalStrength,
    ) -> Signal:
        """Build a Signal object for a company with research papers."""
        paper_titles = [p.get("title", "") for p in papers]
        paper_ids = [p.get("externalIds", {}).get("ArXiv") or p.get("paperId", "") for p in papers]
        author_names = list(
            {
                author.get("name", "")
                for p in papers
                for author in p.get("authors", [])
                if author.get("name")
            }
        )

        first_arxiv_id = next(
            (
                p.get("externalIds", {}).get("ArXiv")
                for p in papers
                if p.get("externalIds", {}).get("ArXiv")
            ),
            None,
        )
        source_url = (
            f"https://arxiv.org/abs/{first_arxiv_id}"
            if first_arxiv_id
            else f"https://www.semanticscholar.org/search?q={company.replace(' ', '+')}"
        )

        return Signal(
            signal_type="arxiv_paper",
            company_name=company,
            signal_strength=score,
            source_url=source_url,
            raw_data={"papers": papers},
            metadata={
                "paper_titles": paper_titles,
                "paper_ids": paper_ids,
                "author_names": author_names,
                "paper_count": len(papers),
            },
        )


# ---------------------------------------------------------------------------
# Backward-compat alias with RL_SEARCH_QUERIES as a class attribute
# ---------------------------------------------------------------------------


class ArxivRLMonitor(ArxivMonitor):
    """Backward-compatible alias. Use ArxivMonitor directly for new code.

    Kept so existing tests can do `ArxivRLMonitor.__new__(ArxivRLMonitor)` and
    patch `monitor.RL_SEARCH_QUERIES` / `monitor._is_recent`.
    """

    RL_SEARCH_QUERIES: list[str] = []

    def __init__(self, config: Any | None = None) -> None:  # noqa: ANN401
        app_cfg = config or get_config()
        super().__init__(api_key=getattr(app_cfg, "semantic_scholar_key", None))

    def scan(self, lookback_days: int = 7) -> ScanResult:
        """Run scan using instance RL_SEARCH_QUERIES attribute."""
        return self.scan_with_queries(self.RL_SEARCH_QUERIES, lookback_days)


# ---------------------------------------------------------------------------
# Module-level entry point
# ---------------------------------------------------------------------------


def scan(config: ScannerConfig) -> ScanResult:
    """Run a full Semantic Scholar scan using configuration.

    Args:
        config: ScannerConfig with queries list and lookback_days.

    Returns:
        ScanResult with Signal objects for each qualifying company.
    """
    app_config = get_config()
    monitor = ArxivMonitor(api_key=app_config.semantic_scholar_key)
    return monitor.scan_with_queries(config.queries, config.lookback_days)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan ArXiv/Semantic Scholar for companies publishing research.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Number of days back to scan for new papers.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to write results as JSON.",
    )
    parser.add_argument(
        "--min-strength",
        type=int,
        default=1,
        choices=[1, 2, 3],
        help="Minimum signal strength to include (1=WEAK, 2=MODERATE, 3=STRONG).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the ArXiv scanner."""
    from scripts.config_loader import load_config

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    sf_config = load_config()
    scanner_cfg = sf_config.scanners.get("arxiv")
    if scanner_cfg is None:
        raise SystemExit("No 'arxiv' scanner configured in config.yaml")

    if args.lookback_days != 7:
        scanner_cfg = scanner_cfg.model_copy(update={"lookback_days": args.lookback_days})

    result = scan(scanner_cfg)

    filtered_signals = [s for s in result.signals_found if s.signal_strength >= args.min_strength]

    print(f"Scan complete — {len(filtered_signals)} signals (min strength: {args.min_strength})")
    print(f"  Raw results:  {result.total_raw_results}")
    print(f"  After dedup:  {result.total_after_dedup}")
    print(f"  After filter: {len(filtered_signals)}")

    for signal in sorted(filtered_signals, key=lambda s: s.signal_strength, reverse=True):
        strength_label = SignalStrength(signal.signal_strength).name
        print(f"  [{strength_label:8s}] {signal.company_name} — {signal.source_url}")

    if args.output:
        output_data = {
            "scan_id": result.scan_id,
            "scan_type": result.scan_type,
            "started_at": result.started_at.isoformat(),
            "completed_at": result.completed_at.isoformat(),
            "total_raw_results": result.total_raw_results,
            "total_after_dedup": result.total_after_dedup,
            "signals": [
                {
                    "company_name": s.company_name,
                    "signal_strength": s.signal_strength,
                    "source_url": s.source_url,
                    "metadata": s.metadata,
                }
                for s in filtered_signals
            ],
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
