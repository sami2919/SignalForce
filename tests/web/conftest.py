"""Shared fixtures for the invite-gated web app tests."""

from __future__ import annotations

import contextlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.storage.models import Base
from scripts.web import auth as auth_module
from scripts.web import invites as invites_module

# Every module that opens its own DB session. Add a module here when a task
# introduces a new route or CLI that calls get_session().
SESSION_MODULES = [auth_module, invites_module]


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-test-secret-test-secret-00")
    monkeypatch.delenv("APP_ENV", raising=False)


@pytest.fixture
def web_engine():
    # StaticPool + check_same_thread=False: TestClient runs sync endpoints in
    # a worker thread, and a plain in-memory SQLite gives each thread its own
    # empty database.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def web_session_factory(web_engine):
    return sessionmaker(bind=web_engine, expire_on_commit=False)


@pytest.fixture
def patched_sessions(monkeypatch, web_session_factory):
    @contextlib.contextmanager
    def _get_session():
        session = web_session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    for module in SESSION_MODULES:
        monkeypatch.setattr(module, "get_session", _get_session)
    return web_session_factory
