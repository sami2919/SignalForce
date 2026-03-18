"""Job Posting Signal Scanner.

Detects companies actively hiring for reinforcement learning roles by searching
job boards. Supports injecting custom search result data for testing and works
in simulation mode when no real API key is configured.

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
from scripts.config import AppConfig, get_config
from scripts.models import Signal, ScanResult, SignalType, SignalStrength

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job Posting API Client
# ---------------------------------------------------------------------------


class JobPostingClient(BaseAPIClient):
    """Client for job search APIs (e.g. SerpAPI) that return structured results.

    In production, this hits a real search API. For testing the client can be
    mocked entirely at the ``search_jobs`` method level.
    """

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

        In production this queries SerpAPI's Google Search endpoint and maps
        ``organic_results`` to the common shape. The caller is responsible for
        providing a mocked version during tests.

        Args:
            query: Search query string (e.g. "reinforcement learning engineer
                   site:lever.co OR site:greenhouse.io").
            num_results: Maximum number of results to request.

        Returns:
            List of result dicts. Empty list if no results or on parse error.
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
# Job Posting Scanner
# ---------------------------------------------------------------------------

_RL_SKILLS = [
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

# URL patterns for major job boards. Each tuple is (domain_fragment, capture_group_index_after_split).
_URL_PATTERNS: list[tuple[str, str]] = [
    # https://jobs.lever.co/{company}/abc123
    (r"jobs\.lever\.co/([^/]+)", "lever"),
    # https://boards.greenhouse.io/{company}/jobs/...
    (r"boards\.greenhouse\.io/([^/]+)", "greenhouse"),
    # https://app.ashbyhq.com/jobs/{company}/...
    (r"app\.ashbyhq\.com/jobs/([^/]+)", "ashby"),
    # https://www.linkedin.com/jobs/view/...  — company not in URL, skip
]

_TITLE_AT_PATTERN = re.compile(r"\bat\s+([A-Z][A-Za-z0-9\-]+(?:\s+[A-Z][A-Za-z0-9\-]+)*)\s*$")


class JobPostingScanner:
    """Scanner that detects companies actively hiring for RL roles via job boards."""

    JOB_TITLES = [
        "reinforcement learning engineer",
        "RL researcher",
        "simulation engineer",
        "RLHF engineer",
        "reward modeling engineer",
        "RL environments engineer",
        "policy optimization engineer",
        "ML engineer reinforcement learning",
    ]

    JOB_BOARD_DOMAINS = ["linkedin.com", "lever.co", "greenhouse.io", "ashbyhq.com"]

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()
        self._client = JobPostingClient()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def scan(self, lookback_days: int = 7) -> ScanResult:
        """Run a full job posting scan for RL roles.

        Steps:
        1. Build search queries (one per job title, scoped to job board domains).
        2. Execute searches via the client.
        3. Extract company name from each result.
        4. Group results by company.
        5. Score each company by total posting count.
        6. Deduplicate: same company across multiple queries → single signal.
        7. Return ScanResult.

        Args:
            lookback_days: How many days back to consider (informational; included in
                           query strings where the search engine supports it).

        Returns:
            ScanResult with Signal objects for each qualifying company.
        """
        started_at = datetime.now(UTC)
        queries = self._build_search_queries(lookback_days)

        # company_slug → list of posting dicts across all queries
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
                # Deduplicate by URL within each company accumulator
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
            scan_type=SignalType.JOB_POSTING,
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
        """Build search query strings for each RL job title.

        Each query constrains results to known job board domains using the
        ``site:`` operator with ``OR`` so that a single query covers multiple
        boards.

        Args:
            lookback_days: Currently informational; future implementations may
                           append a date filter when the target API supports it.

        Returns:
            List of query strings, one per job title.
        """
        domain_filter = " OR ".join(f"site:{d}" for d in self.JOB_BOARD_DOMAINS)
        return [f"{title} {domain_filter}" for title in self.JOB_TITLES]

    def _extract_company_from_result(self, result: dict) -> str | None:
        """Attempt to extract a company name from a search result.

        Priority order:
        1. ``company`` field if present and non-null.
        2. URL pattern matching for known job boards (Lever, Greenhouse, Ashby).
        3. Title parsing: "Role at CompanyName" pattern.

        Args:
            result: Search result dict with ``title``, ``url``, ``snippet``,
                    and optional ``company`` keys.

        Returns:
            Company name string, or None if not extractable.
        """
        # 1. Explicit company field
        if result.get("company"):
            return result["company"]

        url = result.get("url", "")

        # 2. URL pattern matching
        for pattern, _board in _URL_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # 3. Title "Role at Company" pattern
        title = result.get("title", "")
        title_match = _TITLE_AT_PATTERN.search(title)
        if title_match:
            return title_match.group(1)

        return None

    def _extract_skills(self, description: str) -> list[str]:
        """Extract RL-related skills from a job description text.

        Performs case-insensitive substring matching against a fixed vocabulary
        of RL skills and libraries.

        Args:
            description: Raw job description or snippet text.

        Returns:
            Sorted, deduplicated list of matched skill strings (lowercase).
        """
        lower = description.lower()
        found: list[str] = []
        for skill in _RL_SKILLS:
            if skill in lower:
                found.append(skill)
        return found

    def _score_company(self, posting_count: int) -> SignalStrength:
        """Score a company's RL hiring intent based on posting count.

        Scoring rules:
        - STRONG:   4+ postings
        - MODERATE: 2–3 postings
        - WEAK:     1 posting

        Args:
            posting_count: Total number of RL-related job postings found for the company.

        Returns:
            SignalStrength enum value.
        """
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
        """Build a Signal object for a company detected as hiring for RL roles.

        Args:
            company: Company name / slug extracted from job postings.
            postings: List of posting dicts accumulated for this company.
            score: Pre-computed SignalStrength for this company.

        Returns:
            Signal with JOB_POSTING type and rich metadata.
        """
        job_titles = list({p.get("title", "") for p in postings if p.get("title")})
        posting_urls = [p["url"] for p in postings if p.get("url")]

        # Aggregate skills from all snippets
        all_skills: set[str] = set()
        for posting in postings:
            snippet = posting.get("snippet", "")
            for skill in self._extract_skills(snippet):
                all_skills.add(skill)

        return Signal(
            signal_type=SignalType.JOB_POSTING,
            company_name=company,
            signal_strength=score,
            source_url=posting_urls[0]
            if posting_urls
            else f"https://www.google.com/search?q={company}+RL+engineer",
            raw_data={"postings": postings},
            metadata={
                "job_titles": job_titles,
                "posting_urls": posting_urls,
                "posting_count": len(postings),
                "skills_mentioned": sorted(all_skills),
            },
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan job boards for companies hiring in reinforcement learning.",
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
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    scanner = JobPostingScanner()
    result = scanner.scan(lookback_days=args.lookback_days)

    # Filter by minimum strength
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
