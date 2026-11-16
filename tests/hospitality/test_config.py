from pathlib import Path

from scripts.hospitality.config import load_config


def test_load_config_reads_priors() -> None:
    cfg = load_config(Path("examples/magic-loyalist/hospitality.yaml"))
    assert cfg.priors["license_pending"].precision == 0.30
    assert cfg.window_pre_days == 183
    assert cfg.priors["private_events"].half_life_days == 120
    assert cfg.nyc_counties[0] == "New York"


def test_example_config_cites_no_gitignored_file() -> None:
    """M15: the committed example config is read by other users; it must not point at
    `.superpowers/` (gitignored) or other local-only paths."""
    from scripts.hospitality.config import DEFAULT_CONFIG_PATH

    text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
    assert ".superpowers" not in text and "data/magic" not in text and "out/magic" not in text
