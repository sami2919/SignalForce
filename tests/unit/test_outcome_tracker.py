"""Unit tests for scripts/outcome_tracker.py — full feedback loop tracking."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from scripts.db import create_db_engine, init_db
from scripts.outcome_tracker import (
    create_campaign,
    get_best_performing_signals,
    get_conversion_rates,
    log_outcome,
    log_outreach,
    log_signal,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    """In-memory SQLite engine with tables ready."""
    eng = create_db_engine("sqlite:///:memory:")
    init_db(eng)
    return eng


@pytest.fixture()
def campaign_id(engine):
    """A default campaign for tests."""
    return create_campaign(engine, client_name="TestCo", icp_description="ML infra teams")


# ---------------------------------------------------------------------------
# Full feedback loop
# ---------------------------------------------------------------------------


def test_full_feedback_loop(engine, campaign_id):
    """signal -> outreach -> reply -> meeting flows end-to-end."""
    sig_id = log_signal(
        engine,
        campaign_id,
        signal_type="github_repo",
        company_name="Acme",
        company_domain="acme.com",
        signal_strength=3,
        source_url="https://github.com/acme/project",
    )
    assert isinstance(sig_id, int)

    outreach_id = log_outreach(
        engine,
        sig_id,
        channel="email",
        template="cold-intro-v2",
        angle="open-source-contributor",
    )
    assert isinstance(outreach_id, int)

    reply_id = log_outcome(engine, outreach_id, outcome_type="reply", notes="Interested")
    assert isinstance(reply_id, int)

    meeting_id = log_outcome(
        engine, outreach_id, outcome_type="meeting_scheduled", notes="Demo next Tuesday"
    )
    assert isinstance(meeting_id, int)


# ---------------------------------------------------------------------------
# Conversion rate calculations
# ---------------------------------------------------------------------------


def test_conversion_rates_basic(engine, campaign_id):
    """Conversion rates are calculated correctly for a simple funnel."""
    # 2 signals, 2 outreach, 1 reply, 1 meeting
    sig1 = log_signal(
        engine, campaign_id, signal_type="github_repo",
        company_name="A", signal_strength=3,
    )
    sig2 = log_signal(
        engine, campaign_id, signal_type="github_repo",
        company_name="B", signal_strength=2,
    )

    out1 = log_outreach(engine, sig1, channel="email")
    out2 = log_outreach(engine, sig2, channel="email")

    log_outcome(engine, out1, outcome_type="reply")
    log_outcome(engine, out1, outcome_type="meeting_scheduled")

    rates = get_conversion_rates(engine, campaign_id=campaign_id)

    assert rates["total_signals"] == 2
    assert rates["total_outreach"] == 2
    assert rates["outcomes"]["reply"] == 1
    assert rates["outcomes"]["meeting_scheduled"] == 1
    assert rates["rates"]["signal_to_outreach"] == 1.0
    assert rates["rates"]["outreach_to_reply"] == 0.5  # 1 reply / 2 outreach
    assert rates["rates"]["outreach_to_meeting"] == 0.5


def test_conversion_rates_empty_db(engine):
    """Empty database returns zeros, not errors."""
    rates = get_conversion_rates(engine)

    assert rates["total_signals"] == 0
    assert rates["total_outreach"] == 0
    for count in rates["outcomes"].values():
        assert count == 0
    for rate in rates["rates"].values():
        assert rate == 0.0


def test_conversion_rates_filter_by_signal_type(engine, campaign_id):
    """Filtering by signal_type narrows results correctly."""
    sig_gh = log_signal(
        engine, campaign_id, signal_type="github_repo",
        company_name="A", signal_strength=3,
    )
    sig_arxiv = log_signal(
        engine, campaign_id, signal_type="arxiv_paper",
        company_name="B", signal_strength=2,
    )

    out_gh = log_outreach(engine, sig_gh, channel="email")
    out_arxiv = log_outreach(engine, sig_arxiv, channel="email")

    log_outcome(engine, out_gh, outcome_type="positive_reply")
    log_outcome(engine, out_arxiv, outcome_type="reply")

    rates_gh = get_conversion_rates(engine, signal_type="github_repo")
    assert rates_gh["total_signals"] == 1
    assert rates_gh["outcomes"]["positive_reply"] == 1
    assert rates_gh["outcomes"]["reply"] == 0

    rates_arxiv = get_conversion_rates(engine, signal_type="arxiv_paper")
    assert rates_arxiv["total_signals"] == 1
    assert rates_arxiv["outcomes"]["reply"] == 1
    assert rates_arxiv["outcomes"]["positive_reply"] == 0


def test_conversion_rates_filter_by_campaign(engine):
    """Filtering by campaign_id isolates campaigns."""
    c1 = create_campaign(engine, client_name="CampA")
    c2 = create_campaign(engine, client_name="CampB")

    sig1 = log_signal(engine, c1, signal_type="github_repo", company_name="A", signal_strength=3)
    sig2 = log_signal(engine, c2, signal_type="github_repo", company_name="B", signal_strength=2)

    out1 = log_outreach(engine, sig1, channel="email")
    out2 = log_outreach(engine, sig2, channel="email")

    log_outcome(engine, out1, outcome_type="deal_closed")

    rates_c1 = get_conversion_rates(engine, campaign_id=c1)
    assert rates_c1["total_signals"] == 1
    assert rates_c1["outcomes"]["deal_closed"] == 1

    rates_c2 = get_conversion_rates(engine, campaign_id=c2)
    assert rates_c2["total_signals"] == 1
    assert rates_c2["outcomes"]["deal_closed"] == 0


def test_conversion_rates_filter_by_date_range(engine, campaign_id):
    """Date range filter works correctly."""
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=30)

    log_signal(
        engine, campaign_id, signal_type="github_repo",
        company_name="Old", signal_strength=2, detected_at=old,
    )
    log_signal(
        engine, campaign_id, signal_type="github_repo",
        company_name="New", signal_strength=3, detected_at=now,
    )

    rates = get_conversion_rates(
        engine,
        date_range=(now - timedelta(days=1), now + timedelta(days=1)),
    )
    assert rates["total_signals"] == 1


# ---------------------------------------------------------------------------
# Best performing signals
# ---------------------------------------------------------------------------


def test_best_performing_signals(engine, campaign_id):
    """Signals are ranked by positive outcome count."""
    # github_repo: 2 signals, 2 positive outcomes
    for name in ("A", "B"):
        sig = log_signal(
            engine, campaign_id, signal_type="github_repo",
            company_name=name, signal_strength=3,
        )
        out = log_outreach(engine, sig, channel="email")
        log_outcome(engine, out, outcome_type="positive_reply")

    # arxiv_paper: 2 signals, 0 positive outcomes (only plain replies)
    for name in ("C", "D"):
        sig = log_signal(
            engine, campaign_id, signal_type="arxiv_paper",
            company_name=name, signal_strength=2,
        )
        out = log_outreach(engine, sig, channel="email")
        log_outcome(engine, out, outcome_type="reply")

    results = get_best_performing_signals(engine, campaign_id=campaign_id)

    assert len(results) == 2
    assert results[0]["signal_type"] == "github_repo"
    assert results[0]["positive_outcomes"] == 2
    assert results[0]["conversion_rate"] == 1.0
    assert results[1]["signal_type"] == "arxiv_paper"
    assert results[1]["positive_outcomes"] == 0


def test_best_performing_signals_empty_db(engine):
    """Empty database returns empty list, not an error."""
    results = get_best_performing_signals(engine)
    assert results == []


def test_best_performing_signals_limit(engine, campaign_id):
    """Limit parameter restricts result count."""
    for i in range(5):
        sig = log_signal(
            engine, campaign_id, signal_type=f"type_{i}",
            company_name=f"Co{i}", signal_strength=2,
        )

    results = get_best_performing_signals(engine, limit=3)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_invalid_channel_raises(engine, campaign_id):
    """log_outreach rejects invalid channel values."""
    sig = log_signal(
        engine, campaign_id, signal_type="github_repo",
        company_name="A", signal_strength=3,
    )
    with pytest.raises(ValueError, match="channel"):
        log_outreach(engine, sig, channel="carrier_pigeon")


def test_invalid_outcome_type_raises(engine, campaign_id):
    """log_outcome rejects invalid outcome_type values."""
    sig = log_signal(
        engine, campaign_id, signal_type="github_repo",
        company_name="A", signal_strength=3,
    )
    out = log_outreach(engine, sig, channel="email")
    with pytest.raises(ValueError, match="outcome_type"):
        log_outcome(engine, out, outcome_type="magic")


# ---------------------------------------------------------------------------
# Duplicate / multiple signals for same company
# ---------------------------------------------------------------------------


def test_multiple_signals_same_company(engine, campaign_id):
    """Multiple signals for the same company are tracked independently."""
    sig1 = log_signal(
        engine, campaign_id, signal_type="github_repo",
        company_name="Acme", signal_strength=3,
    )
    sig2 = log_signal(
        engine, campaign_id, signal_type="arxiv_paper",
        company_name="Acme", signal_strength=2,
    )
    assert sig1 != sig2

    rates = get_conversion_rates(engine, campaign_id=campaign_id)
    assert rates["total_signals"] == 2
