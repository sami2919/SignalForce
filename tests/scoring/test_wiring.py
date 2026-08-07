"""Tests for scripts/scoring/wiring.py.

ADR-0016 is the spec.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from scripts.scoring.wiring import load_latest_account_score, run_scoring_stage
from scripts.storage.models import Account, Base, Score, SignalEvent, Tenant

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


@pytest.fixture
def tenant(session):
    t = Tenant(slug="t1", name="T1")
    session.add(t)
    session.commit()
    return t


def _make_account(session, tenant, domain="acme.com"):
    account = Account(tenant_id=tenant.id, domain=domain, name=domain)
    session.add(account)
    session.commit()
    return account


def _signal(session, tenant, account, *, signal_type, detected_at, confidence=1.0):
    s = SignalEvent(
        tenant_id=tenant.id,
        account_id=account.id,
        signal_type=signal_type,
        payload={},
        detected_at=detected_at,
        confidence=confidence,
    )
    session.add(s)
    session.commit()
    return s


def test_scores_every_account_in_the_tenant(session, tenant):
    _make_account(session, tenant, "a.com")
    _make_account(session, tenant, "b.com")

    report = run_scoring_stage(tenant.id, session, now=NOW)

    assert report.accounts_scored == 2
    assert report.scores_persisted == 2


def test_an_account_with_no_signals_still_gets_a_zero_score(session, tenant):
    _make_account(session, tenant)

    run_scoring_stage(tenant.id, session, now=NOW)

    score = session.execute(select(Score)).scalar_one()
    assert score.score == 0.0


def test_a_real_signal_produces_a_nonzero_score(session, tenant):
    account = _make_account(session, tenant)
    _signal(session, tenant, account, signal_type="hiring", detected_at=NOW - timedelta(days=1))

    run_scoring_stage(tenant.id, session, now=NOW)

    score = session.execute(select(Score)).scalar_one()
    assert score.score > 0.0
    assert score.account_id == account.id


def test_signals_outside_the_window_are_excluded(session, tenant):
    account = _make_account(session, tenant)
    _signal(session, tenant, account, signal_type="hiring", detected_at=NOW - timedelta(days=200))

    run_scoring_stage(tenant.id, session, now=NOW, window_days=90)

    score = session.execute(select(Score)).scalar_one()
    assert score.score == 0.0


def test_signals_inside_a_custom_window_are_included(session, tenant):
    account = _make_account(session, tenant)
    _signal(session, tenant, account, signal_type="hiring", detected_at=NOW - timedelta(days=100))

    run_scoring_stage(tenant.id, session, now=NOW, window_days=120)

    score = session.execute(select(Score)).scalar_one()
    assert score.score > 0.0


def test_repeated_runs_append_new_score_rows_not_upsert(session, tenant):
    account = _make_account(session, tenant)
    _signal(session, tenant, account, signal_type="hiring", detected_at=NOW - timedelta(days=1))

    run_scoring_stage(tenant.id, session, now=NOW)
    run_scoring_stage(tenant.id, session, now=NOW + timedelta(days=1))

    scores = session.execute(select(Score).where(Score.account_id == account.id)).scalars().all()
    assert len(scores) == 2


def test_a_signal_on_one_account_never_leaks_into_another_accounts_score(session, tenant):
    """Mutation-confirmed: removing the account_id filter (keeping only the
    tenant_id filter) survived every other test, since they only ever had
    one account with real signals. Two accounts, only one with a signal,
    are required to distinguish 'scoped correctly' from 'happened to work'."""
    quiet_account = _make_account(session, tenant, "quiet.com")
    loud_account = _make_account(session, tenant, "loud.com")
    _signal(
        session, tenant, loud_account, signal_type="hiring", detected_at=NOW - timedelta(days=1)
    )

    run_scoring_stage(tenant.id, session, now=NOW)

    quiet_score = session.execute(
        select(Score).where(Score.account_id == quiet_account.id)
    ).scalar_one()
    loud_score = session.execute(
        select(Score).where(Score.account_id == loud_account.id)
    ).scalar_one()
    assert quiet_score.score == 0.0
    assert loud_score.score > 0.0


def test_unrecognized_signal_type_gets_a_fallback_weight_not_a_crash(session, tenant):
    account = _make_account(session, tenant)
    _signal(
        session, tenant, account, signal_type="totally_unknown", detected_at=NOW - timedelta(days=1)
    )

    report = run_scoring_stage(tenant.id, session, now=NOW)

    assert report.scores_persisted == 1
    score = session.execute(select(Score)).scalar_one()
    assert score.score > 0.0


def test_agent_email_repo_signal_is_classified_as_icp_not_intent(session, tenant):
    """ADR-0016 Decision 1: agent_email_repo is a fit signal (is_icp=True),
    distinguishing it from hiring/funding/stack_change intent signals --
    checked via the persisted trace, since that's the only externally
    visible record of the classification actually applied."""
    account = _make_account(session, tenant)
    _signal(
        session,
        tenant,
        account,
        signal_type="agent_email_repo",
        detected_at=NOW - timedelta(days=1),
    )

    run_scoring_stage(tenant.id, session, now=NOW)

    score = session.execute(select(Score)).scalar_one()
    assert score.trace["components"][0]["is_icp"] is True


def test_confidence_scales_the_effective_weight(session, tenant):
    account = _make_account(session, tenant)
    _signal(
        session,
        tenant,
        account,
        signal_type="hiring",
        detected_at=NOW - timedelta(days=1),
        confidence=0.5,
    )

    run_scoring_stage(tenant.id, session, now=NOW)

    score = session.execute(select(Score)).scalar_one()
    full_confidence_component = score.trace["components"][0]
    # base_weight for hiring is 0.8; at confidence=0.5 the component's own
    # base_weight (post-multiplication) should be 0.4, not 0.8.
    assert full_confidence_component["base_weight"] == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# load_latest_account_score (ADR-0016 Decision 5)
# ---------------------------------------------------------------------------


def test_load_latest_account_score_returns_zero_for_a_cold_start(session, tenant):
    account = _make_account(session, tenant)
    assert load_latest_account_score(tenant.id, account.id, session) == 0.0


def test_load_latest_account_score_returns_the_most_recent_score(session, tenant):
    account = _make_account(session, tenant)
    session.add(
        Score(
            tenant_id=tenant.id,
            account_id=account.id,
            score=10.0,
            computed_at=NOW - timedelta(days=2),
        )
    )
    session.add(
        Score(
            tenant_id=tenant.id,
            account_id=account.id,
            score=42.0,
            computed_at=NOW - timedelta(days=1),
        )
    )
    session.commit()

    assert load_latest_account_score(tenant.id, account.id, session) == 42.0


def test_load_latest_account_score_never_returns_a_different_accounts_score(session, tenant):
    account_a = _make_account(session, tenant, "a.com")
    account_b = _make_account(session, tenant, "b.com")
    session.add(Score(tenant_id=tenant.id, account_id=account_b.id, score=99.0, computed_at=NOW))
    session.commit()

    assert load_latest_account_score(tenant.id, account_a.id, session) == 0.0
