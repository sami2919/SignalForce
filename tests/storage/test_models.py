import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.storage.models import (
    Account,
    AccountSource,
    Base,
    Probe,
    ScanRun,
    Score,
    SignalEvent,
    Tenant,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)()


def test_account_source_unique_per_type(session):
    t = Tenant(slug="agentmail", name="AgentMail")
    a = Account(tenant=t, domain="acme.com", name="Acme")
    session.add_all(
        [
            t,
            a,
            AccountSource(
                tenant=t, account=a, source_type="careers", url="https://acme.com/careers"
            ),
        ]
    )
    session.commit()
    assert session.query(AccountSource).one().url == "https://acme.com/careers"


def test_tenant_slug_is_unique(session):
    session.add(Tenant(slug="dup", name="A"))
    session.commit()
    session.add(Tenant(slug="dup", name="B"))
    with pytest.raises(Exception):
        session.commit()


def test_account_unique_per_tenant_but_allowed_across_tenants(session):
    t1 = Tenant(slug="t1", name="T1")
    t2 = Tenant(slug="t2", name="T2")
    session.add_all([t1, t2])
    session.commit()

    session.add(Account(tenant=t1, domain="acme.com", name="Acme"))
    session.commit()

    # Same domain under a different tenant is fine.
    session.add(Account(tenant=t2, domain="acme.com", name="Acme"))
    session.commit()
    assert session.query(Account).count() == 2

    # Same domain twice under the same tenant is not.
    session.add(Account(tenant=t1, domain="acme.com", name="Acme Dup"))
    with pytest.raises(Exception):
        session.commit()


def test_account_source_unique_per_account_and_type(session):
    t = Tenant(slug="t1", name="T1")
    a = Account(tenant=t, domain="acme.com", name="Acme")
    session.add_all([t, a])
    session.commit()

    session.add(
        AccountSource(tenant=t, account=a, source_type="careers", url="https://acme.com/careers")
    )
    session.commit()

    session.add(
        AccountSource(tenant=t, account=a, source_type="careers", url="https://acme.com/careers-2")
    )
    session.rollback()
    session.add(
        AccountSource(tenant=t, account=a, source_type="careers", url="https://acme.com/careers-2")
    )
    with pytest.raises(Exception):
        session.commit()


def test_account_source_defaults(session):
    t = Tenant(slug="t1", name="T1")
    a = Account(tenant=t, domain="acme.com", name="Acme")
    src = AccountSource(tenant=t, account=a, source_type="careers", url="https://acme.com/careers")
    session.add_all([t, a, src])
    session.commit()

    row = session.query(AccountSource).one()
    assert row.consecutive_failures == 0
    assert row.active is True
    assert row.last_hash is None


def test_probe_round_trips_fields(session):
    t = Tenant(slug="t1", name="T1")
    a = Account(tenant=t, domain="acme.com", name="Acme")
    src = AccountSource(tenant=t, account=a, source_type="careers", url="https://acme.com/careers")
    run = ScanRun(tenant=t)
    session.add_all([t, a, src, run])
    session.commit()

    from datetime import datetime, timezone

    probe = Probe(
        tenant=t,
        account_source=src,
        scan_run=run,
        fetched_at=datetime.now(timezone.utc),
        content_hash="abc123",
        changed=True,
        status_code=200,
        latency_ms=150,
        bytes=4096,
    )
    session.add(probe)
    session.commit()

    row = session.query(Probe).one()
    assert row.content_hash == "abc123"
    assert row.changed is True
    assert row.status_code == 200
    assert row.latency_ms == 150
    assert row.bytes == 4096


def test_signal_event_round_trips_payload(session):
    t = Tenant(slug="t1", name="T1")
    a = Account(tenant=t, domain="acme.com", name="Acme")
    session.add_all([t, a])
    session.commit()

    payload = {"foo": "bar", "nested": {"count": 3}}
    event = SignalEvent(
        tenant=t,
        account=a,
        signal_type="job_posting",
        payload=payload,
        detected_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    session.add(event)
    session.commit()

    row = session.query(SignalEvent).one()
    assert row.payload == payload


def test_score_round_trips_trace(session):
    t = Tenant(slug="t1", name="T1")
    a = Account(tenant=t, domain="acme.com", name="Acme")
    session.add_all([t, a])
    session.commit()

    trace = {"components": {"funding": 0.8, "hiring": 0.5}}
    score = Score(tenant=t, account=a, score=0.65, trace=trace)
    session.add(score)
    session.commit()

    row = session.query(Score).one()
    assert row.trace == trace


def test_scan_run_persists_with_running_status_and_nullable_finished_at(session):
    t = Tenant(slug="t1", name="T1")
    session.add(t)
    session.commit()

    run = ScanRun(tenant=t)
    session.add(run)
    session.commit()

    row = session.query(ScanRun).one()
    assert row.status == "running"
    assert row.finished_at is None
