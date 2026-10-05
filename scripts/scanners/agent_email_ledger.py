"""SQLAlchemy-backed ledger for scripts/scanners/agent_email_scanner.py.

Implements the LedgerPort protocol defined in agent_email_scanner.py against
scripts.storage.models.RepoObservation. Kept separate from the scanner module
so scanner unit tests never touch a Session (ADR-0006, Task 2.2 brief:
"Keep the DB out of scanner unit tests").
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.scanners.agent_email_scanner import RepoObservationRecord
from scripts.storage.models import RepoObservation


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqlAlchemyRepoLedger:
    """Concrete ledger backed by the repo_observations table for one tenant."""

    def __init__(self, session: Session, tenant_id: int) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def is_empty(self) -> bool:
        """True iff this tenant has zero repo_observations rows — a seeding run."""
        existing = self._session.execute(
            select(RepoObservation.id).where(RepoObservation.tenant_id == self._tenant_id).limit(1)
        ).first()
        return existing is None

    def known(self, full_names: list[str]) -> set[str]:
        """Return the subset of full_names already recorded for this tenant."""
        if not full_names:
            return set()
        rows = self._session.execute(
            select(RepoObservation.full_name).where(
                RepoObservation.tenant_id == self._tenant_id,
                RepoObservation.full_name.in_(full_names),
            )
        ).scalars()
        return set(rows)

    def record(self, observations: list[RepoObservationRecord]) -> None:
        """Insert one row per observation. Callers must only pass genuinely new repos —
        this is an insert, not an upsert, and relies on the (tenant_id, full_name)
        unique constraint to fail loudly on a caller bug rather than silently overwrite
        first_seen_at."""
        if not observations:
            return
        for obs in observations:
            self._session.add(
                RepoObservation(
                    tenant_id=self._tenant_id,
                    full_name=obs.full_name,
                    first_seen_at=_utcnow(),
                    owner_login=obs.owner_login,
                    html_url=obs.html_url,
                    created_at_gh=obs.created_at_gh,
                    pushed_at_gh=obs.pushed_at_gh,
                    stars_at_first_seen=obs.stars_at_first_seen,
                    archived=obs.archived,
                )
            )
        try:
            self._session.commit()
        except Exception:
            # Without this the Session stays in a failed-transaction state and
            # every subsequent use raises PendingRollbackError. Invisible via
            # the CLI (throwaway session) but fatal for the deployed worker,
            # which holds one Session for the whole run.
            self._session.rollback()
            raise
