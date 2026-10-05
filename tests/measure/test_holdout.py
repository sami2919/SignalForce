"""Tests for scripts/measure/holdout.py.

The heart of this file: test_changed_hash_no_second_fetch -- the regression
test that proves the deep scan does NOT inherit the watch layer's
confirm-on-change behavior (ADR-0010 Decision 1), and
test_last_hash_is_never_touched -- the constraint most likely to be violated
by copying scripts/watch/runner.py's patterns too literally.
"""

from __future__ import annotations

import contextlib

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.measure import holdout as holdout_module
from scripts.measure.holdout import run_deep_scan, select_holdout
from scripts.storage.models import Account, AccountSource, Base, HoldoutScan, Tenant
from scripts.watch.runner import run_watch_pass
from scripts.watch import runner as runner_module

PAGE_A = "<html><body><h1>Open roles</h1><p>Engineer A</p></body></html>"
PAGE_B = "<html><body><h1>Open roles</h1><p>Engineer B</p></body></html>"
ROBOTS_ALLOW = "User-agent: *\nAllow: /\n"


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def _patch_session(monkeypatch, session_factory):
    """Route get_session at both holdout and runner modules to the same in-memory engine."""

    @contextlib.contextmanager
    def _get_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(holdout_module, "get_session", _get_session)
    monkeypatch.setattr(runner_module, "get_session", _get_session)


_tenant_counter = {"n": 0}


def _make_tenant_and_sources(
    session_factory, urls: list[str], *, active: bool = True
) -> tuple[int, list[int]]:
    _tenant_counter["n"] += 1
    session = session_factory()
    tenant = Tenant(slug=f"t{_tenant_counter['n']}", name="T1")
    session.add(tenant)
    session.commit()

    account = Account(tenant_id=tenant.id, domain="acme.com", name="Acme")
    session.add(account)
    session.commit()

    source_ids = []
    for i, url in enumerate(urls):
        src = AccountSource(
            tenant_id=tenant.id,
            account_id=account.id,
            source_type=["careers", "docs", "changelog", "pricing", "blog"][i % 5],
            url=url,
            active=active,
        )
        session.add(src)
        session.commit()
        source_ids.append(src.id)

    tenant_id = tenant.id
    session.close()
    return tenant_id, source_ids


def _static_handler(text: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        return httpx.Response(200, text=text)

    return handler


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    """Default: every non-robots URL returns PAGE_A. Individual tests override via _install."""
    state = {"handler": _static_handler(PAGE_A)}
    _RealAsyncClient = httpx.AsyncClient

    class _Client:
        def __init__(self, *args, **kwargs):
            self._transport = httpx.MockTransport(lambda req: state["handler"](req))
            self._inner = _RealAsyncClient(transport=self._transport)

        async def __aenter__(self):
            return self._inner

        async def __aexit__(self, *exc):
            await self._inner.aclose()

    monkeypatch.setattr(holdout_module.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(runner_module.httpx, "AsyncClient", _Client)
    return state


# --- select_holdout ---


def test_select_holdout_is_deterministic_for_a_seed():
    account_ids = list(range(1, 21))
    a = select_holdout(account_ids, size=5, seed=42)
    b = select_holdout(account_ids, size=5, seed=42)
    assert a == b


def test_select_holdout_respects_size():
    account_ids = list(range(1, 21))
    result = select_holdout(account_ids, size=5, seed=42)
    assert len(result) == 5


def test_select_holdout_caps_at_population_size():
    account_ids = [1, 2, 3]
    result = select_holdout(account_ids, size=5, seed=42)
    assert len(result) == 3


def test_select_holdout_is_stable_when_an_unrelated_account_is_removed():
    """Fixed on review: random.sample() reshuffled the ENTIRE holdout when a
    single account not even IN the holdout was removed (measured: 2/5
    overlap). The whole point of a fixed seed is that this must not happen.
    """
    base = list(range(1, 21))
    original = select_holdout(base, size=5, seed=42)

    unrelated_id = next(i for i in base if i not in original)
    shrunk = [i for i in base if i != unrelated_id]
    after_removal = select_holdout(shrunk, size=5, seed=42)

    assert after_removal == original


def test_select_holdout_is_mostly_stable_under_population_growth():
    """Growth can legitimately displace a member (a new account can rank
    into the top `size`), but must not reshuffle the whole holdout. Measured:
    random.sample() dropped to 3/5 overlap on +5 growth; consistent hashing
    holds at 4/5."""
    base = list(range(1, 21))
    original = set(select_holdout(base, size=5, seed=42))

    grown = base + list(range(21, 26))  # +5 new accounts
    after_growth = set(select_holdout(grown, size=5, seed=42))

    assert len(original & after_growth) >= 4


def test_select_holdout_different_seeds_select_differently():
    # Confirms `seed` is actually mixed into the selection, not a no-op --
    # a different tenant/measurement should not be forced onto one fixed
    # holdout regardless of the seed it was configured with.
    account_ids = list(range(1, 21))
    a = select_holdout(account_ids, size=5, seed=1)
    b = select_holdout(account_ids, size=5, seed=2)
    assert a != b


def test_select_holdout_membership_is_a_per_item_function_not_positional():
    """The defining property of consistent hashing: whether account X is in
    the holdout depends only on (seed, X, current population), never on
    which OTHER accounts happen to be present. Verified directly by checking
    that every member of a smaller holdout remains a member of a superset
    selection with a larger size, for the same seed."""
    account_ids = list(range(1, 51))
    small = set(select_holdout(account_ids, size=5, seed=7))
    large = set(select_holdout(account_ids, size=15, seed=7))
    assert small <= large


# --- run_deep_scan ---


@pytest.mark.asyncio
async def test_first_ever_scan_records_changed_false(session_factory):
    tenant_id, source_ids = _make_tenant_and_sources(session_factory, ["https://acme.com/careers"])
    run_deep_scan_result = await run_deep_scan(tenant_id, holdout_size=1, seed=42)
    assert run_deep_scan_result is not None

    session = session_factory()
    rows = session.query(HoldoutScan).filter_by(account_source_id=source_ids[0]).all()
    assert len(rows) == 1
    assert rows[0].changed is False


@pytest.mark.asyncio
async def test_changed_hash_records_changed_true_with_no_second_fetch(
    session_factory, _patch_client
):
    """Regression test proving confirm-on-change was genuinely NOT applied:
    the hash differs from the prior HoldoutScan row and is recorded as
    changed=True after exactly ONE fetch, not two."""
    tenant_id, source_ids = _make_tenant_and_sources(session_factory, ["https://acme.com/careers"])

    _patch_client["handler"] = _static_handler(PAGE_A)
    await run_deep_scan(tenant_id, holdout_size=1, seed=42)  # seeds baseline

    hit_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        hit_count["n"] += 1
        return httpx.Response(200, text=PAGE_B)

    _patch_client["handler"] = handler
    await run_deep_scan(tenant_id, holdout_size=1, seed=42)

    assert hit_count["n"] == 1  # exactly one fetch, no confirm re-fetch

    session = session_factory()
    rows = (
        session.query(HoldoutScan)
        .filter_by(account_source_id=source_ids[0])
        .order_by(HoldoutScan.fetched_at)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].changed is False
    assert rows[1].changed is True


@pytest.mark.asyncio
async def test_unchanged_hash_records_changed_false(session_factory, _patch_client):
    tenant_id, source_ids = _make_tenant_and_sources(session_factory, ["https://acme.com/careers"])

    _patch_client["handler"] = _static_handler(PAGE_A)
    await run_deep_scan(tenant_id, holdout_size=1, seed=42)  # seeds baseline
    await run_deep_scan(tenant_id, holdout_size=1, seed=42)  # same content

    session = session_factory()
    rows = (
        session.query(HoldoutScan)
        .filter_by(account_source_id=source_ids[0])
        .order_by(HoldoutScan.fetched_at)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].changed is False
    assert rows[1].changed is False


@pytest.mark.asyncio
async def test_last_hash_is_never_touched(session_factory, _patch_client):
    tenant_id, source_ids = _make_tenant_and_sources(session_factory, ["https://acme.com/careers"])

    session = session_factory()
    before = session.get(AccountSource, source_ids[0]).last_hash
    session.close()
    assert before is None

    _patch_client["handler"] = _static_handler(PAGE_A)
    await run_deep_scan(tenant_id, holdout_size=1, seed=42)

    _patch_client["handler"] = _static_handler(PAGE_B)
    await run_deep_scan(tenant_id, holdout_size=1, seed=42)

    session = session_factory()
    after = session.get(AccountSource, source_ids[0]).last_hash
    session.close()
    assert after == before  # untouched by run_deep_scan, even after a "change"


@pytest.mark.asyncio
async def test_inactive_sources_are_excluded_from_the_deep_scan(session_factory, _patch_client):
    # Mutation-confirmed gap: removing the active=True filter passed every
    # other test in this file. A deactivated source (e.g. one the watch
    # layer gave up on after 5 consecutive failures) must not be
    # fetched or scored as ground truth.
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory, ["https://acme.com/careers"], active=False
    )

    _patch_client["handler"] = _static_handler(PAGE_A)
    await run_deep_scan(tenant_id, holdout_size=5, seed=42)

    session = session_factory()
    rows = session.query(HoldoutScan).filter(HoldoutScan.account_source_id == source_ids[0]).all()
    assert rows == []


@pytest.mark.asyncio
async def test_watch_pass_still_runs_unmodified_against_holdout_accounts(
    session_factory, _patch_client
):
    """A holdout account's AccountSource must be indistinguishable from any
    other to run_watch_pass -- this task must not add any skip-if-holdout
    logic anywhere."""
    tenant_id, source_ids = _make_tenant_and_sources(session_factory, ["https://acme.com/careers"])

    _patch_client["handler"] = _static_handler(PAGE_A)
    await run_deep_scan(tenant_id, holdout_size=1, seed=42)  # this account is now in the holdout

    watch_run_id = await run_watch_pass(tenant_id)

    from scripts.storage.models import Probe

    session = session_factory()
    probes = session.query(Probe).filter_by(scan_run_id=watch_run_id).all()
    assert len(probes) == 1
    assert probes[0].account_source_id == source_ids[0]

    src = session.get(AccountSource, source_ids[0])
    assert src.last_hash is not None  # run_watch_pass set it normally


def _make_many_single_source_accounts(session_factory, n: int) -> tuple[int, list[int]]:
    """One tenant, n accounts, each with exactly one AccountSource."""
    _tenant_counter["n"] += 1
    session = session_factory()
    tenant = Tenant(slug=f"t{_tenant_counter['n']}", name="T1")
    session.add(tenant)
    session.commit()

    source_ids = []
    for i in range(n):
        account = Account(tenant_id=tenant.id, domain=f"acme{i}.com", name=f"Acme{i}")
        session.add(account)
        session.commit()
        src = AccountSource(
            tenant_id=tenant.id,
            account_id=account.id,
            source_type="careers",
            url=f"https://acme{i}.com/careers",
            active=True,
        )
        session.add(src)
        session.commit()
        source_ids.append(src.id)

    tenant_id = tenant.id
    session.close()
    return tenant_id, source_ids


@pytest.mark.asyncio
async def test_same_seed_targets_the_same_accounts_across_calls(session_factory, _patch_client):
    tenant_id, source_ids = _make_many_single_source_accounts(session_factory, 10)

    _patch_client["handler"] = _static_handler(PAGE_A)
    await run_deep_scan(tenant_id, holdout_size=3, seed=42)
    session = session_factory()
    first_scanned = {r.account_source_id for r in session.query(HoldoutScan).all()}
    session.close()

    await run_deep_scan(tenant_id, holdout_size=3, seed=42)
    session = session_factory()
    second_scanned = {r.account_source_id for r in session.query(HoldoutScan).all()}
    session.close()

    assert first_scanned == second_scanned
    assert len(first_scanned) == 3


@pytest.mark.asyncio
async def test_no_active_accounts_scans_nothing(session_factory):
    _tenant_counter["n"] += 1
    session = session_factory()
    tenant = Tenant(slug=f"t{_tenant_counter['n']}", name="Empty")
    session.add(tenant)
    session.commit()
    tenant_id = tenant.id
    session.close()

    result = await run_deep_scan(tenant_id, holdout_size=5, seed=42)
    assert result == 0

    session = session_factory()
    assert session.query(HoldoutScan).count() == 0


def test_cli_main_runs_deep_scan(monkeypatch, session_factory):
    from scripts.measure import holdout as holdout_mod

    tenant_id, _ = _make_tenant_and_sources(session_factory, ["https://acme.com/careers"])

    async def _fake_run_deep_scan(tid, *, holdout_size, seed):
        assert tid == tenant_id
        assert holdout_size == 3
        assert seed == 7
        return 2

    monkeypatch.setattr(holdout_mod, "run_deep_scan", _fake_run_deep_scan)
    monkeypatch.setattr(holdout_mod, "ensure_tenant", lambda slug, name, session: tenant_id)

    exit_code = holdout_mod.main(
        ["--tenant-slug", "whatever", "--holdout-size", "3", "--seed", "7"]
    )
    assert exit_code == 0


def test_cli_main_returns_1_on_failure(monkeypatch, session_factory):
    from scripts.measure import holdout as holdout_mod

    tenant_id, _ = _make_tenant_and_sources(session_factory, ["https://acme.com/careers"])

    async def _boom(tid, *, holdout_size, seed):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(holdout_mod, "run_deep_scan", _boom)
    monkeypatch.setattr(holdout_mod, "ensure_tenant", lambda slug, name, session: tenant_id)

    exit_code = holdout_mod.main(["--tenant-slug", "whatever"])
    assert exit_code == 1


@pytest.mark.asyncio
async def test_one_failing_source_does_not_abort_the_deep_scan(session_factory, _patch_client):
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory,
        ["https://bad.com/careers", "https://acme.com/docs"],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        if request.url.host == "bad.com":
            raise httpx.ConnectError("boom")
        return httpx.Response(200, text=PAGE_A)

    _patch_client["handler"] = handler
    await run_deep_scan(tenant_id, holdout_size=2, seed=42)

    session = session_factory()
    rows = session.query(HoldoutScan).all()
    assert len(rows) == 2
    by_source = {r.account_source_id: r for r in rows}
    assert by_source[source_ids[0]].error is not None
    assert by_source[source_ids[1]].error is None
    assert by_source[source_ids[1]].changed is False


@pytest.mark.asyncio
async def test_a_failed_fetch_between_two_real_states_does_not_hide_the_change(
    session_factory, _patch_client
):
    """Fixed on review, 2026-08-06: _most_recent_prior_scan grabbed the
    literal most recent HoldoutScan row with no content_hash filter, so a
    failed fetch between two successful scans reset the comparison baseline
    to None instead of falling back to the last known-good hash. Reproduced:
    scan 1 succeeds (PAGE_A), scan 2 fails, scan 3 succeeds with genuinely
    different content (PAGE_B) -- scan 3 must report changed=True against
    scan 1's hash, not silently compare against scan 2's null hash and
    report no change. This is the deep scan's whole reason to exist: it
    must never under-count a real change.
    """
    tenant_id, source_ids = _make_tenant_and_sources(session_factory, ["https://acme.com/careers"])

    _patch_client["handler"] = _static_handler(PAGE_A)
    await run_deep_scan(tenant_id, holdout_size=1, seed=42)  # scan 1: succeeds, hash(A)

    def failing_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        raise httpx.ConnectError("boom")

    _patch_client["handler"] = failing_handler
    await run_deep_scan(tenant_id, holdout_size=1, seed=42)  # scan 2: fails

    _patch_client["handler"] = _static_handler(PAGE_B)
    await run_deep_scan(tenant_id, holdout_size=1, seed=42)  # scan 3: succeeds, hash(B) != hash(A)

    session = session_factory()
    rows = (
        session.query(HoldoutScan)
        .filter(HoldoutScan.account_source_id == source_ids[0])
        .order_by(HoldoutScan.fetched_at)
        .all()
    )
    assert len(rows) == 3
    assert rows[0].changed is False  # first-ever scan: seeds silently
    assert rows[1].content_hash is None  # the failed fetch
    assert rows[2].changed is True  # THE REGRESSION: must detect A->B despite the gap
