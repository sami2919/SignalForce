"""Tests for the test-isolation mechanism itself.

These guard the property that the suite does not depend on gitignored local
state (config/, .env). If these fail, the suite's results are a function of
whoever's laptop it ran on.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_config_dir_env_var_overrides_default(monkeypatch) -> None:
    from scripts import config_loader

    monkeypatch.setenv("SIGNALFORCE_CONFIG_DIR", str(REPO_ROOT / "config.example"))
    assert config_loader.config_dir() == REPO_ROOT / "config.example"


def test_config_dir_defaults_to_config_when_unset(monkeypatch) -> None:
    """Production behaviour must be unchanged when the override is absent."""
    from scripts import config_loader

    monkeypatch.delenv("SIGNALFORCE_CONFIG_DIR", raising=False)
    assert config_loader.config_dir() == REPO_ROOT / "config"


def test_load_config_resolves_path_at_call_time(monkeypatch) -> None:
    """The import-time default-arg binding is the bug this guards against."""
    from scripts import config_loader

    monkeypatch.setenv("SIGNALFORCE_CONFIG_DIR", str(REPO_ROOT / "config.example"))
    cfg = config_loader.load_config()
    assert cfg is not None


def test_load_config_still_honours_an_explicit_path(monkeypatch) -> None:
    """Callers passing an explicit path must be unaffected."""
    from scripts import config_loader

    explicit = REPO_ROOT / "config.example" / "config.yaml"
    monkeypatch.delenv("SIGNALFORCE_CONFIG_DIR", raising=False)
    assert config_loader.load_config(explicit) is not None


def test_dotenv_does_not_leak_into_app_config() -> None:
    """A real .env on the developer's machine must not reach AppConfig."""
    from scripts.config import get_config

    cfg = get_config()
    assert cfg.github_token in (None, "")


def test_app_config_cache_is_cleared_between_tests(monkeypatch) -> None:
    """Proves the lru_cache singleton cannot carry state across tests."""
    from scripts.config import get_config

    monkeypatch.setenv("GITHUB_TOKEN", "sentinel-value-abc")
    get_config.cache_clear()
    assert get_config().github_token == "sentinel-value-abc"


def test_agent_email_scanner_is_disabled_by_default_in_config_example(monkeypatch) -> None:
    """Pins the scanner_runner incompatibility: agent_email.scan() requires a
    ledger argument, unlike scanner_runner's `scan(ScannerConfig) -> ScanResult`
    convention (Task 2.2 report). If this ever flips to enabled: true, someone
    must first wire a ledger through scanner_runner's config-only dispatch —
    dispatching it as-is would raise a TypeError for every scheduled run."""
    from scripts import config_loader

    monkeypatch.setenv("SIGNALFORCE_CONFIG_DIR", str(REPO_ROOT / "config.example"))
    cfg = config_loader.load_config()
    agent_email_cfg = cfg.scanners.get("agent_email")
    assert agent_email_cfg is not None
    assert agent_email_cfg.enabled is False


def test_no_real_credentials_visible_to_tests() -> None:
    """Catches the whole class: a Neon password or API key reaching a test."""
    from scripts.config import AppConfig, get_config

    cfg = get_config()
    for field in AppConfig.model_fields:
        value = getattr(cfg, field, None)
        if isinstance(value, str) and value:
            assert not value.startswith(("npg_", "sk-", "ghp_", "github_pat_")), (
                f"{field} contains what looks like a real credential"
            )
