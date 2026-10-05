"""Turns Probe/HoldoutScan rows into DetectedChange lists over a bounded window
and calls compute_recall (ADR-0013 Decision 3).

`compute_recall` (Task 3.2) has never had a caller -- it's a pure function
over `DetectedChange` lists, and nothing in this codebase loaded those from
real data until now. The two sides must be the SAME account population
(ADR-0010 Decision 1's "doubly instrumented" holdout), so this reuses
`select_holdout` with the identical `seed`/`holdout_size` `run_deep_scan`
uses -- a different seed here would silently compare mismatched populations.

The window is bounded (default 7 days), not "all history": ADR-0010's own
Consequences section warns that `compute_recall`'s per-key sequential
matching requires a genuinely coherent measurement window, and an
ever-growing window both violates that and makes the query cost unbounded.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.measure.holdout import load_active_account_ids, select_holdout
from scripts.measure.lag import DetectedChange, RecallReport, compute_recall
from scripts.storage.models import AccountSource, HoldoutScan, Probe

_DEFAULT_WINDOW_DAYS = 7
_DEFAULT_HOLDOUT_SIZE = 5
_DEFAULT_SEED = 42


def _load_watch_changes(
    tenant_id: int, holdout_account_ids: list[int], window_start: datetime, session: Session
) -> list[DetectedChange]:
    rows = session.execute(
        select(AccountSource.account_id, AccountSource.source_type, Probe.fetched_at)
        .join(AccountSource, Probe.account_source_id == AccountSource.id)
        .where(
            Probe.tenant_id == tenant_id,
            AccountSource.account_id.in_(holdout_account_ids),
            Probe.changed.is_(True),
            Probe.fetched_at >= window_start,
        )
    ).all()
    return [
        DetectedChange(account_id=account_id, source_type=source_type, detected_at=fetched_at)
        for account_id, source_type, fetched_at in rows
    ]


def _load_deep_changes(
    tenant_id: int, holdout_account_ids: list[int], window_start: datetime, session: Session
) -> list[DetectedChange]:
    rows = session.execute(
        select(AccountSource.account_id, AccountSource.source_type, HoldoutScan.fetched_at)
        .join(AccountSource, HoldoutScan.account_source_id == AccountSource.id)
        .where(
            HoldoutScan.tenant_id == tenant_id,
            AccountSource.account_id.in_(holdout_account_ids),
            HoldoutScan.changed.is_(True),
            HoldoutScan.fetched_at >= window_start,
        )
    ).all()
    return [
        DetectedChange(account_id=account_id, source_type=source_type, detected_at=fetched_at)
        for account_id, source_type, fetched_at in rows
    ]


def compute_recall_for_tenant(
    tenant_id: int,
    session: Session,
    now: datetime,
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    holdout_size: int = _DEFAULT_HOLDOUT_SIZE,
    seed: int = _DEFAULT_SEED,
) -> RecallReport:
    account_ids = load_active_account_ids(tenant_id, session)
    holdout_account_ids = select_holdout(account_ids, size=holdout_size, seed=seed)

    if not holdout_account_ids:
        return compute_recall([], [])

    window_start = now - timedelta(days=window_days)
    deep_changes = _load_deep_changes(tenant_id, holdout_account_ids, window_start, session)
    watch_changes = _load_watch_changes(tenant_id, holdout_account_ids, window_start, session)
    return compute_recall(deep_changes, watch_changes)
