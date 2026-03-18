"""Unit tests for FundingTracker — written FIRST (TDD RED phase).

All HTTP calls are mocked at the FundingClient method level.
No real API calls are made.
"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch


from scripts.models import SignalType, SignalStrength, ScanResult, Signal

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "funding_responses.json"


def load_fixture() -> dict:
    with open(FIXTURES_PATH) as f:
        return json.load(f)


def make_funding_round(
    company_name: str = "Acme AI",
    funding_amount: int | None = 10_000_000,
    round_type: str = "series_a",
    investors: list[str] | None = None,
    announced_date: str = "2026-03-10",
    company_description: str = "A company building machine learning infrastructure.",
    source_url: str = "https://techcrunch.com/example",
) -> dict:
    """Build a minimal funding round dict."""
    return {
        "company_name": company_name,
        "funding_amount": funding_amount,
        "round_type": round_type,
        "investors": investors or ["Some VC"],
        "announced_date": announced_date,
        "company_description": company_description,
        "source_url": source_url,
    }


# ---------------------------------------------------------------------------
# FundingClient tests
# ---------------------------------------------------------------------------


class TestFundingClient:
    def test_client_initializes_with_base_url(self):
        from scripts.funding_tracker import FundingClient

        client = FundingClient(base_url="https://api.crunchbase.com")
        assert client.base_url == "https://api.crunchbase.com"

    def test_search_funding_rounds_returns_list(self):
        from scripts.funding_tracker import FundingClient

        client = FundingClient(base_url="https://api.crunchbase.com")
        with patch.object(
            client,
            "get",
            return_value={"funding_rounds": [make_funding_round()]},
        ):
            results = client.search_funding_rounds("artificial intelligence")
        assert isinstance(results, list)

    def test_search_funding_rounds_empty_response(self):
        from scripts.funding_tracker import FundingClient

        client = FundingClient(base_url="https://api.crunchbase.com")
        with patch.object(client, "get", return_value={}):
            results = client.search_funding_rounds("artificial intelligence")
        assert results == []

    def test_simulation_mode_returns_list_when_no_api_key(self):
        from scripts.funding_tracker import FundingClient

        client = FundingClient(base_url="https://api.crunchbase.com", api_key=None)
        results = client.search_funding_rounds("artificial intelligence")
        assert isinstance(results, list)

    def test_search_funding_rounds_with_min_date(self):
        from scripts.funding_tracker import FundingClient

        # Provide an api_key so the client is NOT in simulation mode and makes real HTTP calls.
        client = FundingClient(base_url="https://api.crunchbase.com", api_key="test-key")
        with patch.object(
            client,
            "get",
            return_value={"funding_rounds": [make_funding_round()]},
        ) as mock_get:
            client.search_funding_rounds("AI", min_date="2026-01-01")
            mock_get.assert_called_once()

    def test_search_funding_rounds_respects_limit(self):
        from scripts.funding_tracker import FundingClient

        client = FundingClient(base_url="https://api.crunchbase.com")
        rounds = [make_funding_round(company_name=f"Company{i}") for i in range(10)]
        with patch.object(
            client,
            "get",
            return_value={"funding_rounds": rounds},
        ):
            results = client.search_funding_rounds("AI", limit=5)
        assert len(results) <= 5


# ---------------------------------------------------------------------------
# test_scan_returns_scan_result
# ---------------------------------------------------------------------------


class TestScanReturnsScanResult:
    def test_scan_returns_scan_result_type(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        tracker._client = MagicMock()
        tracker._client.search_funding_rounds.return_value = []

        result = tracker.scan(lookback_days=30)

        assert isinstance(result, ScanResult)
        assert result.scan_type == SignalType.FUNDING_EVENT

    def test_scan_has_started_and_completed_at(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        tracker._client = MagicMock()
        tracker._client.search_funding_rounds.return_value = []

        result = tracker.scan(lookback_days=30)

        assert isinstance(result.started_at, datetime)
        assert isinstance(result.completed_at, datetime)
        assert result.completed_at >= result.started_at


# ---------------------------------------------------------------------------
# test_longer_default_lookback
# ---------------------------------------------------------------------------


class TestLongerDefaultLookback:
    def test_default_lookback_is_30_days(self):
        """FundingTracker.scan() default lookback is 30 days (not 7)."""
        from scripts.funding_tracker import FundingTracker
        import inspect

        sig = inspect.signature(FundingTracker.scan)
        default_lookback = sig.parameters["lookback_days"].default
        assert default_lookback == 30

    def test_scan_passes_lookback_to_client(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        tracker._client = MagicMock()
        tracker._client.search_funding_rounds.return_value = []

        tracker.scan(lookback_days=30)

        # Client must have been called (queries were built)
        assert tracker._client.search_funding_rounds.called


# ---------------------------------------------------------------------------
# test_filters_non_ai_companies
# ---------------------------------------------------------------------------


class TestFiltersNonAiCompanies:
    def test_filters_non_ai_companies(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        tracker._client = MagicMock()

        tracker._client.search_funding_rounds.return_value = [
            make_funding_round(
                company_name="RetailEdge Inc",
                company_description="Supply chain optimization software for enterprise retail.",
                round_type="series_c",
                funding_amount=100_000_000,
            )
        ]

        with patch.object(tracker, "_build_search_queries", return_value=["AI startup funding"]):
            result = tracker.scan(lookback_days=30)

        company_names = [s.company_name for s in result.signals_found]
        assert "RetailEdge Inc" not in company_names

    def test_includes_ai_companies(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        tracker._client = MagicMock()

        tracker._client.search_funding_rounds.return_value = [
            make_funding_round(
                company_name="NeuralDrive AI",
                company_description="NeuralDrive builds AI infrastructure for model training.",
                round_type="series_b",
                funding_amount=50_000_000,
            )
        ]

        with patch.object(tracker, "_build_search_queries", return_value=["AI startup funding"]):
            result = tracker.scan(lookback_days=30)

        company_names = [s.company_name for s in result.signals_found]
        assert "NeuralDrive AI" in company_names


# ---------------------------------------------------------------------------
# test_classify_round_*
# ---------------------------------------------------------------------------


class TestClassifyRound:
    def test_classify_round_seed_is_weak(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("seed") == SignalStrength.WEAK

    def test_classify_round_pre_seed_is_weak(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("pre_seed") == SignalStrength.WEAK

    def test_classify_round_pre_seed_hyphen_is_weak(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("pre-seed") == SignalStrength.WEAK

    def test_classify_round_angel_is_weak(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("angel") == SignalStrength.WEAK

    def test_classify_round_grant_is_weak(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("grant") == SignalStrength.WEAK

    def test_classify_round_series_a_is_moderate(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("series_a") == SignalStrength.MODERATE

    def test_classify_round_series_a_spaced_is_moderate(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("series a") == SignalStrength.MODERATE

    def test_classify_round_series_b_is_strong(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("series_b") == SignalStrength.STRONG

    def test_classify_round_series_b_spaced_is_strong(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("series b") == SignalStrength.STRONG

    def test_classify_round_series_c_is_strong(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("series_c") == SignalStrength.STRONG

    def test_classify_round_series_d_is_strong(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("series_d") == SignalStrength.STRONG

    def test_classify_round_growth_is_strong(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("growth") == SignalStrength.STRONG

    def test_classify_round_unknown_is_weak(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("unknown") == SignalStrength.WEAK

    def test_classify_round_empty_string_is_weak(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("") == SignalStrength.WEAK

    def test_classify_round_case_insensitive(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._classify_round("Series A") == SignalStrength.MODERATE
        assert tracker._classify_round("SEED") == SignalStrength.WEAK
        assert tracker._classify_round("Series B") == SignalStrength.STRONG


# ---------------------------------------------------------------------------
# test_metadata_includes_funding_amount
# ---------------------------------------------------------------------------


class TestMetadataIncludesFundingAmount:
    def test_metadata_includes_funding_amount(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        funding_data = make_funding_round(
            company_name="AI Corp",
            funding_amount=15_000_000,
            round_type="series_a",
        )
        signal = tracker._create_signal("AI Corp", funding_data, SignalStrength.MODERATE)

        assert "funding_amount" in signal.metadata
        assert signal.metadata["funding_amount"] == 15_000_000

    def test_metadata_includes_round_type(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        funding_data = make_funding_round(round_type="series_b")
        signal = tracker._create_signal("AI Corp", funding_data, SignalStrength.STRONG)

        assert "round_type" in signal.metadata
        assert signal.metadata["round_type"] == "series_b"

    def test_metadata_includes_investors(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        funding_data = make_funding_round(investors=["Andreessen Horowitz", "Sequoia"])
        signal = tracker._create_signal("AI Corp", funding_data, SignalStrength.MODERATE)

        assert "investors" in signal.metadata
        assert signal.metadata["investors"] == ["Andreessen Horowitz", "Sequoia"]

    def test_metadata_includes_announced_date(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        funding_data = make_funding_round(announced_date="2026-03-10")
        signal = tracker._create_signal("AI Corp", funding_data, SignalStrength.MODERATE)

        assert "announced_date" in signal.metadata
        assert signal.metadata["announced_date"] == "2026-03-10"

    def test_metadata_includes_company_description(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        funding_data = make_funding_round(
            company_description="Builds reinforcement learning infrastructure."
        )
        signal = tracker._create_signal("AI Corp", funding_data, SignalStrength.MODERATE)

        assert "company_description" in signal.metadata
        assert "reinforcement learning" in signal.metadata["company_description"]


# ---------------------------------------------------------------------------
# test_handles_undisclosed_amount
# ---------------------------------------------------------------------------


class TestHandlesUndisclosedAmount:
    def test_handles_undisclosed_amount(self):
        """funding_amount can be None (undisclosed rounds)."""
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        tracker._client = MagicMock()

        tracker._client.search_funding_rounds.return_value = [
            make_funding_round(
                company_name="StealthAI",
                funding_amount=None,
                company_description="Building LLM-based autonomous systems.",
            )
        ]

        with patch.object(tracker, "_build_search_queries", return_value=["AI startup funding"]):
            result = tracker.scan(lookback_days=30)

        # Should not crash; signal should still be created
        company_names = [s.company_name for s in result.signals_found]
        assert "StealthAI" in company_names

    def test_metadata_funding_amount_is_none_when_undisclosed(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        funding_data = make_funding_round(funding_amount=None)
        signal = tracker._create_signal("StealthAI", funding_data, SignalStrength.WEAK)

        assert signal.metadata["funding_amount"] is None


# ---------------------------------------------------------------------------
# test_deduplicates_by_company
# ---------------------------------------------------------------------------


class TestDeduplicatesByCompany:
    def test_deduplicates_by_company(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        tracker._client = MagicMock()

        same_company_round = make_funding_round(
            company_name="AI Corp",
            company_description="Machine learning infrastructure company.",
        )
        # Two search queries both return the same company
        tracker._client.search_funding_rounds.side_effect = [
            [same_company_round],
            [same_company_round],
        ]

        with patch.object(
            tracker,
            "_build_search_queries",
            return_value=["artificial intelligence funding", "machine learning funding"],
        ):
            result = tracker.scan(lookback_days=30)

        company_names = [s.company_name for s in result.signals_found]
        assert company_names.count("AI Corp") == 1

    def test_deduplication_keeps_first_occurrence(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        tracker._client = MagicMock()

        round_occurrence = make_funding_round(
            company_name="AI Corp",
            round_type="series_b",
            company_description="Building reinforcement learning platforms.",
        )
        tracker._client.search_funding_rounds.side_effect = [
            [round_occurrence],
            [round_occurrence],
        ]

        with patch.object(
            tracker,
            "_build_search_queries",
            return_value=["query_1", "query_2"],
        ):
            result = tracker.scan(lookback_days=30)

        assert len([s for s in result.signals_found if s.company_name == "AI Corp"]) == 1


# ---------------------------------------------------------------------------
# test_handles_empty_results
# ---------------------------------------------------------------------------


class TestHandlesEmptyResults:
    def test_handles_empty_results(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        tracker._client = MagicMock()
        tracker._client.search_funding_rounds.return_value = []

        result = tracker.scan(lookback_days=30)

        assert result.total_after_dedup == 0
        assert result.signals_found == []

    def test_handles_client_exception_gracefully(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        tracker._client = MagicMock()
        tracker._client.search_funding_rounds.side_effect = Exception("Network error")

        with patch.object(
            tracker,
            "_build_search_queries",
            return_value=["AI startup funding"],
        ):
            result = tracker.scan(lookback_days=30)

        assert isinstance(result, ScanResult)
        assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# test_is_ai_company
# ---------------------------------------------------------------------------


class TestIsAiCompany:
    def test_returns_true_for_machine_learning(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._is_ai_company("A company building machine learning pipelines.")

    def test_returns_true_for_reinforcement_learning(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._is_ai_company("Develops reinforcement learning algorithms.")

    def test_returns_true_for_llm(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._is_ai_company("Building LLM-based enterprise automation.")

    def test_returns_true_case_insensitive(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert tracker._is_ai_company("A MACHINE LEARNING startup.")

    def test_returns_false_for_non_ai_description(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert not tracker._is_ai_company(
            "Supply chain optimization for enterprise retail companies."
        )

    def test_returns_false_for_empty_description(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        assert not tracker._is_ai_company("")


# ---------------------------------------------------------------------------
# test_create_signal
# ---------------------------------------------------------------------------


class TestCreateSignal:
    def test_create_signal_has_correct_type(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        funding_data = make_funding_round()
        signal = tracker._create_signal("AI Corp", funding_data, SignalStrength.MODERATE)
        assert signal.signal_type == SignalType.FUNDING_EVENT

    def test_create_signal_has_correct_company(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        funding_data = make_funding_round()
        signal = tracker._create_signal("Acme AI Labs", funding_data, SignalStrength.MODERATE)
        assert signal.company_name == "Acme AI Labs"

    def test_create_signal_has_correct_strength(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        funding_data = make_funding_round(round_type="series_b")
        signal = tracker._create_signal("AI Corp", funding_data, SignalStrength.STRONG)
        assert signal.signal_strength == SignalStrength.STRONG

    def test_create_signal_source_url_from_funding_data(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        funding_data = make_funding_round(
            source_url="https://techcrunch.com/2026/03/10/acme-raises-series-b"
        )
        signal = tracker._create_signal("AI Corp", funding_data, SignalStrength.STRONG)
        assert signal.source_url == "https://techcrunch.com/2026/03/10/acme-raises-series-b"

    def test_create_signal_metadata_has_required_keys(self):
        from scripts.funding_tracker import FundingTracker

        tracker = FundingTracker.__new__(FundingTracker)
        funding_data = make_funding_round()
        signal = tracker._create_signal("AI Corp", funding_data, SignalStrength.MODERATE)
        assert "funding_amount" in signal.metadata
        assert "round_type" in signal.metadata
        assert "investors" in signal.metadata
        assert "announced_date" in signal.metadata
        assert "company_description" in signal.metadata


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    def test_cli_prints_summary(self, capsys):
        from scripts.funding_tracker import main

        mock_result = ScanResult(
            scan_type=SignalType.FUNDING_EVENT,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
        )

        with patch("scripts.funding_tracker.FundingTracker") as MockTracker:
            mock_instance = MockTracker.return_value
            mock_instance.scan.return_value = mock_result
            main(["--lookback-days", "30"])

        captured = capsys.readouterr()
        assert "0" in captured.out

    def test_cli_default_lookback_is_30(self, capsys):
        from scripts.funding_tracker import _build_arg_parser

        parser = _build_arg_parser()
        args = parser.parse_args([])
        assert args.lookback_days == 30

    def test_cli_with_min_strength_filters(self, capsys):
        from scripts.funding_tracker import main

        weak_signal = Signal(
            signal_type=SignalType.FUNDING_EVENT,
            company_name="SeedAI",
            signal_strength=SignalStrength.WEAK,
            source_url="https://techcrunch.com/seedai-raises-seed",
            raw_data={"funding_data": {}},
            metadata={
                "funding_amount": 500_000,
                "round_type": "seed",
                "investors": ["Angel Investor"],
                "announced_date": "2026-03-01",
                "company_description": "Building AI agents.",
            },
        )

        mock_result = ScanResult(
            scan_type=SignalType.FUNDING_EVENT,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[weak_signal],
            total_raw_results=1,
            total_after_dedup=1,
        )

        with patch("scripts.funding_tracker.FundingTracker") as MockTracker:
            mock_instance = MockTracker.return_value
            mock_instance.scan.return_value = mock_result
            main(["--lookback-days", "30", "--min-strength", "2"])

        captured = capsys.readouterr()
        # WEAK signal filtered → 0 after filter
        assert "0" in captured.out

    def test_cli_writes_output_file(self, tmp_path):
        from scripts.funding_tracker import main

        mock_result = ScanResult(
            scan_type=SignalType.FUNDING_EVENT,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
        )

        output_file = tmp_path / "output.json"

        with patch("scripts.funding_tracker.FundingTracker") as MockTracker:
            mock_instance = MockTracker.return_value
            mock_instance.scan.return_value = mock_result
            main(["--lookback-days", "30", "--output", str(output_file)])

        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert "scan_id" in data
        assert "signals" in data


# ---------------------------------------------------------------------------
# Fixture data tests
# ---------------------------------------------------------------------------


class TestFixtureData:
    def test_fixture_file_is_valid_json(self):
        fixture = load_fixture()
        assert isinstance(fixture, dict)

    def test_fixture_has_funding_rounds_key(self):
        fixture = load_fixture()
        assert "funding_rounds" in fixture

    def test_fixture_has_five_rounds(self):
        fixture = load_fixture()
        assert len(fixture["funding_rounds"]) == 5

    def test_fixture_has_series_b_strong_company(self):
        fixture = load_fixture()
        rounds = fixture["funding_rounds"]
        series_b = [r for r in rounds if r["round_type"] == "series_b"]
        assert len(series_b) == 1
        assert series_b[0]["funding_amount"] == 50_000_000

    def test_fixture_has_non_ai_company(self):
        fixture = load_fixture()
        rounds = fixture["funding_rounds"]
        non_ai = [
            r
            for r in rounds
            if "retail" in r["company_description"].lower()
            or "supply chain" in r["company_description"].lower()
        ]
        assert len(non_ai) >= 1

    def test_fixture_has_null_funding_amount(self):
        fixture = load_fixture()
        rounds = fixture["funding_rounds"]
        undisclosed = [r for r in rounds if r["funding_amount"] is None]
        assert len(undisclosed) == 1

    def test_fixture_has_unknown_round_type(self):
        fixture = load_fixture()
        rounds = fixture["funding_rounds"]
        unknown = [r for r in rounds if r["round_type"] == "unknown"]
        assert len(unknown) == 1
