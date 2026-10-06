import pytest
from fastapi.testclient import TestClient

from scripts.web.app import create_app
from scripts.web.invites import create_invite, revoke_invite


@pytest.fixture
def invite_code(patched_sessions):
    with patched_sessions() as session:
        code = create_invite(session, label="Maya", tenant_slug="maya")
        session.commit()
    return code


@pytest.fixture
def client(patched_sessions):
    return TestClient(create_app(), follow_redirects=False)


def test_landing_page_is_public(client):
    assert client.get("/").status_code == 200


def test_health_endpoints_stay_public(client):
    assert client.get("/healthz").status_code == 200


def test_anonymous_dashboard_redirects_to_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 303 and response.headers["location"] == "/login"


def test_valid_code_logs_in_and_unlocks_the_dashboard(client, invite_code):
    response = client.post("/login", data={"code": invite_code})
    assert response.status_code == 303 and response.headers["location"] == "/audit"
    assert client.get("/dashboard").status_code == 200


def test_wrong_code_is_rejected_and_grants_nothing(client):
    response = client.post("/login", data={"code": "not-a-real-code"})
    assert response.status_code == 401
    assert client.get("/dashboard").status_code == 303


def test_revoking_an_invite_ends_access_on_the_next_request(client, invite_code, patched_sessions):
    client.post("/login", data={"code": invite_code})
    assert client.get("/dashboard").status_code == 200
    with patched_sessions() as session:
        revoke_invite(session, "Maya")
        session.commit()
    assert client.get("/dashboard").status_code == 303


def test_a_tampered_session_cookie_redirects_instead_of_erroring(client):
    client.cookies.set("sf_session", "this-is-not-a-signed-cookie")
    assert client.get("/dashboard").status_code == 303


def test_logout_ends_the_session(client, invite_code):
    client.post("/login", data={"code": invite_code})
    response = client.post("/logout")
    assert response.status_code == 303 and response.headers["location"] == "/"
    assert client.get("/dashboard").status_code == 303


def test_production_refuses_to_start_without_a_session_secret(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        create_app()
