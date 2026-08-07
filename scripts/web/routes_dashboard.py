"""Read-only dashboard: accounts, account detail, source health, run history.

ADR-0018 is the spec. Four pages, Jinja2 + HTMX, no build step (ADR-0002
Decision 2). Every route scopes to the single tenant named by TENANT_SLUG,
the same env var every CLI entrypoint in this codebase already reads
(ADR-0018 Decision 2) -- no tenant selector, since ADR-0001 Decision 4
deferred auth entirely and a selector with no auth in front of it would let
anyone URL-guess their way into another tenant's data.

Never raises on missing data: an unset TENANT_SLUG, a tenant with no rows
yet, or a requested account_id that doesn't exist all render a normal page
(or a 404 for the single case where "this specific thing wasn't found" is
the correct HTTP semantics) -- never a 500, matching ADR-0002's "health
endpoints must never raise" posture extended to a human-facing page.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scripts.measure.recall_report import compute_recall_for_tenant
from scripts.scoring.engine import score_account, zero_out
from scripts.scoring.wiring import load_signal_inputs
from scripts.storage.models import (
    Account,
    AccountSource,
    ScanRun,
    Score,
    SignalEvent,
    SourceHealthRecord,
    Tenant,
)
from scripts.storage.session import get_session

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

_RECENT_SIGNAL_WINDOW_DAYS = 30
_SIGNAL_TIMELINE_LIMIT = 50
_RUN_HISTORY_LIMIT = 30
_HEALTH_TRAILING_DAYS = 14


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tenant_id(session: Session) -> int | None:
    slug = os.environ.get("TENANT_SLUG")
    if not slug:
        return None
    return session.execute(select(Tenant.id).where(Tenant.slug == slug)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# /dashboard -- top-scored accounts
# ---------------------------------------------------------------------------


def _load_latest_scores(tenant_id: int, session: Session) -> dict[int, Score]:
    latest_ids = (
        select(func.max(Score.id)).where(Score.tenant_id == tenant_id).group_by(Score.account_id)
    )
    rows = session.execute(select(Score).where(Score.id.in_(latest_ids))).scalars().all()
    return {s.account_id: s for s in rows}


def _load_recent_signal_types(
    tenant_id: int, window_start: datetime, session: Session
) -> dict[int, list[str]]:
    rows = session.execute(
        select(SignalEvent.account_id, SignalEvent.signal_type)
        .where(SignalEvent.tenant_id == tenant_id, SignalEvent.detected_at >= window_start)
        .distinct()
    ).all()
    out: dict[int, list[str]] = {}
    for account_id, signal_type in rows:
        out.setdefault(account_id, []).append(signal_type)
    for signal_types in out.values():
        signal_types.sort()
    return out


def _load_last_changed(tenant_id: int, session: Session) -> dict[int, datetime | None]:
    rows = session.execute(
        select(AccountSource.account_id, func.max(AccountSource.last_changed_at))
        .where(AccountSource.tenant_id == tenant_id)
        .group_by(AccountSource.account_id)
    ).all()
    return dict(rows)


def _load_account_rows(tenant_id: int, session: Session) -> list[dict[str, object]]:
    accounts = (
        session.execute(select(Account).where(Account.tenant_id == tenant_id)).scalars().all()
    )
    latest_scores = _load_latest_scores(tenant_id, session)
    recent_signals = _load_recent_signal_types(
        tenant_id, _utcnow() - timedelta(days=_RECENT_SIGNAL_WINDOW_DAYS), session
    )
    last_changed = _load_last_changed(tenant_id, session)

    rows = []
    for account in accounts:
        score = latest_scores.get(account.id)
        rows.append(
            {
                "account": account,
                "score": score.score if score is not None else None,
                "signal_types": recent_signals.get(account.id, []),
                "last_changed_at": last_changed.get(account.id),
            }
        )
    # Scored accounts first (highest score first); unscored accounts last.
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0.0)))
    return rows


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    # Rendered INSIDE the session block, not after: get_session()'s commit
    # expires every loaded ORM attribute by default (expire_on_commit=True),
    # and Jinja2's TemplateResponse renders synchronously in __init__ -- if
    # rendering happened after the `with` block closed the session, any
    # attribute the template touches that wasn't already materialized would
    # raise DetachedInstanceError. Reproduced directly before this fix.
    with get_session() as session:
        tenant_id = _tenant_id(session)
        rows = _load_account_rows(tenant_id, session) if tenant_id is not None else []
        return templates.TemplateResponse(
            request, "accounts.html", {"rows": rows, "tenant_configured": tenant_id is not None}
        )


# ---------------------------------------------------------------------------
# /dashboard/account/{id} -- full trace, timeline, sources, zero-out table
# ---------------------------------------------------------------------------


def _load_account_detail(
    tenant_id: int, account_id: int, session: Session
) -> dict[str, object] | None:
    account = session.execute(
        select(Account).where(Account.id == account_id, Account.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if account is None:
        return None

    latest_score = session.execute(
        select(Score)
        .where(Score.tenant_id == tenant_id, Score.account_id == account_id)
        .order_by(Score.computed_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    signal_events = (
        session.execute(
            select(SignalEvent)
            .where(SignalEvent.tenant_id == tenant_id, SignalEvent.account_id == account_id)
            .order_by(SignalEvent.detected_at.desc())
            .limit(_SIGNAL_TIMELINE_LIMIT)
        )
        .scalars()
        .all()
    )

    sources = (
        session.execute(
            select(AccountSource).where(
                AccountSource.tenant_id == tenant_id, AccountSource.account_id == account_id
            )
        )
        .scalars()
        .all()
    )

    zero_out_rows = _compute_zero_out_table(tenant_id, account_id, session)

    return {
        "account": account,
        "score": latest_score,
        "signal_events": signal_events,
        "sources": sources,
        "zero_out_rows": zero_out_rows,
    }


def _compute_zero_out_table(
    tenant_id: int, account_id: int, session: Session
) -> list[dict[str, object]]:
    """One row per distinct signal_type present, showing the account's real
    score next to its score with that signal_type removed -- Sami's "zero
    out which signal one by one" (ADR-0015). Reuses scoring/wiring.py's own
    signal loader (ADR-0018 Decision 3) so this can never silently drift
    from what run_scoring_stage actually scored."""
    now = _utcnow()
    window_start = now - timedelta(days=90)  # matches ADR-0016 Decision 2's scoring window
    signals = load_signal_inputs(tenant_id, account_id, window_start, session, warned=set())
    if not signals:
        return []

    full = score_account(signals, now=now)
    distinct_types = sorted({s.signal_type for s in signals})
    return [
        {
            "signal_type": signal_type,
            "full_score": full.score,
            "without_score": zero_out(signals, signal_type, now=now).score,
        }
        for signal_type in distinct_types
    ]


@router.get("/dashboard/account/{account_id}", response_class=HTMLResponse)
def account_detail(request: Request, account_id: int) -> HTMLResponse:
    with get_session() as session:
        tenant_id = _tenant_id(session)
        detail = (
            _load_account_detail(tenant_id, account_id, session) if tenant_id is not None else None
        )
        if detail is None:
            raise HTTPException(status_code=404, detail="Account not found")
        return templates.TemplateResponse(request, "account_detail.html", detail)


# ---------------------------------------------------------------------------
# /dashboard/health -- recall, detection lag, per-source health trend
# ---------------------------------------------------------------------------


def _load_health_rows(tenant_id: int, session: Session) -> list[dict[str, object]]:
    cutoff = (_utcnow() - timedelta(days=_HEALTH_TRAILING_DAYS)).date()
    rows = (
        session.execute(
            select(SourceHealthRecord)
            .where(
                SourceHealthRecord.tenant_id == tenant_id,
                SourceHealthRecord.run_date >= cutoff,
            )
            .order_by(SourceHealthRecord.source_type, SourceHealthRecord.run_date.desc())
        )
        .scalars()
        .all()
    )
    by_source_type: dict[str, list[SourceHealthRecord]] = {}
    for row in rows:
        by_source_type.setdefault(row.source_type, []).append(row)

    return [
        {
            "source_type": source_type,
            "latest": records[0],
            "trend": records,
        }
        for source_type, records in sorted(by_source_type.items())
    ]


@router.get("/dashboard/health", response_class=HTMLResponse)
def health(request: Request) -> HTMLResponse:
    with get_session() as session:
        tenant_id = _tenant_id(session)
        if tenant_id is None:
            recall_report = None
            health_rows: list[dict[str, object]] = []
        else:
            recall_report = compute_recall_for_tenant(tenant_id, session, _utcnow())
            health_rows = _load_health_rows(tenant_id, session)
        return templates.TemplateResponse(
            request, "health.html", {"recall": recall_report, "health_rows": health_rows}
        )


# ---------------------------------------------------------------------------
# /dashboard/runs -- scan run history
# ---------------------------------------------------------------------------


def _load_runs(tenant_id: int, session: Session) -> list[dict[str, object]]:
    runs = (
        session.execute(
            select(ScanRun)
            .where(ScanRun.tenant_id == tenant_id)
            .order_by(ScanRun.started_at.desc())
            .limit(_RUN_HISTORY_LIMIT)
        )
        .scalars()
        .all()
    )
    rows = []
    for run in runs:
        duration_s = None
        if run.started_at is not None and run.finished_at is not None:
            duration_s = (run.finished_at - run.started_at).total_seconds()
        change_rate = None
        if run.sources_probed:
            change_rate = run.changes_detected / run.sources_probed
        rows.append({"run": run, "duration_s": duration_s, "change_rate": change_rate})
    return rows


@router.get("/dashboard/runs", response_class=HTMLResponse)
def runs(request: Request) -> HTMLResponse:
    with get_session() as session:
        tenant_id = _tenant_id(session)
        rows = _load_runs(tenant_id, session) if tenant_id is not None else []
        return templates.TemplateResponse(request, "runs.html", {"rows": rows})
