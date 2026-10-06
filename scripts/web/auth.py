"""Invite-code authentication: hashed codes in Postgres, identity in a signed session cookie."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import select

from scripts.storage.models import Invite
from scripts.storage.session import get_session

SESSION_KEY = "invite_id"


@dataclass(frozen=True)
class InviteIdentity:
    """Who is making the request. A plain value so it is safe after the DB session closes."""

    id: int
    label: str
    tenant_id: int | None
    is_owner: bool


class LoginRequired(Exception):
    """Raised by require_invite; the app turns it into a redirect to /login."""


def new_code() -> str:
    return secrets.token_urlsafe(16)


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _identity(invite: Invite) -> InviteIdentity:
    return InviteIdentity(
        id=invite.id, label=invite.label, tenant_id=invite.tenant_id, is_owner=invite.is_owner
    )


def authenticate(code: str) -> InviteIdentity | None:
    """Return the identity for a live invite code and record its use; None if unknown or revoked."""
    if not code.strip():
        return None
    with get_session() as session:
        invite = session.scalar(
            select(Invite).where(Invite.code_hash == hash_code(code), Invite.revoked_at.is_(None))
        )
        if invite is None:
            return None
        invite.last_used_at = datetime.now(timezone.utc)
        return _identity(invite)


def load_identity(invite_id: int) -> InviteIdentity | None:
    with get_session() as session:
        invite = session.scalar(
            select(Invite).where(Invite.id == invite_id, Invite.revoked_at.is_(None))
        )
        return _identity(invite) if invite is not None else None


def require_invite(request: Request) -> InviteIdentity:
    """FastAPI dependency: the signed-in identity, or LoginRequired."""
    invite_id = request.session.get(SESSION_KEY)
    identity = load_identity(invite_id) if isinstance(invite_id, int) else None
    if identity is None:
        request.session.clear()
        raise LoginRequired()
    return identity
