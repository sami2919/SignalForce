"""Tests for scripts/registry/store.py.

The important one: test_store_resolution_does_not_touch_last_hash. Resolution
runs independently of the watch pass (e.g. re-resolution after a source goes
dead), and it must never reset the watch state of a source that already has
one — clobbering last_hash would make the next watch pass report a spurious
change for every re-resolved source.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.registry.models import ResolutionReport, ResolvedSource, SourceAttempt
from scripts.registry.store import ensure_account, ensure_tenant, store_resolution
from scripts.storage.models import AccountSource, Base, Tenant


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)()


def test_ensure_tenant_creates_then_returns_same_id(session):
    id1 = ensure_tenant("agentmail", "AgentMail", session)
    id2 = ensure_tenant("agentmail", "AgentMail", session)
    assert id1 == id2
    assert session.query(Tenant).count() == 1


def test_ensure_account_is_idempotent_per_tenant(session):
    tenant_id = ensure_tenant("agentmail", "AgentMail", session)
    a1 = ensure_account(tenant_id, "acme.com", session)
    a2 = ensure_account(tenant_id, "acme.com", session)
    assert a1 == a2


def test_same_domain_under_two_tenants_is_allowed(session):
    t1 = ensure_tenant("t1", "T1", session)
    t2 = ensure_tenant("t2", "T2", session)
    a1 = ensure_account(t1, "acme.com", session)
    a2 = ensure_account(t2, "acme.com", session)
    assert a1 != a2


def _report(domain: str = "acme.com", url: str = "https://acme.com/careers") -> ResolutionReport:
    return ResolutionReport(
        domain=domain,
        sources=[
            ResolvedSource(source_type="careers", url=url, method="heuristic", confidence=0.9)
        ],
        attempts=[SourceAttempt(source_type="careers", outcome="resolved", url=url, detail="")],
        homepage_reachable=True,
    )


def test_store_resolution_creates_account_source_rows(session):
    tenant_id = ensure_tenant("agentmail", "AgentMail", session)
    result = store_resolution(tenant_id, _report(), session)
    assert result.created == 1
    assert result.updated == 0
    assert result.deactivated == 0

    row = session.query(AccountSource).one()
    assert row.source_type == "careers"
    assert row.url == "https://acme.com/careers"
    assert row.tenant_id == tenant_id


def test_store_resolution_is_idempotent(session):
    tenant_id = ensure_tenant("agentmail", "AgentMail", session)
    store_resolution(tenant_id, _report(), session)
    result = store_resolution(tenant_id, _report(), session)
    assert result.created == 0
    assert result.updated == 1
    assert session.query(AccountSource).count() == 1


def test_store_resolution_updates_url_when_it_changed(session):
    tenant_id = ensure_tenant("agentmail", "AgentMail", session)
    store_resolution(tenant_id, _report(url="https://acme.com/careers"), session)
    result = store_resolution(
        tenant_id, _report(url="https://acme.com/jobs.greenhouse.io"), session
    )
    assert result.updated == 1
    row = session.query(AccountSource).one()
    assert row.url == "https://acme.com/jobs.greenhouse.io"


def test_store_resolution_reactivates_a_previously_dead_source(session):
    tenant_id = ensure_tenant("agentmail", "AgentMail", session)
    store_resolution(tenant_id, _report(), session)

    row = session.query(AccountSource).one()
    row.active = False
    row.consecutive_failures = 7
    session.commit()

    store_resolution(tenant_id, _report(), session)

    row = session.query(AccountSource).one()
    assert row.active is True
    assert row.consecutive_failures == 0


def test_store_resolution_does_not_touch_last_hash(session):
    """The heart of this test file.

    Re-resolving an account must not reset last_hash, last_fetched_at, or
    consecutive_failures on a source that already exists and is being
    watched — that would make the next watch pass report a spurious change
    for every re-resolved source.
    """
    tenant_id = ensure_tenant("agentmail", "AgentMail", session)
    store_resolution(tenant_id, _report(), session)

    row = session.query(AccountSource).one()
    row.last_hash = "deadbeef"
    fetched_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row.last_fetched_at = fetched_at
    row.consecutive_failures = 2
    session.commit()

    store_resolution(tenant_id, _report(), session)

    row = session.query(AccountSource).one()
    assert row.last_hash == "deadbeef"
    # SQLite drops tzinfo on round-trip; compare naive.
    assert row.last_fetched_at == fetched_at.replace(tzinfo=None)
    assert row.consecutive_failures == 2


def test_unresolved_source_types_create_no_rows(session):
    tenant_id = ensure_tenant("agentmail", "AgentMail", session)
    report = ResolutionReport(
        domain="acme.com",
        sources=[],
        attempts=[SourceAttempt(source_type="careers", outcome="not_found", url=None, detail="")],
        homepage_reachable=True,
    )
    result = store_resolution(tenant_id, report, session)
    assert result.created == 0
    assert session.query(AccountSource).count() == 0
