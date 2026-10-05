"""Tests for scripts/measure/daily_postprocess.py.

ADR-0013 Decision 2 is the spec: each stage (health, recall, retention) is
independently wrapped so one failing does not block the others. That
independence is the property most worth proving here, since it's exactly
the kind of thing that looks correct by inspection but silently isn't
without a failure-injection test (this project's established pattern --
see ADR-0012 Decision 2's genuine-failure-injection retention test).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.measure import daily_postprocess as postprocess_module
from scripts.measure.daily_postprocess import run_daily_postprocess
from scripts.storage.models import (
    Account,
    AccountSource,
    Base,
    Probe,
    ScanRun,
    SourceHealthRecord,
    Tenant,
)

NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


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


def _make_source(session, tenant, source_type="careers"):
    account = Account(tenant_id=tenant.id, domain="acme.com", name="Acme")
    session.add(account)
    session.flush()
    src = AccountSource(
        tenant_id=tenant.id,
        account_id=account.id,
        source_type=source_type,
        url=f"https://acme.com/{source_type}",
    )
    session.add(src)
    session.commit()
    return src


def _probe(session, tenant, source, *, fetched_at, changed=False, succeeded=True):
    run = ScanRun(tenant_id=tenant.id, status="success")
    session.add(run)
    session.flush()
    p = Probe(
        tenant_id=tenant.id,
        account_source_id=source.id,
        scan_run_id=run.id,
        fetched_at=fetched_at,
        content_hash="h" if succeeded else None,
        changed=changed,
        status_code=200 if succeeded else 503,
        error=None if succeeded else "timeout",
    )
    session.add(p)
    session.commit()
    return p


def test_all_stages_succeed_on_a_normal_run(session, tenant):
    source = _make_source(session, tenant)
    _probe(session, tenant, source, fetched_at=NOW)

    report = run_daily_postprocess(tenant.id, session, now=NOW)

    assert report.health_ok is True
    assert report.recall_ok is True
    assert report.retention_ok is True
    assert report.all_ok is True


def test_health_stage_persists_a_source_health_row_for_today(session, tenant):
    source = _make_source(session, tenant, source_type="careers")
    _probe(session, tenant, source, fetched_at=NOW, succeeded=True)

    run_daily_postprocess(tenant.id, session, now=NOW)

    record = (
        session.query(SourceHealthRecord)
        .filter_by(tenant_id=tenant.id, source_type="careers", run_date=NOW.date())
        .one()
    )
    assert record.fetch_success_rate == 1.0


def test_a_health_stage_failure_does_not_block_recall_or_retention(session, tenant, monkeypatch):
    source = _make_source(session, tenant)
    _probe(session, tenant, source, fetched_at=NOW)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated health failure")

    monkeypatch.setattr(postprocess_module, "_distinct_active_source_types", _boom)

    report = run_daily_postprocess(tenant.id, session, now=NOW)

    assert report.health_ok is False
    assert report.recall_ok is True
    assert report.retention_ok is True
    assert report.all_ok is False


def test_a_recall_stage_failure_does_not_block_health_or_retention(session, tenant, monkeypatch):
    source = _make_source(session, tenant)
    _probe(session, tenant, source, fetched_at=NOW)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated recall failure")

    monkeypatch.setattr(postprocess_module, "compute_recall_for_tenant", _boom)

    report = run_daily_postprocess(tenant.id, session, now=NOW)

    assert report.health_ok is True
    assert report.recall_ok is False
    assert report.retention_ok is True
    # Health must have actually run and persisted, not just reported ok.
    record = (
        session.query(SourceHealthRecord)
        .filter_by(tenant_id=tenant.id, source_type="careers", run_date=NOW.date())
        .one_or_none()
    )
    assert record is not None


def test_a_retention_stage_failure_does_not_block_health_or_recall(session, tenant, monkeypatch):
    source = _make_source(session, tenant)
    _probe(session, tenant, source, fetched_at=NOW - timedelta(days=45), changed=False)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated retention failure")

    monkeypatch.setattr(postprocess_module, "rollup_and_prune", _boom)

    report = run_daily_postprocess(tenant.id, session, now=NOW)

    assert report.health_ok is True
    assert report.recall_ok is True
    assert report.retention_ok is False


def test_a_source_type_with_no_probes_today_is_skipped_not_a_crash(session, tenant):
    """An active source_type with zero probes today gets a rollup with
    fetch_success_rate=None (compute_health's undefined-not-zero case).
    detect_anomaly cannot run on None -- the health stage must skip this
    source_type gracefully rather than crash the whole stage.

    Trailing history is seeded here (mutation-confirmed necessary): with an
    empty trailing list, detect_anomaly's own _MIN_HISTORY guard returns
    None before ever touching `current` arithmetically, which would mask
    the missing continue/skip guard entirely. Only with real history present
    does `current - mean` (current=None) actually get reached and crash.
    """
    _make_source(session, tenant, source_type="careers")
    for days_back in range(1, 15):
        session.add(
            SourceHealthRecord(
                tenant_id=tenant.id,
                source_type="careers",
                run_date=(NOW - timedelta(days=days_back)).date(),
                fetch_success_rate=0.98,
                parse_success_rate=None,
                zero_result_rate=None,
                sample_size=10,
            )
        )
    session.commit()
    # No probes recorded at all for this source today.

    report = run_daily_postprocess(tenant.id, session, now=NOW)

    assert report.health_ok is True
    record = (
        session.query(SourceHealthRecord)
        .filter_by(tenant_id=tenant.id, source_type="careers", run_date=NOW.date())
        .one()
    )
    assert record.fetch_success_rate is None


def test_an_anomalous_fetch_success_rate_is_detected_against_trailing_history(
    session, tenant, caplog
):
    """Seed 14 days of a healthy trailing baseline directly into
    source_health, then run postprocess on a day with a real fetch failure
    spike -- proves detect_anomaly is actually wired to real persisted
    trailing data, not just called with an empty list."""
    source = _make_source(session, tenant, source_type="careers")

    for days_back in range(1, 15):
        session.add(
            SourceHealthRecord(
                tenant_id=tenant.id,
                source_type="careers",
                run_date=(NOW - timedelta(days=days_back)).date(),
                fetch_success_rate=0.98,
                parse_success_rate=None,
                zero_result_rate=None,
                sample_size=10,
            )
        )
    session.commit()

    # Today: every probe fails.
    for _ in range(5):
        _probe(session, tenant, source, fetched_at=NOW, succeeded=False)

    with caplog.at_level("WARNING", logger="scripts.measure.daily_postprocess"):
        report = run_daily_postprocess(tenant.id, session, now=NOW)

    assert report.health_ok is True
    record = (
        session.query(SourceHealthRecord)
        .filter_by(tenant_id=tenant.id, source_type="careers", run_date=NOW.date())
        .one()
    )
    assert record.fetch_success_rate == 0.0
    anomaly_records = [r for r in caplog.records if "anomaly" in r.message]
    assert len(anomaly_records) == 1
    # Mutation-confirmed: the trailing-history query must exclude TODAY's own
    # just-persisted row (run_date < today, not <=) -- if it leaked in, the
    # baseline would be pulled toward today's own 0.0 and report 0.9147
    # instead of the true 14-day baseline of 0.98.
    assert anomaly_records[0].baseline_mean == 0.98
