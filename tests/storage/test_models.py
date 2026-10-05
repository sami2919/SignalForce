import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.storage.models import (
    Account,
    AccountSource,
    Audience,
    Base,
    Contact,
    Outreach,
    Persona,
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


# ---------------------------------------------------------------------------
# ADR-0019: Persona, Audience, Contact, Outreach
# ---------------------------------------------------------------------------


def test_persona_round_trips_title_patterns(session):
    t = Tenant(slug="t1", name="T1")
    session.add(t)
    session.commit()

    persona = Persona(
        tenant=t, name="Growth Marketer", title_patterns=["growth", "demand gen"], seniority_min=1
    )
    session.add(persona)
    session.commit()

    row = session.query(Persona).one()
    assert row.title_patterns == ["growth", "demand gen"]
    assert row.seniority_min == 1


def test_persona_name_is_unique_per_tenant(session):
    t = Tenant(slug="t1", name="T1")
    session.add(t)
    session.commit()
    session.add(Persona(tenant=t, name="Growth Marketer", title_patterns=[], seniority_min=1))
    session.commit()

    session.add(Persona(tenant=t, name="Growth Marketer", title_patterns=[], seniority_min=2))
    with pytest.raises(Exception):
        session.commit()


def test_audience_round_trips_predicate(session):
    t = Tenant(slug="t1", name="T1")
    session.add(t)
    session.commit()

    predicate = {"and": [{"has_signal": "hiring"}, {"min_score": 60}]}
    audience = Audience(tenant=t, name="Hot leads", predicate=predicate)
    session.add(audience)
    session.commit()

    row = session.query(Audience).one()
    assert row.predicate == predicate


def test_contact_links_to_account_and_optional_persona(session):
    t = Tenant(slug="t1", name="T1")
    a = Account(tenant=t, domain="acme.com", name="Acme")
    session.add_all([t, a])
    session.commit()
    persona = Persona(tenant=t, name="Growth Marketer", title_patterns=["growth"], seniority_min=1)
    session.add(persona)
    session.commit()

    contact = Contact(
        tenant=t,
        account=a,
        email="jane@acme.com",
        name="Jane Doe",
        title="Growth Lead",
        persona=persona,
    )
    session.add(contact)
    session.commit()

    row = session.query(Contact).one()
    assert row.email == "jane@acme.com"
    assert row.persona.name == "Growth Marketer"


def test_contact_without_a_persona_is_allowed(session):
    t = Tenant(slug="t1", name="T1")
    a = Account(tenant=t, domain="acme.com", name="Acme")
    session.add_all([t, a])
    session.commit()

    contact = Contact(tenant=t, account=a, email="jane@acme.com")
    session.add(contact)
    session.commit()

    row = session.query(Contact).one()
    assert row.persona_id is None


def test_contact_email_is_unique_per_tenant(session):
    t = Tenant(slug="t1", name="T1")
    a = Account(tenant=t, domain="acme.com", name="Acme")
    session.add_all([t, a])
    session.commit()
    session.add(Contact(tenant=t, account=a, email="jane@acme.com"))
    session.commit()

    session.add(Contact(tenant=t, account=a, email="jane@acme.com"))
    with pytest.raises(Exception):
        session.commit()


def test_outreach_round_trips_triggering_signal_ids(session):
    from datetime import datetime, timezone

    t = Tenant(slug="t1", name="T1")
    a = Account(tenant=t, domain="acme.com", name="Acme")
    session.add_all([t, a])
    session.commit()
    contact = Contact(tenant=t, account=a, email="jane@acme.com")
    session.add(contact)
    session.commit()

    outreach = Outreach(
        tenant=t,
        contact=contact,
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_456",
        sent_at=datetime.now(timezone.utc),
        triggering_signal_ids=[1, 2, 3],
    )
    session.add(outreach)
    session.commit()

    row = session.query(Outreach).one()
    assert row.triggering_signal_ids == [1, 2, 3]
    assert row.audience_id is None
    assert row.replied_at is None


def test_outreach_agentmail_thread_id_is_globally_unique(session):
    from datetime import datetime, timezone

    t = Tenant(slug="t1", name="T1")
    a = Account(tenant=t, domain="acme.com", name="Acme")
    session.add_all([t, a])
    session.commit()
    contact1 = Contact(tenant=t, account=a, email="jane@acme.com")
    contact2 = Contact(tenant=t, account=a, email="john@acme.com")
    session.add_all([contact1, contact2])
    session.commit()

    session.add(
        Outreach(
            tenant=t,
            contact=contact1,
            agentmail_inbox_id="ib_123",
            agentmail_thread_id="th_dup",
            sent_at=datetime.now(timezone.utc),
        )
    )
    session.commit()

    session.add(
        Outreach(
            tenant=t,
            contact=contact2,
            agentmail_inbox_id="ib_123",
            agentmail_thread_id="th_dup",
            sent_at=datetime.now(timezone.utc),
        )
    )
    with pytest.raises(Exception):
        session.commit()


def test_outreach_with_an_audience_links_back_to_the_predicate(session):
    from datetime import datetime, timezone

    t = Tenant(slug="t1", name="T1")
    a = Account(tenant=t, domain="acme.com", name="Acme")
    session.add_all([t, a])
    session.commit()
    contact = Contact(tenant=t, account=a, email="jane@acme.com")
    audience = Audience(tenant=t, name="Hot leads", predicate={"min_score": 60})
    session.add_all([contact, audience])
    session.commit()

    outreach = Outreach(
        tenant=t,
        contact=contact,
        audience=audience,
        agentmail_inbox_id="ib_123",
        agentmail_thread_id="th_789",
        sent_at=datetime.now(timezone.utc),
    )
    session.add(outreach)
    session.commit()

    row = session.query(Outreach).one()
    assert row.audience.predicate == {"min_score": 60}
