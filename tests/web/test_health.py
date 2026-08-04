"""Health endpoint tests.

The liveness/readiness split is the point of these tests: /healthz must stay
green during a database outage (see docs/decisions/0002-web-layer-and-health-checks.md).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scripts.web.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_healthz_returns_ok(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_healthz_stays_green_when_database_is_down(client: TestClient, monkeypatch) -> None:
    """The whole point of the split: a DB outage must NOT fail liveness.

    Fly restarts machines that fail liveness. Restarting cannot fix a remote
    database, so a DB-sensitive /healthz turns an outage into a crash loop.
    """

    def boom():
        raise RuntimeError("database is on fire")

    monkeypatch.setattr("scripts.web.routes_health.get_session", boom)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_reports_503_when_database_unreachable(client: TestClient, monkeypatch) -> None:
    def boom():
        raise RuntimeError("DATABASE_URL is not set")

    monkeypatch.setattr("scripts.web.routes_health.get_session", boom)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json() == {"status": "not_ready", "db": False}


def test_readyz_reports_200_when_database_reachable(client: TestClient, monkeypatch) -> None:
    from contextlib import contextmanager

    class _FakeSession:
        def execute(self, _stmt) -> None:
            return None

    @contextmanager
    def fake_session():
        yield _FakeSession()

    monkeypatch.setattr("scripts.web.routes_health.get_session", fake_session)
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "db": True}


def test_readyz_never_raises_on_unexpected_error(client: TestClient, monkeypatch) -> None:
    """A health endpoint that 500s is indistinguishable from a dead process."""
    from contextlib import contextmanager

    @contextmanager
    def exploding_session():
        raise ValueError("something entirely unexpected")
        yield  # pragma: no cover

    monkeypatch.setattr("scripts.web.routes_health.get_session", exploding_session)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["db"] is False


def test_create_app_returns_independent_instances() -> None:
    """Factory pattern exists for test isolation — verify it actually isolates."""
    assert create_app() is not create_app()


def test_openapi_schema_is_available(client: TestClient) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/healthz" in resp.json()["paths"]
