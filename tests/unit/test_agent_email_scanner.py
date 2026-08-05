"""Unit tests for scripts/scanners/agent_email_scanner.py.

All HTTP calls are mocked at the GitHubClient method level. No real API
calls, no DB — the ledger is a plain in-memory fake (FakeLedger below),
per the Task 2.2 brief's "keep the DB out of scanner unit tests" seam.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import requests

from scripts.api_client import APIError
from scripts.config_loader import ScannerConfig
from scripts.models import ScanResult, SignalStrength
from scripts.scanners.agent_email_scanner import (
    ALLOWED_QUALIFIERS,
    GitHubClient,
    RepoObservationRecord,
    _extract_candidate,
    _parse_gh_datetime,
    build_matrix,
    build_query,
    qualifiers_in_query,
    scan,
    scan_with_stats,
)


# ---------------------------------------------------------------------------
# Fakes / builders
# ---------------------------------------------------------------------------


class FakeLedger:
    """In-memory LedgerPort fake. `seed` pre-populates known full_names."""

    def __init__(self, seed: set[str] | None = None) -> None:
        self._known: set[str] = set(seed) if seed else set()
        self.recorded: list[RepoObservationRecord] = []
        self.known_calls: list[list[str]] = []

    def is_empty(self) -> bool:
        return not self._known

    def known(self, full_names: list[str]) -> set[str]:
        self.known_calls.append(list(full_names))
        return {fn for fn in full_names if fn in self._known}

    def record(self, observations: list[RepoObservationRecord]) -> None:
        self.recorded.extend(observations)
        self._known.update(o.full_name for o in observations)


def make_scanner_config(custom_params: dict | None = None) -> ScannerConfig:
    return ScannerConfig(
        module="scripts.scanners.agent_email_scanner",
        custom_params=custom_params
        or {
            "python_frameworks": ["langgraph"],
            "python_email_libs": ["resend"],
            "python_manifests": ["pyproject.toml"],
            "js_frameworks": [],
            "js_email_libs": [],
        },
    )


def make_search_item(
    full_name: str,
    owner_type: str = "Organization",
    fork: bool = False,
) -> dict:
    owner_login = full_name.split("/")[0]
    return {
        "name": "pyproject.toml",
        "path": "pyproject.toml",
        "repository": {
            "full_name": full_name,
            "html_url": f"https://github.com/{full_name}",
            "description": "test repo",
            "fork": fork,
            "owner": {"login": owner_login, "type": owner_type},
        },
    }


def make_search_response(items: list[dict], total: int | None = None) -> dict:
    return {
        "total_count": total if total is not None else len(items),
        "incomplete_results": False,
        "items": items,
    }


def make_repo_response(
    full_name: str,
    created_at: str = "2026-01-01T00:00:00Z",
    stars: int = 5,
    archived: bool = False,
) -> dict:
    return {
        "full_name": full_name,
        "created_at": created_at,
        "pushed_at": "2026-08-01T00:00:00Z",
        "stargazers_count": stars,
        "archived": archived,
        "fork": False,
    }


def _run_scan(config, ledger, search_side_effect=None, repo_side_effect=None):
    with patch("scripts.scanners.agent_email_scanner.get_config") as mock_get_config:
        mock_get_config.return_value = MagicMock(github_token="fake-token")
        with patch("scripts.scanners.agent_email_scanner.GitHubClient") as MockClient:
            mock_client = MockClient.return_value
            if search_side_effect is not None:
                mock_client.search_code.side_effect = search_side_effect
            if repo_side_effect is not None:
                mock_client.get_repo.side_effect = repo_side_effect
            result, stats = scan_with_stats(config, ledger)
    return result, stats


# ---------------------------------------------------------------------------
# Decision 2 canary: qualifier allowlist
# ---------------------------------------------------------------------------


class TestQualifierAllowlist:
    def test_build_query_uses_only_allowed_qualifiers(self):
        query = build_query("langgraph", "resend", "pyproject.toml")
        used = qualifiers_in_query(query)
        assert used, "query should contain at least the filename: qualifier"
        assert used <= ALLOWED_QUALIFIERS

    def test_allowed_qualifiers_excludes_recency_and_star_filters(self):
        # This is the canary: if someone later adds "pushed:" or "stars:" to
        # ALLOWED_QUALIFIERS, this test catches it (ADR-0006 Decision 2 — those
        # qualifiers return total_count: 0 with HTTP 200, a silent corpus wipe).
        assert "pushed" not in ALLOWED_QUALIFIERS
        assert "stars" not in ALLOWED_QUALIFIERS
        assert "created" not in ALLOWED_QUALIFIERS

    def test_qualifiers_in_query_detects_disallowed_qualifier(self):
        used = qualifiers_in_query('"langgraph" "resend" pushed:>2026-01-01')
        assert "pushed" in used
        assert not (used <= ALLOWED_QUALIFIERS)

    def test_build_query_contains_framework_and_lib_and_manifest(self):
        query = build_query("crewai", "sendgrid", "requirements.txt")
        assert '"crewai"' in query
        assert '"sendgrid"' in query
        assert "filename:requirements.txt" in query


# ---------------------------------------------------------------------------
# Matrix construction
# ---------------------------------------------------------------------------


class TestBuildMatrix:
    def test_matrix_uses_config_custom_params(self):
        config = make_scanner_config(
            {
                "python_frameworks": ["langgraph"],
                "python_email_libs": ["resend"],
                "python_manifests": ["pyproject.toml"],
                "js_frameworks": [],
                "js_email_libs": [],
            }
        )
        matrix = build_matrix(config)
        assert len(matrix) == 1
        assert matrix[0].framework == "langgraph"
        assert matrix[0].email_lib == "resend"
        assert matrix[0].manifest == "pyproject.toml"

    def test_matrix_falls_back_to_defaults_when_config_omits_lists(self):
        config = ScannerConfig(module="scripts.scanners.agent_email_scanner")
        matrix = build_matrix(config)
        # 6 py frameworks * 4 py email libs * 2 py manifests = 48
        # + 3 js frameworks * 4 js email libs * 1 js manifest = 12  => 60
        assert len(matrix) == 60


# ---------------------------------------------------------------------------
# Org filter / fork filter
# ---------------------------------------------------------------------------


class TestOwnerAndForkFiltering:
    def test_does_not_emit_for_user_owned_repo(self):
        config = make_scanner_config()
        ledger = FakeLedger()
        item = make_search_item("someuser/agent-mailer", owner_type="User")
        result, stats = _run_scan(
            config,
            ledger,
            search_side_effect=[make_search_response([item])],
            repo_side_effect=[],
        )
        assert result.signals_found == []
        assert stats.after_org_filter == 0

    def test_does_not_emit_for_fork(self):
        config = make_scanner_config()
        ledger = FakeLedger()
        item = make_search_item("acme/agent-mailer", fork=True)
        result, stats = _run_scan(
            config,
            ledger,
            search_side_effect=[make_search_response([item])],
            repo_side_effect=[],
        )
        assert result.signals_found == []
        assert stats.after_fork_drop == 0

    def test_org_owned_non_fork_repo_reaches_org_filter(self):
        config = make_scanner_config()
        ledger = FakeLedger()
        item = make_search_item("acme/agent-mailer")
        result, stats = _run_scan(
            config,
            ledger,
            search_side_effect=[make_search_response([item])],
            repo_side_effect=[make_repo_response("acme/agent-mailer")],
        )
        assert stats.after_org_filter == 1
        assert stats.new_to_us == 1


# ---------------------------------------------------------------------------
# Emit-once / ledger diff
# ---------------------------------------------------------------------------


class TestEmitOnce:
    def test_does_not_emit_for_repo_already_in_ledger(self):
        config = make_scanner_config()
        ledger = FakeLedger(seed={"acme/agent-mailer"})
        item = make_search_item("acme/agent-mailer")
        result, stats = _run_scan(
            config,
            ledger,
            search_side_effect=[make_search_response([item])],
            repo_side_effect=[],
        )
        assert result.signals_found == []
        assert stats.new_to_us == 0
        assert stats.enriched == 0

    def test_emits_for_new_org_repo_in_both_framework_and_email_manifest_hit(self):
        config = make_scanner_config()
        ledger = FakeLedger(seed={"someone-else/other-repo"})  # non-empty ledger, not seeding
        item = make_search_item("acme/agent-mailer")
        result, stats = _run_scan(
            config,
            ledger,
            search_side_effect=[make_search_response([item])],
            repo_side_effect=[make_repo_response("acme/agent-mailer", stars=42)],
        )
        assert len(result.signals_found) == 1
        signal = result.signals_found[0]
        assert signal.signal_type == "agent_email_repo"
        assert signal.company_name == "acme"
        assert signal.signal_strength == SignalStrength.STRONG
        assert signal.metadata["stars"] == 42
        assert stats.emitted == 1


# ---------------------------------------------------------------------------
# Archived
# ---------------------------------------------------------------------------


class TestArchived:
    def test_does_not_emit_for_archived_repo_but_records_it(self):
        config = make_scanner_config()
        ledger = FakeLedger(seed={"someone-else/other-repo"})
        item = make_search_item("acme/agent-mailer")
        result, stats = _run_scan(
            config,
            ledger,
            search_side_effect=[make_search_response([item])],
            repo_side_effect=[make_repo_response("acme/agent-mailer", archived=True)],
        )
        assert result.signals_found == []
        assert len(ledger.recorded) == 1
        assert ledger.recorded[0].archived is True


# ---------------------------------------------------------------------------
# Seeding run
# ---------------------------------------------------------------------------


class TestSeedingRun:
    def test_seeding_run_records_but_emits_nothing(self):
        config = make_scanner_config()
        ledger = FakeLedger()  # empty -> seeding
        item = make_search_item("acme/agent-mailer")
        result, stats = _run_scan(
            config,
            ledger,
            search_side_effect=[make_search_response([item])],
            repo_side_effect=[make_repo_response("acme/agent-mailer")],
        )
        assert stats.seeding_run is True
        assert result.signals_found == []
        assert len(ledger.recorded) == 1

    def test_non_empty_ledger_is_not_a_seeding_run(self):
        config = make_scanner_config()
        ledger = FakeLedger(seed={"someone-else/other-repo"})
        result, stats = _run_scan(
            config,
            ledger,
            search_side_effect=[make_search_response([])],
            repo_side_effect=[],
        )
        assert stats.seeding_run is False


# ---------------------------------------------------------------------------
# Enrichment call-count discipline
# ---------------------------------------------------------------------------


class TestEnrichmentCallCount:
    def test_enrichment_called_only_for_new_repos_not_known_ones(self):
        config = ScannerConfig(
            module="scripts.scanners.agent_email_scanner",
            custom_params={
                "python_frameworks": ["langgraph"],
                "python_email_libs": ["resend"],
                "python_manifests": ["pyproject.toml"],
                "js_frameworks": [],
                "js_email_libs": [],
            },
        )
        ledger = FakeLedger(seed={"known-org/known-repo"})
        items = [
            make_search_item("known-org/known-repo"),
            make_search_item("new-org/new-repo"),
        ]
        with patch("scripts.scanners.agent_email_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.agent_email_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_code.side_effect = [make_search_response(items)]
                mock_client.get_repo.side_effect = [make_repo_response("new-org/new-repo")]
                result, stats = scan_with_stats(config, ledger)

        assert mock_client.get_repo.call_count == 1
        mock_client.get_repo.assert_called_once_with("new-org/new-repo")
        assert stats.enriched == 1


# ---------------------------------------------------------------------------
# Truncation warning
# ---------------------------------------------------------------------------


class TestTruncationWarning:
    def test_pair_over_the_page_cap_logs_truncation_warning(self, caplog):
        config = make_scanner_config()
        ledger = FakeLedger(seed={"x/y"})
        item = make_search_item("acme/agent-mailer")
        with caplog.at_level("WARNING"):
            result, stats = _run_scan(
                config,
                ledger,
                search_side_effect=[make_search_response([item], total=5000)],
                repo_side_effect=[make_repo_response("acme/agent-mailer")],
            )
        assert len(stats.truncated_pairs) == 1
        # The warning must name BOTH the cap we applied and the true total, so an
        # operator reading `fly logs` can size the recall gap without re-querying.
        messages = [rec.getMessage() for rec in caplog.records]
        assert any("truncated" in m.lower() and "5000" in m for m in messages), messages

    def test_pair_within_the_page_cap_does_not_truncate(self):
        config = make_scanner_config()
        ledger = FakeLedger(seed={"x/y"})
        item = make_search_item("acme/agent-mailer")
        result, stats = _run_scan(
            config,
            ledger,
            search_side_effect=[make_search_response([item], total=42)],
            repo_side_effect=[make_repo_response("acme/agent-mailer")],
        )
        assert stats.truncated_pairs == []

    # See TestTruncationAtOurOwnCap below for the total_count=500 regression
    # (the gap between our own 300-result page cap and the API's 1000 ceiling).


# ---------------------------------------------------------------------------
# Per-query isolation — one query's APIError does not abort the scan
# ---------------------------------------------------------------------------


class TestEnrichmentIsolation:
    def test_enrichment_api_error_on_one_repo_does_not_abort_scan(self):
        config = make_scanner_config()
        ledger = FakeLedger(seed={"x/y"})
        items = [
            make_search_item("acme/broken-repo"),
            make_search_item("acme/good-repo"),
        ]

        def get_repo_side_effect(full_name):
            if full_name == "acme/broken-repo":
                raise APIError(status_code=500, message="boom", url="https://api.github.com")
            return make_repo_response(full_name)

        with patch("scripts.scanners.agent_email_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.agent_email_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_code.side_effect = [make_search_response(items)]
                mock_client.get_repo.side_effect = get_repo_side_effect
                result, stats = scan_with_stats(config, ledger)

        assert stats.enriched == 1
        assert len(result.signals_found) == 1
        assert result.signals_found[0].company_name == "acme"
        assert any("broken-repo" in e for e in result.errors)


class TestEnrichmentTransportErrorIsolation:
    """`except APIError` alone cannot catch requests.RequestException — a
    second consecutive Timeout (BaseAPIClient only retries a timeout once,
    outside any try — api_client.py's timeout branch re-raises on a second
    failure) was leaking past the enrichment handler. See
    TestTransportErrorIsolation below for the equivalent search-loop case."""

    def test_timeout_on_enrichment_does_not_abort_run(self):
        config = make_scanner_config()
        ledger = FakeLedger(seed={"x/y"})
        items = [
            make_search_item("acme/broken-repo"),
            make_search_item("acme/good-repo"),
        ]

        def get_repo_side_effect(full_name):
            if full_name == "acme/broken-repo":
                raise requests.Timeout("timed out twice")
            return make_repo_response(full_name)

        with patch("scripts.scanners.agent_email_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.agent_email_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_code.side_effect = [make_search_response(items)]
                mock_client.get_repo.side_effect = get_repo_side_effect
                result, stats = scan_with_stats(config, ledger)

        assert stats.enriched == 1
        assert len(result.signals_found) == 1
        assert any("broken-repo" in e for e in result.errors)


# See TestSeedingRunFloodRegression below for the seeding-run
# partial-enrichment-failure regression (RUN1/RUN2 sequence).


class TestPerQueryIsolation:
    def test_api_error_on_one_query_does_not_abort_whole_scan(self):
        config = ScannerConfig(
            module="scripts.scanners.agent_email_scanner",
            custom_params={
                "python_frameworks": ["langgraph", "crewai"],
                "python_email_libs": ["resend"],
                "python_manifests": ["pyproject.toml"],
                "js_frameworks": [],
                "js_email_libs": [],
            },
        )
        ledger = FakeLedger(seed={"x/y"})
        good_item = make_search_item("acme/agent-mailer")

        def search_side_effect(query, page=1):
            if "crewai" in query:
                raise APIError(status_code=422, message="boom", url="https://api.github.com")
            return make_search_response([good_item])

        with patch("scripts.scanners.agent_email_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.agent_email_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_code.side_effect = search_side_effect
                mock_client.get_repo.side_effect = [make_repo_response("acme/agent-mailer")]
                result, stats = scan_with_stats(config, ledger)

        # The failing query is recorded as an error, but the scan completes and
        # the other query's results still make it through.
        assert len(stats.failed_queries) == 1
        assert len(result.signals_found) == 1
        assert any("boom" in e or "422" in e for e in result.errors)


# ---------------------------------------------------------------------------
# scan() wrapper shape
# ---------------------------------------------------------------------------


class TestScanReturnsScanResult:
    def test_scan_returns_scan_result_type(self):
        config = make_scanner_config()
        ledger = FakeLedger(seed={"x/y"})
        result, _ = _run_scan(
            config,
            ledger,
            search_side_effect=[make_search_response([])],
            repo_side_effect=[],
        )
        assert isinstance(result, ScanResult)

    def test_scan_wrapper_returns_only_scan_result(self):
        config = make_scanner_config()
        ledger = FakeLedger(seed={"x/y"})
        with patch("scripts.scanners.agent_email_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.agent_email_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_code.side_effect = [make_search_response([])]
                result = scan(config, ledger)
        assert isinstance(result, ScanResult)
        assert result.scan_type == "agent_email_repo"


# ---------------------------------------------------------------------------
# GitHubClient
# ---------------------------------------------------------------------------


class TestCandidateExtraction:
    def test_extract_candidate_returns_none_for_missing_repository(self):
        assert _extract_candidate({"name": "pyproject.toml"}) is None

    def test_extract_candidate_returns_none_for_missing_full_name(self):
        assert _extract_candidate({"repository": {"owner": {}}}) is None


class TestParseGithubDatetime:
    def test_parse_gh_datetime_handles_z_suffix(self):
        parsed = _parse_gh_datetime("2026-01-01T00:00:00Z")
        assert parsed is not None
        assert parsed.year == 2026

    def test_parse_gh_datetime_returns_none_for_none(self):
        assert _parse_gh_datetime(None) is None

    def test_parse_gh_datetime_returns_none_for_garbage(self):
        assert _parse_gh_datetime("not-a-date") is None


class TestPagination:
    def test_pages_until_short_page_or_cap(self):
        """A full first page (100 items) should trigger a second search_code call."""
        config = make_scanner_config()
        ledger = FakeLedger(seed={"x/y"})
        full_page = [make_search_item(f"acme/repo-{i}") for i in range(100)]
        short_page = [make_search_item("acme/final-repo")]

        with patch("scripts.scanners.agent_email_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.agent_email_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                mock_client.search_code.side_effect = [
                    make_search_response(full_page, total=101),
                    make_search_response(short_page, total=101),
                ]
                mock_client.get_repo.side_effect = [
                    make_repo_response(f"acme/repo-{i}") for i in range(100)
                ] + [make_repo_response("acme/final-repo")]
                result, stats = scan_with_stats(config, ledger)

        assert mock_client.search_code.call_count == 2
        assert stats.search_requests == 2
        assert stats.raw_hits == 101


class TestBuildMatrixInvalidTriple:
    def test_invalid_triple_is_skipped_not_fatal(self):
        """A config-supplied framework containing a disallowed qualifier fails that
        one query but the scan still completes (per-query isolation)."""
        config = ScannerConfig(
            module="scripts.scanners.agent_email_scanner",
            custom_params={
                "python_frameworks": ["pushed:>2026-01-01"],
                "python_email_libs": ["resend"],
                "python_manifests": ["pyproject.toml"],
                "js_frameworks": [],
                "js_email_libs": [],
            },
        )
        ledger = FakeLedger(seed={"x/y"})
        with patch("scripts.scanners.agent_email_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(github_token="fake")
            with patch("scripts.scanners.agent_email_scanner.GitHubClient") as MockClient:
                mock_client = MockClient.return_value
                result, stats = scan_with_stats(config, ledger)

        mock_client.search_code.assert_not_called()
        assert len(stats.failed_queries) == 1
        assert result.signals_found == []


class TestGitHubClientNoToken:
    def test_no_token_creates_unauthenticated_client(self):
        client = GitHubClient(token=None)
        assert client is not None
        assert "Authorization" not in client._session.headers


class TestGitHubClient:
    def test_search_code_calls_correct_endpoint(self):
        client = GitHubClient(token="fake-token")
        with patch.object(client, "get", return_value={"total_count": 0, "items": []}) as mock_get:
            client.search_code('"langgraph" "resend" filename:pyproject.toml')
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[0][0] == "/search/code"
            assert call_args[1]["params"]["q"] == '"langgraph" "resend" filename:pyproject.toml'

    def test_get_repo_calls_correct_endpoint(self):
        client = GitHubClient(token="fake-token")
        with patch.object(client, "get", return_value={"full_name": "acme/repo"}) as mock_get:
            client.get_repo("acme/repo")
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[0][0] == "/repos/acme/repo"


# ---------------------------------------------------------------------------
# Fix round 1 regressions (review of commit 28b7333)
# ---------------------------------------------------------------------------


class TestTruncationAtOurOwnCap:
    """The warning must fire at the point WE truncate (_MAX_PAGES * _PER_PAGE),
    not at the API's 1000-result ceiling. A pair with total_count=500 loses 200
    matches to the page cap and must not do so silently (ADR-0006 Consequences).
    """

    def test_total_count_500_is_reported_as_truncated(self):
        full_page = [make_search_item(f"org{i}/repo{i}") for i in range(100)]

        def search(query, page=1, per_page=100):
            return make_search_response(full_page if page <= 3 else [], total=500)

        ledger = FakeLedger(seed={"sentinel/seen"})
        _result, stats = _run_scan(
            make_scanner_config(),
            ledger,
            search_side_effect=search,
            repo_side_effect=lambda fn: make_repo_response(fn),
        )

        assert stats.truncated_pairs, (
            "total_count=500 with a 3-page cap discards 200 matches and must be "
            f"flagged; truncated_pairs was {stats.truncated_pairs}"
        )
        assert stats.raw_hits == 300


class TestSearchTransportErrorIsolation:
    """Search-path counterpart to TestTransportErrorIsolation (enrichment path).

    requests.RequestException is not an APIError. BaseAPIClient leaks
    ConnectionError and a second consecutive Timeout, so a bare `except APIError`
    let one TCP reset abort the remaining queries mid-run.
    """

    def test_connection_error_on_one_query_does_not_abort_the_run(self):
        import requests

        calls = {"n": 0}

        def search(query, page=1, per_page=100):
            calls["n"] += 1
            if calls["n"] == 1:
                raise requests.ConnectionError("connection reset by peer")
            return make_search_response([make_search_item("goodorg/repo")])

        ledger = FakeLedger(seed={"sentinel/seen"})
        result, stats = _run_scan(
            make_scanner_config(
                {
                    "python_frameworks": ["langgraph"],
                    "python_email_libs": ["resend", "sendgrid"],
                    "python_manifests": ["pyproject.toml"],
                    "js_frameworks": [],
                    "js_email_libs": [],
                }
            ),
            ledger,
            search_side_effect=search,
            repo_side_effect=lambda fn: make_repo_response(fn),
        )

        assert len(stats.failed_queries) == 1
        assert any("connection reset" in e for e in result.errors)
        # The surviving query still produced its signal — the run was not aborted.
        assert stats.emitted == 1


class TestSeedingRunFloodRegression:
    """A seeding run whose enrichment partially fails must still RECORD the
    candidates it saw. Otherwise the next run sees them as new-to-us and emits
    a flood of false signals for repos that were present during seeding —
    corrupting the Phase 3 detection-lag record.
    """

    def test_partially_failed_seeding_does_not_flood_the_next_run(self):
        items = [make_search_item(f"org{i}/repo") for i in range(5)]

        def search(query, page=1, per_page=100):
            return make_search_response(items if page == 1 else [])

        quota_dead = {"v": True}

        def enrich(full_name):
            idx = int(full_name[3])
            if quota_dead["v"] and idx >= 2:
                raise APIError(status_code=403, message="quota exhausted", url=full_name)
            return make_repo_response(full_name)

        ledger = FakeLedger()
        cfg = make_scanner_config()

        _r1, s1 = _run_scan(cfg, ledger, search_side_effect=search, repo_side_effect=enrich)
        assert s1.seeding_run is True
        assert s1.emitted == 0
        assert len(ledger.recorded) == 5, (
            "a seeding run must record every org candidate it saw, including "
            f"those whose enrichment failed; recorded {len(ledger.recorded)}"
        )

        assert s1.enriched == 2, (
            "stats.enriched must count successful GET /repos calls, not recorded "
            f"rows — the seeding placeholders are not enrichments; got {s1.enriched}"
        )

        quota_dead["v"] = False  # quota recovers before the next run
        _r2, s2 = _run_scan(cfg, ledger, search_side_effect=search, repo_side_effect=enrich)
        assert s2.seeding_run is False
        assert s2.emitted == 0, (
            f"repos present during seeding must never emit as new-to-us; emitted {s2.emitted}"
        )


class TestPayloadCarriesBothTimeNotions:
    """ADR-0006 Decision 5: the payload carries created_at and pushed_at
    alongside first_seen_at, so "new to us" is never misread as "shipped now".
    """

    def test_signal_metadata_has_created_pushed_and_first_seen(self):
        def search(query, page=1, per_page=100):
            return make_search_response([make_search_item("acme/agent")] if page == 1 else [])

        ledger = FakeLedger(seed={"sentinel/seen"})
        result, _stats = _run_scan(
            make_scanner_config(),
            ledger,
            search_side_effect=search,
            repo_side_effect=lambda fn: make_repo_response(fn),
        )

        assert len(result.signals_found) == 1
        meta = result.signals_found[0].metadata
        assert meta["created_at"] == "2026-01-01T00:00:00+00:00"
        assert meta["pushed_at"] == "2026-08-01T00:00:00+00:00"
        # The POINT of Decision 5 is that first_seen_at is a DISTINCT notion from
        # the GitHub timestamps — asserting only "is not None" would pass even if
        # first_seen_at were collapsed onto created_at, which is the exact
        # misreporting ("new to us" == "shipped this week") the ADR forbids.
        assert meta["first_seen_at"] not in (meta["created_at"], meta["pushed_at"])
        assert datetime.fromisoformat(meta["first_seen_at"]).year >= 2026


class TestConfigExampleKeepsScannerDisabled:
    """scan() takes a required `ledger` arg and cannot be dispatched by
    scanner_runner's one-arg convention. config.example must keep it disabled so
    it never presents as "enabled, 0 signals forever" — which reads as a quiet
    market, the exact ambiguity ADR-0006 exists to remove.
    """

    def test_agent_email_scanner_is_disabled_in_config_example(self):
        from pathlib import Path

        import yaml

        repo_root = Path(__file__).resolve().parents[2]
        cfg = yaml.safe_load((repo_root / "config.example" / "config.yaml").read_text())
        assert cfg["scanners"]["agent_email"]["enabled"] is False


class TestTruncationBoundary:
    """total_count exactly at the cap is fully fetched and must NOT be flagged;
    one above it must be. Guards the `>` vs `>=` off-by-one.
    """

    def _run(self, total: int):
        full_page = [make_search_item(f"org{i}/repo{i}") for i in range(100)]

        def search(query, page=1, per_page=100):
            fetched = (page - 1) * 100
            remaining = max(total - fetched, 0)
            items = full_page[: min(100, remaining)]
            return make_search_response(items, total=total)

        ledger = FakeLedger(seed={"sentinel/seen"})
        _r, stats = _run_scan(
            make_scanner_config(),
            ledger,
            search_side_effect=search,
            repo_side_effect=lambda fn: make_repo_response(fn),
        )
        return stats

    def test_exactly_at_cap_is_not_truncated(self):
        assert self._run(300).truncated_pairs == []

    def test_one_over_cap_is_truncated(self):
        assert self._run(301).truncated_pairs != []

    def test_truncated_pair_records_the_magnitude(self):
        """Without total_count the recall gap cannot be sized from the run log,
        so the _MAX_PAGES decision could not be made on data."""
        assert "total_count=750" in self._run(750).truncated_pairs[0]
