"""Tests for scripts/measure/retention.py.

ADR-0012 (docs/decisions/0012-probe-retention-and-rollup.md) is the spec. It corrects a
contradiction in the plan: the plan's Step 3 says rollup_and_prune computes a day's
source_health rollup itself if missing, but the plan's own test for the safety property
omits any health data and expects the day to be skipped anyway -- which only makes sense
if the function does NOT self-compute, contradicting its own Step 3. Decision 1 resolves
this by keeping Step 3's stated design (rollup_and_prune is self-sufficient) and replacing
the plan's fixture-omission test with a genuine failure-injection test
(test_a_day_is_never_pruned_if_its_rollup_cannot_be_persisted below) that proves the
"verify before delete" safety property for real, not by assumption.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from scripts.measure import retention as retention_module
from scripts.measure.retention import rollup_and_prune
from scripts.storage.models import (
    Account,
    AccountSource,
    Base,
    Probe,
    ScanRun,
    SourceHealthRecord,
    Tenant,
)

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


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


_tenant_counter = {"n": 0}


@pytest.fixture
def tenant(session):
    _tenant_counter["n"] += 1
    t = Tenant(slug=f"t{_tenant_counter['n']}", name="T")
    session.add(t)
    session.commit()
    return t


def _make_source(session, tenant, source_type: str = "careers") -> AccountSource:
    account = session.execute(
        select(Account).where(Account.tenant_id == tenant.id, Account.domain == "acme.com")
    ).scalar_one_or_none()
    if account is None:
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
    session.flush()
    return src


def _make_scan_run(session, tenant) -> ScanRun:
    run = ScanRun(tenant_id=tenant.id, status="success")
    session.add(run)
    session.flush()
    return run


def _probe(
    session,
    tenant,
    source: AccountSource,
    run: ScanRun,
    *,
    fetched_at: datetime,
    changed: bool,
    succeeded: bool = True,
) -> Probe:
    probe = Probe(
        tenant_id=tenant.id,
        account_source_id=source.id,
        scan_run_id=run.id,
        fetched_at=fetched_at,
        content_hash="deadbeef" if succeeded else None,
        changed=changed,
        status_code=200 if succeeded else None,
        error=None if succeeded else "timeout",
    )
    session.add(probe)
    session.commit()
    return probe


def _days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


# ---------------------------------------------------------------------------
# Two-tier retention windows (plan's core spec)
# ---------------------------------------------------------------------------


def test_prunes_unchanged_probes_older_than_30_days(session, tenant):
    source = _make_source(session, tenant)
    run = _make_scan_run(session, tenant)
    _probe(session, tenant, source, run, fetched_at=_days_ago(45), changed=False)

    report = rollup_and_prune(tenant.id, session, now=NOW)

    assert report.unchanged_pruned == 1


def test_keeps_unchanged_probes_inside_the_window(session, tenant):
    source = _make_source(session, tenant)
    run = _make_scan_run(session, tenant)
    _probe(session, tenant, source, run, fetched_at=_days_ago(10), changed=False)

    report = rollup_and_prune(tenant.id, session, now=NOW)

    assert report.unchanged_pruned == 0


def test_keeps_changed_probes_for_180_days(session, tenant):
    source = _make_source(session, tenant)
    run = _make_scan_run(session, tenant)
    _probe(session, tenant, source, run, fetched_at=_days_ago(45), changed=True)

    report = rollup_and_prune(tenant.id, session, now=NOW)

    assert report.changed_pruned == 0


def test_prunes_changed_probes_past_180_days(session, tenant):
    source = _make_source(session, tenant)
    run = _make_scan_run(session, tenant)
    _probe(session, tenant, source, run, fetched_at=_days_ago(200), changed=True)

    report = rollup_and_prune(tenant.id, session, now=NOW)

    assert report.changed_pruned == 1


def test_a_day_past_both_cutoffs_prunes_unchanged_and_changed_independently(session, tenant):
    """A day past 180 days is past 30 too -- both rules apply to the same day,
    and they must not interfere with each other's counts."""
    source = _make_source(session, tenant)
    run = _make_scan_run(session, tenant)
    _probe(session, tenant, source, run, fetched_at=_days_ago(200), changed=False)
    _probe(session, tenant, source, run, fetched_at=_days_ago(200), changed=True)

    report = rollup_and_prune(tenant.id, session, now=NOW)

    assert report.unchanged_pruned == 1
    assert report.changed_pruned == 1


# ---------------------------------------------------------------------------
# Rollup creation and idempotency (ADR-0012 Decision 1)
# ---------------------------------------------------------------------------


def test_rollup_creates_a_source_health_row_with_real_fetch_data(session, tenant):
    source = _make_source(session, tenant, source_type="careers")
    run = _make_scan_run(session, tenant)
    day = _days_ago(45)
    _probe(session, tenant, source, run, fetched_at=day, changed=False, succeeded=True)
    _probe(session, tenant, source, run, fetched_at=day, changed=False, succeeded=False)

    rollup_and_prune(tenant.id, session, now=NOW)

    record = session.execute(
        select(SourceHealthRecord).where(
            SourceHealthRecord.tenant_id == tenant.id,
            SourceHealthRecord.source_type == "careers",
        )
    ).scalar_one()
    assert record.sample_size == 2
    assert record.fetch_success_rate == 0.5
    assert record.parse_success_rate is None
    assert record.zero_result_rate is None
    assert record.run_date == day.date()


def test_rollup_is_idempotent(session, tenant):
    """Re-running must not double-count into source_health."""
    source = _make_source(session, tenant)
    run = _make_scan_run(session, tenant)
    _probe(session, tenant, source, run, fetched_at=_days_ago(45), changed=False)

    first = rollup_and_prune(tenant.id, session, now=NOW)
    second = rollup_and_prune(tenant.id, session, now=NOW)

    assert first.rows_rolled_up >= 1
    assert second.rows_rolled_up == 0


def test_rows_rolled_up_does_not_count_a_day_whose_rollup_already_existed(session, tenant):
    """Distinguishes 'newly created' from 'already there' -- a prerequisite
    for idempotency counting to mean anything (ADR-0012 Decision 6)."""
    source = _make_source(session, tenant)
    run = _make_scan_run(session, tenant)
    day_a = _days_ago(45)
    day_b = _days_ago(50)
    _probe(session, tenant, source, run, fetched_at=day_a, changed=False)

    first = rollup_and_prune(tenant.id, session, now=NOW)
    assert first.rows_rolled_up == 1

    _probe(session, tenant, source, run, fetched_at=day_b, changed=False)
    second = rollup_and_prune(tenant.id, session, now=NOW)
    # day_a's rollup already exists; only day_b's is new.
    assert second.rows_rolled_up == 1


# ---------------------------------------------------------------------------
# The safety property: never prune a day whose rollup cannot be confirmed
# (ADR-0012 Decisions 1 + 2 -- replaces the plan's fixture-omission test with
# genuine failure injection).
# ---------------------------------------------------------------------------


def test_a_day_is_never_pruned_if_its_rollup_cannot_be_persisted(session, tenant, monkeypatch):
    """THE safety property. Force the source_health persist step to fail and
    prove the day's probes survive untouched, rather than trusting that a
    missing precondition alone implies safety (which is what the plan's own
    test literally checked, contradicting the plan's own Step 3 design that
    rollup_and_prune computes rollups itself)."""

    def _boom(session, record):
        # Simulate a failure AFTER the insert has entered the transaction
        # (e.g. commit failing over a dropped connection), not before it --
        # this is the realistic case where the session is left needing an
        # explicit rollback() before it can be used for anything else,
        # unlike a failure that raises before touching the session at all.
        session.add(record)
        session.flush()
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(retention_module, "_persist_rollup", _boom)

    source = _make_source(session, tenant)
    run = _make_scan_run(session, tenant)
    _probe(session, tenant, source, run, fetched_at=_days_ago(45), changed=False)

    report = rollup_and_prune(tenant.id, session, now=NOW)

    assert report.unchanged_pruned == 0
    assert report.rows_rolled_up == 0
    assert report.skipped_days_missing_rollup == 1
    remaining = session.execute(select(Probe)).scalars().all()
    assert len(remaining) == 1


def test_a_day_with_a_confirmed_rollup_prunes_normally_after_a_prior_failure(
    session, tenant, monkeypatch
):
    """A day that failed to roll up on one call must not be permanently stuck
    -- a later call (persistence now working) must roll it up and prune it."""
    source = _make_source(session, tenant)
    run = _make_scan_run(session, tenant)
    _probe(session, tenant, source, run, fetched_at=_days_ago(45), changed=False)

    def _boom(session, record):
        # Simulate a failure AFTER the insert has entered the transaction
        # (e.g. commit failing over a dropped connection), not before it --
        # this is the realistic case where the session is left needing an
        # explicit rollback() before it can be used for anything else,
        # unlike a failure that raises before touching the session at all.
        session.add(record)
        session.flush()
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(retention_module, "_persist_rollup", _boom)
    first = rollup_and_prune(tenant.id, session, now=NOW)
    assert first.unchanged_pruned == 0

    monkeypatch.undo()
    second = rollup_and_prune(tenant.id, session, now=NOW)
    assert second.unchanged_pruned == 1


def test_candidate_days_are_processed_in_deterministic_sorted_order(session, tenant, monkeypatch):
    """Two source_types with same-day probes are inserted in an order that,
    if processing followed insertion/query order rather than a deterministic
    sort, would come out reversed. Mutation-confirmed: dropping the
    sorted(set(...)) down to a plain list survives every other test in this
    file (SQL DISTINCT already dedupes, so nothing breaks on count alone) but
    fails this one, since only the sort pins the processing order."""
    pricing = _make_source(session, tenant, source_type="pricing")
    careers = _make_source(session, tenant, source_type="careers")
    run = _make_scan_run(session, tenant)
    day = _days_ago(45)
    # Inserted pricing-then-careers -- reverse of alphabetical -- so a
    # non-deterministic (e.g. insertion-order) result would show pricing first.
    _probe(session, tenant, pricing, run, fetched_at=day, changed=False)
    _probe(session, tenant, careers, run, fetched_at=day, changed=False)

    seen_order: list[tuple[str, date]] = []
    original = retention_module.ensure_rollup

    def _spy(tenant_id, source_type, run_date, session):
        seen_order.append((source_type, run_date))
        return original(tenant_id, source_type, run_date, session)

    monkeypatch.setattr(retention_module, "ensure_rollup", _spy)

    rollup_and_prune(tenant.id, session, now=NOW)

    assert seen_order == sorted(seen_order)


# ---------------------------------------------------------------------------
# Batched deletes
# ---------------------------------------------------------------------------


def test_prune_is_batched(session, tenant):
    """A single unbounded DELETE can hold a lock long enough to stall the scan run."""
    source = _make_source(session, tenant)
    run = _make_scan_run(session, tenant)
    day = _days_ago(45)
    for _ in range(2500):
        _probe(session, tenant, source, run, fetched_at=day, changed=False)

    report = rollup_and_prune(tenant.id, session, now=NOW, batch_size=1000)

    assert report.unchanged_pruned == 2500
    assert report.batches >= 3


# ---------------------------------------------------------------------------
# Isolation: source_type, tenant
# ---------------------------------------------------------------------------


def test_source_types_get_independent_rollups_and_pruning(session, tenant):
    careers = _make_source(session, tenant, source_type="careers")
    pricing = _make_source(session, tenant, source_type="pricing")
    run = _make_scan_run(session, tenant)
    day = _days_ago(45)
    _probe(session, tenant, careers, run, fetched_at=day, changed=False)
    _probe(session, tenant, pricing, run, fetched_at=day, changed=False)
    _probe(session, tenant, pricing, run, fetched_at=day, changed=False, succeeded=False)

    report = rollup_and_prune(tenant.id, session, now=NOW)

    assert report.unchanged_pruned == 3
    careers_health = session.execute(
        select(SourceHealthRecord).where(SourceHealthRecord.source_type == "careers")
    ).scalar_one()
    pricing_health = session.execute(
        select(SourceHealthRecord).where(SourceHealthRecord.source_type == "pricing")
    ).scalar_one()
    assert careers_health.fetch_success_rate == 1.0
    assert pricing_health.fetch_success_rate == 0.5


def test_other_tenants_are_never_touched(session, engine):
    t1 = Tenant(slug="tenant-one", name="One")
    t2 = Tenant(slug="tenant-two", name="Two")
    session.add_all([t1, t2])
    session.commit()

    source1 = _make_source(session, t1)
    run1 = _make_scan_run(session, t1)
    _probe(session, t1, source1, run1, fetched_at=_days_ago(45), changed=False)

    source2 = _make_source(session, t2)
    run2 = _make_scan_run(session, t2)
    _probe(session, t2, source2, run2, fetched_at=_days_ago(45), changed=False)

    report = rollup_and_prune(t1.id, session, now=NOW)

    assert report.unchanged_pruned == 1
    remaining = session.execute(select(Probe).where(Probe.tenant_id == t2.id)).scalars().all()
    assert len(remaining) == 1
