"""Global test isolation.

The suite must not depend on gitignored local state. Two things leak without
these fixtures:

  1. .env  — scripts/config.py calls load_dotenv() at import time AND declares
             env_file=".env" on AppConfig, so real credentials reach tests.
             get_config() is lru_cached, so the first caller poisons the rest.
  2. config/ — gitignored, so a fresh clone or CI runner has no config.yaml.

Both fixtures are autouse: isolation you have to remember to opt into is
isolation that will be forgotten.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

REPO_ROOT = Path(__file__).resolve().parent
EXAMPLE_CONFIG_DIR = REPO_ROOT / "config.example"


@pytest.fixture(autouse=True)
def isolate_env_from_dotenv(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Stop a developer's real .env from reaching AppConfig."""
    from scripts.config import AppConfig, get_config

    # Disable pydantic-settings' own .env read.
    monkeypatch.setitem(AppConfig.model_config, "env_file", None)

    # load_dotenv() already pushed values into os.environ at import time;
    # remove every key AppConfig would read.
    for field_name in AppConfig.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)

    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture(autouse=True)
def use_example_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point config loading at committed example config, not gitignored config/."""
    monkeypatch.setenv("SIGNALFORCE_CONFIG_DIR", str(EXAMPLE_CONFIG_DIR))
