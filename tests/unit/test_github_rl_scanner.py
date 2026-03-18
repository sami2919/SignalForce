"""Unit tests for GitHubRLScanner — written FIRST (TDD RED phase).

All HTTP calls are mocked at the GitHubClient method level.
No real API calls are made.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from io import StringIO

import pytest

from scripts.models import SignalType, SignalStrength, ScanResult, Signal
from scripts.github_rl_scanner import GitHubClient, GitHubRLScanner

# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "github_responses.json"


def load_fixture() -> dict:
    with open(FIXTURES_PATH) as f:
        return json.load(f)


def make_org_repo(org_name: str, repo_name: str, repo_id: int = 1) -> dict:
    """Build a minimal org repo dict matching GitHub API shape."""
    return {
        "id": repo_id,
        "name": repo_name,
        "full_name": f"{org_name}/{repo_name}",
        "html_url": f"https://github.com/{org_name}/{repo_name}",
        "description": "A test repo",
        "stargazers_count": 10,
        "forks_count": 2,
        "topics": ["reinforcement-learning"],
        "pushed_at": "2024-01-15T10:00:00Z",
        "owner": {
            "login": org_name,
            "type": "Organization",
            "html_url": f"https://github.com/{org_name}",
        },
    }


def make_user_repo(username: str, repo_name: str) -> dict:
    """Build a minimal personal (User) repo dict."""
    return {
        "id": 999,
        "name": repo_name,
        "full_name": f"{username}/{repo_name}",
        "html_url": f"https://github.com/{username}/{repo_name}",
        "description": "Personal project",
        "stargazers_count": 5,
        "forks_count": 0,
        "topics": ["reinforcement-learning"],
        "pushed_at": "2024-01-10T09:00:00Z",
        "owner": {
            "login": username,
            "type": "User",
            "html_url": f"https://github.com/{username}",
        },
    }


def make_search_response(items: list[dict], total: int | None = None) -> dict:
    return {
        "total_count": total if total is not None else len(items),
        "incomplete_results": False,
        "items": items,
    }


# ---------------------------------------------------------------------------
# GitHubClient tests
# ---------------------------------------------------------------------------


class TestGitHubClient:
    def test_search_repos_calls_correct_endpoint(self):
        client = GitHubClient(token="fake-token")
        with patch.object(client, "get", return_value={"total_count": 0, "items": []}) as mock_get:
            result = client.search_repos("topic:reinforcement-learning")
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[0][0] == "/search/repositories"
            assert call_args[1]["params"]["q"] == "topic:reinforcement-learning"

    def test_get_org_info_calls_correct_endpoint(self):
        client = GitHubClient(token="fake-token")
        with patch.object(client, "get", return_value={"login": "deepmind"}) as mock_get:
            result = client.get_org_info("deepmind")
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert "/orgs/deepmind" in call_args[0][0]

    def test_no_token_creates_unauthenticated_client(self):
        client = GitHubClient(token=None)
        # Should not raise; session just has no auth header
        assert client is not None


# ---------------------------------------------------------------------------
# GitHubRLScanner unit tests
# ---------------------------------------------------------------------------


class TestScanReturnsScanResult:
    def test_scan_returns_scan_result_type(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        scanner._client = MagicMock()
        scanner._client.search_repos.return_value = make_search_response([])

        with patch.object(scanner, "_build_search_queries", return_value=["topic:reinforcement-learning pushed:>2024-01-01"]):
            result = scanner.scan(lookback_days=7)

        assert isinstance(result, ScanResult)
        assert result.scan_type == SignalType.GITHUB_RL_REPO

    def test_scan_has_started_and_completed_at(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        scanner._client = MagicMock()
        scanner._client.search_repos.return_value = make_search_response([])

        with patch.object(scanner, "_build_search_queries", return_value=[]):
            result = scanner.scan(lookback_days=7)

        assert isinstance(result.started_at, datetime)
        assert isinstance(result.completed_at, datetime)
        assert result.completed_at >= result.started_at


class TestFiltersPersonalRepos:
    def test_filters_personal_repos_only_keeps_org_repos(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        scanner._client = MagicMock()

        org_repo = make_org_repo("acme-ai", "rl-framework")
        user_repo = make_user_repo("johndoe", "my-rl-project")

        scanner._client.search_repos.return_value = make_search_response(
            [org_repo, user_repo]
        )

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=["topic:reinforcement-learning pushed:>2024-01-01"],
        ):
            result = scanner.scan(lookback_days=7)

        # Only the org repo should produce a signal
        assert result.total_after_dedup == 1
        assert all(s.company_name == "acme-ai" for s in result.signals_found)

    def test_is_organization_returns_true_for_org(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        owner = {"login": "acme", "type": "Organization"}
        assert scanner._is_organization(owner) is True

    def test_is_organization_returns_false_for_user(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        owner = {"login": "johndoe", "type": "User"}
        assert scanner._is_organization(owner) is False


class TestDeduplicatesSameOrg:
    def test_deduplicates_same_org_found_via_multiple_queries(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        scanner._client = MagicMock()

        repo1 = make_org_repo("acme-ai", "rl-agent", repo_id=1)
        repo2 = make_org_repo("acme-ai", "rl-env", repo_id=2)

        # Two queries return same org
        scanner._client.search_repos.side_effect = [
            make_search_response([repo1]),  # first query
            make_search_response([repo2]),  # second query
        ]

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=[
                "topic:reinforcement-learning pushed:>2024-01-01",
                "topic:rlhf pushed:>2024-01-01",
            ],
        ):
            result = scanner.scan(lookback_days=7)

        # Should deduplicate to single signal for acme-ai
        assert result.total_after_dedup == 1
        assert len(result.signals_found) == 1
        assert result.signals_found[0].company_name == "acme-ai"

    def test_dedup_keeps_highest_score(self):
        """Org found via 2 queries with different repo counts → keep highest score."""
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        scanner._client = MagicMock()

        # First query returns 1 repo (WEAK candidate)
        repo1 = make_org_repo("acme-ai", "rl-agent", repo_id=1)
        # Second query returns 4 repos → STRONG
        repos_strong = [
            make_org_repo("acme-ai", f"repo-{i}", repo_id=10 + i) for i in range(4)
        ]

        scanner._client.search_repos.side_effect = [
            make_search_response([repo1]),
            make_search_response(repos_strong),
        ]

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=[
                "topic:reinforcement-learning pushed:>2024-01-01",
                "topic:rl pushed:>2024-01-01",
            ],
        ):
            result = scanner.scan(lookback_days=7)

        assert result.total_after_dedup == 1
        assert result.signals_found[0].signal_strength == SignalStrength.STRONG


class TestScoringWeak:
    def test_scoring_weak_1_repo_few_contributors(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        score = scanner._score_org(repo_count=1, contributor_count=2)
        assert score == SignalStrength.WEAK

    def test_scoring_weak_1_repo_4_contributors(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        score = scanner._score_org(repo_count=1, contributor_count=4)
        assert score == SignalStrength.WEAK


class TestScoringModerate:
    def test_scoring_moderate_2_repos(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        score = scanner._score_org(repo_count=2, contributor_count=3)
        assert score == SignalStrength.MODERATE

    def test_scoring_moderate_3_repos(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        score = scanner._score_org(repo_count=3, contributor_count=2)
        assert score == SignalStrength.MODERATE

    def test_scoring_moderate_1_repo_5_contributors(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        score = scanner._score_org(repo_count=1, contributor_count=5)
        assert score == SignalStrength.MODERATE

    def test_scoring_moderate_1_repo_9_contributors(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        score = scanner._score_org(repo_count=1, contributor_count=9)
        assert score == SignalStrength.MODERATE


class TestScoringStrong:
    def test_scoring_strong_4_repos(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        score = scanner._score_org(repo_count=4, contributor_count=3)
        assert score == SignalStrength.STRONG

    def test_scoring_strong_5_repos_15_contributors(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        score = scanner._score_org(repo_count=5, contributor_count=15)
        assert score == SignalStrength.STRONG

    def test_scoring_strong_10_plus_contributors(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        score = scanner._score_org(repo_count=1, contributor_count=10)
        assert score == SignalStrength.STRONG

    def test_scoring_strong_many_repos(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        score = scanner._score_org(repo_count=10, contributor_count=0)
        assert score == SignalStrength.STRONG


class TestSearchQueryFormat:
    def test_build_search_queries_returns_list(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        queries = scanner._build_search_queries(lookback_days=7)
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_search_query_contains_date(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        queries = scanner._build_search_queries(lookback_days=7)
        # Each query must include a pushed:> date filter
        for q in queries:
            assert "pushed:>" in q, f"Query missing date filter: {q}"

    def test_search_query_date_format(self):
        """Date in queries must be in YYYY-MM-DD format."""
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        queries = scanner._build_search_queries(lookback_days=30)
        for q in queries:
            # Extract date portion after "pushed:>"
            date_part = q.split("pushed:>")[1].strip().split()[0]
            # Should parse as a date
            datetime.strptime(date_part, "%Y-%m-%d")

    def test_search_query_includes_rl_topics(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        queries = scanner._build_search_queries(lookback_days=7)
        # At least one query should reference RL topics
        all_queries = " ".join(queries)
        assert any(
            term in all_queries
            for term in ["reinforcement-learning", "rlhf", "rl", "grpo"]
        )


class TestHandlesEmptyResults:
    def test_handles_empty_api_response(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        scanner._client = MagicMock()
        scanner._client.search_repos.return_value = make_search_response([])

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=["topic:reinforcement-learning pushed:>2024-01-01"],
        ):
            result = scanner.scan(lookback_days=7)

        assert result.total_after_dedup == 0
        assert result.signals_found == []

    def test_handles_no_queries(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        scanner._client = MagicMock()

        with patch.object(scanner, "_build_search_queries", return_value=[]):
            result = scanner.scan(lookback_days=7)

        assert result.total_after_dedup == 0
        assert result.signals_found == []
        scanner._client.search_repos.assert_not_called()

    def test_handles_missing_items_key(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        scanner._client = MagicMock()
        scanner._client.search_repos.return_value = {"total_count": 0}  # no "items" key

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=["topic:reinforcement-learning pushed:>2024-01-01"],
        ):
            result = scanner.scan(lookback_days=7)

        assert result.total_after_dedup == 0


class TestMetadataContainsRepoName:
    def test_signal_metadata_has_repo_name_key(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        scanner._client = MagicMock()

        org_repo = make_org_repo("acme-ai", "rl-framework")
        scanner._client.search_repos.return_value = make_search_response([org_repo])

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=["topic:reinforcement-learning pushed:>2024-01-01"],
        ):
            result = scanner.scan(lookback_days=7)

        assert len(result.signals_found) == 1
        signal = result.signals_found[0]
        assert "repo_name" in signal.metadata

    def test_signal_metadata_repo_name_is_string(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        scanner._client = MagicMock()

        org_repo = make_org_repo("acme-ai", "rl-framework")
        scanner._client.search_repos.return_value = make_search_response([org_repo])

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=["topic:reinforcement-learning pushed:>2024-01-01"],
        ):
            result = scanner.scan(lookback_days=7)

        signal = result.signals_found[0]
        assert isinstance(signal.metadata["repo_name"], str)
        assert len(signal.metadata["repo_name"]) > 0

    def test_create_signal_includes_repo_name(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        repos = [make_org_repo("acme-ai", "rl-framework")]
        signal = scanner._create_signal("acme-ai", repos, SignalStrength.MODERATE)
        assert "repo_name" in signal.metadata
        assert signal.signal_type == SignalType.GITHUB_RL_REPO
        assert signal.company_name == "acme-ai"


class TestCLIOutput:
    def test_cli_output_prints_summary(self, capsys):
        """Mock scan and verify CLI prints summary."""
        from scripts.github_rl_scanner import main

        mock_result = ScanResult(
            scan_type=SignalType.GITHUB_RL_REPO,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
        )

        with patch("scripts.github_rl_scanner.GitHubRLScanner") as MockScanner:
            mock_instance = MockScanner.return_value
            mock_instance.scan.return_value = mock_result
            main(["--lookback-days", "7"])

        captured = capsys.readouterr()
        assert "0" in captured.out  # some numeric output

    def test_cli_with_min_strength_filters(self, capsys, tmp_path):
        """CLI --min-strength filters signals below threshold."""
        from scripts.github_rl_scanner import main

        weak_signal = Signal(
            signal_type=SignalType.GITHUB_RL_REPO,
            company_name="weak-corp",
            signal_strength=SignalStrength.WEAK,
            source_url="https://github.com/weak-corp/repo",
            raw_data={"items": []},
            metadata={"repo_name": "repo"},
        )

        mock_result = ScanResult(
            scan_type=SignalType.GITHUB_RL_REPO,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[weak_signal],
            total_raw_results=1,
            total_after_dedup=1,
        )

        output_file = tmp_path / "output.json"

        with patch("scripts.github_rl_scanner.GitHubRLScanner") as MockScanner:
            mock_instance = MockScanner.return_value
            mock_instance.scan.return_value = mock_result
            # min-strength=2 should filter out WEAK (1) signals
            main(["--lookback-days", "7", "--min-strength", "2", "--output", str(output_file)])

        captured = capsys.readouterr()
        # With min-strength=2, WEAK signals are excluded
        assert "0" in captured.out


class TestTotalRawResults:
    def test_total_raw_results_counts_all_repos_before_dedup(self):
        scanner = GitHubRLScanner.__new__(GitHubRLScanner)
        scanner._client = MagicMock()

        # Two org repos from two different queries
        repo1 = make_org_repo("acme-ai", "rl-agent", repo_id=1)
        repo2 = make_org_repo("beta-ml", "rl-gym", repo_id=2)

        scanner._client.search_repos.side_effect = [
            make_search_response([repo1]),
            make_search_response([repo2]),
        ]

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=[
                "topic:reinforcement-learning pushed:>2024-01-01",
                "topic:rlhf pushed:>2024-01-01",
            ],
        ):
            result = scanner.scan(lookback_days=7)

        assert result.total_raw_results == 2
        assert result.total_after_dedup == 2

    def test_fixture_data_search_result_org(self):
        """Verify the fixture file parses correctly for org search."""
        fixture = load_fixture()
        assert "search_result_org" in fixture
        items = fixture["search_result_org"]["items"]
        assert len(items) == 3
        for item in items:
            assert item["owner"]["type"] == "Organization"

    def test_fixture_data_search_result_personal(self):
        """Verify the fixture file parses correctly for personal user search."""
        fixture = load_fixture()
        assert "search_result_personal" in fixture
        items = fixture["search_result_personal"]["items"]
        assert len(items) == 1
        assert items[0]["owner"]["type"] == "User"
