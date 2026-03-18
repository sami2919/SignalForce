"""Job Posting Scanner.

Detects companies actively hiring for target roles by searching job boards.
Supports injecting custom search result data for testing and works in
simulation mode when no real API key is configured.

Scoring by posting count:
    1 posting  → WEAK
    2–3 postings → MODERATE
    4+ postings → STRONG
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, UTC

from scripts.api_client import BaseAPIClient
from scripts.config import get_config
from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job Posting API Client
# ---------------------------------------------------------------------------


class JobPostingClient(BaseAPIClient):
    """Client for job search APIs (e.g. SerpAPI) that return structured results."""

    def __init__(
        self,
        base_url: str = "https://serpapi.com",
        api_key: str | None = None,
        timeout: int = 30,
    ) -> None:
        auth_headers: dict[str, str] | None = None
        if api_key:
            auth_headers = {"X-API-Key": api_key}
        super().__init__(base_url=base_url, auth_headers=auth_headers, timeout=timeout)
        self._api_key = api_key

    def search_jobs(self, query: str, num_results: int = 10) -> list[dict]:
        """Search for job postings matching a query.

        Returns a list of result dicts, each with keys:
            - title: str
            - url: str
            - snippet: str
            - company: str | None
        """
        if not self._api_key:
            logger.debug("No API key configured — returning empty results for query: %s", query)
            return []

        try:
            response = self.get(
                "/search",
                params={"q": query, "num": num_results, "api_key": self._api_key},
            )
        except Exception as exc:
            logger.warning("Job search request failed for query '%s': %s", query, exc)
            return []

        organic = response.get("organic_results", [])
        results: list[dict] = []
        for item in organic:
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "company": item.get("source", None),
                }
            )
        return results


# ---------------------------------------------------------------------------
# URL patterns for major job boards
# ---------------------------------------------------------------------------

_URL_PATTERNS: list[tuple[str, str]] = [
    (r"jobs\.lever\.co/([^/]+)", "lever"),
    (r"boards\.greenhouse\.io/([^/]+)", "greenhouse"),
    (r"app\.ashbyhq\.com/jobs/([^/]+)", "ashby"),
]

_TITLE_AT_PATTERN = re.compile(r"\bat\s+([A-Z][A-Za-z0-9\-]+(?:\s+[A-Z][A-Za-z0-9\-]+)*)\s*$")

# Default skills vocabulary (used when no skills configured; kept for backward compat)
_DEFAULT_SKILLS: list[str] = [
    "gymnasium",
    "pytorch",
    "tensorflow",
    "simulation",
    "reward design",
    "reward modeling",
    "reward shaping",
    "policy optimization",
    "policy gradient",
    "rlhf",
    "ppo",
    "dqn",
    "stable-baselines",
    "stable baselines",
    "rllib",
    "torchrl",
    "cleanrl",
    "jax",
    "mujoco",
    "isaacgym",
    "isaaclab",
]


# ---------------------------------------------------------------------------
# Scanner class (internal implementation)
# ---------------------------------------------------------------------------


class JobPostingScanner:
    """Scanner that detects companies actively hiring via job boards."""

    JOB_BOARD_DOMAINS = ["linkedin.com", "lever.co", "greenhouse.io", "ashbyhq.com"]
    JOB_TITLES: list[str] = []

    def __init__(
        self,
        titles: list[str] | None = None,
        skills: list[str] | None = None,
    ) -> None:
        self._client = JobPostingClient()
        self.JOB_TITLES = titles or []
        self._skills = skills if skills is not None else _DEFAULT_SKILLS

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def scan(self, lookback_days: int = 7) -> ScanResult:
        """Run a full job posting scan.

        Steps:
        1. Build search queries (one per job title, scoped to job board domains).
        2. Execute searches via the client.
        3. Extract company name from each result.
        4. Group results by company.
        5. Score each company by total posting count.
        6. Deduplicate: same company across multiple queries → single signal.
        7. Return ScanResult.
        """
        started_at = datetime.now(UTC)
        queries = self._build_search_queries(lookback_days)

        company_postings: dict[str, list[dict]] = defaultdict(list)
        total_raw = 0
        errors: list[str] = []

        for query in queries:
            try:
                results = self._client.search_jobs(query)
            except Exception as exc:
                msg = f"Search query failed: '{query}' — {exc}"
                logger.warning(msg)
                errors.append(msg)
                continue

            for result in results:
                company = self._extract_company_from_result(result)
                if company is None:
                    continue
                total_raw += 1
                existing_urls = {p["url"] for p in company_postings[company]}
                if result["url"] not in existing_urls:
                    company_postings[company].append(result)

        signals: list[Signal] = []
        for company, postings in company_postings.items():
            score = self._score_company(len(postings))
            signal = self._create_signal(company, postings, score)
            signals.append(signal)

        completed_at = datetime.now(UTC)

        return ScanResult(
            scan_type="job_posting",
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
        """Build search query strings for each job title."""
        domain_filter = " OR ".join(f"site:{d}" for d in self.JOB_BOARD_DOMAINS)
        return [f"{title} {domain_filter}" for title in self.JOB_TITLES]

    def _extract_company_from_result(self, result: dict) -> str | None:
        """Attempt to extract a company name from a search result."""
        if result.get("company"):
            return result["company"]

        url = result.get("url", "")
        for pattern, _board in _URL_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        title = result.get("title", "")
        title_match = _TITLE_AT_PATTERN.search(title)
        if title_match:
            return title_match.group(1)

        return None

    def _extract_skills(self, description: str) -> list[str]:
        """Extract relevant skills from a job description text."""
        lower = description.lower()
        found: list[str] = []
        for skill in self._skills:
            if skill in lower:
                found.append(skill)
        return found

    def _score_company(self, posting_count: int) -> SignalStrength:
        """Score a company's hiring intent based on posting count."""
        if posting_count >= 4:
            return SignalStrength.STRONG
        if posting_count >= 2:
            return SignalStrength.MODERATE
        return SignalStrength.WEAK

    def _create_signal(
        self,
        company: str,
        postings: list[dict],
        score: SignalStrength,
    ) -> Signal:
        """Build a Signal object for a company detected as hiring."""
        job_titles = list({p.get("title", "") for p in postings if p.get("title")})
        posting_urls = [p["url"] for p in postings if p.get("url")]

        all_skills: set[str] = set()
        for posting in postings:
            snippet = posting.get("snippet", "")
            for skill in self._extract_skills(snippet):
                all_skills.add(skill)

        return Signal(
            signal_type="job_posting",
            company_name=company,
            signal_strength=score,
            source_url=posting_urls[0]
            if posting_urls
            else f"https://www.google.com/search?q={company}+engineer",
            raw_data={"postings": postings},
            metadata={
                "job_titles": job_titles,
                "posting_urls": posting_urls,
                "posting_count": len(postings),
                "skills_mentioned": sorted(all_skills),
            },
        )


# ---------------------------------------------------------------------------
# Module-level entry point
# ---------------------------------------------------------------------------


def scan(config: ScannerConfig) -> ScanResult:
    """Run a full job posting scan using configuration.

    Args:
        config: ScannerConfig with titles, skills, and lookback_days.

    Returns:
        ScanResult with Signal objects for each qualifying company.
    """
    scanner = JobPostingScanner(titles=config.titles, skills=config.skills)
    return scanner.scan(config.lookback_days)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan job boards for companies hiring in target roles.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Number of days back to scan for new job postings.",
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
    """CLI entry point for the job posting scanner."""
    from scripts.config_loader import load_config

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    sf_config = load_config()
    scanner_cfg = sf_config.scanners.get("jobs")
    if scanner_cfg is None:
        raise SystemExit("No 'jobs' scanner configured in config.yaml")

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
        posting_count = signal.metadata.get("posting_count", "?")
        print(f"  [{strength_label:8s}] {signal.company_name} — {posting_count} posting(s)")

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
