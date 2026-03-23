"""Tests for playbook loading, validation, and lookup."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from scripts.config_loader import load_playbooks, lookup_playbooks_by_signal_type
from scripts.models import PlaybookEntry

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_VALID = _FIXTURES / "playbooks.yaml"


class TestLoadPlaybooks:
    def test_loads_valid_playbook_yaml(self) -> None:
        playbooks = load_playbooks(_VALID)
        assert len(playbooks) == 3
        assert all(isinstance(p, PlaybookEntry) for p in playbooks)

    def test_playbook_fields_populated(self) -> None:
        playbooks = load_playbooks(_VALID)
        first = playbooks[0]
        assert first.signal_type == "github_repo"
        assert first.angle_name == "build-vs-buy"
        assert "{{repo_name}}" in first.email_opener
        assert "{{customer_name}}" in first.proof_point_template

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No playbooks found"):
            load_playbooks(tmp_path / "nonexistent.yaml")

    def test_raises_on_bad_yaml(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(": invalid: yaml: {{{}}")
        with pytest.raises(yaml.YAMLError):
            load_playbooks(bad)

    def test_returns_empty_list_for_no_entries(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.yaml"
        empty.write_text("playbooks: []")
        playbooks = load_playbooks(empty)
        assert playbooks == []


class TestPlaybookValidationErrors:
    def test_missing_signal_type(self, tmp_path: Path) -> None:
        data = {
            "playbooks": [
                {
                    "trigger_pattern": "some pattern",
                    "angle_name": "test",
                    "angle_description": "test desc",
                    "email_opener": "opener",
                    "proof_point_template": "proof",
                }
            ]
        }
        path = tmp_path / "missing_signal.yaml"
        path.write_text(yaml.dump(data))
        with pytest.raises(ValidationError, match="signal_type"):
            load_playbooks(path)

    def test_missing_angle_name(self, tmp_path: Path) -> None:
        data = {
            "playbooks": [
                {
                    "signal_type": "github_repo",
                    "trigger_pattern": "some pattern",
                    "angle_description": "test desc",
                    "email_opener": "opener",
                    "proof_point_template": "proof",
                }
            ]
        }
        path = tmp_path / "missing_angle.yaml"
        path.write_text(yaml.dump(data))
        with pytest.raises(ValidationError, match="angle_name"):
            load_playbooks(path)

    def test_missing_email_opener(self, tmp_path: Path) -> None:
        data = {
            "playbooks": [
                {
                    "signal_type": "github_repo",
                    "trigger_pattern": "some pattern",
                    "angle_name": "test",
                    "angle_description": "test desc",
                    "proof_point_template": "proof",
                }
            ]
        }
        path = tmp_path / "missing_opener.yaml"
        path.write_text(yaml.dump(data))
        with pytest.raises(ValidationError, match="email_opener"):
            load_playbooks(path)

    def test_missing_multiple_fields(self, tmp_path: Path) -> None:
        data = {"playbooks": [{"signal_type": "github_repo"}]}
        path = tmp_path / "missing_many.yaml"
        path.write_text(yaml.dump(data))
        with pytest.raises(ValidationError):
            load_playbooks(path)


class TestLookupBySignalType:
    def test_returns_matching_entries(self) -> None:
        playbooks = load_playbooks(_VALID)
        results = lookup_playbooks_by_signal_type(playbooks, "github_repo")
        assert len(results) == 1
        assert all(p.signal_type == "github_repo" for p in results)

    def test_returns_multiple_matches(self) -> None:
        playbooks = load_playbooks(_VALID)
        # Fixture has github_repo, arxiv_paper, job_posting — one each
        all_types = {p.signal_type for p in playbooks}
        assert all_types == {"github_repo", "arxiv_paper", "job_posting"}

    def test_unknown_signal_type_returns_empty(self) -> None:
        playbooks = load_playbooks(_VALID)
        results = lookup_playbooks_by_signal_type(playbooks, "unknown_type")
        assert results == []

    def test_empty_playbooks_returns_empty(self) -> None:
        results = lookup_playbooks_by_signal_type([], "github_repo")
        assert results == []


class TestPlaybookEntryModel:
    def test_frozen(self) -> None:
        entry = PlaybookEntry(
            signal_type="github_repo",
            trigger_pattern="test",
            angle_name="test",
            angle_description="test",
            email_opener="test",
            proof_point_template="test",
        )
        with pytest.raises(ValidationError):
            entry.signal_type = "changed"  # type: ignore[misc]
