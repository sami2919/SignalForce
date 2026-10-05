"""Liveness and readiness endpoints.

These are two different questions with opposite correct answers when the
database is down:

    /healthz  "is this process alive?"        -> never touches the DB
    /readyz   "can it serve real traffic?"    -> checks the DB, 503 if not

Fly.io restarts machines whose health check fails. Restarting a web process
cannot fix an unreachable Neon instance, so a DB-sensitive liveness check turns
a database outage into a database outage PLUS a crash-looping web tier.

See docs/decisions/0002-web-layer-and-health-checks.md, Decision 3.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from scripts.storage.session import get_session

logger = logging.getLogger(__name__)

# A readiness probe that hangs is worse than one that fails: the caller's own
# timeout fires and the result is ambiguous.
_DB_PROBE_TIMEOUT_SECONDS = 2

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness. Deliberately checks nothing external.

    If this process can execute this function, it is alive. Any dependency
    check here would be a lie about what a restart can fix.
    """
    return {"status": "ok"}


@router.get("/readyz")
def readyz(response: Response) -> dict[str, object]:
    """Readiness. Reports whether the database is reachable."""
    db_ok = False
    try:
        with get_session() as session:
            session.execute(
                text(f"SET LOCAL statement_timeout = {_DB_PROBE_TIMEOUT_SECONDS * 1000}")
            )
            session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        # Deliberate broad catch. A health endpoint that raises is
        # indistinguishable from a dead process and triggers the same bad
        # restart. This is the one place in the codebase where swallowing is
        # correct — so it is logged, never silent.
        logger.warning("Readiness probe failed: database unreachable", exc_info=True)

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "db": False}

    return {"status": "ready", "db": True}
