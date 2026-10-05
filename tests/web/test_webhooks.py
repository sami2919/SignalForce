"""Tests for scripts/web/routes_webhooks.py.

ADR-0020 is the spec. Signature verification is tested with the REAL svix
Webhook.sign()/.verify() round trip (not mocked crypto) for the happy and
bad-signature paths, since a mock could too easily encode the same wrong
assumption the implementation makes. Uses a real secret and real headers
throughout.
"""

from __future__ import annotations

import contextlib
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from svix.webhooks import Webhook

from scripts.storage.models import Account, Base, Contact, Outreach, Tenant
from scripts.web.app import create_app
import scripts.web.routes_webhooks as webhooks_module

SECRET = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


def _sign(body: bytes, *, secret: str = SECRET, msg_id: str = "msg_test_1") -> dict[str, str]:
    """Real Svix signature generation -- not a mock. Uses the library's own
    sign() so these tests exercise genuine cryptographic round-trip
    verification, not an assumption about what verify() checks."""
    timestamp = datetime.now(timezone.utc)
    signature = Webhook(secret).sign(msg_id=msg_id, timestamp=timestamp, data=body.decode())
    return {
        "svix-id": msg_id,
        "svix-timestamp": str(int(timestamp.timestamp())),
        "svix-signature": signature,
    }


def _received_payload(thread_id: str, text: str = "sure, let's talk") -> bytes:
    return json.dumps(
        {
            "type": "event",
            "event_type": "message.received",
            "event_id": "evt_1",
            "message": {
                "inbox_id": "ib_123",
                "thread_id": thread_id,
                "message_id": "msg_1",
                "text": text,
                "subject": "Re: hello",
            },
            "thread": {"thread_id": thread_id},
        }
    ).encode()


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
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

    monkeypatch.setattr(webhooks_module, "get_session", _get_session)


@pytest.fixture(autouse=True)
def _webhook_secret(monkeypatch):
    monkeypatch.setenv("AGENTMAIL_WEBHOOK_SECRET", SECRET)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def seeded_outreach(session_factory):
    session = session_factory()
    tenant = Tenant(slug="t1", name="T1")
    session.add(tenant)
    session.commit()
    account = Account(tenant_id=tenant.id, domain="acme.com", name="Acme")
    session.add(account)
    session.commit()
    contact = Contact(tenant_id=tenant.id, account_id=account.id, email="jane@acme.com")
    session.add(contact)
    session.commit()
    outreach = Outreach(
        tenant_id=tenant.id,
        contact_id=contact.id,
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_real_1",
        sent_at=NOW,
    )
    session.add(outreach)
    session.commit()
    outreach_id = outreach.id
    session.close()
    return outreach_id


# ---------------------------------------------------------------------------
# Happy path -- real signature, real payload, real DB write
# ---------------------------------------------------------------------------


def test_valid_reply_webhook_records_reply(client, session_factory, seeded_outreach):
    body = _received_payload("th_real_1")
    headers = _sign(body)

    resp = client.post("/webhooks/agentmail", content=body, headers=headers)

    assert resp.status_code == 200
    session = session_factory()
    row = session.get(Outreach, seeded_outreach)
    assert row.replied_at is not None
    session.close()


def test_unknown_thread_is_ignored_not_errored(client):
    """Webhooks must never treat a permanent non-match as a failure --
    retrying can never make an unknown thread_id exist."""
    body = _received_payload("th_nope")
    headers = _sign(body)

    resp = client.post("/webhooks/agentmail", content=body, headers=headers)

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Signature verification -- real crypto, both directions
# ---------------------------------------------------------------------------


def test_invalid_signature_is_rejected_with_401(client):
    body = _received_payload("th_real_1")
    headers = _sign(body, secret="whsec_wrongwrongwrongwrongwrongwrong")

    resp = client.post("/webhooks/agentmail", content=body, headers=headers)

    assert resp.status_code == 401


def test_tampered_body_after_signing_is_rejected(client):
    """The signature is over the ORIGINAL body -- a body swapped in after
    signing must fail verification even with otherwise-valid headers."""
    original_body = _received_payload("th_real_1")
    headers = _sign(original_body)
    tampered_body = _received_payload("th_someone_elses_thread")

    resp = client.post("/webhooks/agentmail", content=tampered_body, headers=headers)

    assert resp.status_code == 401


def test_missing_signature_headers_is_rejected(client):
    body = _received_payload("th_real_1")
    resp = client.post("/webhooks/agentmail", content=body, headers={})
    assert resp.status_code == 401


def test_missing_webhook_secret_is_a_500_not_a_silent_pass(client, monkeypatch):
    monkeypatch.delenv("AGENTMAIL_WEBHOOK_SECRET", raising=False)
    body = _received_payload("th_real_1")
    headers = _sign(body)

    resp = client.post("/webhooks/agentmail", content=body, headers=headers)

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Permanent non-matches -- all 200, per ADR-0020 Decision 3
# ---------------------------------------------------------------------------


def test_non_message_received_event_is_ignored(client, session_factory, seeded_outreach):
    """Mutation-confirmed: a payload with an empty `message` object can't
    distinguish 'skipped due to wrong event_type' from 'fell through the
    missing-thread_id branch' -- both produce 200 with no DB write either
    way. A payload carrying a REAL, matching thread_id is required to prove
    the event_type check is actually what's stopping the write."""
    body = json.dumps(
        {
            "type": "event",
            "event_type": "message.sent",
            "event_id": "evt_2",
            "message": {"thread_id": "th_real_1", "text": "should not be recorded"},
        }
    ).encode()
    headers = _sign(body)

    resp = client.post("/webhooks/agentmail", content=body, headers=headers)

    assert resp.status_code == 200
    session = session_factory()
    row = session.get(Outreach, seeded_outreach)
    assert row.replied_at is None
    session.close()


def test_message_received_with_no_thread_id_is_ignored(client):
    body = json.dumps(
        {"type": "event", "event_type": "message.received", "event_id": "evt_3", "message": {}}
    ).encode()
    headers = _sign(body)

    resp = client.post("/webhooks/agentmail", content=body, headers=headers)

    assert resp.status_code == 200


def test_a_reply_only_updates_the_matching_thread_not_every_outreach_row(
    client, session_factory, seeded_outreach
):
    """Mutation-confirmed: dropping the WHERE clause on the lookup query
    survived every other test, since seeded_outreach's table only ever has
    ONE row -- select(Outreach).scalar_one_or_none() with no filter still
    finds that same single row 'by accident'. A second, sibling Outreach
    row for a DIFFERENT thread is required to prove the filter is real."""
    session = session_factory()
    row = session.get(Outreach, seeded_outreach)
    tenant_id, contact_id = row.tenant_id, row.contact_id
    sibling = Outreach(
        tenant_id=tenant_id,
        contact_id=contact_id,
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_sibling",
        sent_at=NOW,
    )
    session.add(sibling)
    session.commit()
    sibling_id = sibling.id
    session.close()

    body = _received_payload("th_real_1")
    resp = client.post("/webhooks/agentmail", content=body, headers=_sign(body))

    assert resp.status_code == 200
    session = session_factory()
    assert session.get(Outreach, seeded_outreach).replied_at is not None
    assert session.get(Outreach, sibling_id).replied_at is None
    session.close()


# ---------------------------------------------------------------------------
# First-reply-wins (ADR-0020 Decision 4)
# ---------------------------------------------------------------------------


def test_a_second_reply_does_not_overwrite_the_first_replied_at(
    client, session_factory, seeded_outreach
):
    body1 = _received_payload("th_real_1", text="first reply")
    client.post("/webhooks/agentmail", content=body1, headers=_sign(body1, msg_id="msg_a"))

    session = session_factory()
    first_replied_at = session.get(Outreach, seeded_outreach).replied_at
    session.close()
    assert first_replied_at is not None

    body2 = _received_payload("th_real_1", text="second reply")
    resp = client.post("/webhooks/agentmail", content=body2, headers=_sign(body2, msg_id="msg_b"))

    assert resp.status_code == 200
    session = session_factory()
    row = session.get(Outreach, seeded_outreach)
    assert row.replied_at == first_replied_at
    session.close()
