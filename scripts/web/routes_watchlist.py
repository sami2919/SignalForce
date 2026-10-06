"""Watchlist: up to MAX_WATCHLIST target domains per tenant, watched daily."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
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


def _rows(tenant_id: int, session: Session) -> list[dict[str, object]]:
    active = (
        select(AccountSource.account_id, func.count().label("n"))
        .where(AccountSource.tenant_id == tenant_id, AccountSource.active.is_(True))
        .group_by(AccountSource.account_id)
        .subquery()
    )
    stmt = (
        select(Account.domain, func.coalesce(active.c.n, 0))
        .outerjoin(active, active.c.account_id == Account.id)
        .where(Account.tenant_id == tenant_id)
        .order_by(Account.domain)
    )
    return [{"domain": d, "sources": n} for d, n in session.execute(stmt).all()]


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
    try:
        asyncio.run(resolve_and_store(tenant_id, domains))
    except Exception as exc:  # noqa: BLE001 -- a background failure must never surface as a 500
        logger.error("watchlist resolution failed", extra={"tenant_id": tenant_id, "error": str(exc)})


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
        existing = {r["domain"] for r in _rows(invite.tenant_id, session)}
    new = [d for d in wanted if d not in existing]
    if len(existing) + len(new) > MAX_WATCHLIST:
        return _page(request, invite, f"A watchlist holds at most {MAX_WATCHLIST} domains.", 422)
    refused = _refused(new)
    if refused:
        return _page(request, invite, "Refused: " + "; ".join(refused), 422)
    with get_session() as session:
        for domain in new:
            ensure_account(invite.tenant_id, domain, session)
    if new:
        background.add_task(_resolve_in_background, invite.tenant_id, new)
    return RedirectResponse("/watchlist", status_code=303)
