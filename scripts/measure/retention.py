"""Probe retention with rollup-before-prune (ADR-0012).

`probes` is the only unbounded table in the schema -- one row per source per
run, forever. `rollup_and_prune` caps it: for every distinct (source_type,
day) old enough to be pruning-eligible, it ensures a `source_health` rollup
exists (creating it via `compute_health` if missing), confirms the rollup
actually landed by re-reading it back, and ONLY THEN deletes the raw probe
rows for a day it has just confirmed. A day whose rollup can't be confirmed
is skipped entirely -- its probes are never touched, regardless of *why* the
rollup couldn't be confirmed. That "verify before delete" ordering, not the
specific failure mode, is the safety property this module exists for.

Two-tier retention: unchanged probes (the bulk, ~85-95%) live 30 days --
`source_health` already records that the source was alive, so the row itself
adds nothing once rolled up. Changed probes (~10%) live 180 days -- the only
per-event forensic record for detection-lag debugging.

Deletes are batched (`SELECT ... LIMIT :batch_size` then `DELETE ... WHERE id
IN (...)`, repeated) rather than one unbounded DELETE, which could hold locks
long enough to stall a concurrent scan run (same reasoning as Task 1.3a's
per-host concurrency caps).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from scripts.measure.health import ProbeOutcome, compute_health
from scripts.storage.models import AccountSource, Probe, SourceHealthRecord

logger = logging.getLogger(__name__)

_UNCHANGED_RETENTION_DAYS = 30
_CHANGED_RETENTION_DAYS = 180


class RetentionReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    # New source_health rows created this run -- a day whose rollup already
    # existed does NOT increment this (ADR-0012 Decision 6), so re-running
    # against the same data reports 0 here (test_rollup_is_idempotent).
    rows_rolled_up: int
    unchanged_pruned: int
    changed_pruned: int
    # Count of DAYS, not probes, whose rollup could not be confirmed --
    # every probe on such a day survives this run untouched.
    skipped_days_missing_rollup: int
    batches: int


def _as_date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _day_bounds(run_date: date) -> tuple[datetime, datetime]:
    start = datetime(run_date.year, run_date.month, run_date.day, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _distinct_candidate_days(
    tenant_id: int, unchanged_cutoff: datetime, session: Session
) -> list[tuple[str, date]]:
    """Every (source_type, day) with at least one probe old enough for ANY
    pruning to apply. The 180-day (changed) cutoff needs no separate scan --
    any day old enough for changed-probe pruning is, by definition, also
    older than the 30-day cutoff scanned here (ADR-0012 Decision 4).
    """
    rows = session.execute(
        select(AccountSource.source_type, func.date(Probe.fetched_at))
        .join(AccountSource, Probe.account_source_id == AccountSource.id)
        .where(Probe.tenant_id == tenant_id, Probe.fetched_at < unchanged_cutoff)
        .distinct()
    ).all()
    return sorted({(source_type, _as_date(raw_date)) for source_type, raw_date in rows})


def _load_outcomes_for_day(
    tenant_id: int, source_type: str, run_date: date, session: Session
) -> list[ProbeOutcome]:
    start, end = _day_bounds(run_date)
    rows = session.execute(
        select(Probe.fetched_at, Probe.content_hash)
        .join(AccountSource, Probe.account_source_id == AccountSource.id)
        .where(
            Probe.tenant_id == tenant_id,
            AccountSource.source_type == source_type,
            Probe.fetched_at >= start,
            Probe.fetched_at < end,
        )
    ).all()
    return [
        ProbeOutcome(
            source_type=source_type, fetched_at=fetched_at, succeeded=content_hash is not None
        )
        for fetched_at, content_hash in rows
    ]


def _find_rollup(
    tenant_id: int, source_type: str, run_date: date, session: Session
) -> SourceHealthRecord | None:
    return session.execute(
        select(SourceHealthRecord).where(
            SourceHealthRecord.tenant_id == tenant_id,
            SourceHealthRecord.source_type == source_type,
            SourceHealthRecord.run_date == run_date,
        )
    ).scalar_one_or_none()


def _persist_rollup(session: Session, record: SourceHealthRecord) -> None:
    """Isolated so tests can inject a persistence failure (ADR-0012 Decision 2)
    without fighting SQLAlchemy internals directly."""
    session.add(record)
    session.flush()
    session.commit()


def _ensure_rollup(tenant_id: int, source_type: str, run_date: date, session: Session) -> bool:
    """Attempt to create today's rollup. Returns True only if newly created --
    NOT a safety guarantee the row exists afterward. Callers must independently
    re-confirm via `_find_rollup` before pruning (ADR-0012 Decision 1)."""
    if _find_rollup(tenant_id, source_type, run_date, session) is not None:
        return False

    outcomes = _load_outcomes_for_day(tenant_id, source_type, run_date, session)
    health = compute_health(outcomes, source_type=source_type, run_date=run_date)
    record = SourceHealthRecord(
        tenant_id=tenant_id,
        source_type=source_type,
        run_date=run_date,
        fetch_success_rate=health.fetch_success_rate,
        parse_success_rate=health.parse_success_rate,
        zero_result_rate=health.zero_result_rate,
        sample_size=health.sample_size,
    )
    try:
        _persist_rollup(session, record)
        return True
    except IntegrityError:
        # Another writer already created this day's rollup (Decision 3's
        # select-then-insert race backstop) -- not a failure.
        session.rollback()
        return False
    except Exception:
        logger.error(
            "failed to persist source_health rollup",
            extra={"tenant_id": tenant_id, "source_type": source_type, "run_date": str(run_date)},
        )
        session.rollback()
        return False


def _prune_day(
    tenant_id: int,
    source_type: str,
    run_date: date,
    *,
    changed: bool,
    cutoff: datetime,
    session: Session,
    batch_size: int,
) -> tuple[int, int]:
    start, end = _day_bounds(run_date)
    total = 0
    batches = 0
    while True:
        ids = list(
            session.execute(
                select(Probe.id)
                .join(AccountSource, Probe.account_source_id == AccountSource.id)
                .where(
                    Probe.tenant_id == tenant_id,
                    AccountSource.source_type == source_type,
                    Probe.fetched_at >= start,
                    Probe.fetched_at < end,
                    Probe.changed.is_(changed),
                    Probe.fetched_at < cutoff,
                )
                .limit(batch_size)
            )
            .scalars()
            .all()
        )
        if not ids:
            break
        session.execute(delete(Probe).where(Probe.id.in_(ids)))
        session.commit()
        total += len(ids)
        batches += 1
    return total, batches


def rollup_and_prune(
    tenant_id: int, session: Session, now: datetime, *, batch_size: int = 1000
) -> RetentionReport:
    unchanged_cutoff = now - timedelta(days=_UNCHANGED_RETENTION_DAYS)
    changed_cutoff = now - timedelta(days=_CHANGED_RETENTION_DAYS)

    candidate_days = _distinct_candidate_days(tenant_id, unchanged_cutoff, session)

    rows_rolled_up = 0
    skipped_days = 0
    confirmed_days: list[tuple[str, date]] = []

    for source_type, run_date in candidate_days:
        if _ensure_rollup(tenant_id, source_type, run_date, session):
            rows_rolled_up += 1
        if _find_rollup(tenant_id, source_type, run_date, session) is not None:
            confirmed_days.append((source_type, run_date))
        else:
            skipped_days += 1

    unchanged_pruned = 0
    changed_pruned = 0
    batches = 0

    for source_type, run_date in confirmed_days:
        n, b = _prune_day(
            tenant_id,
            source_type,
            run_date,
            changed=False,
            cutoff=unchanged_cutoff,
            session=session,
            batch_size=batch_size,
        )
        unchanged_pruned += n
        batches += b

        n2, b2 = _prune_day(
            tenant_id,
            source_type,
            run_date,
            changed=True,
            cutoff=changed_cutoff,
            session=session,
            batch_size=batch_size,
        )
        changed_pruned += n2
        batches += b2

    return RetentionReport(
        rows_rolled_up=rows_rolled_up,
        unchanged_pruned=unchanged_pruned,
        changed_pruned=changed_pruned,
        skipped_days_missing_rollup=skipped_days,
        batches=batches,
    )
