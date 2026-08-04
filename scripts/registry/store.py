"""Persist resolution reports into the URL registry.

Sync, takes a Session — see docs/decisions/0005-watch-layer-concurrency-and-
persistence.md, Decision 3: SQLAlchemy stays sync everywhere in this project.

Upsert semantics on (account_id, source_type), the unique constraint from
Task 0.1. An existing row's `url`, `resolved_at`, and `resolution_method` are
refreshed; `last_hash`, `last_fetched_at`, and `last_changed_at` are never
touched here — those belong to the watch pass (scripts/watch/runner.py), and
resolution runs independently of it (e.g. re-resolving a dead source). If
resolution touched them, every re-resolved source would report a spurious
change on the next watch pass.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.registry.models import ResolutionReport
from scripts.storage.models import Account, AccountSource, Tenant

logger = logging.getLogger(__name__)


class StoreResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    created: int = 0
    updated: int = 0
    deactivated: int = 0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_tenant(slug: str, name: str, session: Session) -> int:
    """Idempotent: returns the existing tenant's id if the slug is already registered."""
    existing = session.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()
    if existing is not None:
        return existing.id
    tenant = Tenant(slug=slug, name=name)
    session.add(tenant)
    session.commit()
    return tenant.id


def ensure_account(tenant_id: int, domain: str, session: Session) -> int:
    """Idempotent per tenant. The same domain under a different tenant is a separate row."""
    existing = session.execute(
        select(Account).where(Account.tenant_id == tenant_id, Account.domain == domain)
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id
    account = Account(tenant_id=tenant_id, domain=domain, name=domain)
    session.add(account)
    session.commit()
    return account.id


def store_resolution(tenant_id: int, report: ResolutionReport, session: Session) -> StoreResult:
    """Upsert account_sources rows from a resolution report.

    Only ResolvedSource entries create/update rows. SourceAttempt failures
    are logged at INFO and otherwise produce no row — absence is diagnostic
    (see scripts/registry/models.py's ResolutionOutcome), not silence.
    """
    account_id = ensure_account(tenant_id, report.domain, session)

    for attempt in report.attempts:
        if attempt.outcome != "resolved":
            logger.info(
                "source not resolved; no row written",
                extra={
                    "domain": report.domain,
                    "source_type": attempt.source_type,
                    "outcome": attempt.outcome,
                },
            )

    created = 0
    updated = 0
    deactivated = 0

    for source in report.sources:
        existing = session.execute(
            select(AccountSource).where(
                AccountSource.account_id == account_id,
                AccountSource.source_type == source.source_type,
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(
                AccountSource(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    source_type=source.source_type,
                    url=source.url,
                    resolved_at=_utcnow(),
                    resolution_method=source.method,
                )
            )
            created += 1
            continue

        existing.url = source.url
        existing.resolved_at = _utcnow()
        existing.resolution_method = source.method
        if not existing.active:
            # ADR-0004 Decision 6: re-resolution recovery path. A source that
            # resolves again after going dead is worth watching again.
            existing.active = True
            existing.consecutive_failures = 0
        updated += 1

    session.commit()
    return StoreResult(created=created, updated=updated, deactivated=deactivated)
