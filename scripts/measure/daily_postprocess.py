"""Runs after the daily watch pass: today's health rollup + anomaly check per
source_type, a trailing recall report, and retention pruning (ADR-0013).

Each stage is independently wrapped (Decision 2): a failure in one must not
prevent the others from running, and none of them touch the `scan_runs` row
`run_watch_pass` already finalized before this runs -- the watch pass's own
success is never retroactively affected by a post-processing failure.
`run_daily_postprocess`'s return value tells the caller whether ANYTHING
failed (for the exit code), but every stage that succeeded before a later
one failed has already run and logged its own result.

Order: health (so today's rollup exists and anomalies are visible as early
as possible) -> recall (a read against Probe/HoldoutScan, unaffected by
anything retention is about to prune, since the 7-day recall window sits
well inside the 30-day retention floor) -> retention (old-data cleanup,
last on purpose -- pruning before measuring would be backwards).
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from scripts.measure import retention as retention_module
from scripts.measure.health import detect_anomaly
from scripts.measure.recall_report import compute_recall_for_tenant
from scripts.measure.retention import rollup_and_prune
from scripts.storage.models import AccountSource, SourceHealthRecord

logger = logging.getLogger(__name__)

_ANOMALY_TRAILING_DAYS = 14


class PostprocessReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    health_ok: bool
    recall_ok: bool
    retention_ok: bool

    @property
    def all_ok(self) -> bool:
        return self.health_ok and self.recall_ok and self.retention_ok


def _distinct_active_source_types(tenant_id: int, session: Session) -> list[str]:
    rows = (
        session.execute(
            select(AccountSource.source_type)
            .where(AccountSource.tenant_id == tenant_id, AccountSource.active.is_(True))
            .distinct()
        )
        .scalars()
        .all()
    )
    return sorted(set(rows))


def _load_trailing_fetch_success_rates(
    tenant_id: int, source_type: str, before: date, session: Session, *, limit: int
) -> list[float]:
    rows = (
        session.execute(
            select(SourceHealthRecord.fetch_success_rate)
            .where(
                SourceHealthRecord.tenant_id == tenant_id,
                SourceHealthRecord.source_type == source_type,
                SourceHealthRecord.run_date < before,
                SourceHealthRecord.fetch_success_rate.is_not(None),
            )
            .order_by(SourceHealthRecord.run_date.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(rows)


def _run_health_stage(tenant_id: int, session: Session, now: datetime) -> bool:
    today = now.date()
    try:
        for source_type in _distinct_active_source_types(tenant_id, session):
            retention_module.ensure_rollup(tenant_id, source_type, today, session)
            record = retention_module.find_rollup(tenant_id, source_type, today, session)
            if record is None or record.fetch_success_rate is None:
                continue

            trailing = _load_trailing_fetch_success_rates(
                tenant_id, source_type, today, session, limit=_ANOMALY_TRAILING_DAYS
            )
            anomaly = detect_anomaly(
                record.fetch_success_rate,
                trailing,
                metric_name="fetch_success_rate",
                source_type=source_type,
                direction="low_is_bad",
            )
            if anomaly is not None:
                logger.warning(
                    "source health anomaly detected",
                    extra={
                        "tenant_id": tenant_id,
                        "source_type": anomaly.source_type,
                        "metric": anomaly.metric,
                        "current": anomaly.current,
                        "baseline_mean": anomaly.baseline_mean,
                        "sigma": anomaly.sigma,
                        "detail": anomaly.message,
                    },
                )
            else:
                logger.info(
                    "source health computed",
                    extra={
                        "tenant_id": tenant_id,
                        "source_type": source_type,
                        "fetch_success_rate": record.fetch_success_rate,
                        "sample_size": record.sample_size,
                    },
                )
        return True
    except Exception:
        logger.error("health stage failed", extra={"tenant_id": tenant_id}, exc_info=True)
        return False


def _run_recall_stage(tenant_id: int, session: Session, now: datetime) -> bool:
    try:
        report = compute_recall_for_tenant(tenant_id, session, now)
        logger.info(
            "recall report computed",
            extra={
                "tenant_id": tenant_id,
                "recall": report.recall,
                "deep_count": report.deep_count,
                "caught_count": report.caught_count,
                "missed_count": report.missed_count,
                "p50_lag_hours": report.p50_lag_hours,
                "p95_lag_hours": report.p95_lag_hours,
                "extraneous_watch_count": report.extraneous_watch_count,
            },
        )
        return True
    except Exception:
        logger.error("recall stage failed", extra={"tenant_id": tenant_id}, exc_info=True)
        return False


def _run_retention_stage(tenant_id: int, session: Session, now: datetime) -> bool:
    try:
        report = rollup_and_prune(tenant_id, session, now)
        logger.info(
            "retention run completed",
            extra={
                "tenant_id": tenant_id,
                "rows_rolled_up": report.rows_rolled_up,
                "unchanged_pruned": report.unchanged_pruned,
                "changed_pruned": report.changed_pruned,
                "skipped_days_missing_rollup": report.skipped_days_missing_rollup,
                "batches": report.batches,
            },
        )
        return True
    except Exception:
        logger.error("retention stage failed", extra={"tenant_id": tenant_id}, exc_info=True)
        return False


def run_daily_postprocess(tenant_id: int, session: Session, now: datetime) -> PostprocessReport:
    health_ok = _run_health_stage(tenant_id, session, now)
    recall_ok = _run_recall_stage(tenant_id, session, now)
    retention_ok = _run_retention_stage(tenant_id, session, now)
    return PostprocessReport(health_ok=health_ok, recall_ok=recall_ok, retention_ok=retention_ok)
