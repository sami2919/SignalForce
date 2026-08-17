"""Unit tests for email open tracking helpers."""

from __future__ import annotations

import pytest

from scripts.analytics import get_funnel_metrics
from scripts.db import OutcomeEvent, OutreachEvent, create_db_engine, get_session, init_db
from scripts.email_tracker import (
    TRACKING_PIXEL_BYTES,
    build_open_tracking_url,
    build_tracking_pixel_html,
    log_email_open,
    tracking_pixel_response,
)
from scripts.outcome_tracker import create_campaign, log_outcome, log_outreach, log_signal


@pytest.fixture()
def engine():
    eng = create_db_engine("sqlite:///:memory:")
    init_db(eng)
    return eng


@pytest.fixture()
def outreach_id(engine):
    campaign_id = create_campaign(engine, client_name="TrackCo")
    signal_id = log_signal(
        engine,
        campaign_id,
        signal_type="job_posting",
        company_name="Acme",
        signal_strength=3,
    )
    outreach = log_outreach(engine, signal_id, channel="email", template="hiring-signal")
    log_outcome(engine, outreach, outcome_type="delivered")
    return outreach


def test_build_open_tracking_url_and_img(engine, outreach_id):
    url = build_open_tracking_url(
        engine,
        outreach_id,
        base_url="https://track.signalforce.dev/",
    )
    img = build_tracking_pixel_html(
        engine,
        outreach_id,
        base_url="https://track.signalforce.dev/",
    )

    assert url.startswith("https://track.signalforce.dev/track/open.gif?t=")
    assert f'src="{url}"' in img
    assert 'width="1"' in img
    assert 'height="1"' in img


def test_log_email_open_is_idempotent_and_updates_open_rate(engine, outreach_id):
    token = _tracking_token(engine, outreach_id)

    first = log_email_open(
        engine,
        token,
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    second = log_email_open(engine, token)
    metrics = get_funnel_metrics(engine)

    assert first == second
    assert metrics["totals"]["opened"] == 1
    assert metrics["rates"]["open_rate"] == 1.0

    with get_session(engine) as session:
        outcomes = session.query(OutcomeEvent).filter(OutcomeEvent.outcome_type == "opened").all()
        assert len(outcomes) == 1
        assert outcomes[0].external_id == token
        assert "user_agent=pytest" in outcomes[0].notes


def test_invalid_token_returns_pixel_without_recording_open(engine):
    status, headers, body = tracking_pixel_response(engine, "missing-token")

    assert status == 200
    assert headers["Content-Type"] == "image/gif"
    assert body == TRACKING_PIXEL_BYTES
    assert get_funnel_metrics(engine)["totals"]["opened"] == 0


def _tracking_token(engine, outreach_id: int) -> str:
    with get_session(engine) as session:
        outreach = session.query(OutreachEvent).filter(OutreachEvent.id == outreach_id).one()
        assert outreach is not None
        assert outreach.tracking_token
        return str(outreach.tracking_token)
