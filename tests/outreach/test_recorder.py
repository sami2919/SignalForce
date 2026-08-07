"""Tests for scripts/outreach/recorder.py.

ADR-0023 is the spec. `record_outreach` is what connects a real
AgentMailClient.send() (Task 5.1) to the Outreach table (Task 5.0) --
nothing wired them together before this task, which is what the live
end-to-end reply-webhook test surfaced.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from scripts.outreach.recorder import record_outreach
from scripts.storage.models import Account, Base, Contact, Outreach, Tenant

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


@pytest.fixture
def tenant_and_account(session):
    tenant = Tenant(slug="agentmail", name="AgentMail")
    account = Account(tenant=tenant, domain="acme.com", name="Acme")
    session.add_all([tenant, account])
    session.commit()
    return tenant.id, account.id


def test_records_a_new_contact_and_outreach(session, tenant_and_account):
    tenant_id, account_id = tenant_and_account

    outreach = record_outreach(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        contact_email="jane@acme.com",
        contact_name="Jane Doe",
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_1",
        sent_at=NOW,
    )
    session.commit()

    assert outreach.id is not None
    assert outreach.agentmail_thread_id == "th_1"
    # SQLite drops tzinfo on DateTime round-trip (Postgres, the real target,
    # does not) -- compare the naive value re-attached to UTC.
    assert outreach.sent_at.replace(tzinfo=timezone.utc) == NOW
    assert outreach.replied_at is None

    contact = session.get(Contact, outreach.contact_id)
    assert contact.email == "jane@acme.com"
    assert contact.name == "Jane Doe"
    assert contact.account_id == account_id


def test_reuses_an_existing_contact_by_tenant_and_email(session, tenant_and_account):
    """A second outreach to the same person must NOT create a second Contact
    row -- Contact is find-or-create by (tenant_id, email) per ADR-0023
    Decision 2, not always-insert."""
    tenant_id, account_id = tenant_and_account

    first = record_outreach(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        contact_email="jane@acme.com",
        contact_name="Jane Doe",
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_1",
        sent_at=NOW,
    )
    session.commit()

    second = record_outreach(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        contact_email="jane@acme.com",
        contact_name="Jane Doe (again)",
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_2",
        sent_at=NOW,
    )
    session.commit()

    assert first.contact_id == second.contact_id
    assert session.query(Contact).count() == 1
    assert session.query(Outreach).count() == 2


def test_duplicate_thread_id_raises_instead_of_silently_upserting(session, tenant_and_account):
    """Mutation-confirmed guard: calling this twice for the SAME real
    AgentMail thread must surface as a database error (ADR-0023 Decision
    2), not silently overwrite or duplicate -- an accidental double-record
    of the same send is exactly the kind of silent-no-op this project has
    repeatedly found and rejected elsewhere (soft-404s, accounts_probed,
    the truncation ceiling)."""
    tenant_id, account_id = tenant_and_account

    record_outreach(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        contact_email="jane@acme.com",
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_dup",
        sent_at=NOW,
    )
    session.commit()

    # record_outreach flushes internally (to populate outreach.id for the
    # caller, same pattern as every other write helper in this codebase),
    # so the second call's flush is where the unique constraint fires --
    # not deferred to a later session.commit().
    with pytest.raises(IntegrityError):
        record_outreach(
            session,
            tenant_id=tenant_id,
            account_id=account_id,
            contact_email="jane@acme.com",
            agentmail_inbox_id="ib_123",
            agentmail_thread_id="th_dup",
            sent_at=NOW,
        )


def test_same_email_in_a_different_tenant_is_a_separate_contact(session, tenant_and_account):
    """Mutation-confirmed: dropping tenant_id from the lookup filter
    survived every other test, since they all use a single tenant --
    two tenants sharing a contact email must NOT collapse onto one
    Contact row (Contact's uniqueness is (tenant_id, email), not email
    alone, per ADR-0019)."""
    tenant_id, account_id = tenant_and_account
    other_tenant = Tenant(slug="other", name="Other")
    other_account = Account(tenant=other_tenant, domain="other.com", name="Other Co")
    session.add_all([other_tenant, other_account])
    session.commit()

    first = record_outreach(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        contact_email="shared@example.com",
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_1",
        sent_at=NOW,
    )
    second = record_outreach(
        session,
        tenant_id=other_tenant.id,
        account_id=other_account.id,
        contact_email="shared@example.com",
        agentmail_inbox_id="ib_456",
        agentmail_thread_id="th_2",
        sent_at=NOW,
    )
    session.commit()

    assert first.contact_id != second.contact_id
    assert session.query(Contact).count() == 2


def test_outreach_contact_id_is_the_contact_not_the_account(session, tenant_and_account):
    """Mutation-confirmed: swapping contact_id for account_id survived
    every other test. Account and Contact each autoincrement from 1
    independently, so a test with exactly one of each gets contact_id=1
    and account_id=1 by sheer coincidence -- passing either value looks
    identical. Recording a DECOY contact first shifts the target contact's
    id to 2 while account_id stays 1, so the two can no longer be
    confused by accident."""
    tenant_id, account_id = tenant_and_account

    record_outreach(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        contact_email="decoy@acme.com",
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_decoy",
        sent_at=NOW,
    )
    session.commit()

    outreach = record_outreach(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        contact_email="jane@acme.com",
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_1",
        sent_at=NOW,
    )
    session.commit()

    assert outreach.contact_id != account_id
    contact = session.get(Contact, outreach.contact_id)
    assert contact is not None
    assert contact.email == "jane@acme.com"


def test_two_different_contacts_at_the_same_account_stay_distinct(session, tenant_and_account):
    tenant_id, account_id = tenant_and_account

    record_outreach(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        contact_email="jane@acme.com",
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_1",
        sent_at=NOW,
    )
    record_outreach(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        contact_email="bob@acme.com",
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_2",
        sent_at=NOW,
    )
    session.commit()

    assert session.query(Contact).count() == 2


def test_optional_fields_default_sensibly(session, tenant_and_account):
    tenant_id, account_id = tenant_and_account

    outreach = record_outreach(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        contact_email="jane@acme.com",
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_1",
        sent_at=NOW,
    )
    session.commit()

    assert outreach.audience_id is None
    assert outreach.triggering_signal_ids == []
    contact = session.get(Contact, outreach.contact_id)
    assert contact.name == ""
    assert contact.title == ""
    assert contact.persona_id is None


def test_optional_fields_are_stored_when_provided(session, tenant_and_account):
    tenant_id, account_id = tenant_and_account

    outreach = record_outreach(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        contact_email="jane@acme.com",
        contact_name="Jane Doe",
        contact_title="VP Eng",
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_1",
        sent_at=NOW,
        audience_id=None,
        triggering_signal_ids=[7, 9],
    )
    session.commit()

    assert outreach.triggering_signal_ids == [7, 9]
    contact = session.get(Contact, outreach.contact_id)
    assert contact.title == "VP Eng"
