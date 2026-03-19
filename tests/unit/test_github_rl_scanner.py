"""Unit tests for github_scanner — written FIRST (TDD RED phase).

All HTTP calls are mocked at the GitHubClient method level.
No real API calls are made.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch


from scripts.models import SignalStrength, ScanResult
from scripts.scanners.github_scanner import (
    GitHubClient,
    _build_search_queries,
    _is_organization,
    _score_org,
    _create_signal,
    scan,
)
from scripts.config_loader import ScannerConfig

# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "github_responses.json"


def load_fixture() -> dict:
    with open(FIXTURES_PATH) as f:
        return json.load(f)


def make_scanner_config(
    topics: list[str] | None = None,
    libraries: list[str] | None = None,
    keywords: list[str] | None = None,
    lookback_days: int = 7,
) -> ScannerConfig:
    """Build a minimal ScannerConfig for testing."""
    return ScannerConfig(
        module="scripts.scanners.github_scanner",
        topics=topics or ["reinforcement-learning", "rl", "rlhf", "grpo"],
        libraries=libraries or ["gymnasium", "stable-baselines3"],
        keywords=keywords or [],
        lookback_days=lookback_days,
    )


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
            client.search_repos("topic:reinforcement-learning")
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[0][0] == "/search/repositories"
            assert call_args[1]["params"]["q"] == "topic:reinforcement-learning"

    def test_get_org_info_calls_correct_endpoint(self):
        client = GitHubClient(token="fake-token")
        with patch.object(client, "get", return_value={"login": "deepmind"}) as mock_get:
            client.get_org_info("deepmind")
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert "/orgs/deepmind" in call_args[0][0]

    def test_no_token_creates_unauthenticated_client(self):
        client = GitHubClient(token=None)
        # Should not raise; session just has no auth header
        assert client is not None


# ---------------------------------------------------------------------------
# scan() unit tests
# ---------------------------------------------------------------------------


class TestScanReturnsScanResult:
    def test_scan_returns_scan_result_type(self):
        config = make_scanner_config()
        with patch("scripts.scanners.github_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.github_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_repos.return_value = make_search_response([])
                result = scan(config)

        assert isinstance(result, ScanResult)
        assert result.scan_type == "github_repo"

    def test_scan_has_started_and_completed_at(self):
        config = make_scanner_config()
        with patch("scripts.scanners.github_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.github_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_repos.return_value = make_search_response([])
                result = scan(config)

        assert isinstance(result.started_at, datetime)
        assert isinstance(result.completed_at, datetime)
        assert result.completed_at >= result.started_at


class TestFiltersPersonalRepos:
    def test_filters_personal_repos_only_keeps_org_repos(self):
        config = make_scanner_config(topics=["reinforcement-learning"], libraries=[])
        org_repo = make_org_repo("acme-ai", "rl-framework")
        user_repo = make_user_repo("johndoe", "my-rl-project")

        with patch("scripts.scanners.github_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.github_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_repos.return_value = make_search_response([org_repo, user_repo])
                result = scan(config)

        assert result.total_after_dedup == 1
        assert all(s.company_name == "acme-ai" for s in result.signals_found)

    def test_is_organization_returns_true_for_org(self):
        owner = {"login": "acme", "type": "Organization"}
        assert _is_organization(owner) is True

    def test_is_organization_returns_false_for_user(self):
        owner = {"login": "johndoe", "type": "User"}
        assert _is_organization(owner) is False


class TestDeduplicatesSameOrg:
    def test_deduplicates_same_org_found_via_multiple_queries(self):
        config = make_scanner_config(topics=["reinforcement-learning", "rlhf"], libraries=[])
        repo1 = make_org_repo("acme-ai", "rl-agent", repo_id=1)
        repo2 = make_org_repo("acme-ai", "rl-env", repo_id=2)

        with patch("scripts.scanners.github_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.github_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_repos.side_effect = [
                    make_search_response([repo1]),
                    make_search_response([repo2]),
                ]
                result = scan(config)

        assert result.total_after_dedup == 1
        assert len(result.signals_found) == 1
        assert result.signals_found[0].company_name == "acme-ai"

    def test_dedup_keeps_highest_score(self):
        """Org found via 2 queries with different repo counts → keep highest score."""
        config = make_scanner_config(topics=["reinforcement-learning", "rl"], libraries=[])
        repo1 = make_org_repo("acme-ai", "rl-agent", repo_id=1)
        repos_strong = [make_org_repo("acme-ai", f"repo-{i}", repo_id=10 + i) for i in range(4)]

        with patch("scripts.scanners.github_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.github_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_repos.side_effect = [
                    make_search_response([repo1]),
                    make_search_response(repos_strong),
                ]
                result = scan(config)

        assert result.total_after_dedup == 1
        assert result.signals_found[0].signal_strength == SignalStrength.STRONG


class TestScoringWeak:
    def test_scoring_weak_1_repo_few_contributors(self):
        score = _score_org(repo_count=1, contributor_count=2)
        assert score == SignalStrength.WEAK

    def test_scoring_weak_1_repo_4_contributors(self):
        score = _score_org(repo_count=1, contributor_count=4)
        assert score == SignalStrength.WEAK


class TestScoringModerate:
    def test_scoring_moderate_2_repos(self):
        score = _score_org(repo_count=2, contributor_count=3)
        assert score == SignalStrength.MODERATE

    def test_scoring_moderate_3_repos(self):
        score = _score_org(repo_count=3, contributor_count=2)
        assert score == SignalStrength.MODERATE

    def test_scoring_moderate_1_repo_5_contributors(self):
        score = _score_org(repo_count=1, contributor_count=5)
        assert score == SignalStrength.MODERATE

    def test_scoring_moderate_1_repo_9_contributors(self):
        score = _score_org(repo_count=1, contributor_count=9)
        assert score == SignalStrength.MODERATE


class TestScoringStrong:
    def test_scoring_strong_4_repos(self):
        score = _score_org(repo_count=4, contributor_count=3)
        assert score == SignalStrength.STRONG

    def test_scoring_strong_5_repos_15_contributors(self):
        score = _score_org(repo_count=5, contributor_count=15)
        assert score == SignalStrength.STRONG

    def test_scoring_strong_10_plus_contributors(self):
        score = _score_org(repo_count=1, contributor_count=10)
        assert score == SignalStrength.STRONG

    def test_scoring_strong_many_repos(self):
        score = _score_org(repo_count=10, contributor_count=0)
        assert score == SignalStrength.STRONG


class TestSearchQueryFormat:
    def test_build_search_queries_returns_list(self):
        config = make_scanner_config()
        queries = _build_search_queries(config, lookback_days=7)
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_search_query_contains_date(self):
        config = make_scanner_config()
        queries = _build_search_queries(config, lookback_days=7)
        for q in queries:
            assert "pushed:>" in q, f"Query missing date filter: {q}"

    def test_search_query_date_format(self):
        """Date in queries must be in YYYY-MM-DD format."""
        config = make_scanner_config()
        queries = _build_search_queries(config, lookback_days=30)
        for q in queries:
            date_part = q.split("pushed:>")[1].strip().split()[0]
            datetime.strptime(date_part, "%Y-%m-%d")

    def test_search_query_includes_configured_topics(self):
        config = make_scanner_config(topics=["reinforcement-learning", "rlhf", "grpo"])
        queries = _build_search_queries(config, lookback_days=7)
        all_queries = " ".join(queries)
        assert any(term in all_queries for term in ["reinforcement-learning", "rlhf", "grpo"])


class TestHandlesEmptyResults:
    def test_handles_empty_api_response(self):
        config = make_scanner_config(topics=["reinforcement-learning"], libraries=[])
        with patch("scripts.scanners.github_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.github_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_repos.return_value = make_search_response([])
                result = scan(config)

        assert result.total_after_dedup == 0
        assert result.signals_found == []

    def test_handles_no_topics_or_libraries(self):
        """Empty topics/libraries/keywords → no queries → no API calls → empty result."""
        config = make_scanner_config(topics=[], libraries=[], keywords=[])
        with patch("scripts.scanners.github_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.github_scanner.GitHubClient"):
                result = scan(config)

        assert result.total_after_dedup == 0
        assert result.signals_found == []

    def test_handles_missing_items_key(self):
        config = make_scanner_config(topics=["reinforcement-learning"], libraries=[])
        with patch("scripts.scanners.github_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.github_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_repos.return_value = {"total_count": 0}  # no "items" key
                result = scan(config)

        assert result.total_after_dedup == 0


class TestMetadataContainsRepoName:
    def test_signal_metadata_has_repo_name_key(self):
        config = make_scanner_config(topics=["reinforcement-learning"], libraries=[])
        org_repo = make_org_repo("acme-ai", "rl-framework")

        with patch("scripts.scanners.github_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.github_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_repos.return_value = make_search_response([org_repo])
                result = scan(config)

        assert len(result.signals_found) == 1
        signal = result.signals_found[0]
        assert "repo_name" in signal.metadata

    def test_signal_metadata_repo_name_is_string(self):
        config = make_scanner_config(topics=["reinforcement-learning"], libraries=[])
        org_repo = make_org_repo("acme-ai", "rl-framework")

        with patch("scripts.scanners.github_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.github_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_repos.return_value = make_search_response([org_repo])
                result = scan(config)

        signal = result.signals_found[0]
        assert isinstance(signal.metadata["repo_name"], str)
        assert len(signal.metadata["repo_name"]) > 0

    def test_create_signal_includes_repo_name(self):
        repos = [make_org_repo("acme-ai", "rl-framework")]
        signal = _create_signal("acme-ai", repos, SignalStrength.MODERATE)
        assert "repo_name" in signal.metadata
        assert signal.signal_type == "github_repo"
        assert signal.company_name == "acme-ai"


class TestTotalRawResults:
    def test_total_raw_results_counts_all_repos_before_dedup(self):
        config = make_scanner_config(topics=["reinforcement-learning", "rlhf"], libraries=[])
        repo1 = make_org_repo("acme-ai", "rl-agent", repo_id=1)
        repo2 = make_org_repo("beta-ml", "rl-gym", repo_id=2)

        with patch("scripts.scanners.github_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.github_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_repos.side_effect = [
                    make_search_response([repo1]),
                    make_search_response([repo2]),
                ]
                result = scan(config)

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
