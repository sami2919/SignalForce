"""Unit tests for SignalForce analytics queries and report rendering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.analytics import (
    get_breakdown,
    get_funnel_metrics,
    get_recommendations,
    get_stale_signals,
)
from scripts.analytics_report import build_report_payload, render_markdown
from scripts.db import create_db_engine, init_db
from scripts.outcome_tracker import create_campaign, log_outcome, log_outreach, log_signal


@pytest.fixture()
def engine():
    eng = create_db_engine("sqlite:///:memory:")
    init_db(eng)
    return eng


@pytest.fixture()
def campaign_id(engine):
    return create_campaign(engine, client_name="AnalyticsCo", icp_description="B2B SaaS")


def test_funnel_metrics_empty_db(engine):
    metrics = get_funnel_metrics(engine)

    assert metrics["totals"]["signals"] == 0
    assert metrics["totals"]["outreach"] == 0
    assert all(value == 0.0 for value in metrics["rates"].values())


def test_funnel_metrics_counts_events_and_rates(engine, campaign_id):
    sig = log_signal(
        engine,
        campaign_id,
        signal_type="github_repo",
        company_name="Acme",
        signal_strength=3,
        icp_grade="A",
        scanner_name="github",
    )
    outreach = log_outreach(engine, sig, channel="email", template="github-signal")
    for outcome_type in ["delivered", "opened", "clicked", "positive_reply", "meeting_scheduled"]:
        log_outcome(engine, outreach, outcome_type=outcome_type)

    metrics = get_funnel_metrics(engine, campaign_id=campaign_id)

    assert metrics["totals"]["signals"] == 1
    assert metrics["totals"]["outreach"] == 1
    assert metrics["totals"]["delivered"] == 1
    assert metrics["totals"]["positive_replies"] == 1
    assert metrics["totals"]["meetings"] == 1
    assert metrics["rates"]["signal_to_outreach"] == 1.0
    assert metrics["rates"]["meeting_rate"] == 1.0


def test_breakdown_by_signal_type_and_template(engine, campaign_id):
    _seed_outreach(
        engine,
        campaign_id,
        signal_type="github_repo",
        template="github-signal",
        positive=True,
    )
    _seed_outreach(
        engine,
        campaign_id,
        signal_type="job_posting",
        template="hiring-signal",
        positive=False,
    )

    by_signal = get_breakdown(engine, group_by="signal_type", campaign_id=campaign_id)
    by_template = get_breakdown(engine, group_by="template_used", campaign_id=campaign_id)

    assert by_signal[0]["value"] == "github_repo"
    assert by_signal[0]["positive_outcomes"] == 2
    assert by_signal[0]["meetings"] == 1
    assert {row["value"] for row in by_template} == {"github-signal", "hiring-signal"}


def test_breakdown_rejects_unsupported_group(engine):
    with pytest.raises(ValueError, match="group_by"):
        get_breakdown(engine, group_by="company_name")


def test_stale_signals_only_returns_unworked_old_signals(engine, campaign_id):
    old = datetime.now(timezone.utc) - timedelta(days=5)
    new = datetime.now(timezone.utc)
    stale_id = log_signal(
        engine,
        campaign_id,
        signal_type="funding_event",
        company_name="OldCo",
        signal_strength=2,
        detected_at=old,
    )
    worked_id = log_signal(
        engine,
        campaign_id,
        signal_type="github_repo",
        company_name="WorkedCo",
        signal_strength=3,
        detected_at=old,
    )
    log_signal(
        engine,
        campaign_id,
        signal_type="job_posting",
        company_name="NewCo",
        signal_strength=3,
        detected_at=new,
    )
    log_outreach(engine, worked_id, channel="email")

    stale = get_stale_signals(engine, campaign_id=campaign_id, older_than_hours=72)

    assert [item["id"] for item in stale] == [stale_id]
    assert stale[0]["company_name"] == "OldCo"


def test_recommendations_flag_best_signal_and_weak_template(engine, campaign_id):
    for _ in range(5):
        _seed_outreach(
            engine,
            campaign_id,
            signal_type="github_repo",
            template="github-signal",
            positive=True,
        )
        _seed_outreach(
            engine,
            campaign_id,
            signal_type="job_posting",
            template="weak-template",
            positive=False,
            icp_grade="C",
        )

    recommendations = get_recommendations(engine, campaign_id=campaign_id, min_sample_size=5)
    messages = [item["message"] for item in recommendations]

    assert any("github_repo is the strongest signal source" in message for message in messages)
    assert any("Template weak-template" in message for message in messages)
    assert any("ICP grade C" in message for message in messages)


def test_report_payload_and_markdown(engine, campaign_id):
    _seed_outreach(
        engine,
        campaign_id,
        signal_type="github_repo",
        template="github-signal",
        positive=True,
    )
    now = datetime.now(timezone.utc)
    payload = build_report_payload(
        engine,
        campaign_id=campaign_id,
        date_range=(now - timedelta(days=1), now + timedelta(days=1)),
        last_days=1,
    )
    markdown = render_markdown(payload)

    assert payload["funnel"]["totals"]["signals"] == 1
    assert "# SignalForce Analytics Report" in markdown
    assert "## By Signal Type" in markdown
    assert "github_repo" in markdown


def _seed_outreach(
    engine,
    campaign_id: int,
    *,
    signal_type: str,
    template: str,
    positive: bool,
    icp_grade: str = "A",
) -> None:
    sig = log_signal(
        engine,
        campaign_id,
        signal_type=signal_type,
        company_name=f"{signal_type} Co",
        signal_strength=3,
        icp_grade=icp_grade,
    )
    outreach = log_outreach(engine, sig, channel="email", template=template)
    log_outcome(engine, outreach, outcome_type="delivered")
    if positive:
        log_outcome(engine, outreach, outcome_type="positive_reply")
        log_outcome(engine, outreach, outcome_type="meeting_scheduled")
    else:
        log_outcome(engine, outreach, outcome_type="opened")
