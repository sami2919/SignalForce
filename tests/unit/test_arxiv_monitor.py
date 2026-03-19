"""Unit tests for arxiv_scanner — written FIRST (TDD RED phase).

All HTTP calls are mocked at the SemanticScholarClient.search_papers level.
No real API calls are made.
"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch


from scripts.models import SignalStrength, ScanResult, Signal

FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "semantic_scholar_responses.json"


def load_fixture() -> dict:
    with open(FIXTURES_PATH) as f:
        return json.load(f)


def make_paper(
    paper_id: str,
    title: str,
    affiliations_per_author: list[list[str]],
    year: int = 2024,
    arxiv_id: str | None = None,
) -> dict:
    """Build a minimal paper dict matching Semantic Scholar API shape."""
    authors = []
    for i, affiliations in enumerate(affiliations_per_author):
        authors.append(
            {
                "authorId": f"author_{paper_id}_{i}",
                "name": f"Author {i}",
                "affiliations": affiliations,
            }
        )
    return {
        "paperId": paper_id,
        "title": title,
        "year": year,
        "abstract": f"Abstract for {title}",
        "externalIds": {"ArXiv": arxiv_id or paper_id},
        "authors": authors,
    }


def make_search_response(papers: list[dict]) -> dict:
    return {
        "total": len(papers),
        "offset": 0,
        "data": papers,
    }


# ---------------------------------------------------------------------------
# SemanticScholarClient tests
# ---------------------------------------------------------------------------


class TestSemanticScholarClient:
    def test_search_papers_calls_correct_endpoint(self):
        from scripts.scanners.arxiv_scanner import SemanticScholarClient

        client = SemanticScholarClient(api_key="fake-key")
        with patch.object(client, "get", return_value={"total": 0, "data": []}) as mock_get:
            client.search_papers("reinforcement learning")
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert "/paper/search" in call_args[0][0]

    def test_search_papers_passes_query_param(self):
        from scripts.scanners.arxiv_scanner import SemanticScholarClient

        client = SemanticScholarClient(api_key="fake-key")
        with patch.object(client, "get", return_value={"total": 0, "data": []}) as mock_get:
            client.search_papers("RLHF")
            params = mock_get.call_args[1]["params"]
            assert params["query"] == "RLHF"

    def test_works_without_api_key(self):
        from scripts.scanners.arxiv_scanner import SemanticScholarClient

        client = SemanticScholarClient(api_key=None)
        assert client is not None
        assert "x-api-key" not in client._session.headers

    def test_sets_api_key_header_when_provided(self):
        from scripts.scanners.arxiv_scanner import SemanticScholarClient

        client = SemanticScholarClient(api_key="my-secret-key")
        assert client._session.headers.get("x-api-key") == "my-secret-key"


# ---------------------------------------------------------------------------
# ArxivRLMonitor unit tests
# ---------------------------------------------------------------------------


class TestScanReturnsScanResult:
    def test_scan_returns_scan_result(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()
        monitor._client.search_papers.return_value = make_search_response([])

        result = monitor.scan(lookback_days=7)

        assert isinstance(result, ScanResult)
        assert result.scan_type == "arxiv_paper"

    def test_scan_has_started_and_completed_at(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()
        monitor._client.search_papers.return_value = make_search_response([])

        result = monitor.scan(lookback_days=7)

        assert isinstance(result.started_at, datetime)
        assert isinstance(result.completed_at, datetime)
        assert result.completed_at >= result.started_at


class TestFiltersUniversityAffiliations:
    def test_filters_university_affiliations(self):
        """Papers from university authors should be excluded."""
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()

        mit_paper = make_paper(
            "mit_paper",
            "RL at MIT",
            [["Massachusetts Institute of Technology"]],
        )
        monitor._client.search_papers.return_value = make_search_response([mit_paper])

        with patch.object(monitor, "_is_recent", return_value=True):
            result = monitor.scan(lookback_days=7)

        assert result.total_after_dedup == 0
        assert result.signals_found == []

    def test_filters_institute_affiliations(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        normalized = monitor._normalize_affiliation("Stanford Institute for AI Research")
        assert normalized is None

    def test_filters_college_affiliations(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        normalized = monitor._normalize_affiliation("Carnegie Mellon College of Science")
        assert normalized is None

    def test_filters_school_affiliations(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        normalized = monitor._normalize_affiliation("School of Computer Science")
        assert normalized is None

    def test_filters_department_of_affiliations(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        normalized = monitor._normalize_affiliation("Department of Computer Science")
        assert normalized is None


class TestNormalizesKnownCompanies:
    def test_normalizes_google_deepmind(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        assert monitor._normalize_affiliation("Google DeepMind") == "Google"

    def test_normalizes_meta_ai(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        assert monitor._normalize_affiliation("Meta AI") == "Meta"

    def test_normalizes_meta_ai_research(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        assert monitor._normalize_affiliation("Meta AI Research") == "Meta"

    def test_normalizes_microsoft_research(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        assert monitor._normalize_affiliation("Microsoft Research") == "Microsoft"

    def test_normalizes_openai(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        assert monitor._normalize_affiliation("OpenAI") == "OpenAI"

    def test_normalizes_anthropic(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        assert monitor._normalize_affiliation("Anthropic") == "Anthropic"

    def test_normalizes_deepmind(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        assert monitor._normalize_affiliation("DeepMind") == "Google"

    def test_normalizes_google_brain(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        assert monitor._normalize_affiliation("Google Brain") == "Google"

    def test_normalizes_fair(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        assert monitor._normalize_affiliation("FAIR") == "Meta"

    def test_normalizes_case_insensitive(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        assert monitor._normalize_affiliation("google deepmind") == "Google"


class TestNormalizesUnknownCompany:
    def test_strips_inc_suffix(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        result = monitor._normalize_affiliation("Acme Robotics Inc")
        assert result == "Acme Robotics"

    def test_strips_ltd_suffix(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        result = monitor._normalize_affiliation("TechCorp Ltd")
        assert result == "TechCorp"

    def test_strips_corp_suffix(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        result = monitor._normalize_affiliation("BigCo Corp")
        assert result == "BigCo"

    def test_strips_research_suffix(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        result = monitor._normalize_affiliation("Acme Research")
        assert result == "Acme"

    def test_strips_ai_lab_suffix(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        result = monitor._normalize_affiliation("StartupCo AI Lab")
        assert result == "StartupCo"

    def test_strips_labs_suffix(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        result = monitor._normalize_affiliation("Innovation Labs")
        assert result == "Innovation"

    def test_returns_cleaned_name_for_unknown(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        result = monitor._normalize_affiliation("NovaTech AI")
        assert result is not None
        assert len(result) > 0


class TestScoringByPaperCount:
    def test_scoring_1_paper_is_weak(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        score = monitor._score_company(1)
        assert score == SignalStrength.WEAK

    def test_scoring_2_papers_is_moderate(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        score = monitor._score_company(2)
        assert score == SignalStrength.MODERATE

    def test_scoring_3_papers_is_moderate(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        score = monitor._score_company(3)
        assert score == SignalStrength.MODERATE

    def test_scoring_4_papers_is_strong(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        score = monitor._score_company(4)
        assert score == SignalStrength.STRONG

    def test_scoring_10_papers_is_strong(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        score = monitor._score_company(10)
        assert score == SignalStrength.STRONG


class TestDeduplicatesAcrossQueries:
    def test_deduplicates_same_paper_across_queries(self):
        """Same paper appearing in multiple queries is counted only once."""
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()

        paper = make_paper(
            "paper1",
            "RL Paper",
            [["Google DeepMind"]],
            arxiv_id="2401.00001",
        )
        monitor._client.search_papers.side_effect = [
            make_search_response([paper]),
            make_search_response([paper]),
        ]

        with patch.object(monitor, "_is_recent", return_value=True):
            with patch.object(
                monitor,
                "RL_SEARCH_QUERIES",
                ["reinforcement learning", "RLHF"],
            ):
                result = monitor.scan(lookback_days=7)

        assert result.total_after_dedup == 1
        assert result.signals_found[0].company_name == "Google"

    def test_same_company_multiple_papers_different_queries(self):
        """Same company papers from different queries are grouped and scored together."""
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()

        paper1 = make_paper("paper1", "RL Paper 1", [["Meta AI"]], arxiv_id="2401.00001")
        paper2 = make_paper("paper2", "RL Paper 2", [["Meta AI"]], arxiv_id="2401.00002")
        paper3 = make_paper("paper3", "RL Paper 3", [["Meta AI"]], arxiv_id="2401.00003")
        paper4 = make_paper("paper4", "RL Paper 4", [["Meta AI"]], arxiv_id="2401.00004")

        monitor._client.search_papers.side_effect = [
            make_search_response([paper1, paper2]),
            make_search_response([paper3, paper4]),
        ]

        with patch.object(monitor, "_is_recent", return_value=True):
            with patch.object(
                monitor,
                "RL_SEARCH_QUERIES",
                ["reinforcement learning", "RLHF"],
            ):
                result = monitor.scan(lookback_days=7)

        assert result.total_after_dedup == 1
        assert result.signals_found[0].signal_strength == SignalStrength.STRONG


class TestHandlesMissingAffiliations:
    def test_handles_missing_affiliations(self):
        """Papers with no affiliations are skipped."""
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()

        no_affil_paper = make_paper("no_affil", "RL Paper", [[]])
        monitor._client.search_papers.return_value = make_search_response([no_affil_paper])

        with patch.object(monitor, "_is_recent", return_value=True):
            result = monitor.scan(lookback_days=7)

        assert result.total_after_dedup == 0
        assert result.signals_found == []

    def test_handles_authors_without_affiliations_key(self):
        """Authors missing 'affiliations' key entirely are skipped gracefully."""
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()

        paper = {
            "paperId": "no_key",
            "title": "RL Paper",
            "year": 2024,
            "abstract": "Test",
            "externalIds": {"ArXiv": "2401.00000"},
            "authors": [{"authorId": "a1", "name": "Jane Doe"}],  # no affiliations key
        }
        monitor._client.search_papers.return_value = make_search_response([paper])

        with patch.object(monitor, "_is_recent", return_value=True):
            result = monitor.scan(lookback_days=7)

        assert result.total_after_dedup == 0


class TestMetadataContainsPaperTitles:
    def test_metadata_contains_paper_titles(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()

        paper = make_paper("p1", "Deep RL for Games", [["OpenAI"]])
        monitor._client.search_papers.return_value = make_search_response([paper])

        with patch.object(monitor, "_is_recent", return_value=True):
            result = monitor.scan_with_queries(["test query"], lookback_days=7)

        assert len(result.signals_found) == 1
        signal = result.signals_found[0]
        assert "paper_titles" in signal.metadata
        assert "Deep RL for Games" in signal.metadata["paper_titles"]

    def test_metadata_contains_paper_ids(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()

        paper = make_paper("p1", "Deep RL", [["OpenAI"]], arxiv_id="2401.11111")
        monitor._client.search_papers.return_value = make_search_response([paper])

        with patch.object(monitor, "_is_recent", return_value=True):
            result = monitor.scan_with_queries(["test query"], lookback_days=7)

        signal = result.signals_found[0]
        assert "paper_ids" in signal.metadata
        assert len(signal.metadata["paper_ids"]) > 0

    def test_metadata_contains_author_names(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()

        paper = {
            "paperId": "p1",
            "title": "Deep RL",
            "year": 2024,
            "abstract": "Test",
            "externalIds": {"ArXiv": "2401.11111"},
            "authors": [{"authorId": "a1", "name": "Alice Smith", "affiliations": ["OpenAI"]}],
        }
        monitor._client.search_papers.return_value = make_search_response([paper])

        with patch.object(monitor, "_is_recent", return_value=True):
            result = monitor.scan_with_queries(["test query"], lookback_days=7)

        signal = result.signals_found[0]
        assert "author_names" in signal.metadata
        assert "Alice Smith" in signal.metadata["author_names"]

    def test_metadata_contains_paper_count(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()

        paper = make_paper("p1", "Deep RL", [["Anthropic"]])
        monitor._client.search_papers.return_value = make_search_response([paper])

        with patch.object(monitor, "_is_recent", return_value=True):
            result = monitor.scan_with_queries(["test query"], lookback_days=7)

        signal = result.signals_found[0]
        assert "paper_count" in signal.metadata
        assert signal.metadata["paper_count"] == 1


class TestWorksWithoutApiKey:
    def test_scan_works_without_api_key(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor
        from scripts.config import AppConfig

        config = AppConfig(semantic_scholar_key=None)
        monitor = ArxivRLMonitor(config=config)

        assert "x-api-key" not in monitor._client._session.headers

    def test_monitor_initializes_without_config(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        with patch("scripts.scanners.arxiv_scanner.get_config") as mock_get_config:
            mock_get_config.return_value = MagicMock(semantic_scholar_key=None)
            monitor = ArxivRLMonitor()
            assert monitor is not None


class TestHandlesEmptyResults:
    def test_handles_empty_api_response(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()
        monitor._client.search_papers.return_value = {"total": 0, "data": []}

        result = monitor.scan(lookback_days=7)

        assert result.total_after_dedup == 0
        assert result.signals_found == []

    def test_handles_missing_data_key(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()
        monitor._client.search_papers.return_value = {"total": 0}  # no "data" key

        result = monitor.scan(lookback_days=7)

        assert result.total_after_dedup == 0

    def test_handles_api_error_gracefully(self):
        """If search_papers raises, the query is skipped, scan continues."""
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor
        from scripts.api_client import APIError

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        monitor._client = MagicMock()
        monitor._client.search_papers.side_effect = APIError(
            status_code=500, message="Server error", url="https://api.semanticscholar.org"
        )

        with patch.object(
            monitor,
            "RL_SEARCH_QUERIES",
            ["reinforcement learning"],
        ):
            result = monitor.scan(lookback_days=7)

        assert result.total_after_dedup == 0
        assert len(result.errors) > 0


class TestIsRecent:
    def test_is_recent_returns_true_for_current_year(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        current_year = datetime.now(UTC).year
        paper = {"year": current_year, "title": "Test"}
        assert monitor._is_recent(paper, lookback_days=365) is True

    def test_is_recent_returns_false_for_old_paper(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        paper = {"year": 2010, "title": "Old Paper"}
        assert monitor._is_recent(paper, lookback_days=7) is False

    def test_is_recent_returns_false_when_year_missing(self):
        from scripts.scanners.arxiv_scanner import ArxivRLMonitor

        monitor = ArxivRLMonitor.__new__(ArxivRLMonitor)
        paper = {"title": "No Year Paper"}
        assert monitor._is_recent(paper, lookback_days=7) is False


class TestCLIOutput:
    def test_cli_output_prints_summary(self, capsys):
        from scripts.scanners.arxiv_scanner import main

        mock_result = ScanResult(
            scan_type="arxiv_paper",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
        )

        with patch("scripts.scanners.arxiv_scanner.scan") as mock_scan:
            mock_scan.return_value = mock_result
            with patch("scripts.config_loader.load_config") as mock_load:
                mock_sf_config = MagicMock()
                mock_sf_config.scanners.get.return_value = MagicMock(lookback_days=7, queries=[])
                mock_load.return_value = mock_sf_config
                main(["--lookback-days", "7"])

        captured = capsys.readouterr()
        assert "0" in captured.out

    def test_cli_with_min_strength_filters(self, capsys):
        from scripts.scanners.arxiv_scanner import main

        weak_signal = Signal(
            signal_type="arxiv_paper",
            company_name="WeakCo",
            signal_strength=SignalStrength.WEAK,
            source_url="https://arxiv.org/abs/2401.00001",
            raw_data={"papers": []},
            metadata={
                "paper_titles": ["Test Paper"],
                "paper_ids": ["2401.00001"],
                "author_names": ["Alice"],
                "paper_count": 1,
            },
        )

        mock_result = ScanResult(
            scan_type="arxiv_paper",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[weak_signal],
            total_raw_results=1,
            total_after_dedup=1,
        )

        with patch("scripts.scanners.arxiv_scanner.scan") as mock_scan:
            mock_scan.return_value = mock_result
            with patch("scripts.config_loader.load_config") as mock_load:
                mock_sf_config = MagicMock()
                mock_sf_config.scanners.get.return_value = MagicMock(lookback_days=7, queries=[])
                mock_load.return_value = mock_sf_config
                main(["--lookback-days", "7", "--min-strength", "2"])

        captured = capsys.readouterr()
        assert "0" in captured.out

    def test_cli_with_output_file(self, capsys, tmp_path):
        from scripts.scanners.arxiv_scanner import main

        strong_signal = Signal(
            signal_type="arxiv_paper",
            company_name="StrongCo",
            signal_strength=SignalStrength.STRONG,
            source_url="https://arxiv.org/abs/2401.00099",
            raw_data={"papers": []},
            metadata={
                "paper_titles": ["Paper A", "Paper B", "Paper C", "Paper D"],
                "paper_ids": ["2401.00096", "2401.00097", "2401.00098", "2401.00099"],
                "author_names": ["Bob"],
                "paper_count": 4,
            },
        )

        mock_result = ScanResult(
            scan_type="arxiv_paper",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[strong_signal],
            total_raw_results=4,
            total_after_dedup=1,
        )

        output_file = tmp_path / "output.json"

        with patch("scripts.scanners.arxiv_scanner.scan") as mock_scan:
            mock_scan.return_value = mock_result
            with patch("scripts.config_loader.load_config") as mock_load:
                mock_sf_config = MagicMock()
                mock_sf_config.scanners.get.return_value = MagicMock(lookback_days=7, queries=[])
                mock_load.return_value = mock_sf_config
                main(["--lookback-days", "7", "--output", str(output_file)])

        assert output_file.exists()
        with open(output_file) as f:
            data = json.load(f)
        assert "signals" in data
        assert len(data["signals"]) == 1
        captured = capsys.readouterr()
        assert "Results written to" in captured.out

    def test_cli_prints_signal_details_for_strong_signals(self, capsys):
        from scripts.scanners.arxiv_scanner import main

        strong_signal = Signal(
            signal_type="arxiv_paper",
            company_name="MegaCorp",
            signal_strength=SignalStrength.STRONG,
            source_url="https://arxiv.org/abs/2401.00099",
            raw_data={"papers": []},
            metadata={
                "paper_titles": ["P1", "P2", "P3", "P4"],
                "paper_ids": ["id1", "id2", "id3", "id4"],
                "author_names": ["Author"],
                "paper_count": 4,
            },
        )

        mock_result = ScanResult(
            scan_type="arxiv_paper",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[strong_signal],
            total_raw_results=4,
            total_after_dedup=1,
        )

        with patch("scripts.scanners.arxiv_scanner.scan") as mock_scan:
            mock_scan.return_value = mock_result
            with patch("scripts.config_loader.load_config") as mock_load:
                mock_sf_config = MagicMock()
                mock_sf_config.scanners.get.return_value = MagicMock(lookback_days=7, queries=[])
                mock_load.return_value = mock_sf_config
                main(["--lookback-days", "7"])

        captured = capsys.readouterr()
        assert "MegaCorp" in captured.out
        assert "STRONG" in captured.out


class TestFixtureData:
    def test_fixture_paper_search_result_has_papers(self):
        fixture = load_fixture()
        assert "paper_search_result" in fixture
        papers = fixture["paper_search_result"]["data"]
        assert len(papers) == 5

    def test_fixture_has_google_deepmind_paper(self):
        fixture = load_fixture()
        papers = fixture["paper_search_result"]["data"]
        deepmind_papers = [
            p
            for p in papers
            if any("Google DeepMind" in a.get("affiliations", []) for a in p.get("authors", []))
        ]
        assert len(deepmind_papers) >= 1

    def test_fixture_has_mit_paper(self):
        fixture = load_fixture()
        papers = fixture["paper_search_result"]["data"]
        mit_papers = [
            p
            for p in papers
            if any(
                any(
                    "MIT" in affil or "Massachusetts" in affil
                    for affil in a.get("affiliations", [])
                )
                for a in p.get("authors", [])
            )
        ]
        assert len(mit_papers) >= 1

    def test_fixture_paper_no_affiliations(self):
        fixture = load_fixture()
        assert "paper_no_affiliations" in fixture
        papers = fixture["paper_no_affiliations"]["data"]
        assert len(papers) == 1
        all_affils = [
            affil
            for p in papers
            for a in p.get("authors", [])
            for affil in a.get("affiliations", [])
        ]
        assert all_affils == []
