"""Tests for config loading and validation."""

from pathlib import Path
import pytest
import yaml

from scripts.config_loader import (
    load_config,
    SignalForceConfig,
)

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_VALID = _FIXTURES / "sample_config.yaml"
_BAD = _FIXTURES / "bad_config.yaml"


class TestLoadConfig:
    def test_loads_valid_config(self) -> None:
        config = load_config(_VALID)
        assert isinstance(config, SignalForceConfig)
        assert config.company.name == "Test Corp"

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No config found"):
            load_config(tmp_path / "nonexistent.yaml")

    def test_raises_on_bad_yaml(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(": invalid: yaml: {{{}}")
        with pytest.raises(yaml.YAMLError):
            load_config(bad)

    def test_raises_on_schema_violation(self) -> None:
        with pytest.raises(Exception):  # pydantic.ValidationError
            load_config(_BAD)

    def test_ignores_extra_fields(self, tmp_path: Path) -> None:
        """Forward compatibility: unknown fields are silently ignored."""
        data = yaml.safe_load(_VALID.read_text())
        data["future_field"] = "ignored"
        data["scanners"]["github"]["future_param"] = "also ignored"
        p = tmp_path / "extra.yaml"
        p.write_text(yaml.dump(data))
        config = load_config(p)
        assert config.company.name == "Test Corp"


class TestScannerConfig:
    def test_enabled_scanner(self) -> None:
        config = load_config(_VALID)
        assert config.scanners["github"].enabled is True
        assert config.scanners["github"].topics == ["test-topic"]

    def test_disabled_scanner(self) -> None:
        config = load_config(_VALID)
        assert config.scanners["arxiv"].enabled is False

    def test_defaults(self) -> None:
        config = load_config(_VALID)
        gh = config.scanners["github"]
        assert gh.lookback_days == 7
        assert gh.custom_params == {}


class TestScoringConfig:
    def test_weights_loaded(self) -> None:
        config = load_config(_VALID)
        assert config.scoring.intent_weights["github"] == 2.5
        assert config.scoring.half_lives_days["arxiv"] == 10

    def test_defaults(self) -> None:
        config = load_config(_VALID)
        assert config.scoring.icp_weight == 0.4
        assert config.scoring.intent_weight == 0.6

    def test_grade_thresholds(self) -> None:
        config = load_config(_VALID)
        assert config.scoring.grade_thresholds["A"] == 8.0
