"""Tests for scripts/measure/recall_report.py.

ADR-0013 Decision 3 is the spec. The critical property this file protects:
compute_recall_for_tenant must compare the SAME account population on both
sides (deep vs watch) -- using a different seed/size for the holdout
selection than run_deep_scan would silently compare mismatched populations
and produce a meaningless recall number.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from scripts.measure.holdout import load_active_account_ids, select_holdout
from scripts.measure.recall_report import compute_recall_for_tenant
from scripts.storage.models import Account, AccountSource, Base, HoldoutScan, Probe, ScanRun, Tenant

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


def _make_account_with_source(session, tenant, domain: str, source_type: str = "careers"):
    account = Account(tenant_id=tenant.id, domain=domain, name=domain)
    session.add(account)
    session.flush()
    src = AccountSource(
        tenant_id=tenant.id,
        account_id=account.id,
        source_type=source_type,
        url=f"https://{domain}/{source_type}",
    )
    session.add(src)
    session.commit()
    return account, src


def _make_scan_run(session, tenant) -> ScanRun:
    run = ScanRun(tenant_id=tenant.id, status="success")
    session.add(run)
    session.flush()
    return run


def _probe(session, tenant, source, run, *, fetched_at, changed):
    p = Probe(
        tenant_id=tenant.id,
        account_source_id=source.id,
        scan_run_id=run.id,
        fetched_at=fetched_at,
        content_hash="h",
        changed=changed,
        status_code=200,
    )
    session.add(p)
    session.commit()
    return p


def _holdout_scan(session, tenant, source, *, fetched_at, changed):
    hs = HoldoutScan(
        tenant_id=tenant.id,
        account_source_id=source.id,
        fetched_at=fetched_at,
        content_hash="h",
        changed=changed,
        status_code=200,
    )
    session.add(hs)
    session.commit()
    return hs


def test_no_active_accounts_yields_undefined_recall(session, tenant):
    report = compute_recall_for_tenant(tenant.id, session, now=NOW)
    assert report.recall is None
    assert report.deep_count == 0


def test_uses_the_same_holdout_selection_as_run_deep_scan(session, tenant):
    """The critical property: a different seed/size than run_deep_scan's
    defaults would compare mismatched populations. compute_recall_for_tenant's
    defaults must match run_deep_scan's defaults exactly."""
    accounts = [_make_account_with_source(session, tenant, f"acme{i}.com")[0] for i in range(10)]
    account_ids = load_active_account_ids(tenant.id, session)
    expected_holdout = select_holdout(account_ids, size=5, seed=42)

    # Put a genuine deep+watch change on a holdout account and on a
    # non-holdout account; only the holdout one should be counted.
    holdout_account_id = expected_holdout[0]
    non_holdout_account_id = next(a.id for a in accounts if a.id not in expected_holdout)

    def _source_for(account_id: int) -> AccountSource:
        return session.execute(
            select(AccountSource).where(AccountSource.account_id == account_id)
        ).scalar_one()

    for account_id in (holdout_account_id, non_holdout_account_id):
        src = _source_for(account_id)
        _holdout_scan(session, tenant, src, fetched_at=NOW - timedelta(hours=1), changed=True)
        run = _make_scan_run(session, tenant)
        _probe(session, tenant, src, run, fetched_at=NOW - timedelta(hours=2), changed=True)

    report = compute_recall_for_tenant(tenant.id, session, now=NOW)

    # Only the holdout account's change is counted -- the non-holdout
    # account's identical change never enters deep_count at all.
    assert report.deep_count == 1
    # And it must not leak in on the WATCH side either -- mutation-confirmed:
    # dropping the holdout-account filter from the watch-side query survives
    # a bare deep_count check (the non-holdout probe lands under a key with
    # no matching deep change and would just look like an unrelated
    # extraneous detection), so this must be checked explicitly.
    assert report.extraneous_watch_count == 0


def test_matched_deep_and_watch_changes_compute_a_real_recall(session, tenant):
    account, src = _make_account_with_source(session, tenant, "acme.com")
    account_ids = load_active_account_ids(tenant.id, session)
    holdout = select_holdout(account_ids, size=5, seed=42)
    assert account.id in holdout  # sole account, always selected

    _holdout_scan(session, tenant, src, fetched_at=NOW - timedelta(hours=10), changed=True)
    run = _make_scan_run(session, tenant)
    _probe(session, tenant, src, run, fetched_at=NOW - timedelta(hours=4), changed=True)

    report = compute_recall_for_tenant(tenant.id, session, now=NOW)

    assert report.deep_count == 1
    assert report.caught_count == 1
    assert report.recall == 1.0
    # deep at -10h, watch at -4h -> lag = deep - watch = -10 - (-4) = -6h.
    assert report.p50_lag_hours == -6.0


def test_a_deep_change_with_no_matching_watch_detection_is_a_miss(session, tenant):
    account, src = _make_account_with_source(session, tenant, "acme.com")
    _holdout_scan(session, tenant, src, fetched_at=NOW - timedelta(hours=10), changed=True)

    report = compute_recall_for_tenant(tenant.id, session, now=NOW)

    assert report.deep_count == 1
    assert report.missed_count == 1
    assert report.recall == 0.0


def test_unchanged_rows_are_never_treated_as_detected_changes(session, tenant):
    account, src = _make_account_with_source(session, tenant, "acme.com")
    _holdout_scan(session, tenant, src, fetched_at=NOW - timedelta(hours=10), changed=False)
    run = _make_scan_run(session, tenant)
    _probe(session, tenant, src, run, fetched_at=NOW - timedelta(hours=4), changed=False)

    report = compute_recall_for_tenant(tenant.id, session, now=NOW)

    assert report.deep_count == 0
    assert report.extraneous_watch_count == 0


def test_changes_outside_the_window_are_excluded(session, tenant):
    account, src = _make_account_with_source(session, tenant, "acme.com")
    _holdout_scan(session, tenant, src, fetched_at=NOW - timedelta(days=30), changed=True)
    run = _make_scan_run(session, tenant)
    _probe(session, tenant, src, run, fetched_at=NOW - timedelta(days=30), changed=True)

    report = compute_recall_for_tenant(tenant.id, session, now=NOW, window_days=7)

    assert report.deep_count == 0


def test_changes_inside_a_custom_window_are_included(session, tenant):
    account, src = _make_account_with_source(session, tenant, "acme.com")
    _holdout_scan(session, tenant, src, fetched_at=NOW - timedelta(days=10), changed=True)
    run = _make_scan_run(session, tenant)
    _probe(session, tenant, src, run, fetched_at=NOW - timedelta(days=10), changed=True)

    report = compute_recall_for_tenant(tenant.id, session, now=NOW, window_days=14)

    assert report.deep_count == 1
    assert report.caught_count == 1
