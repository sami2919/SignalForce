"""Every shipped example vertical must load through the real config loader.

This backs the README claim that SignalForce is config-driven: pointing it at a
new market is a YAML change, and each example proves it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.config_loader import load_config

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
VERTICALS = sorted(p.parent.name for p in EXAMPLES_DIR.glob("*/config.yaml"))


def test_expected_verticals_are_present() -> None:
    assert {"cybersecurity", "data-infra", "devtools", "rl-infrastructure", "inference-infra"} <= set(
        VERTICALS
    )


@pytest.mark.parametrize("vertical", VERTICALS)
def test_vertical_config_loads(vertical: str) -> None:
    config = load_config(EXAMPLES_DIR / vertical / "config.yaml")

    assert config.company.name
    assert config.icp.tiers, "a vertical needs at least one ICP tier"
    assert config.icp.target_titles
    assert any(s.enabled for s in config.scanners.values()), "at least one scanner enabled"
    assert 0 < config.scoring.icp_weight < 1
    assert config.scoring.icp_weight + config.scoring.intent_weight == pytest.approx(1.0)
