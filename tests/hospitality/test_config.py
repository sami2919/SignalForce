from pathlib import Path

from scripts.hospitality.config import load_config


def test_load_config_reads_priors() -> None:
    cfg = load_config(Path("examples/magic-loyalist/hospitality.yaml"))
    assert cfg.priors["license_pending"].precision == 0.30
    assert cfg.window_pre_days == 183
    assert cfg.priors["private_events"].half_life_days == 120
    assert cfg.nyc_counties[0] == "New York"
