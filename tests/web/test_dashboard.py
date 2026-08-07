"""Tests for scripts/web/routes_dashboard.py.

ADR-0018 is the spec. The plan's own test references a `seeded_db` fixture
that is never defined anywhere -- built here from scratch, matching this
project's established DB-test pattern (in-memory SQLite, get_session
monkeypatched at the route module, same shape tests/web/test_health.py
already uses for scripts.web.routes_health).
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.storage.models import (
    Account,
    AccountSource,
    Base,
    HoldoutScan,
    Probe,
    ScanRun,
    Score,
    SignalEvent,
    SourceHealthRecord,
    Tenant,
)
from scripts.web.app import create_app
import scripts.web.routes_dashboard as dashboard_module

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


@pytest.fixture
def engine():
    # FastAPI's TestClient runs sync endpoints in a worker thread. A plain
    # sqlite:///:memory: engine hands each thread its own separate,
    # empty in-memory database -- StaticPool + check_same_thread=False
    # pins every connection to the same single in-memory DB regardless of
    # which thread asks for it.
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def _patch_session(monkeypatch, session_factory):
    @contextlib.contextmanager
    def _get_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(dashboard_module, "get_session", _get_session)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def seeded_db(session_factory, monkeypatch):
    """A tenant with two accounts: one fully populated (score, signals,
    sources, a scan run), one never scored (tests Decision 4's "show
    unscored accounts too" behavior)."""
    monkeypatch.setenv("TENANT_SLUG", "acme")
    session = session_factory()

    tenant = Tenant(slug="acme", name="Acme")
    session.add(tenant)
    session.commit()

    loud = Account(tenant_id=tenant.id, domain="loud.com", name="Loud Co")
    quiet = Account(tenant_id=tenant.id, domain="quiet.com", name="Quiet Co")
    session.add_all([loud, quiet])
    session.commit()

    src = AccountSource(
        tenant_id=tenant.id,
        account_id=loud.id,
        source_type="careers",
        url="https://loud.com/careers",
        active=True,
        last_fetched_at=NOW - timedelta(hours=2),
        last_changed_at=NOW - timedelta(hours=2),
    )
    session.add(src)
    session.commit()

    signal = SignalEvent(
        tenant_id=tenant.id,
        account_id=loud.id,
        account_source_id=src.id,
        signal_type="hiring",
        payload={"kind": "added", "field": "jobs"},
        detected_at=NOW - timedelta(hours=1),
        confidence=1.0,
    )
    session.add(signal)
    session.commit()

    score = Score(
        tenant_id=tenant.id,
        account_id=loud.id,
        score=42.5,
        computed_at=NOW,
        trace={"components": []},
    )
    session.add(score)
    session.commit()

    run = ScanRun(
        tenant_id=tenant.id,
        started_at=NOW - timedelta(minutes=5),
        finished_at=NOW,
        status="completed",
        accounts_probed=2,
        sources_probed=2,
        changes_detected=1,
        verify_calls=1,
        signals_emitted=1,
        cost_usd=0.04,
    )
    session.add(run)
    session.commit()

    health = SourceHealthRecord(
        tenant_id=tenant.id,
        source_type="careers",
        run_date=NOW.date(),
        fetch_success_rate=1.0,
        parse_success_rate=None,
        zero_result_rate=None,
        sample_size=2,
    )
    session.add(health)
    session.commit()

    # Holdout ground truth + a matching probe, so compute_recall_for_tenant
    # returns a real, non-null recall number.
    holdout = HoldoutScan(
        tenant_id=tenant.id,
        account_source_id=src.id,
        fetched_at=NOW - timedelta(hours=3),
        content_hash="h1",
        changed=True,
    )
    probe = Probe(
        tenant_id=tenant.id,
        account_source_id=src.id,
        scan_run_id=run.id,
        fetched_at=NOW - timedelta(hours=2),
        content_hash="h1",
        changed=True,
    )
    session.add_all([holdout, probe])
    session.commit()

    ids = {"tenant_id": tenant.id, "loud_id": loud.id, "quiet_id": quiet.id}
    session.close()
    return ids


# ---------------------------------------------------------------------------
# /dashboard
# ---------------------------------------------------------------------------


def test_dashboard_renders(client, seeded_db):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Accounts" in resp.text


def test_dashboard_shows_scored_and_unscored_accounts(client, seeded_db):
    resp = client.get("/dashboard")
    assert "Loud Co" in resp.text
    assert "Quiet Co" in resp.text


def test_dashboard_shows_the_real_score(client, seeded_db):
    resp = client.get("/dashboard")
    assert "42.5" in resp.text


def test_dashboard_with_no_tenant_configured_renders_empty_state(client, monkeypatch):
    monkeypatch.delenv("TENANT_SLUG", raising=False)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Accounts" in resp.text


def test_dashboard_with_a_tenant_but_no_accounts_renders_empty_state(
    client, session_factory, monkeypatch
):
    monkeypatch.setenv("TENANT_SLUG", "empty-co")
    session = session_factory()
    session.add(Tenant(slug="empty-co", name="Empty Co"))
    session.commit()
    session.close()

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "No accounts yet" in resp.text


def test_dashboard_orders_by_score_descending(client, session_factory, monkeypatch):
    """Mutation-confirmed: removing the sort call SURVIVED a first version
    of this test with only two accounts -- SQLite's unordered row scan
    happened to already return them in score-descending order by
    coincidence, regardless of insertion order or its reverse. Three
    accounts inserted in an order that matches NEITHER the correct
    (score-descending) order NOR its reverse forces the distinction:
    inserted Z(50), X(90), Y(10); correct output is X, Z, Y, which isn't
    achievable by insertion order (Z,X,Y) or reverse (Y,X,Z) alone."""
    monkeypatch.setenv("TENANT_SLUG", "rank-co")
    session = session_factory()
    tenant = Tenant(slug="rank-co", name="Rank Co")
    session.add(tenant)
    session.commit()
    acct_z = Account(tenant_id=tenant.id, domain="z.com", name="ZMidScoreCo")
    acct_x = Account(tenant_id=tenant.id, domain="x.com", name="XHighScoreCo")
    acct_y = Account(tenant_id=tenant.id, domain="y.com", name="YLowScoreCo")
    session.add_all([acct_z, acct_x, acct_y])
    session.commit()
    session.add(
        Score(tenant_id=tenant.id, account_id=acct_z.id, score=50.0, computed_at=NOW, trace={})
    )
    session.add(
        Score(tenant_id=tenant.id, account_id=acct_x.id, score=90.0, computed_at=NOW, trace={})
    )
    session.add(
        Score(tenant_id=tenant.id, account_id=acct_y.id, score=10.0, computed_at=NOW, trace={})
    )
    session.commit()
    session.close()

    resp = client.get("/dashboard")
    x_idx = resp.text.index("XHighScoreCo")
    z_idx = resp.text.index("ZMidScoreCo")
    y_idx = resp.text.index("YLowScoreCo")
    assert x_idx < z_idx < y_idx


# ---------------------------------------------------------------------------
# /dashboard/account/{id}
# ---------------------------------------------------------------------------


def test_account_detail_renders(client, seeded_db):
    resp = client.get(f"/dashboard/account/{seeded_db['loud_id']}")
    assert resp.status_code == 200
    assert "Loud Co" in resp.text
    assert "42.5" in resp.text


def test_account_detail_shows_the_zero_out_table(client, seeded_db):
    resp = client.get(f"/dashboard/account/{seeded_db['loud_id']}")
    assert "hiring" in resp.text
    assert "Zero-out analysis" in resp.text


def test_account_detail_for_unknown_account_is_404(client, seeded_db):
    resp = client.get("/dashboard/account/999999")
    assert resp.status_code == 404


def test_account_detail_for_an_account_in_another_tenant_is_404(client, session_factory, seeded_db):
    """Cross-tenant isolation: an account id that exists but belongs to a
    DIFFERENT tenant must 404, not leak."""
    session = session_factory()
    other_tenant = Tenant(slug="other", name="Other")
    session.add(other_tenant)
    session.commit()
    other_account = Account(tenant_id=other_tenant.id, domain="other.com", name="Other Co")
    session.add(other_account)
    session.commit()
    other_account_id = other_account.id
    session.close()

    resp = client.get(f"/dashboard/account/{other_account_id}")
    assert resp.status_code == 404


def test_account_detail_never_shows_a_sibling_accounts_sources_or_signals(
    client, session_factory, seeded_db
):
    """Mutation-confirmed: dropping the account_id filter (keeping only
    tenant_id) on the sources/signal_events queries survived every existing
    test, since seeded_db's only account with real data ('loud') was also
    the only one ever queried. A second, sibling account with ITS OWN
    source AND signal is required to distinguish 'scoped to this account'
    from 'happened to work'."""
    session = session_factory()
    sibling_source = AccountSource(
        tenant_id=seeded_db["tenant_id"],
        account_id=seeded_db["quiet_id"],
        source_type="pricing",
        url="https://quiet.com/pricing",
        active=True,
    )
    session.add(sibling_source)
    session.commit()
    sibling_signal = SignalEvent(
        tenant_id=seeded_db["tenant_id"],
        account_id=seeded_db["quiet_id"],
        account_source_id=sibling_source.id,
        signal_type="funding",
        payload={"kind": "unique-sibling-marker"},
        detected_at=NOW,
        confidence=1.0,
    )
    session.add(sibling_signal)
    session.commit()
    session.close()

    resp = client.get(f"/dashboard/account/{seeded_db['loud_id']}")
    assert "quiet.com/pricing" not in resp.text
    assert "unique-sibling-marker" not in resp.text


# ---------------------------------------------------------------------------
# /dashboard/health
# ---------------------------------------------------------------------------


def test_health_page_shows_recall(client, seeded_db):
    resp = client.get("/dashboard/health")
    assert resp.status_code == 200
    assert "Recall" in resp.text and "Detection lag" in resp.text


def test_health_page_shows_fetch_success_rate(client, seeded_db):
    resp = client.get("/dashboard/health")
    assert "careers" in resp.text
    assert "100%" in resp.text


def test_health_page_marks_zero_result_rate_as_not_yet_available(client, seeded_db):
    """ADR-0011's scope was never expanded -- the dashboard must not fake
    a number for a field nothing populates yet."""
    resp = client.get("/dashboard/health")
    assert "not yet available" in resp.text


def test_health_page_with_no_tenant_renders_empty_state(client, monkeypatch):
    monkeypatch.delenv("TENANT_SLUG", raising=False)
    resp = client.get("/dashboard/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /dashboard/runs
# ---------------------------------------------------------------------------


def test_runs_page_renders(client, seeded_db):
    resp = client.get("/dashboard/runs")
    assert resp.status_code == 200
    assert "completed" in resp.text


def test_runs_page_shows_cost(client, seeded_db):
    resp = client.get("/dashboard/runs")
    assert "0.040" in resp.text


def test_runs_page_shows_the_real_duration(client, seeded_db):
    """Mutation-confirmed: hardcoding duration_s=0 survived every other
    test, since none asserted the actual computed value -- seeded_db's run
    spans exactly 5 minutes (300.0s)."""
    resp = client.get("/dashboard/runs")
    assert "300.0s" in resp.text


def test_runs_page_handles_zero_sources_probed_without_crashing(
    client, session_factory, monkeypatch
):
    """A run that failed before probing anything has sources_probed=0 --
    change_rate must render as unavailable, not raise ZeroDivisionError."""
    monkeypatch.setenv("TENANT_SLUG", "zero-co")
    session = session_factory()
    tenant = Tenant(slug="zero-co", name="Zero Co")
    session.add(tenant)
    session.commit()
    session.add(
        ScanRun(
            tenant_id=tenant.id,
            started_at=NOW,
            finished_at=NOW,
            status="failed",
            accounts_probed=0,
            sources_probed=0,
            changes_detected=0,
        )
    )
    session.commit()
    session.close()

    resp = client.get("/dashboard/runs")
    assert resp.status_code == 200
    assert "failed" in resp.text


def test_runs_page_with_no_runs_renders_empty_state(client, session_factory, monkeypatch):
    monkeypatch.setenv("TENANT_SLUG", "empty-co")
    session = session_factory()
    session.add(Tenant(slug="empty-co", name="Empty Co"))
    session.commit()
    session.close()

    resp = client.get("/dashboard/runs")
    assert resp.status_code == 200
    assert "No runs yet" in resp.text
