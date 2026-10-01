import csv
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from scripts.export.audit_export import export_tenant
from scripts.storage.models import (
    Account,
    AccountSource,
    Base,
    Contact,
    Outreach,
    SignalEvent,
    Tenant,
)

T0 = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def test_export_writes_audit_inputs_without_person_data(session, tmp_path):
    tenant = Tenant(slug="acme", name="Acme")
    session.add(tenant)
    session.flush()
    account = Account(
        tenant_id=tenant.id,
        domain="widgets.example",
        name="Widgets Inc",
        account_metadata={"employee_band": "51-250"},
    )
    session.add(account)
    session.flush()
    source = AccountSource(
        tenant_id=tenant.id,
        account_id=account.id,
        source_type="careers",
        url="https://widgets.example/careers",
    )
    session.add(source)
    session.flush()
    session.add(
        SignalEvent(
            tenant_id=tenant.id,
            account_id=account.id,
            account_source_id=source.id,
            signal_type="careers_page_change",
            detected_at=T0,
            occurred_at=T0 - timedelta(hours=20),
        )
    )
    contact = Contact(
        tenant_id=tenant.id,
        account_id=account.id,
        email="jane.doe@widgets.example",
        name="Jane Doe",
        title="VP Sales",
    )
    session.add(contact)
    session.flush()
    session.add(
        Outreach(
            tenant_id=tenant.id,
            contact_id=contact.id,
            agentmail_inbox_id="inbox",
            agentmail_thread_id="t1",
            sent_at=T0,
            replied_at=T0 + timedelta(days=2),
        )
    )
    session.commit()

    counts = export_tenant(session, tenant.id, tmp_path)

    assert counts == {"accounts": 1, "signals": 1, "outcomes": 1, "engagements": 1}
    signal = read(tmp_path / "signals.csv")[0]
    assert signal["domain"] == "widgets.example" and signal["source"] == "signalforce_careers"
    assert signal["source_event_id"].startswith("sf:") and signal["verified"] == "true"
    assert (
        signal["observed_at"] == "2026-07-31T16:00:00+00:00"
        and signal["ingested_at"] == "2026-08-01T12:00:00+00:00"
    )
    assert read(tmp_path / "outcomes.csv")[0] == {
        "domain": "widgets.example",
        "outcome_type": "reply",
        "occurred_at": "2026-08-03T12:00:00+00:00",
    }
    assert read(tmp_path / "engagements.csv")[0]["end_at"] == "2026-08-15T12:00:00+00:00"
    assert json.loads((tmp_path / "audit.json").read_text()) == {
        "source_families": {"signalforce_careers": "web_change"}
    }
    for name in ("accounts.csv", "signals.csv", "outcomes.csv", "engagements.csv"):
        text = (tmp_path / name).read_text()
        assert "@" not in text and "Jane" not in text and "VP Sales" not in text, name


def test_export_excludes_cross_tenant_rows_even_without_a_composite_fk(session, tmp_path):
    """No composite (tenant_id, id) FK ties SignalEvent.account_id to a same-tenant
    Account, or Outreach.contact_id to a same-tenant Contact -- those are plain integer
    FKs. This test simulates that invariant being violated (e.g. a bug elsewhere writes
    a row whose tenant_id doesn't match the tenant of the row it points to) and asserts
    the export still never leaks the other tenant's domain: every join must be scoped
    to the exporting tenant, not just the top-level WHERE.
    """
    tenant1 = Tenant(slug="acme", name="Acme")
    tenant2 = Tenant(slug="evil", name="Evil Corp")
    session.add_all([tenant1, tenant2])
    session.flush()

    account1 = Account(tenant_id=tenant1.id, domain="widgets.example", name="Widgets Inc")
    account2 = Account(tenant_id=tenant2.id, domain="evil.example", name="Evil Inc")
    session.add_all([account1, account2])
    session.flush()

    source1 = AccountSource(
        tenant_id=tenant1.id,
        account_id=account1.id,
        source_type="careers",
        url="https://widgets.example/careers",
    )
    source2 = AccountSource(
        tenant_id=tenant2.id,
        account_id=account2.id,
        source_type="careers",
        url="https://evil.example/careers",
    )
    session.add_all([source1, source2])
    session.flush()

    # Legitimate tenant1 signal.
    session.add(
        SignalEvent(
            tenant_id=tenant1.id,
            account_id=account1.id,
            account_source_id=source1.id,
            signal_type="careers_page_change",
            detected_at=T0,
            occurred_at=T0 - timedelta(hours=20),
        )
    )
    # Simulated violated invariant: tenant_id says tenant1, but account_id/
    # account_source_id point at tenant2's rows.
    session.add(
        SignalEvent(
            tenant_id=tenant1.id,
            account_id=account2.id,
            account_source_id=source2.id,
            signal_type="careers_page_change",
            detected_at=T0,
            occurred_at=T0 - timedelta(hours=20),
        )
    )

    contact1 = Contact(
        tenant_id=tenant1.id, account_id=account1.id, email="jane.doe@widgets.example"
    )
    # tenant2's own, legitimate contact.
    contact2 = Contact(tenant_id=tenant2.id, account_id=account2.id, email="evil@evil.example")
    session.add_all([contact1, contact2])
    session.flush()

    # Legitimate tenant1 outreach.
    session.add(
        Outreach(
            tenant_id=tenant1.id,
            contact_id=contact1.id,
            agentmail_inbox_id="inbox",
            agentmail_thread_id="t1",
            sent_at=T0,
            replied_at=T0 + timedelta(days=2),
        )
    )
    # Simulated violated invariant: tenant_id says tenant1, but contact_id points at
    # tenant2's contact (and thus tenant2's account/domain).
    session.add(
        Outreach(
            tenant_id=tenant1.id,
            contact_id=contact2.id,
            agentmail_inbox_id="inbox",
            agentmail_thread_id="t2",
            sent_at=T0,
            replied_at=T0 + timedelta(days=2),
        )
    )
    session.commit()

    counts = export_tenant(session, tenant1.id, tmp_path)

    assert counts == {"accounts": 1, "signals": 1, "outcomes": 1, "engagements": 1}
    for name in ("accounts.csv", "signals.csv", "outcomes.csv", "engagements.csv"):
        text = (tmp_path / name).read_text()
        assert "evil.example" not in text, name
