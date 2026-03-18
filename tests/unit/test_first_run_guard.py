"""Tests for first-run onboarding guard."""

from pathlib import Path
import pytest

from scripts.config_loader import check_config_exists


class TestCheckConfigExists:
    def test_exits_when_dir_missing(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            check_config_exists(tmp_path / "nonexistent")

    def test_exits_when_yaml_missing(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        with pytest.raises(SystemExit):
            check_config_exists(config_dir)

    def test_passes_when_config_exists(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "config.yaml").write_text("company: {}")
        check_config_exists(config_dir)
