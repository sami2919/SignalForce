"""Engine and session factory. DATABASE_URL from env."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_SessionLocal = None


def _init() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        return
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # Neon pooler works fine with modest pool sizes; fail fast on exhaustion.
    _engine = create_engine(url, pool_size=5, max_overflow=5, pool_pre_ping=True)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def migration_url() -> str:
    """Database URL for Alembic. Prefers the direct (non-pooled) endpoint.

    The app uses the pooled endpoint because PgBouncer multiplexes many short
    connections. Migrations must NOT: transaction-mode pooling can hand
    consecutive statements to different backends, so DDL can partially apply
    and still report success.

    See docs/decisions/0003-deployment-and-scheduling.md, Decision 3.
    """
    url = os.environ.get("DATABASE_URL_DIRECT") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Neither DATABASE_URL_DIRECT nor DATABASE_URL is set — cannot run migrations"
        )
    return url


@contextmanager
def get_session() -> Iterator[Session]:
    _init()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
