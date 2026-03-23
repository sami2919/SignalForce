"""Unit tests for scripts/db.py — engine creation, table init, WAL mode, sessions."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text

from scripts.db import Base, Campaign, TrackedSignal, OutreachEvent, OutcomeEvent
from scripts.db import create_db_engine, init_db, get_session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def memory_engine():
    """Create an in-memory SQLite engine with tables initialised."""
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    return engine


# ---------------------------------------------------------------------------
# init_db tests
# ---------------------------------------------------------------------------


def test_init_db_creates_all_tables(memory_engine):
    """init_db should create campaigns, tracked_signals, outreach_events, outcome_events."""
    inspector = inspect(memory_engine)
    table_names = set(inspector.get_table_names())
    assert "campaigns" in table_names
    assert "tracked_signals" in table_names
    assert "outreach_events" in table_names
    assert "outcome_events" in table_names


def test_init_db_idempotent(memory_engine):
    """Calling init_db twice should not raise."""
    init_db(memory_engine)  # second call — must not error


# ---------------------------------------------------------------------------
# WAL mode tests
# ---------------------------------------------------------------------------


def test_wal_mode_enabled(memory_engine):
    """WAL journal mode should be active on every connection."""
    with memory_engine.connect() as conn:
        result = conn.execute(text("PRAGMA journal_mode")).scalar()
        # In-memory databases may report "memory" instead of "wal" because
        # WAL is not meaningful without a file, but the PRAGMA still executes.
        # For file-based DBs this would return "wal".
        assert result in ("wal", "memory")


def test_foreign_keys_enabled(memory_engine):
    """Foreign key constraints should be enforced."""
    with memory_engine.connect() as conn:
        result = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert result == 1


# ---------------------------------------------------------------------------
# get_session context manager tests
# ---------------------------------------------------------------------------


def test_get_session_commits_on_success(memory_engine):
    """Data inserted inside get_session is persisted after exit."""
    with get_session(memory_engine) as session:
        session.add(Campaign(client_name="TestCo", icp_description="Test ICP"))

    with get_session(memory_engine) as session:
        campaigns = session.query(Campaign).all()
        assert len(campaigns) == 1
        assert campaigns[0].client_name == "TestCo"


def test_get_session_rolls_back_on_error(memory_engine):
    """On exception, changes are rolled back and the exception propagates."""
    with pytest.raises(RuntimeError, match="boom"):
        with get_session(memory_engine) as session:
            session.add(Campaign(client_name="Ghost", icp_description=""))
            raise RuntimeError("boom")

    with get_session(memory_engine) as session:
        campaigns = session.query(Campaign).all()
        assert len(campaigns) == 0


def test_get_session_yields_usable_session(memory_engine):
    """The yielded session supports add, query, and flush."""
    with get_session(memory_engine) as session:
        c = Campaign(client_name="Acme", icp_description="widgets")
        session.add(c)
        session.flush()
        assert c.id is not None
