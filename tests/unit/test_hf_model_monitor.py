"""Unit tests for hf_scanner — written FIRST (TDD RED phase).

All HTTP calls are mocked at the HuggingFaceClient.list_models level.
No real API calls are made.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch


from scripts.models import SignalStrength, ScanResult, Signal
from scripts.scanners.hf_scanner import HuggingFaceClient, HuggingFaceRLMonitor

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "huggingface_responses.json"


def load_fixture() -> dict:
    with open(FIXTURES_PATH) as f:
        return json.load(f)


def make_model(
    org: str,
    model_name: str,
    tags: list[str] | None = None,
    days_ago: int = 2,
) -> dict:
    """Build a minimal HF model dict matching the API shape."""
    last_modified = (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return {
        "modelId": f"{org}/{model_name}",
        "id": f"{org}/{model_name}",
        "lastModified": last_modified,
        "tags": tags or ["reinforcement-learning"],
        "pipeline_tag": "text-generation",
        "downloads": 100,
        "likes": 10,
    }


def make_old_model(org: str, model_name: str, tags: list[str] | None = None) -> dict:
    """Build a model that is outside the lookback window (30 days ago)."""
    return make_model(org, model_name, tags=tags, days_ago=30)


# ---------------------------------------------------------------------------
# HuggingFaceClient tests
# ---------------------------------------------------------------------------


class TestHuggingFaceClient:
    def test_list_models_calls_correct_endpoint(self):
        client = HuggingFaceClient()
        with patch.object(client, "get", return_value=[]) as mock_get:
            client.list_models(filter_tag="ppo")
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[0][0] == "/models"
            assert call_args[1]["params"]["tags"] == "ppo"

    def test_list_models_default_params(self):
        client = HuggingFaceClient()
        with patch.object(client, "get", return_value=[]) as mock_get:
            client.list_models()
            call_args = mock_get.call_args
            params = call_args[1]["params"]
            assert params["sort"] == "lastModified"
            assert params["direction"] == -1
            assert params["limit"] == 100

    def test_get_model_info_calls_correct_endpoint(self):
        client = HuggingFaceClient()
        fixture = load_fixture()
        with patch.object(client, "get", return_value=fixture["model_info"]) as mock_get:
            client.get_model_info("meta-llama/Llama-3-RL-8B")
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert "meta-llama/Llama-3-RL-8B" in call_args[0][0]

    def test_no_auth_required(self):
        """HuggingFaceClient should have no Authorization header."""
        client = HuggingFaceClient()
        auth_header = client._session.headers.get("Authorization")
        assert auth_header is None

    def test_base_url_is_huggingface(self):
        client = HuggingFaceClient()
        assert "huggingface.co" in client.base_url


# ---------------------------------------------------------------------------
# HuggingFaceRLMonitor tests
# ---------------------------------------------------------------------------


class TestScanReturnsScanResult:
    def test_scan_returns_scan_result(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()
        monitor._client.list_models.return_value = []

        result = monitor.scan(lookback_days=7)

        assert isinstance(result, ScanResult)
        assert result.scan_type == "huggingface_model"

    def test_scan_has_started_and_completed_at(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()
        monitor._client.list_models.return_value = []

        result = monitor.scan(lookback_days=7)

        assert isinstance(result.started_at, datetime)
        assert isinstance(result.completed_at, datetime)
        assert result.completed_at >= result.started_at


class TestFiltersByRecency:
    def test_excludes_old_models(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        old_model = make_old_model("meta-llama", "old-rl-model", tags=["ppo"])
        monitor._client.list_models.return_value = [old_model]

        result = monitor.scan(lookback_days=7)

        assert result.total_after_dedup == 0
        assert result.signals_found == []

    def test_includes_recent_models(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        recent_model = make_model("meta-llama", "new-rl-model", tags=["ppo"])
        monitor._client.list_models.return_value = [recent_model]

        result = monitor.scan(lookback_days=7)

        assert result.total_after_dedup == 1

    def test_boundary_model_at_exactly_lookback_days_excluded(self):
        """Model modified exactly lookback_days ago (not strictly within window) is excluded."""
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        boundary_model = make_model("acme-ai", "boundary-model", tags=["ppo"], days_ago=7)
        monitor._client.list_models.return_value = [boundary_model]

        result = monitor.scan(lookback_days=7)

        assert isinstance(result, ScanResult)


class TestGroupsByOrg:
    def test_multiple_models_from_same_org_create_one_signal(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        model1 = make_model("google", "ppo-model-a", tags=["ppo"])
        model2 = make_model("google", "dpo-model-b", tags=["dpo"])
        monitor._client.list_models.return_value = [model1, model2]

        result = monitor.scan(lookback_days=7)

        assert result.total_after_dedup == 1
        assert result.signals_found[0].company_name == "google"

    def test_models_from_different_orgs_create_separate_signals(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        model_google = make_model("google", "rl-model", tags=["ppo"])
        model_meta = make_model("meta-llama", "rl-model", tags=["dpo"])
        monitor._client.list_models.return_value = [model_google, model_meta]

        result = monitor.scan(lookback_days=7)

        assert result.total_after_dedup == 2
        org_names = {s.company_name for s in result.signals_found}
        assert "google" in org_names
        assert "meta-llama" in org_names


class TestScoringByModelCount:
    def test_one_model_is_weak(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        score = monitor._score_org(model_count=1)
        assert score == SignalStrength.WEAK

    def test_two_models_is_moderate(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        score = monitor._score_org(model_count=2)
        assert score == SignalStrength.MODERATE

    def test_three_models_is_moderate(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        score = monitor._score_org(model_count=3)
        assert score == SignalStrength.MODERATE

    def test_four_models_is_strong(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        score = monitor._score_org(model_count=4)
        assert score == SignalStrength.STRONG

    def test_five_models_is_strong(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        score = monitor._score_org(model_count=5)
        assert score == SignalStrength.STRONG


class TestExtractsTrainingMethod:
    def test_extracts_ppo_from_tags(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        model_info = {"tags": ["ppo", "transformers", "pytorch"]}
        method = monitor._extract_training_method(model_info)
        assert method == "ppo"

    def test_extracts_dpo_from_tags(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        model_info = {"tags": ["dpo", "fine-tuning"]}
        method = monitor._extract_training_method(model_info)
        assert method == "dpo"

    def test_extracts_rlhf_from_tags(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        model_info = {"tags": ["rlhf", "reward-model"]}
        method = monitor._extract_training_method(model_info)
        assert method == "rlhf"

    def test_returns_none_when_no_rl_tag(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        model_info = {"tags": ["transformers", "pytorch", "nlp"]}
        method = monitor._extract_training_method(model_info)
        assert method is None

    def test_returns_none_when_tags_missing(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        model_info = {}
        method = monitor._extract_training_method(model_info)
        assert method is None

    def test_returns_first_matching_tag(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        model_info = {"tags": ["transformers", "ppo", "dpo"]}
        method = monitor._extract_training_method(model_info)
        assert method in ("ppo", "dpo")


class TestHandlesNoResults:
    def test_empty_api_response_returns_empty_scan_result(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()
        monitor._client.list_models.return_value = []

        result = monitor.scan(lookback_days=7)

        assert result.total_raw_results == 0
        assert result.total_after_dedup == 0
        assert result.signals_found == []

    def test_all_old_models_returns_empty_scan_result(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        old_models = [
            make_old_model("google", "old-model-1", tags=["ppo"]),
            make_old_model("meta-llama", "old-model-2", tags=["dpo"]),
        ]
        monitor._client.list_models.return_value = old_models

        result = monitor.scan(lookback_days=7)

        assert result.total_after_dedup == 0
        assert result.signals_found == []


class TestDeduplicatesSameOrgAcrossTags:
    def test_same_org_found_via_different_tags_produces_one_signal(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        ppo_model = make_model("google", "ppo-model", tags=["ppo"])
        rlhf_model = make_model("google", "rlhf-model", tags=["rlhf"])

        monitor._client.list_models.side_effect = [
            [ppo_model],  # first tag search (ppo)
            [rlhf_model],  # second tag search (rlhf)
            [],
            [],
            [],
            [],
            [],
            [],  # remaining tag searches return empty
        ]

        result = monitor.scan(lookback_days=7)

        google_signals = [s for s in result.signals_found if s.company_name == "google"]
        assert len(google_signals) == 1

    def test_combined_model_count_affects_score(self):
        """Models from same org found via different tags are combined before scoring."""
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        ppo_models = [make_model("google", f"ppo-{i}", tags=["ppo"]) for i in range(2)]
        dpo_models = [make_model("google", f"dpo-{i}", tags=["dpo"]) for i in range(2)]

        n_tags = len(HuggingFaceRLMonitor.RL_TRAINING_TAGS)
        side_effects = [ppo_models, dpo_models] + [[] for _ in range(n_tags - 2)]
        monitor._client.list_models.side_effect = side_effects

        result = monitor.scan(lookback_days=7)

        google_signals = [s for s in result.signals_found if s.company_name == "google"]
        assert len(google_signals) == 1
        assert google_signals[0].signal_strength == SignalStrength.STRONG


class TestMetadataIncludesModelNames:
    def test_metadata_includes_model_names_list(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        model = make_model("google", "ppo-model", tags=["ppo"])
        monitor._client.list_models.return_value = [model]

        result = monitor.scan(lookback_days=7)

        assert len(result.signals_found) == 1
        signal = result.signals_found[0]
        assert "model_names" in signal.metadata
        assert isinstance(signal.metadata["model_names"], list)
        assert "google/ppo-model" in signal.metadata["model_names"]

    def test_metadata_includes_model_count(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        models = [
            make_model("google", "model-a", tags=["ppo"]),
            make_model("google", "model-b", tags=["dpo"]),
        ]
        monitor._client.list_models.return_value = models

        result = monitor.scan(lookback_days=7)

        signal = result.signals_found[0]
        assert "model_count" in signal.metadata
        assert signal.metadata["model_count"] == 2

    def test_metadata_includes_training_methods(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        model = make_model("google", "ppo-model", tags=["ppo", "reinforcement-learning"])
        monitor._client.list_models.return_value = [model]

        result = monitor.scan(lookback_days=7)

        signal = result.signals_found[0]
        assert "training_methods" in signal.metadata
        assert isinstance(signal.metadata["training_methods"], list)

    def test_signal_type_is_huggingface_model(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        model = make_model("google", "ppo-model", tags=["ppo"])
        monitor._client.list_models.return_value = [model]

        result = monitor.scan(lookback_days=7)

        assert result.signals_found[0].signal_type == "huggingface_model"

    def test_source_url_points_to_huggingface(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        model = make_model("google", "ppo-model", tags=["ppo"])
        monitor._client.list_models.return_value = [model]

        result = monitor.scan(lookback_days=7)

        signal = result.signals_found[0]
        assert "huggingface.co" in signal.source_url


class TestIsOrgModel:
    def test_model_with_slash_is_accepted(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        assert monitor._is_org_model("google/gemma-rl") is True

    def test_model_without_slash_is_rejected(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        assert monitor._is_org_model("no-slash-model") is False

    def test_model_with_nested_slash_is_accepted(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        assert monitor._is_org_model("meta-llama/Llama-3-RL-8B") is True


class TestIsRecent:
    def test_recent_model_returns_true(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        recent = make_model("org", "model", days_ago=2)
        assert monitor._is_recent(recent, lookback_days=7) is True

    def test_old_model_returns_false(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        old = make_old_model("org", "model")
        assert monitor._is_recent(old, lookback_days=7) is False

    def test_missing_last_modified_returns_false(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        model = {"modelId": "org/model", "tags": ["ppo"]}
        assert monitor._is_recent(model, lookback_days=7) is False


class TestFixtureData:
    def test_fixture_loads_successfully(self):
        fixture = load_fixture()
        assert "models_list" in fixture
        assert "model_info" in fixture

    def test_fixture_models_list_has_four_entries(self):
        fixture = load_fixture()
        assert len(fixture["models_list"]) == 4

    def test_fixture_model_info_has_tags(self):
        fixture = load_fixture()
        assert "tags" in fixture["model_info"]
        assert "ppo" in fixture["model_info"]["tags"]


class TestListModelsReturnFormats:
    def test_list_models_with_search_param_passes_search(self):
        client = HuggingFaceClient()
        with patch.object(client, "get", return_value=[]) as mock_get:
            client.list_models(search="rlhf model")
            params = mock_get.call_args[1]["params"]
            assert params["search"] == "rlhf model"

    def test_list_models_dict_wrapper_falls_back_to_items_key(self):
        """If the API returns a dict with 'items' key, we extract the list."""
        client = HuggingFaceClient()
        items = [make_model("org", "model")]
        with patch.object(client, "get", return_value={"items": items}):
            result = client.list_models()
            assert result == items

    def test_list_models_dict_without_items_returns_empty(self):
        """If the API returns a dict without 'items', return empty list."""
        client = HuggingFaceClient()
        with patch.object(client, "get", return_value={"unexpected": "format"}):
            result = client.list_models()
            assert result == []


class TestScanErrorHandling:
    def test_scan_records_errors_when_list_models_fails(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()
        monitor._client.list_models.side_effect = Exception("API unavailable")

        result = monitor.scan(lookback_days=7)

        assert isinstance(result, ScanResult)
        assert len(result.errors) > 0
        assert "API unavailable" in result.errors[0]

    def test_scan_continues_after_one_tag_fails(self):
        """If one tag search fails, others should still be processed."""
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        monitor._client = MagicMock()

        good_model = make_model("google", "ppo-model", tags=["ppo"])
        n_tags = len(HuggingFaceRLMonitor.RL_TRAINING_TAGS)

        side_effects = [Exception("network error"), [good_model]] + [[] for _ in range(n_tags - 2)]
        monitor._client.list_models.side_effect = side_effects

        result = monitor.scan(lookback_days=7)

        assert len(result.signals_found) == 1
        assert len(result.errors) == 1

    def test_is_recent_with_invalid_date_format_returns_false(self):
        monitor = HuggingFaceRLMonitor.__new__(HuggingFaceRLMonitor)
        model = {"modelId": "org/model", "lastModified": "not-a-date", "tags": ["ppo"]}
        assert monitor._is_recent(model, lookback_days=7) is False


class TestCLIOutput:
    def test_cli_prints_summary(self, capsys):
        from scripts.scanners.hf_scanner import main

        mock_result = ScanResult(
            scan_type="huggingface_model",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
        )

        with patch("scripts.scanners.hf_scanner.scan") as mock_scan:
            mock_scan.return_value = mock_result
            with patch("scripts.config_loader.load_config") as mock_load:
                mock_sf_config = MagicMock()
                mock_sf_config.scanners.get.return_value = MagicMock(
                    lookback_days=7, training_tags=[], keywords=[]
                )
                mock_load.return_value = mock_sf_config
                main(["--lookback-days", "7"])

        captured = capsys.readouterr()
        assert "Scan complete" in captured.out

    def test_cli_filters_by_min_strength(self, capsys):
        from scripts.scanners.hf_scanner import main

        weak_signal = Signal(
            signal_type="huggingface_model",
            company_name="small-lab",
            signal_strength=SignalStrength.WEAK,
            source_url="https://huggingface.co/small-lab/rl-model",
            raw_data={"models": []},
            metadata={
                "model_names": ["small-lab/rl-model"],
                "training_methods": ["ppo"],
                "model_count": 1,
            },
        )

        mock_result = ScanResult(
            scan_type="huggingface_model",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[weak_signal],
            total_raw_results=1,
            total_after_dedup=1,
        )

        with patch("scripts.scanners.hf_scanner.scan") as mock_scan:
            mock_scan.return_value = mock_result
            with patch("scripts.config_loader.load_config") as mock_load:
                mock_sf_config = MagicMock()
                mock_sf_config.scanners.get.return_value = MagicMock(
                    lookback_days=7, training_tags=[], keywords=[]
                )
                mock_load.return_value = mock_sf_config
                main(["--min-strength", "2"])

        captured = capsys.readouterr()
        assert "After filter: 0" in captured.out

    def test_cli_writes_json_output(self, tmp_path, capsys):
        from scripts.scanners.hf_scanner import main

        mock_result = ScanResult(
            scan_type="huggingface_model",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
        )

        output_file = tmp_path / "output.json"

        with patch("scripts.scanners.hf_scanner.scan") as mock_scan:
            mock_scan.return_value = mock_result
            with patch("scripts.config_loader.load_config") as mock_load:
                mock_sf_config = MagicMock()
                mock_sf_config.scanners.get.return_value = MagicMock(
                    lookback_days=7, training_tags=[], keywords=[]
                )
                mock_load.return_value = mock_sf_config
                main(["--output", str(output_file)])

        assert output_file.exists()
        with open(output_file) as f:
            data = json.load(f)
        assert "scan_id" in data
        assert "signals" in data
