from pathlib import Path

import pytest
from scripts.models import Signal, SignalStrength, ICPScore
from scripts.signal_aggregator import aggregate_and_score
from scripts.config_loader import load_config


def _make_signal(
    company: str, signal_type: str, strength: SignalStrength, skills: list[str]
) -> Signal:
    return Signal(
        signal_type=signal_type,
        company_name=company,
        signal_strength=strength,
        source_url="https://example.com",
        raw_data={"postings": [{"snippet": " ".join(skills)}]},
        metadata={"skills_mentioned": skills},
    )


_EXAMPLE_CONFIG = Path(__file__).parent.parent / "examples" / "map-migration" / "config.yaml"


@pytest.fixture
def config():
    return load_config(_EXAMPLE_CONFIG)


def test_aggregate_groups_by_company(config):
    """Signals from the same company should be merged into one ScoredCompany."""
    signals = [
        _make_signal("Acme", "job_posting", SignalStrength.STRONG, ["Marketo", "Salesforce"]),
        _make_signal("Acme", "github_repo", SignalStrength.MODERATE, ["Hightouch"]),
        _make_signal("Beta Inc", "job_posting", SignalStrength.WEAK, []),
    ]
    results = aggregate_and_score(signals, config)
    companies = [r.company_name for r in results]
    assert "Acme" in companies
    assert "Beta Inc" in companies
    acme = next(r for r in results if r.company_name == "Acme")
    assert acme.scoring_result.signal_count == 2


def test_marketo_salesforce_company_gets_b_or_a(config):
    """A company with Marketo+Salesforce job posting should be graded B or A."""
    signals = [
        _make_signal(
            "Marketo Corp",
            "job_posting",
            SignalStrength.MODERATE,
            ["Marketo", "Salesforce", "Hightouch"],
        ),
    ]
    results = aggregate_and_score(signals, config)
    assert len(results) == 1
    grade = results[0].scoring_result.icp_score
    assert grade in (ICPScore.A, ICPScore.B), f"Expected A or B, got {grade}"


def test_results_sorted_by_combined_score_descending(config):
    """Results should be sorted highest combined score first."""
    signals = [
        _make_signal("Weak Co", "job_posting", SignalStrength.WEAK, []),
        _make_signal(
            "Strong Co",
            "job_posting",
            SignalStrength.STRONG,
            ["Marketo", "Salesforce", "Hightouch"],
        ),
    ]
    results = aggregate_and_score(signals, config)
    scores = [r.scoring_result.combined_score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_empty_signals_returns_empty(config):
    results = aggregate_and_score([], config)
    assert results == []


def test_scored_company_has_expected_fields(config):
    """ScoredCompany must expose company_name, signals, icp_fit, scoring_result."""
    signals = [_make_signal("Test Co", "job_posting", SignalStrength.MODERATE, ["Marketo"])]
    results = aggregate_and_score(signals, config)
    r = results[0]
    assert hasattr(r, "company_name")
    assert hasattr(r, "signals")
    assert hasattr(r, "icp_fit")
    assert hasattr(r, "scoring_result")
    assert isinstance(r.icp_fit, float)


def test_blocklisted_company_excluded(config):
    """Companies in the blocklist should be dropped before scoring."""
    from scripts.config_loader import FiltersConfig

    config_with_blocklist = config.model_copy(
        update={"filters": FiltersConfig(company_blocklist=["Anthropic", "Databricks"])}
    )
    signals = [
        _make_signal("Anthropic", "job_posting", SignalStrength.MODERATE, ["Marketo"]),
        _make_signal("Vanta", "job_posting", SignalStrength.MODERATE, ["HubSpot"]),
    ]
    results = aggregate_and_score(signals, config_with_blocklist)
    companies = [r.company_name for r in results]
    assert "Anthropic" not in companies
    assert "Vanta" in companies


def test_blocklist_is_case_insensitive(config):
    """Blocklist matching must normalize case — scanner output can be lowercase."""
    from scripts.config_loader import FiltersConfig

    config_with_blocklist = config.model_copy(
        update={"filters": FiltersConfig(company_blocklist=["Anthropic"])}
    )
    signals = [
        _make_signal("anthropic", "job_posting", SignalStrength.MODERATE, ["Marketo"]),
    ]
    results = aggregate_and_score(signals, config_with_blocklist)
    assert results == []


def test_empty_blocklist_filters_nothing(config):
    """An empty blocklist is the default and must not drop anything."""
    signals = [
        _make_signal("TestCompany", "job_posting", SignalStrength.MODERATE, ["Marketo"]),
    ]
    results = aggregate_and_score(signals, config)
    assert len(results) == 1
