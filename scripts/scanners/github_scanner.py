"""GitHub Repository Scanner.

Detects organizations actively investing in target technologies by monitoring
their GitHub repositories. Scans for relevant topics and libraries, filters to
organization-owned repos, scores orgs by activity level, and returns Signal objects.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, UTC

from scripts.api_client import BaseAPIClient
from scripts.config import get_config
from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GitHub API client
# ---------------------------------------------------------------------------


class GitHubClient(BaseAPIClient):
    """GitHub REST API v3 client with optional token authentication."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None, timeout: int = 30) -> None:
        if token:
            auth_headers: dict[str, str] = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        else:
            auth_headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        super().__init__(base_url=self.BASE_URL, auth_headers=auth_headers, timeout=timeout)

    def search_repos(
        self,
        query: str,
        sort: str = "updated",
        per_page: int = 100,
    ) -> dict:
        """Search GitHub repositories.

        Args:
            query: GitHub search query string (e.g. "topic:reinforcement-learning pushed:>2024-01-01")
            sort: Sort field — "updated", "stars", "forks"
            per_page: Number of results per page (max 100)

        Returns:
            GitHub search response dict with "total_count" and "items" keys.
        """
        return self.get(
            "/search/repositories",
            params={"q": query, "sort": sort, "per_page": per_page},
        )

    def get_org_info(self, org_name: str) -> dict:
        """Fetch organisation details.

        Args:
            org_name: GitHub organisation login name.

        Returns:
            GitHub org response dict.
        """
        return self.get(f"/orgs/{org_name}")


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def _build_search_queries(config: ScannerConfig, lookback_days: int) -> list[str]:
    """Build GitHub search query strings covering configured topics and libraries.

    Args:
        config: Scanner configuration with topics and libraries lists.
        lookback_days: Number of days to look back.

    Returns:
        List of search query strings.
    """
    since_date = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    queries: list[str] = []

    for topic in config.topics:
        queries.append(f"topic:{topic} pushed:>{since_date}")

    for lib in config.libraries:
        queries.append(f"topic:{lib} pushed:>{since_date}")

    # Also include keyword queries if provided
    for kw in config.keywords:
        queries.append(f"{kw} pushed:>{since_date}")

    return queries


def _is_organization(owner: dict) -> bool:
    """Return True if the repo owner is a GitHub Organisation."""
    return owner.get("type") == "Organization"


def _score_org(repo_count: int, contributor_count: int) -> SignalStrength:
    """Score an organisation's investment level.

    Scoring rules:
    - STRONG:   4+ repos  OR  10+ contributors
    - MODERATE: 2-3 repos  OR  1 repo with 5-9 contributors
    - WEAK:     1 repo, <5 contributors

    Args:
        repo_count: Number of relevant repos found for the org.
        contributor_count: Aggregate contributor/fork proxy for the org.

    Returns:
        SignalStrength enum value.
    """
    if repo_count >= 4 or contributor_count >= 10:
        return SignalStrength.STRONG
    if repo_count >= 2 or contributor_count >= 5:
        return SignalStrength.MODERATE
    return SignalStrength.WEAK


def _create_signal(
    org_name: str,
    repos: list[dict],
    score: SignalStrength,
) -> Signal:
    """Build a Signal object for a detected active organisation.

    Args:
        org_name: GitHub organisation login name.
        repos: List of repo dicts collected for this org.
        score: Pre-computed SignalStrength for this org.

    Returns:
        Signal with github_repo type and repo_name in metadata.
    """
    sorted_repos = sorted(
        repos,
        key=lambda r: r.get("pushed_at", ""),
        reverse=True,
    )
    primary_repo = sorted_repos[0]
    repo_names = [r["name"] for r in sorted_repos]

    return Signal(
        signal_type="github_repo",
        company_name=org_name,
        signal_strength=score,
        source_url=primary_repo.get("html_url", f"https://github.com/{org_name}"),
        raw_data={"repos": repos},
        metadata={
            "repo_name": primary_repo["name"],
            "all_repo_names": repo_names,
            "repo_count": len(repos),
            "org_url": primary_repo.get("owner", {}).get(
                "html_url", f"https://github.com/{org_name}"
            ),
        },
    )


def scan(config: ScannerConfig) -> ScanResult:
    """Run a full GitHub scan.

    Steps:
    1. Build search queries for configured topics/libraries within the lookback window.
    2. Query GitHub search API for each query.
    3. Filter: keep only org repos (owner.type == "Organization").
    4. Group repos by org name.
    5. Score each org based on repo count and contributor count.
    6. Deduplicate: same org found via multiple queries → keep highest score.
    7. Build Signal objects and return ScanResult.

    Args:
        config: ScannerConfig with topics, libraries, keywords, and lookback_days.

    Returns:
        ScanResult with Signal objects for each qualifying org.
    """
    app_config = get_config()
    client = GitHubClient(token=app_config.github_token)

    started_at = datetime.now(UTC)
    lookback_days = config.lookback_days
    queries = _build_search_queries(config, lookback_days)

    # org_name → list of repos across all queries
    org_repos: dict[str, list[dict]] = defaultdict(list)
    total_raw = 0

    for query in queries:
        try:
            response = client.search_repos(query)
        except Exception as exc:
            logger.warning("Search query failed: %s — %s", query, exc)
            continue

        items: list[dict] = response.get("items", [])
        for repo in items:
            owner = repo.get("owner", {})
            if not _is_organization(owner):
                continue
            org_name: str = owner["login"]
            existing_ids = {r["id"] for r in org_repos[org_name]}
            if repo["id"] not in existing_ids:
                org_repos[org_name].append(repo)
                total_raw += 1

    signals: list[Signal] = []
    for org_name, repos in org_repos.items():
        repo_count = len(repos)
        contributor_count = sum(r.get("forks_count", 0) for r in repos)
        score = _score_org(repo_count, contributor_count)
        signal = _create_signal(org_name, repos, score)
        signals.append(signal)

    completed_at = datetime.now(UTC)

    return ScanResult(
        scan_type="github_repo",
        started_at=started_at,
        completed_at=completed_at,
        signals_found=signals,
        total_raw_results=total_raw,
        total_after_dedup=len(signals),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan GitHub for organisations actively investing in target technologies.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Number of days back to scan for updated repositories.",
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
    """CLI entry point for the GitHub scanner."""
    from scripts.config_loader import load_config

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    sf_config = load_config()
    scanner_cfg = sf_config.scanners.get("github")
    if scanner_cfg is None:
        raise SystemExit("No 'github' scanner configured in config.yaml")

    # Allow CLI override of lookback_days
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
