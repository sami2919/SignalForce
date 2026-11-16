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


def test_thresholds_and_priors_live_in_config_and_are_required() -> None:
    """M1/M2: event priors, the in-window threshold, the judge pass score, the email
    confidence floor and the benchmark knobs come from config; omitting one fails to load."""
    import pytest
    from pydantic import ValidationError

    from scripts.hospitality.config import HospitalityConfig

    cfg = load_config()
    assert cfg.events.attend_prior["speaker"] == 0.95
    assert cfg.events.meeting_rate_prior["magic_dinner"] == 0.50
    assert cfg.events.in_window_p == 0.30
    assert cfg.events.unmatched_priority == 0.05
    assert cfg.judge_pass_score == 7.0 and cfg.min_email_confidence == 70.0
    assert (cfg.benchmark.runs, cfg.benchmark.max_searches, cfg.benchmark.k) == (3, 20, 50)
    assert cfg.benchmark.web_search_usd_each == 0.01
    raw = cfg.model_dump()
    for key in (
        "events",
        "judge_pass_score",
        "min_email_confidence",
        "benchmark",
        "recall_lead_cap_days",
    ):
        with pytest.raises(ValidationError):
            HospitalityConfig.model_validate({k: v for k, v in raw.items() if k != key})


def test_no_threshold_constants_left_in_the_modules() -> None:
    import scripts.hospitality.cli as cli_mod
    from scripts.hospitality.contacts import waterfall
    from scripts.hospitality.events import rank
    from scripts.hospitality.messages import judge

    for mod, names in (
        (rank, ("ATTEND_PRIOR", "MEETING_RATE_PRIOR", "IN_WINDOW_P", "UNMATCHED_PRIORITY")),
        (judge, ("PASS_SCORE",)),
        (waterfall, ("MIN_EMAIL_CONFIDENCE",)),
        (
            cli_mod,
            ("BENCHMARK_RUNS", "BENCHMARK_MAX_SEARCHES", "BENCHMARK_K", "WEB_SEARCH_USD_EACH"),
        ),
    ):
        for name in names:
            assert not hasattr(mod, name), f"{mod.__name__}.{name}"
