"""Tests for scripts/verify/wiring.py.

ADR-0014 is the spec. `extract_careers_with_usage` is monkeypatched throughout --
this file tests the wiring (gate selection, diff, snapshot persistence, signal
emission, cost accumulation, per-source failure isolation), not extraction itself
(covered by tests/verify/test_extractor.py).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from scripts.storage.models import Account, AccountSource, Base, ScanRun, SignalEvent, Tenant
from scripts.verify import wiring as wiring_module
from scripts.verify.extractor import CareersFacts, ExtractorError, JobFact
from scripts.verify.gate import VerifyBudget
from scripts.verify.wiring import run_verify_stage

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


_domain_counter = {"n": 0}


def _make_source(session, tenant, source_type="careers", url=None):
    _domain_counter["n"] += 1
    domain = f"acme{_domain_counter['n']}.com"
    if url is None:
        url = f"https://{domain}/{source_type}"
    account = Account(tenant_id=tenant.id, domain=domain, name=domain)
    session.add(account)
    session.flush()
    src = AccountSource(
        tenant_id=tenant.id, account_id=account.id, source_type=source_type, url=url
    )
    session.add(src)
    session.commit()
    return src


def _make_scan_run(session, tenant):
    run = ScanRun(tenant_id=tenant.id, status="completed")
    session.add(run)
    session.commit()
    return run


def _usage(input_tokens=1000, output_tokens=200):
    u = MagicMock()
    u.input_tokens = input_tokens
    u.output_tokens = output_tokens
    return u


def _job(identity_key="job-1", title="Engineer") -> JobFact:
    return JobFact(
        identity_key=identity_key, identity_degraded=False, title=title, location=None, url=None
    )


def test_no_retained_bodies_yields_empty_report(session, tenant):
    run = _make_scan_run(session, tenant)
    report = run_verify_stage(tenant.id, session, run.id, {}, NOW)
    assert report.candidates == 0
    assert report.selected == 0
    assert report.extracted == 0


def test_non_careers_sources_are_excluded_from_candidates(session, tenant, monkeypatch):
    pricing_src = _make_source(
        session, tenant, source_type="pricing", url="https://acme.com/pricing"
    )
    run = _make_scan_run(session, tenant)

    called = MagicMock()
    monkeypatch.setattr(wiring_module, "extract_careers_with_usage", called)

    report = run_verify_stage(tenant.id, session, run.id, {pricing_src.id: "<html/>"}, NOW)

    assert report.candidates == 0
    called.assert_not_called()


def test_first_ever_extraction_seeds_snapshot_and_emits_no_signals(session, tenant, monkeypatch):
    src = _make_source(session, tenant)
    run = _make_scan_run(session, tenant)

    facts = CareersFacts(jobs=(_job(),))
    monkeypatch.setattr(wiring_module, "extract_careers_with_usage", lambda html: (facts, _usage()))

    report = run_verify_stage(tenant.id, session, run.id, {src.id: "<html/>"}, NOW)

    assert report.extracted == 1
    assert report.signals_emitted == 0  # seeding, per ADR-0007 Decision 4
    signals = session.execute(select(SignalEvent)).scalars().all()
    assert signals == []
    snapshot = wiring_module._load_snapshot(src.id, session)
    assert snapshot is not None
    assert snapshot.payload["jobs"][0]["identity_key"] == "job-1"


def test_a_real_change_on_the_second_run_emits_signal_events(session, tenant, monkeypatch):
    src = _make_source(session, tenant)
    run1 = _make_scan_run(session, tenant)

    seed_facts = CareersFacts(jobs=(_job("job-1", "Engineer"),))
    monkeypatch.setattr(
        wiring_module, "extract_careers_with_usage", lambda html: (seed_facts, _usage())
    )
    run_verify_stage(tenant.id, session, run1.id, {src.id: "<html/>"}, NOW)

    run2 = _make_scan_run(session, tenant)
    changed_facts = CareersFacts(jobs=(_job("job-1", "Engineer"), _job("job-2", "Designer")))
    monkeypatch.setattr(
        wiring_module, "extract_careers_with_usage", lambda html: (changed_facts, _usage())
    )
    report = run_verify_stage(tenant.id, session, run2.id, {src.id: "<html/>"}, NOW)

    assert report.signals_emitted == 1
    signals = session.execute(select(SignalEvent)).scalars().all()
    assert len(signals) == 1
    assert signals[0].signal_type == "hiring"
    assert signals[0].payload["kind"] == "added"
    assert signals[0].scan_run_id == run2.id
    assert signals[0].account_id == src.account_id


def test_no_change_on_the_second_run_emits_no_signals(session, tenant, monkeypatch):
    src = _make_source(session, tenant)
    run1 = _make_scan_run(session, tenant)
    facts = CareersFacts(jobs=(_job(),))
    monkeypatch.setattr(wiring_module, "extract_careers_with_usage", lambda html: (facts, _usage()))
    run_verify_stage(tenant.id, session, run1.id, {src.id: "<html/>"}, NOW)

    run2 = _make_scan_run(session, tenant)
    report = run_verify_stage(tenant.id, session, run2.id, {src.id: "<html/>"}, NOW)

    assert report.signals_emitted == 0
    signals = session.execute(select(SignalEvent)).scalars().all()
    assert signals == []


def test_budget_caps_selection_below_candidate_count(session, tenant, monkeypatch):
    sources = [_make_source(session, tenant, url=f"https://acme{i}.com/careers") for i in range(5)]
    run = _make_scan_run(session, tenant)
    facts = CareersFacts(jobs=())
    monkeypatch.setattr(wiring_module, "extract_careers_with_usage", lambda html: (facts, _usage()))

    retained = {src.id: "<html/>" for src in sources}
    report = run_verify_stage(
        tenant.id, session, run.id, retained, NOW, budget=VerifyBudget(max_calls=2)
    )

    assert report.candidates == 5
    assert report.selected == 2
    assert report.extracted == 2


def test_an_extraction_failure_is_isolated_and_does_not_abort_the_batch(
    session, tenant, monkeypatch
):
    good_src = _make_source(session, tenant, url="https://good.com/careers")
    bad_src = _make_source(session, tenant, url="https://bad.com/careers")
    run = _make_scan_run(session, tenant)

    def _fake(html):
        if html == "bad":
            raise ExtractorError("boom")
        return CareersFacts(jobs=()), _usage()

    monkeypatch.setattr(wiring_module, "extract_careers_with_usage", _fake)

    retained = {good_src.id: "good", bad_src.id: "bad"}
    report = run_verify_stage(tenant.id, session, run.id, retained, NOW)

    assert report.extracted == 1
    assert report.failed == 1
    # The failed source must not get a snapshot written for it.
    assert wiring_module._load_snapshot(bad_src.id, session) is None
    assert wiring_module._load_snapshot(good_src.id, session) is not None

    session.commit()
    updated_run = session.get(ScanRun, run.id)
    # verify_calls tracks every attempted extraction, not just successes --
    # mutation-confirmed: `extracted + failed` weakened to `extracted` alone
    # is indistinguishable from the correct value whenever failed == 0, so
    # this must be checked in a scenario with a real failure present.
    assert updated_run.verify_calls == 2


def test_a_diff_failure_is_isolated_and_does_not_abort_the_batch(session, tenant, monkeypatch):
    """An identity collision inside diff_facts (differ.py's own documented
    ValueError contract) must be caught here, not propagate and crash the
    whole verify stage for every other source in the same run."""
    src = _make_source(session, tenant)
    run1 = _make_scan_run(session, tenant)

    seed_facts = CareersFacts(jobs=(_job("job-1", "Engineer"),))
    monkeypatch.setattr(
        wiring_module, "extract_careers_with_usage", lambda html: (seed_facts, _usage())
    )
    run_verify_stage(tenant.id, session, run1.id, {src.id: "<html/>"}, NOW)

    # Second run's snapshot has TWO facts sharing the same identity key --
    # diff_facts raises ValueError on this, per its own documented contract.
    run2 = _make_scan_run(session, tenant)
    colliding_facts = CareersFacts(jobs=(_job("job-1", "A"), _job("job-1", "B")))
    monkeypatch.setattr(
        wiring_module, "extract_careers_with_usage", lambda html: (colliding_facts, _usage())
    )
    report = run_verify_stage(tenant.id, session, run2.id, {src.id: "<html/>"}, NOW)

    assert report.failed == 1
    assert report.signals_emitted == 0
    # Snapshot must NOT be overwritten with the colliding data -- next run
    # should still diff against the last successfully-confirmed snapshot.
    snapshot = wiring_module._load_snapshot(src.id, session)
    assert len(snapshot.payload["jobs"]) == 1


def test_cost_is_accumulated_from_usage_tokens(session, tenant, monkeypatch):
    src = _make_source(session, tenant)
    run = _make_scan_run(session, tenant)
    facts = CareersFacts(jobs=())
    monkeypatch.setattr(
        wiring_module,
        "extract_careers_with_usage",
        lambda html: (facts, _usage(input_tokens=100_000, output_tokens=10_000)),
    )

    report = run_verify_stage(tenant.id, session, run.id, {src.id: "<html/>"}, NOW)

    # 100_000 * 5/1e6 + 10_000 * 25/1e6 = 0.5 + 0.25 = 0.75
    assert report.cost_usd == pytest.approx(0.75)


def test_scan_run_row_is_updated_with_verify_metrics(session, tenant, monkeypatch):
    src = _make_source(session, tenant)
    run = _make_scan_run(session, tenant)
    facts = CareersFacts(jobs=(_job(),))
    monkeypatch.setattr(
        wiring_module,
        "extract_careers_with_usage",
        lambda html: (facts, _usage(input_tokens=1000, output_tokens=100)),
    )

    run_verify_stage(tenant.id, session, run.id, {src.id: "<html/>"}, NOW)
    session.commit()

    updated_run = session.get(ScanRun, run.id)
    assert updated_run.verify_calls == 1
    assert updated_run.signals_emitted == 0
    assert updated_run.cost_usd == pytest.approx(1000 * 5e-6 + 100 * 25e-6)
