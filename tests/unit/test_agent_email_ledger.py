"""Tests for scripts/scanners/agent_email_ledger.py — the concrete SQLAlchemy
LedgerPort implementation. Run against in-memory SQLite (CLAUDE.md: never
hit real APIs/DBs from the suite). Kept separate from the scanner's own
mocked unit tests per the Task 2.2 brief ("tested separately").
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.scanners.agent_email_ledger import SqlAlchemyRepoLedger
from scripts.scanners.agent_email_scanner import RepoObservationRecord
from scripts.storage.models import Base, RepoObservation, Tenant


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


@pytest.fixture
def tenant_id(session):
    tenant = Tenant(slug="agentmail", name="AgentMail")
    session.add(tenant)
    session.commit()
    return tenant.id


def _record(full_name: str, archived: bool = False) -> RepoObservationRecord:
    return RepoObservationRecord(
        full_name=full_name,
        owner_login=full_name.split("/")[0],
        html_url=f"https://github.com/{full_name}",
        created_at_gh=datetime(2026, 1, 1, tzinfo=timezone.utc),
        stars_at_first_seen=3,
        archived=archived,
    )


class TestIsEmpty:
    def test_is_empty_true_for_fresh_tenant(self, session, tenant_id):
        ledger = SqlAlchemyRepoLedger(session, tenant_id)
        assert ledger.is_empty() is True

    def test_is_empty_false_after_record(self, session, tenant_id):
        ledger = SqlAlchemyRepoLedger(session, tenant_id)
        ledger.record([_record("acme/repo")])
        assert ledger.is_empty() is False

    def test_is_empty_is_scoped_per_tenant(self, session, tenant_id):
        other_tenant = Tenant(slug="other", name="Other")
        session.add(other_tenant)
        session.commit()

        ledger_a = SqlAlchemyRepoLedger(session, tenant_id)
        ledger_a.record([_record("acme/repo")])

        ledger_b = SqlAlchemyRepoLedger(session, other_tenant.id)
        assert ledger_b.is_empty() is True


class TestKnown:
    def test_known_returns_empty_set_for_empty_ledger(self, session, tenant_id):
        ledger = SqlAlchemyRepoLedger(session, tenant_id)
        assert ledger.known(["acme/repo"]) == set()

    def test_known_returns_recorded_full_names(self, session, tenant_id):
        ledger = SqlAlchemyRepoLedger(session, tenant_id)
        ledger.record([_record("acme/repo"), _record("beta/other")])
        assert ledger.known(["acme/repo", "beta/other", "unknown/repo"]) == {
            "acme/repo",
            "beta/other",
        }

    def test_known_with_empty_input_returns_empty_set_without_query(self, session, tenant_id):
        ledger = SqlAlchemyRepoLedger(session, tenant_id)
        assert ledger.known([]) == set()


class TestRecord:
    def test_record_persists_all_fields(self, session, tenant_id):
        ledger = SqlAlchemyRepoLedger(session, tenant_id)
        ledger.record([_record("acme/repo", archived=True)])

        row = session.query(RepoObservation).filter_by(full_name="acme/repo").one()
        assert row.tenant_id == tenant_id
        assert row.owner_login == "acme"
        assert row.html_url == "https://github.com/acme/repo"
        assert row.stars_at_first_seen == 3
        assert row.archived is True
        assert row.first_seen_at is not None

    def test_record_empty_list_is_noop(self, session, tenant_id):
        ledger = SqlAlchemyRepoLedger(session, tenant_id)
        ledger.record([])
        assert session.query(RepoObservation).count() == 0

    def test_record_enforces_unique_tenant_full_name(self, session, tenant_id):
        ledger = SqlAlchemyRepoLedger(session, tenant_id)
        ledger.record([_record("acme/repo")])
        with pytest.raises(Exception):
            ledger.record([_record("acme/repo")])


def test_record_rolls_back_so_session_stays_usable(session, tenant_id):
    """Without an explicit rollback the Session stays in a failed-transaction
    state and every later use raises PendingRollbackError — fatal for the
    deployed worker, which holds one Session for the whole run.
    """
    ledger = SqlAlchemyRepoLedger(session, tenant_id)
    rec = RepoObservationRecord(
        full_name="acme/agent", owner_login="acme", html_url="https://github.com/acme/agent"
    )
    ledger.record([rec])

    # Same (tenant_id, full_name) again -> unique constraint violation.
    with pytest.raises(Exception):
        ledger.record([rec])

    # The Session must still be usable rather than poisoned.
    assert ledger.known(["acme/agent"]) == {"acme/agent"}
