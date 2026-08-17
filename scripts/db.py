"""SQLite database setup for the SignalForce feedback loop.

Provides SQLAlchemy engine, table definitions, and session management.
DB file lives at data/signalforce.db with WAL mode for concurrent reads.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "signalforce.db"


# ---------------------------------------------------------------------------
# SQLAlchemy base
# ---------------------------------------------------------------------------

Base = declarative_base()


# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(Base):  # type: ignore[misc]
    """A campaign representing a specific ICP / client engagement."""

    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_name = Column(String(255), nullable=False)
    icp_description = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class TrackedSignal(Base):  # type: ignore[misc]
    """A signal that entered the outreach funnel."""

    __tablename__ = "tracked_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    signal_type = Column(String(100), nullable=False)
    company_name = Column(String(255), nullable=False)
    company_domain = Column(String(255), nullable=True)
    signal_strength = Column(Integer, nullable=False)
    source_url = Column(Text, nullable=False, default="")
    detected_at = Column(DateTime, nullable=False, default=_utcnow)
    icp_grade = Column(String(10), nullable=True)
    composite_score = Column(Float, nullable=True)
    scanner_name = Column(String(100), nullable=True)


class OutreachEvent(Base):  # type: ignore[misc]
    """An outreach message sent in response to a signal."""

    __tablename__ = "outreach_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tracked_signal_id = Column(Integer, ForeignKey("tracked_signals.id"), nullable=False)
    channel = Column(String(50), nullable=False)  # email / linkedin
    template_used = Column(String(255), nullable=False, default="")
    angle_used = Column(String(255), nullable=False, default="")
    sent_at = Column(DateTime, nullable=False, default=_utcnow)
    template_variant = Column(String(255), nullable=True)
    subject_variant = Column(String(255), nullable=True)
    cta_variant = Column(String(255), nullable=True)
    experiment_tag = Column(String(255), nullable=True)
    external_id = Column(String(255), nullable=True)
    tracking_token = Column(String(255), nullable=True, index=True)
    detected_to_sent_hours = Column(Float, nullable=True)


class OutcomeEvent(Base):  # type: ignore[misc]
    """An outcome resulting from an outreach event."""

    __tablename__ = "outcome_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    outreach_event_id = Column(Integer, ForeignKey("outreach_events.id"), nullable=False)
    outcome_type = Column(String(50), nullable=False)
    occurred_at = Column(DateTime, nullable=False, default=_utcnow)
    notes = Column(Text, nullable=False, default="")
    external_id = Column(String(255), nullable=True)


# ---------------------------------------------------------------------------
# Engine & session helpers
# ---------------------------------------------------------------------------

_VALID_OUTCOME_TYPES = frozenset(
    {
        "bounced",
        "clicked",
        "delivered",
        "reply",
        "negative_reply",
        "no_response",
        "opened",
        "positive_reply",
        "meeting_scheduled",
        "meeting_completed",
        "deal_closed",
        "unsubscribed",
    }
)


def _enable_wal(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
    """Enable WAL journal mode on every new SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
    """Enable foreign key enforcement on every new SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(db_url: Optional[str] = None) -> Engine:
    """Create a SQLAlchemy engine for the given database URL.

    Args:
        db_url: SQLAlchemy database URL. Defaults to sqlite:///data/signalforce.db.

    Returns:
        A configured SQLAlchemy Engine with WAL mode and foreign keys enabled.
    """
    if db_url is None:
        _DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{_DEFAULT_DB_PATH}"

    engine = create_engine(db_url, echo=False)
    event.listen(engine, "connect", _enable_wal)
    event.listen(engine, "connect", _enable_foreign_keys)
    return engine


def init_db(engine: Optional[Engine] = None) -> Engine:
    """Initialize the database: create all tables if they don't exist.

    Args:
        engine: An existing engine. If None, a default engine is created.

    Returns:
        The engine used (useful when caller passes None).
    """
    if engine is None:
        engine = create_db_engine()
    Base.metadata.create_all(engine)
    _migrate_existing_schema(engine)
    logger.info("Database initialized at %s", engine.url)
    return engine


def _migrate_existing_schema(engine: Engine) -> None:
    """Add newly introduced nullable columns to existing SQLite databases.

    SQLAlchemy's create_all() does not alter existing tables. SignalForce uses a
    local SQLite DB by default, so lightweight additive migrations keep existing
    installs compatible without introducing a migration framework.
    """
    additive_columns = {
        "tracked_signals": {
            "icp_grade": "VARCHAR(10)",
            "composite_score": "FLOAT",
            "scanner_name": "VARCHAR(100)",
        },
        "outreach_events": {
            "template_variant": "VARCHAR(255)",
            "subject_variant": "VARCHAR(255)",
            "cta_variant": "VARCHAR(255)",
            "experiment_tag": "VARCHAR(255)",
            "external_id": "VARCHAR(255)",
            "tracking_token": "VARCHAR(255)",
            "detected_to_sent_hours": "FLOAT",
        },
        "outcome_events": {
            "external_id": "VARCHAR(255)",
        },
    }

    with engine.begin() as conn:
        for table_name, columns in additive_columns.items():
            existing = {
                row[1]
                for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
            }
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    )


@contextmanager
def get_session(engine: Engine) -> Iterator[Session]:
    """Context manager that yields a SQLAlchemy session and handles commit/rollback.

    Usage::

        with get_session(engine) as session:
            session.add(Campaign(client_name="Acme"))

    On normal exit the transaction is committed. On exception it is rolled back
    and the exception re-raised.
    """
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
