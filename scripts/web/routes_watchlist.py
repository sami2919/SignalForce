"""Watchlist: up to MAX_WATCHLIST target domains per tenant, watched daily.

Each account records its last resolution outcome in
`account_metadata["resolution"]` ({"outcome", "at"}) so the page never shows
"resolving…" forever: a domain with no active sources whose outcome is not a
fresh pending is re-queued when it is added again.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scripts.net.guard import BlockedAddress, assert_public_host
from scripts.registry.domains import InvalidDomain, parse_domain_list
from scripts.registry.store import ensure_account
from scripts.storage.models import Account, AccountSource
from scripts.storage.session import get_session
from scripts.watch.runner import resolve_and_store
from scripts.web.auth import InviteIdentity, require_invite

logger = logging.getLogger(__name__)
router = APIRouter(tags=["watchlist"])
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

MAX_WATCHLIST = 25
RESOLUTION_KEY = "resolution"
STALE_PENDING_AFTER = timedelta(minutes=15)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _state(sources: int, metadata: dict | None, now: datetime) -> str:
    """What the page shows for a row.

    "sources" (>=1 active source), "no_sources", "failed", "pending" (fresh,
    under STALE_PENDING_AFTER), "stale" (pending too long) or "unknown" (no
    outcome recorded). A "resolved" outcome whose sources were all since
    deactivated shows as "no_sources".
    """
    if sources:
        return "sources"
    resolution = (metadata or {}).get(RESOLUTION_KEY) or {}
    outcome = resolution.get("outcome")
    if outcome in ("no_sources", "failed"):
        return outcome
    if outcome == "resolved":
        return "no_sources"
    if outcome != "pending":
        return "unknown"
    try:
        at = datetime.fromisoformat(resolution["at"])
    except (KeyError, TypeError, ValueError):
        return "stale"
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return "stale" if now - at > STALE_PENDING_AFTER else "pending"


def _needs_requeue(row: dict[str, object]) -> bool:
    """Zero active sources and not a fresh pending: adding it again retries."""
    return row["state"] not in ("sources", "pending")


def _record_outcome(tenant_id: int, domains: list[str], outcome: str | None, session: Session) -> None:
    """Write {"outcome", "at"} for each domain. outcome=None derives it from active sources.

    Assigns a NEW dict so SQLAlchemy sees the change on the JSON column, and
    keeps every other metadata key.
    """
    at = _utcnow().isoformat()
    accounts = session.scalars(
        select(Account).where(Account.tenant_id == tenant_id, Account.domain.in_(domains))
    ).all()
    for account in accounts:
        value = outcome
        if value is None:
            active = session.scalar(
                select(func.count()).select_from(AccountSource).where(
                    AccountSource.account_id == account.id, AccountSource.active.is_(True)
                )
            )
            value = "resolved" if active else "no_sources"
        account.account_metadata = {
            **(account.account_metadata or {}),
            RESOLUTION_KEY: {"outcome": value, "at": at},
        }
    session.commit()


def _rows(tenant_id: int, session: Session) -> list[dict[str, object]]:
    active = (
        select(AccountSource.account_id, func.count().label("n"))
        .where(AccountSource.tenant_id == tenant_id, AccountSource.active.is_(True))
        .group_by(AccountSource.account_id)
        .subquery()
    )
    stmt = (
        select(Account.domain, Account.account_metadata, func.coalesce(active.c.n, 0))
        .outerjoin(active, active.c.account_id == Account.id)
        .where(Account.tenant_id == tenant_id)
        .order_by(Account.domain)
    )
    now = _utcnow()
    rows = []
    for domain, metadata, n in session.execute(stmt).all():
        rows.append({"domain": domain, "sources": n, "state": _state(n, metadata, now)})
    return rows


def _page(request: Request, invite: InviteIdentity, error: str = "", status: int = 200) -> HTMLResponse:
    rows: list[dict[str, object]] = []
    if invite.tenant_id is not None:
        with get_session() as session:
            rows = _rows(invite.tenant_id, session)
    return templates.TemplateResponse(
        request,
        "watchlist.html",
        {"rows": rows, "error": error, "has_tenant": invite.tenant_id is not None, "max": MAX_WATCHLIST},
        status_code=status,
    )


def _resolve_in_background(tenant_id: int, domains: list[str]) -> None:
    outcome: str | None = None  # derived from active sources after a clean run
    try:
        asyncio.run(resolve_and_store(tenant_id, domains))
    except Exception as exc:  # noqa: BLE001 -- a background failure must never surface as a 500
        outcome = "failed"
        logger.error(
            "watchlist resolution failed",
            extra={"tenant_id": tenant_id, "error_type": type(exc).__name__},
        )
    try:
        with get_session() as session:
            _record_outcome(tenant_id, domains, outcome, session)
    except Exception as exc:  # noqa: BLE001 -- same: never a 500; a stale pending re-queues later
        logger.error(
            "recording watchlist resolution outcome failed",
            extra={"tenant_id": tenant_id, "error_type": type(exc).__name__},
        )


def _refused(domains: list[str]) -> list[str]:
    refused = []
    for domain in domains:
        try:
            assert_public_host(domain)
        except BlockedAddress as exc:
            refused.append(f"{domain}: {exc}")
    return refused


@router.get("/watchlist", response_class=HTMLResponse)
def watchlist(request: Request, invite: InviteIdentity = Depends(require_invite)) -> HTMLResponse:
    return _page(request, invite)


@router.post("/watchlist", response_model=None)
def add_domains(
    request: Request,
    background: BackgroundTasks,
    domains: str = Form(""),
    invite: InviteIdentity = Depends(require_invite),
) -> HTMLResponse | RedirectResponse:
    if invite.tenant_id is None:
        return _page(request, invite, "Your invite has no workspace yet.", 403)
    try:
        wanted = parse_domain_list(domains, limit=MAX_WATCHLIST)
    except InvalidDomain as exc:
        return _page(request, invite, str(exc), 422)
    with get_session() as session:
        existing = {r["domain"]: r for r in _rows(invite.tenant_id, session)}
    new = [d for d in wanted if d not in existing]
    requeue = [d for d in wanted if d in existing and _needs_requeue(existing[d])]
    if len(existing) + len(new) > MAX_WATCHLIST:
        return _page(request, invite, f"A watchlist holds at most {MAX_WATCHLIST} domains.", 422)
    refused = _refused(new + requeue)
    if refused:
        return _page(request, invite, "Refused: " + "; ".join(refused), 422)
    with get_session() as session:
        added = []
        for domain in new:
            try:
                ensure_account(invite.tenant_id, domain, session)
            except IntegrityError:
                # A concurrent POST inserted it first (tenant_id, domain unique):
                # already added, and that request queued its resolution.
                session.rollback()
                continue
            added.append(domain)
        queued = added + requeue
        if queued:
            _record_outcome(invite.tenant_id, queued, "pending", session)
    if queued:
        background.add_task(_resolve_in_background, invite.tenant_id, queued)
    return RedirectResponse("/watchlist", status_code=303)
