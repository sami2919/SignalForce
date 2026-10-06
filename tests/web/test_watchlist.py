import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from scripts.net.guard import BlockedAddress
from scripts.storage.models import Account
from scripts.web import routes_watchlist
from scripts.web.app import create_app
from scripts.web.invites import create_invite


@pytest.fixture
def resolved(monkeypatch):
    """Record background resolutions instead of touching the network."""
    calls: list[tuple[int, list[str]]] = []

    async def fake_resolve(tenant_id, domains):
        calls.append((tenant_id, list(domains)))

    monkeypatch.setattr(routes_watchlist, "resolve_and_store", fake_resolve)
    monkeypatch.setattr(routes_watchlist, "assert_public_host", _fake_public_check)
    return calls


def _fake_public_check(host, resolver=None):
    if host.startswith("internal"):
        raise BlockedAddress(f"{host} resolves to a non-public address (10.0.0.5)")


def _client(patched_sessions, slug):
    with patched_sessions() as session:
        code = create_invite(session, label=slug, tenant_slug=slug)
        session.commit()
    client = TestClient(create_app())
    client.post("/login", data={"code": code}, follow_redirects=False)
    return client


def test_adding_domains_stores_accounts_and_starts_resolution(patched_sessions, resolved):
    client = _client(patched_sessions, "alpha")
    response = client.post("/watchlist", data={"domains": "stripe.com\nhttps://www.vercel.com/jobs"}, follow_redirects=False)
    assert response.status_code == 303
    with patched_sessions() as session:
        assert {a.domain for a in session.scalars(select(Account))} == {"stripe.com", "vercel.com"}
    assert len(resolved) == 1 and resolved[0][1] == ["stripe.com", "vercel.com"]


def test_internal_hosts_are_refused_and_nothing_is_stored(patched_sessions, resolved):
    client = _client(patched_sessions, "alpha")
    response = client.post("/watchlist", data={"domains": "stripe.com internal.example"})
    assert response.status_code == 422 and "internal.example" in response.text
    with patched_sessions() as session:
        assert session.scalars(select(Account)).all() == []
    assert resolved == []


def test_garbage_input_is_a_422_that_names_the_entries(patched_sessions, resolved):
    client = _client(patched_sessions, "alpha")
    response = client.post("/watchlist", data={"domains": "localhost 10.0.0.1 stripe.com"})
    assert response.status_code == 422
    assert "localhost" in response.text and "10.0.0.1" in response.text


def test_the_cap_applies_to_existing_plus_new(patched_sessions, resolved):
    client = _client(patched_sessions, "alpha")
    first = " ".join(f"d{i}.example.com" for i in range(20))
    assert client.post("/watchlist", data={"domains": first}, follow_redirects=False).status_code == 303
    more = " ".join(f"e{i}.example.com" for i in range(6))
    assert client.post("/watchlist", data={"domains": more}).status_code == 422
    with patched_sessions() as session:
        assert len(session.scalars(select(Account)).all()) == 20


def test_re_adding_an_existing_domain_is_not_resolved_twice(patched_sessions, resolved):
    client = _client(patched_sessions, "alpha")
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    client.post("/watchlist", data={"domains": "stripe.com vercel.com"}, follow_redirects=False)
    assert [c[1] for c in resolved] == [["stripe.com"], ["vercel.com"]]


def test_tenants_do_not_see_each_others_watchlists(patched_sessions, resolved):
    alpha = _client(patched_sessions, "alpha")
    bravo = _client(patched_sessions, "bravo")
    alpha.post("/watchlist", data={"domains": "alpha-only.example.com"}, follow_redirects=False)
    assert "alpha-only.example.com" in alpha.get("/watchlist").text
    assert "alpha-only.example.com" not in bravo.get("/watchlist").text


def test_an_invite_with_no_tenant_cannot_add_domains(patched_sessions, resolved):
    with patched_sessions() as session:
        code = create_invite(session, label="none")
        session.commit()
    client = TestClient(create_app())
    client.post("/login", data={"code": code}, follow_redirects=False)
    assert client.post("/watchlist", data={"domains": "stripe.com"}).status_code == 403
