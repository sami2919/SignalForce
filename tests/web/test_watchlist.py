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


def test_re_adding_an_existing_domain_is_not_resolved_twice(patched_sessions, fake):
    # stripe.com resolves to a source; a domain with zero sources is re-queued
    # on re-add by design (see the resolution-outcome tests below).
    fake.with_sources = {"stripe.com"}
    client = _client(patched_sessions, "alpha")
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    client.post("/watchlist", data={"domains": "stripe.com vercel.com"}, follow_redirects=False)
    assert fake.calls == [["stripe.com"], ["vercel.com"]]


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


# ---------------------------------------------------------------------------
# Resolution outcome: the page never says "resolving…" forever
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

from scripts.storage.models import AccountSource  # noqa: E402

FAILED_TEXT = "resolution failed — add the domain again to retry"
NO_SOURCES_TEXT = "no public careers page or repo found"
STALE_TEXT = "resolution did not finish — add the domain again to retry"


class FakeResolution:
    """Background resolve stand-in: records calls, can create sources or fail."""

    def __init__(self, session_factory):
        self.calls: list[list[str]] = []
        self.with_sources: set[str] = set()
        self.fail = False
        self._sessions = session_factory

    async def __call__(self, tenant_id, domains):
        self.calls.append(list(domains))
        if self.fail:
            raise RuntimeError("boom")
        with self._sessions() as session:
            for account in session.scalars(
                select(Account).where(Account.tenant_id == tenant_id, Account.domain.in_(domains))
            ):
                if account.domain in self.with_sources:
                    session.add(AccountSource(
                        tenant_id=tenant_id, account_id=account.id,
                        source_type="careers", url=f"https://{account.domain}/careers",
                    ))
            session.commit()


@pytest.fixture
def fake(monkeypatch, patched_sessions):
    resolution = FakeResolution(patched_sessions)
    monkeypatch.setattr(routes_watchlist, "resolve_and_store", resolution)
    monkeypatch.setattr(routes_watchlist, "assert_public_host", _fake_public_check)
    return resolution


def _metadata(patched_sessions, domain, slug="alpha"):
    from scripts.storage.models import Tenant

    with patched_sessions() as session:
        account = session.scalars(
            select(Account).join(Tenant, Tenant.id == Account.tenant_id)
            .where(Account.domain == domain, Tenant.slug == slug)
        ).one()
        return dict(account.account_metadata or {})


def _set_metadata(patched_sessions, domain, metadata):
    with patched_sessions() as session:
        account = session.scalars(select(Account).where(Account.domain == domain)).one()
        account.account_metadata = metadata
        session.commit()


def _resolution(outcome, minutes_ago=0):
    at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {"outcome": outcome, "at": at.isoformat()}


def _cell(html, domain):
    start = html.index(f"<td>{domain}</td>")
    return html[start:html.index("</tr>", start)]


def test_background_success_with_sources_records_resolved(patched_sessions, fake):
    fake.with_sources = {"stripe.com"}
    client = _client(patched_sessions, "alpha")
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    resolution = _metadata(patched_sessions, "stripe.com")["resolution"]
    assert resolution["outcome"] == "resolved"
    assert datetime.fromisoformat(resolution["at"]).tzinfo is not None
    assert ">1<" in _cell(client.get("/watchlist").text, "stripe.com")


def test_background_success_with_no_sources_records_no_sources(patched_sessions, fake):
    client = _client(patched_sessions, "alpha")
    client.post("/watchlist", data={"domains": "jsonly.example.com"}, follow_redirects=False)
    assert _metadata(patched_sessions, "jsonly.example.com")["resolution"]["outcome"] == "no_sources"
    assert NO_SOURCES_TEXT in _cell(client.get("/watchlist").text, "jsonly.example.com")


def test_background_failure_records_failed(patched_sessions, fake, caplog):
    fake.fail = True
    client = _client(patched_sessions, "alpha")
    response = client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    assert response.status_code == 303
    assert _metadata(patched_sessions, "stripe.com")["resolution"]["outcome"] == "failed"
    assert FAILED_TEXT in _cell(client.get("/watchlist").text, "stripe.com")
    failure = next(r for r in caplog.records if r.getMessage() == "watchlist resolution failed")
    assert failure.error_type == "RuntimeError" and "boom" not in caplog.text


def test_fresh_pending_renders_resolving(patched_sessions, fake):
    client = _client(patched_sessions, "alpha")
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    _set_metadata(patched_sessions, "stripe.com", {"resolution": _resolution("pending", 2)})
    assert "resolving…" in _cell(client.get("/watchlist").text, "stripe.com")


def test_missing_outcome_renders_resolving(patched_sessions, fake):
    client = _client(patched_sessions, "alpha")
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    _set_metadata(patched_sessions, "stripe.com", {})
    assert "resolving…" in _cell(client.get("/watchlist").text, "stripe.com")


def test_stale_pending_renders_did_not_finish(patched_sessions, fake):
    client = _client(patched_sessions, "alpha")
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    _set_metadata(patched_sessions, "stripe.com", {"resolution": _resolution("pending", 16)})
    cell = _cell(client.get("/watchlist").text, "stripe.com")
    assert STALE_TEXT in cell and "resolving…" not in cell


@pytest.mark.parametrize(
    "resolution", [_resolution("failed"), _resolution("no_sources"), _resolution("pending", 16)]
)
def test_re_adding_a_stuck_domain_re_queues_exactly_that_domain(patched_sessions, fake, resolution):
    client = _client(patched_sessions, "alpha")
    client.post("/watchlist", data={"domains": "stripe.com vercel.com"}, follow_redirects=False)
    _set_metadata(patched_sessions, "stripe.com", {"resolution": resolution})
    fake.calls.clear()
    response = client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    assert response.status_code == 303
    assert fake.calls == [["stripe.com"]]
    with patched_sessions() as session:
        assert len(session.scalars(select(Account)).all()) == 2


def test_re_adding_a_fresh_pending_domain_does_not_re_queue(patched_sessions, fake):
    client = _client(patched_sessions, "alpha")
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    _set_metadata(patched_sessions, "stripe.com", {"resolution": _resolution("pending", 2)})
    fake.calls.clear()
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    assert fake.calls == []


def test_re_adding_a_domain_with_active_sources_does_not_re_queue(patched_sessions, fake):
    fake.with_sources = {"stripe.com"}
    client = _client(patched_sessions, "alpha")
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    fake.calls.clear()
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    assert fake.calls == []


def test_re_queued_domains_do_not_count_twice_against_the_cap(patched_sessions, fake):
    client = _client(patched_sessions, "alpha")
    full = " ".join(f"d{i}.example.com" for i in range(routes_watchlist.MAX_WATCHLIST))
    assert client.post("/watchlist", data={"domains": full}, follow_redirects=False).status_code == 303
    fake.calls.clear()
    response = client.post("/watchlist", data={"domains": "d0.example.com d1.example.com"}, follow_redirects=False)
    assert response.status_code == 303
    assert fake.calls == [["d0.example.com", "d1.example.com"]]


def test_re_queued_domains_are_set_pending_and_keep_other_metadata(patched_sessions, fake, monkeypatch):
    client = _client(patched_sessions, "alpha")
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    _set_metadata(patched_sessions, "stripe.com", {"resolution": _resolution("failed"), "note": "keep"})
    monkeypatch.setattr(routes_watchlist, "_resolve_in_background", lambda tenant_id, domains: None)
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    metadata = _metadata(patched_sessions, "stripe.com")
    assert metadata["note"] == "keep" and metadata["resolution"]["outcome"] == "pending"


def test_outcome_update_preserves_other_metadata_keys(patched_sessions, fake):
    client = _client(patched_sessions, "alpha")
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    _set_metadata(patched_sessions, "stripe.com", {"resolution": _resolution("failed"), "note": "keep"})
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    metadata = _metadata(patched_sessions, "stripe.com")
    assert metadata["note"] == "keep" and metadata["resolution"]["outcome"] == "no_sources"


def test_re_queue_still_runs_the_ssrf_intake_check(patched_sessions, fake, monkeypatch):
    client = _client(patched_sessions, "alpha")
    client.post("/watchlist", data={"domains": "stripe.com"}, follow_redirects=False)
    _set_metadata(patched_sessions, "stripe.com", {"resolution": _resolution("failed")})

    def blocked(host, resolver=None):
        raise BlockedAddress(f"{host} resolves to a non-public address (10.0.0.5)")

    monkeypatch.setattr(routes_watchlist, "assert_public_host", blocked)
    fake.calls.clear()
    response = client.post("/watchlist", data={"domains": "stripe.com"})
    assert response.status_code == 422 and fake.calls == []


def test_re_queue_is_tenant_scoped(patched_sessions, fake):
    alpha = _client(patched_sessions, "alpha")
    bravo = _client(patched_sessions, "bravo")
    alpha.post("/watchlist", data={"domains": "shared.example.com"}, follow_redirects=False)
    fake.fail = True
    bravo.post("/watchlist", data={"domains": "shared.example.com"}, follow_redirects=False)
    assert _metadata(patched_sessions, "shared.example.com", "alpha")["resolution"]["outcome"] == "no_sources"
    assert _metadata(patched_sessions, "shared.example.com", "bravo")["resolution"]["outcome"] == "failed"
    assert FAILED_TEXT not in alpha.get("/watchlist").text


def test_a_concurrent_add_of_the_same_domain_is_treated_as_already_added(patched_sessions, fake, monkeypatch):
    from sqlalchemy.exc import IntegrityError

    from scripts.registry.store import ensure_account as real_ensure_account

    raced: list[str] = []

    def racing_ensure_account(tenant_id, domain, session):
        if domain == "stripe.com" and not raced:
            raced.append(domain)
            with patched_sessions() as other:  # the other request wins the insert
                real_ensure_account(tenant_id, domain, other)
            raise IntegrityError("INSERT INTO accounts", {}, Exception("UNIQUE constraint failed"))
        return real_ensure_account(tenant_id, domain, session)

    monkeypatch.setattr(routes_watchlist, "ensure_account", racing_ensure_account)
    client = _client(patched_sessions, "alpha")
    response = client.post("/watchlist", data={"domains": "stripe.com vercel.com"}, follow_redirects=False)
    assert response.status_code == 303
    assert raced == ["stripe.com"]
    assert fake.calls == [["vercel.com"]]
    with patched_sessions() as session:
        assert {a.domain for a in session.scalars(select(Account))} == {"stripe.com", "vercel.com"}
