"""Funding Event Scanner.

Detects AI/ML companies that recently raised funding by monitoring funding
announcements. Designed to accept funding data from any source — Crunchbase,
PitchBook, custom endpoints — via configurable base URL and injectable data.
Runs in simulation mode when no API key is configured.

AI keyword filtering is driven by ScannerConfig.keywords when called via scan();
the class-level AI_KEYWORDS list is kept as a default for backward compatibility.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, UTC
from typing import Any

from scripts.api_client import BaseAPIClient
from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Funding API client
# ---------------------------------------------------------------------------


class FundingClient(BaseAPIClient):
    """HTTP client for funding round data sources.

    Accepts a configurable base_url so it can point at Crunchbase, PitchBook,
    or any custom endpoint that returns funding round records.

    When api_key is None the client operates in simulation mode, returning
    empty results instead of making real HTTP requests.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 30,
    ) -> None:
        auth_headers: dict[str, str] | None = None
        if api_key:
            auth_headers = {"Authorization": f"Bearer {api_key}"}
        super().__init__(base_url=base_url, auth_headers=auth_headers, timeout=timeout)
        self._api_key = api_key

    @property
    def simulation_mode(self) -> bool:
        """True when running without an API key (no real HTTP calls)."""
        return self._api_key is None

    def search_funding_rounds(
        self,
        query: str,
        min_date: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search for recent funding rounds matching the given query.

        Args:
            query: Search string (company type, industry keyword, etc.).
            min_date: ISO date string (YYYY-MM-DD) for earliest announced date.
            limit: Maximum number of results to return.

        Returns:
            List of funding round dicts. Each dict should contain:
            company_name, funding_amount, round_type, investors,
            announced_date, company_description, source_url.
        """
        if self.simulation_mode:
            logger.info("FundingClient in simulation mode — no real API call for query: %s", query)
            return []

        params: dict[str, Any] = {"q": query, "limit": limit}
        if min_date:
            params["min_date"] = min_date

        response = self.get("/funding/search", params=params)
        rounds = response.get("funding_rounds", [])
        return rounds[:limit]


# ---------------------------------------------------------------------------
# Round classification sets
# ---------------------------------------------------------------------------

_WEAK_ROUNDS = {"pre_seed", "pre-seed", "seed", "angel", "grant"}
_MODERATE_ROUNDS = {"series_a", "series a"}
_STRONG_ROUNDS = {"series_b", "series b", "series_c", "series c", "series_d", "series d", "growth"}

# Default AI keyword filter (used when no keywords configured)
_DEFAULT_AI_KEYWORDS: list[str] = [
    "artificial intelligence",
    "machine learning",
    "AI agents",
    "reinforcement learning",
    "LLM",
    "foundation model",
    "AI infrastructure",
    "model training",
    "autonomous systems",
    "robotics",
    "computer vision",
    "natural language processing",
]


# ---------------------------------------------------------------------------
# Funding tracker class
# ---------------------------------------------------------------------------


class FundingTracker:
    """Scanner that detects AI/ML companies that recently raised funding."""

    AI_KEYWORDS: list[str] = _DEFAULT_AI_KEYWORDS

    def __init__(self, keywords: list[str] | None = None) -> None:
        self._client = FundingClient(
            base_url="https://api.crunchbase.com/api/v4",
            api_key=None,  # simulation mode by default
        )
        if keywords is not None:
            self.AI_KEYWORDS = keywords

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def scan(self, lookback_days: int = 30) -> ScanResult:
        """Run a full funding event scan.

        Steps:
        1. Build search queries for AI/ML funding keywords.
        2. Query the funding data source for each query.
        3. Filter results: keep only companies whose description matches AI_KEYWORDS.
        4. Score each company by funding round type.
        5. Deduplicate by company name (keep first occurrence).
        6. Build Signal objects and return ScanResult.

        Args:
            lookback_days: How many days back to scan for announced rounds.

        Returns:
            ScanResult with Signal objects for each qualifying funding event.
        """
        started_at = datetime.now(UTC)
        queries = self._build_search_queries(lookback_days)
        min_date = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        seen_companies: dict[str, dict] = {}
        total_raw = 0
        errors: list[str] = []

        for query in queries:
            try:
                rounds = self._client.search_funding_rounds(query, min_date=min_date)
            except Exception as exc:
                error_msg = f"Funding search query failed: {query!r} — {exc}"
                logger.warning(error_msg)
                errors.append(error_msg)
                continue

            for funding_round in rounds:
                company = funding_round.get("company_name", "").strip()
                if not company:
                    continue

                description = funding_round.get("company_description", "")
                if not self._is_ai_company(description):
                    continue

                total_raw += 1

                if company not in seen_companies:
                    seen_companies[company] = funding_round

        signals: list[Signal] = []
        for company_name, funding_data in seen_companies.items():
            round_type = funding_data.get("round_type", "")
            score = self._classify_round(round_type)
            signal = self._create_signal(company_name, funding_data, score)
            signals.append(signal)

        completed_at = datetime.now(UTC)

        return ScanResult(
            scan_type="funding_event",
            started_at=started_at,
            completed_at=completed_at,
            signals_found=signals,
            total_raw_results=total_raw,
            total_after_dedup=len(signals),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_search_queries(self, lookback_days: int) -> list[str]:
        """Build search query strings for AI/ML funding announcements."""
        return [
            "artificial intelligence startup funding",
            "machine learning company funding round",
            "AI infrastructure funding",
            "reinforcement learning company raised",
            "foundation model startup funding",
        ]

    def _classify_round(self, round_type: str) -> SignalStrength:
        """Map a funding round type string to a SignalStrength.

        Classification:
        - WEAK:     pre_seed, pre-seed, seed, angel, grant, unknown, other
        - MODERATE: series_a, "series a"
        - STRONG:   series_b/c/d, "series b/c/d", growth
        """
        normalised = round_type.strip().lower()

        if normalised in _MODERATE_ROUNDS:
            return SignalStrength.MODERATE

        if normalised in _STRONG_ROUNDS:
            return SignalStrength.STRONG

        return SignalStrength.WEAK

    def _is_ai_company(self, description: str) -> bool:
        """Return True if the description contains any AI_KEYWORDS (case-insensitive)."""
        lower_desc = description.lower()
        return any(kw.lower() in lower_desc for kw in self.AI_KEYWORDS)

    def _create_signal(
        self,
        company: str,
        funding_data: dict,
        score: SignalStrength,
    ) -> Signal:
        """Build a Signal object for a detected funding event."""
        source_url = funding_data.get(
            "source_url", f"https://crunchbase.com/organization/{company}"
        )

        return Signal(
            signal_type="funding_event",
            company_name=company,
            signal_strength=score,
            source_url=source_url,
            raw_data={"funding_data": funding_data},
            metadata={
                "funding_amount": funding_data.get("funding_amount"),
                "round_type": funding_data.get("round_type"),
                "investors": funding_data.get("investors", []),
                "announced_date": funding_data.get("announced_date"),
                "company_description": funding_data.get("company_description"),
            },
        )


# ---------------------------------------------------------------------------
# Module-level entry point
# ---------------------------------------------------------------------------


def scan(config: ScannerConfig) -> ScanResult:
    """Run a full funding event scan using configuration.

    Args:
        config: ScannerConfig with keywords list and lookback_days.

    Returns:
        ScanResult with Signal objects for each qualifying funding event.
    """
    keywords = config.keywords or None
    tracker = FundingTracker(keywords=keywords)
    return tracker.scan(config.lookback_days)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan for AI/ML companies that recently raised funding.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="Number of days back to scan for funding announcements.",
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
    """CLI entry point for the funding event scanner."""
    from scripts.config_loader import load_config

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    sf_config = load_config()
    scanner_cfg = sf_config.scanners.get("funding")
    if scanner_cfg is None:
        # Fallback: run with default keywords
        tracker = FundingTracker()
        result = tracker.scan(lookback_days=args.lookback_days)
    else:
        if args.lookback_days != 30:
            scanner_cfg = scanner_cfg.model_copy(update={"lookback_days": args.lookback_days})
        result = scan(scanner_cfg)

    filtered_signals = [s for s in result.signals_found if s.signal_strength >= args.min_strength]

    print(f"Scan complete — {len(filtered_signals)} signals (min strength: {args.min_strength})")
    print(f"  Raw results:  {result.total_raw_results}")
    print(f"  After dedup:  {result.total_after_dedup}")
    print(f"  After filter: {len(filtered_signals)}")

    for signal in sorted(filtered_signals, key=lambda s: s.signal_strength, reverse=True):
        strength_label = SignalStrength(signal.signal_strength).name
        amount = signal.metadata.get("funding_amount")
        amount_str = f"${amount / 1_000_000:.0f}M" if amount else "undisclosed"
        round_type = signal.metadata.get("round_type", "unknown")
        print(f"  [{strength_label:8s}] {signal.company_name} — {round_type} ({amount_str})")

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
