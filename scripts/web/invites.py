"""Manage invite codes: python -m scripts.web.invites create|list|revoke."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.registry.store import ensure_tenant
from scripts.storage.models import Invite, Tenant
from scripts.storage.session import get_session
from scripts.web.auth import hash_code, new_code


def create_invite(
    session: Session, label: str, tenant_slug: str | None = None, is_owner: bool = False
) -> str:
    """Create an invite and return the plaintext code. It cannot be recovered later."""
    tenant_id = ensure_tenant(tenant_slug, tenant_slug, session) if tenant_slug else None
    code = new_code()
    session.add(
        Invite(code_hash=hash_code(code), label=label, tenant_id=tenant_id, is_owner=is_owner)
    )
    session.flush()
    return code


def revoke_invite(session: Session, label: str) -> int:
    """Revoke every live invite with this label. Returns how many were revoked."""
    now = datetime.now(timezone.utc)
    live = session.scalars(
        select(Invite).where(Invite.label == label, Invite.revoked_at.is_(None))
    ).all()
    for invite in live:
        invite.revoked_at = now
    session.flush()
    return len(live)


def _list(session: Session) -> list[str]:
    rows = session.execute(
        select(Invite, Tenant.slug).outerjoin(Tenant, Tenant.id == Invite.tenant_id).order_by(Invite.id)
    ).all()
    return [
        f"{i.id}\t{i.label}\ttenant={slug or '-'}\towner={i.is_owner}\t"
        f"last_used={i.last_used_at.isoformat() if i.last_used_at else '-'}\t"
        f"revoked={'yes' if i.revoked_at else 'no'}"
        for i, slug in rows
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.web.invites")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--label", required=True)
    create.add_argument("--tenant-slug")
    create.add_argument("--owner", action="store_true")
    sub.add_parser("list")
    revoke = sub.add_parser("revoke")
    revoke.add_argument("--label", required=True)
    args = parser.parse_args(argv)

    with get_session() as session:
        if args.command == "create":
            code = create_invite(session, args.label, args.tenant_slug, args.owner)
            print(f"Invite code for {args.label} (shown once): {code}")
        elif args.command == "list":
            print("\n".join(_list(session)))
        else:
            print(f"revoked {revoke_invite(session, args.label)} invite(s) for {args.label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
