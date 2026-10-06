import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from scripts.registry.store import ensure_account, ensure_tenant
from scripts.storage.models import Account
from scripts.web.app import create_app
from scripts.web.invites import create_invite


@pytest.fixture
def two_tenants(patched_sessions):
    """Tenant A and B, each with one account, and a signed-in client per tenant."""
    clients = {}
    with patched_sessions() as session:
        for slug in ("alpha", "bravo"):
            tenant_id = ensure_tenant(slug, slug, session)
            ensure_account(tenant_id, f"{slug}-corp.example", session)
        session.commit()
        codes = {slug: create_invite(session, label=slug, tenant_slug=slug) for slug in ("alpha", "bravo")}
        session.commit()
    for slug, code in codes.items():
        client = TestClient(create_app())
        assert client.post("/login", data={"code": code}, follow_redirects=False).status_code == 303
        clients[slug] = client
    with patched_sessions() as session:
        ids = {a.domain: a.id for a in session.scalars(select(Account))}
    return clients, ids


def test_each_tenant_sees_only_its_own_accounts(two_tenants):
    clients, _ = two_tenants
    alpha = clients["alpha"].get("/dashboard").text
    assert "alpha-corp.example" in alpha and "bravo-corp.example" not in alpha
    bravo = clients["bravo"].get("/dashboard").text
    assert "bravo-corp.example" in bravo and "alpha-corp.example" not in bravo


def test_a_guessed_account_id_from_another_tenant_is_a_404(two_tenants):
    clients, ids = two_tenants
    own = clients["alpha"].get(f"/dashboard/account/{ids['alpha-corp.example']}")
    assert own.status_code == 200 and "alpha-corp.example" in own.text
    response = clients["alpha"].get(f"/dashboard/account/{ids['bravo-corp.example']}")
    assert response.status_code == 404


def test_an_invite_without_a_tenant_sees_the_empty_state(patched_sessions, monkeypatch):
    monkeypatch.delenv("TENANT_SLUG", raising=False)
    with patched_sessions() as session:
        tenant_id = ensure_tenant("other", "other", session)
        ensure_account(tenant_id, "other-corp.example", session)
        session.commit()
        code = create_invite(session, label="no-tenant")
        session.commit()
    client = TestClient(create_app())
    client.post("/login", data={"code": code}, follow_redirects=False)
    response = client.get("/dashboard")
    assert response.status_code == 200 and "corp.example" not in response.text
