"""Tests for scripts/watch/runner.py.

The heart of this file: test_changed_hash_NOT_confirmed_leaves_last_hash_untouched.
Greenhouse renders an unresolved tags.new i18n key on ~17% of fetches (measured
2026-08-04: 6 fetches, 2 distinct hashes). If an unconfirmed change updated
last_hash, that noise would be recorded as signal and the next run would report
another change when it flipped back — doubling the false-positive rate instead
of removing it. See docs/decisions/0005-watch-layer-concurrency-and-persistence.md,
Decision 2.
"""

from __future__ import annotations


import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.storage.models import AccountSource, Base, Probe, ScanRun, Tenant
from scripts.watch import runner as runner_module
from scripts.watch.runner import resolve_and_store, run_watch_pass

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
    """Route scripts.storage.session.get_session at the runner to our in-memory engine."""
    import contextlib

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

    monkeypatch.setattr(runner_module, "get_session", _get_session)


_tenant_counter = {"n": 0}


def _make_tenant_and_sources(
    session_factory, urls: list[str], *, last_hash: str | None = None, active: bool = True
) -> tuple[int, list[int]]:
    _tenant_counter["n"] += 1
    session = session_factory()
    tenant = Tenant(slug=f"t{_tenant_counter['n']}", name="T1")
    session.add(tenant)
    session.commit()

    from scripts.storage.models import Account

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
            last_hash=last_hash,
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

    monkeypatch.setattr(runner_module.httpx, "AsyncClient", _Client)
    return state


# --- the pass ---


@pytest.mark.asyncio
async def test_watch_pass_creates_a_scan_run_row(session_factory):
    tenant_id, _ = _make_tenant_and_sources(session_factory, ["https://acme.com/careers"])
    run_id = await run_watch_pass(tenant_id)

    session = session_factory()
    run = session.get(ScanRun, run_id)
    assert run is not None
    assert run.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_watch_pass_writes_one_probe_per_active_source(session_factory):
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory,
        ["https://acme.com/careers", "https://acme.com/docs"],
    )
    run_id = await run_watch_pass(tenant_id)

    session = session_factory()
    probes = session.query(Probe).filter_by(scan_run_id=run_id).all()
    assert len(probes) == 2
    assert {p.account_source_id for p in probes} == set(source_ids)


@pytest.mark.asyncio
async def test_watch_pass_skips_inactive_sources(session_factory):
    tenant_id, active_ids = _make_tenant_and_sources(
        session_factory, ["https://acme.com/careers"], active=True
    )
    _tenant_id2, _inactive_ids = _make_tenant_and_sources(
        session_factory, ["https://acme.com/dead"], active=False
    )
    # inactive source belongs to a different account under the SAME tenant
    session = session_factory()
    from scripts.storage.models import Account

    account = session.query(Account).filter_by(tenant_id=tenant_id).one()
    dead = AccountSource(
        tenant_id=tenant_id,
        account_id=account.id,
        source_type="docs",
        url="https://acme.com/dead",
        active=False,
    )
    session.add(dead)
    session.commit()
    session.close()

    run_id = await run_watch_pass(tenant_id)

    session = session_factory()
    probes = session.query(Probe).filter_by(scan_run_id=run_id).all()
    assert len(probes) == 1
    assert probes[0].account_source_id == active_ids[0]


@pytest.mark.asyncio
async def test_watch_pass_records_p50_and_p95_latency(session_factory):
    tenant_id, _ = _make_tenant_and_sources(
        session_factory, ["https://acme.com/careers", "https://acme.com/docs"]
    )
    run_id = await run_watch_pass(tenant_id)

    session = session_factory()
    run = session.get(ScanRun, run_id)
    assert run.p50_latency_ms >= 0
    assert run.p95_latency_ms >= run.p50_latency_ms


@pytest.mark.asyncio
async def test_watch_pass_sets_status_completed_on_success(session_factory):
    tenant_id, _ = _make_tenant_and_sources(session_factory, ["https://acme.com/careers"])
    run_id = await run_watch_pass(tenant_id)

    session = session_factory()
    run = session.get(ScanRun, run_id)
    assert run.status == "completed"
    assert run.finished_at is not None


# --- confirm-on-change ---


@pytest.mark.asyncio
async def test_unchanged_hash_records_probe_with_changed_false(session_factory, _patch_client):
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory, ["https://acme.com/careers"], last_hash=None
    )
    # First pass to establish baseline.
    _patch_client["handler"] = _static_handler(PAGE_A)
    await run_watch_pass(tenant_id)

    # Second pass, same content -> unchanged.
    run_id = await run_watch_pass(tenant_id)

    session = session_factory()
    probe = session.query(Probe).filter_by(scan_run_id=run_id).one()
    assert probe.changed is False


@pytest.mark.asyncio
async def test_changed_hash_confirmed_by_second_fetch_records_change(
    session_factory, _patch_client
):
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory, ["https://acme.com/careers"], last_hash=None
    )
    _patch_client["handler"] = _static_handler(PAGE_A)
    await run_watch_pass(tenant_id)  # baseline

    # Now content genuinely changes and stays changed across both confirm fetches.
    _patch_client["handler"] = _static_handler(PAGE_B)
    run_id = await run_watch_pass(tenant_id)

    session = session_factory()
    probe = session.query(Probe).filter_by(scan_run_id=run_id).one()
    assert probe.changed is True

    src = session.get(AccountSource, source_ids[0])
    from scripts.watch.normalize import content_hash

    assert src.last_hash == content_hash(PAGE_B)

    run = session.get(ScanRun, run_id)
    assert run.changes_detected == 1


@pytest.mark.asyncio
async def test_changed_hash_NOT_confirmed_leaves_last_hash_untouched(
    session_factory, _patch_client
):
    """The heart of this task.

    First fetch of a run differs from last_hash, but the confirmation
    re-fetch disagrees (flaky content). The probe must record changed=False
    and last_hash must be untouched, so the next run re-evaluates from the
    same baseline instead of recording noise as signal.
    """
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory, ["https://acme.com/careers"], last_hash=None
    )
    _patch_client["handler"] = _static_handler(PAGE_A)
    await run_watch_pass(tenant_id)  # baseline: last_hash = hash(PAGE_A)

    from scripts.watch.normalize import content_hash

    baseline_hash = content_hash(PAGE_A)

    # First fetch of pass 2 returns PAGE_B (looks changed); confirmation
    # re-fetch returns PAGE_A again (flip back) -> disagreement.
    calls = {"n": 0}

    def flaky_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        calls["n"] += 1
        return httpx.Response(200, text=PAGE_B if calls["n"] == 1 else PAGE_A)

    _patch_client["handler"] = flaky_handler
    run_id = await run_watch_pass(tenant_id)

    session = session_factory()
    probe = session.query(Probe).filter_by(scan_run_id=run_id).one()
    assert probe.changed is False

    src = session.get(AccountSource, source_ids[0])
    assert src.last_hash == baseline_hash

    run = session.get(ScanRun, run_id)
    assert run.changes_detected == 0


@pytest.mark.asyncio
async def test_unconfirmed_change_increments_confirm_rejected_counter(
    session_factory, _patch_client
):
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory, ["https://acme.com/careers"], last_hash=None
    )
    _patch_client["handler"] = _static_handler(PAGE_A)
    await run_watch_pass(tenant_id)

    calls = {"n": 0}

    def flaky_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        calls["n"] += 1
        return httpx.Response(200, text=PAGE_B if calls["n"] == 1 else PAGE_A)

    _patch_client["handler"] = flaky_handler
    run_id = await run_watch_pass(tenant_id)

    session = session_factory()
    run = session.get(ScanRun, run_id)
    assert run.confirm_rejected == 1


@pytest.mark.asyncio
async def test_confirmation_only_refetches_sources_that_appeared_changed(
    session_factory, _patch_client
):
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory,
        ["https://acme.com/careers", "https://acme.com/docs"],
        last_hash=None,
    )
    _patch_client["handler"] = _static_handler(PAGE_A)
    await run_watch_pass(tenant_id)  # baseline for both

    hits = {"careers": 0, "docs": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        if "careers" in request.url.path:
            hits["careers"] += 1
            return httpx.Response(200, text=PAGE_B)  # changes
        hits["docs"] += 1
        return httpx.Response(200, text=PAGE_A)  # unchanged

    _patch_client["handler"] = handler
    await run_watch_pass(tenant_id)

    # careers fetched twice (initial + confirm), docs fetched once.
    assert hits["careers"] == 2
    assert hits["docs"] == 1


@pytest.mark.asyncio
async def test_first_ever_probe_sets_last_hash_without_requiring_confirmation(
    session_factory, _patch_client
):
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory, ["https://acme.com/careers"], last_hash=None
    )
    hit_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        hit_count["n"] += 1
        return httpx.Response(200, text=PAGE_A)

    _patch_client["handler"] = handler
    run_id = await run_watch_pass(tenant_id)

    # No confirmation fetch on a first probe.
    assert hit_count["n"] == 1

    session = session_factory()
    probe = session.query(Probe).filter_by(scan_run_id=run_id).one()
    assert probe.changed is False

    from scripts.watch.normalize import content_hash

    src = session.get(AccountSource, source_ids[0])
    assert src.last_hash == content_hash(PAGE_A)

    run = session.get(ScanRun, run_id)
    assert run.changes_detected == 0


# --- failure handling ---


@pytest.mark.asyncio
async def test_fetch_error_increments_consecutive_failures(session_factory, _patch_client):
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory, ["https://acme.com/careers"], last_hash=None
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        raise httpx.ConnectError("boom")

    _patch_client["handler"] = handler
    await run_watch_pass(tenant_id)

    session = session_factory()
    src = session.get(AccountSource, source_ids[0])
    assert src.consecutive_failures == 1


@pytest.mark.asyncio
async def test_successful_fetch_resets_consecutive_failures(session_factory, _patch_client):
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory, ["https://acme.com/careers"], last_hash=None
    )
    session = session_factory()
    src = session.get(AccountSource, source_ids[0])
    src.consecutive_failures = 3
    session.commit()
    session.close()

    _patch_client["handler"] = _static_handler(PAGE_A)
    await run_watch_pass(tenant_id)

    session = session_factory()
    src = session.get(AccountSource, source_ids[0])
    assert src.consecutive_failures == 0


@pytest.mark.asyncio
async def test_source_deactivated_after_five_consecutive_failures(session_factory, _patch_client):
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory, ["https://acme.com/careers"], last_hash=None
    )
    session = session_factory()
    src = session.get(AccountSource, source_ids[0])
    src.consecutive_failures = 4
    session.commit()
    session.close()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        raise httpx.ConnectError("boom")

    _patch_client["handler"] = handler
    await run_watch_pass(tenant_id)

    session = session_factory()
    src = session.get(AccountSource, source_ids[0])
    assert src.consecutive_failures == 5
    assert src.active is False


@pytest.mark.asyncio
async def test_deactivated_sources_are_counted_on_the_run(session_factory, _patch_client):
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory, ["https://acme.com/careers"], last_hash=None
    )
    session = session_factory()
    src = session.get(AccountSource, source_ids[0])
    src.consecutive_failures = 4
    session.commit()
    session.close()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        raise httpx.ConnectError("boom")

    _patch_client["handler"] = handler
    run_id = await run_watch_pass(tenant_id)

    session = session_factory()
    run = session.get(ScanRun, run_id)
    assert run.sources_probed == 1


@pytest.mark.asyncio
async def test_one_failing_source_does_not_abort_the_pass(session_factory, _patch_client):
    tenant_id, source_ids = _make_tenant_and_sources(
        session_factory,
        ["https://bad.com/careers", "https://acme.com/docs"],
        last_hash=None,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW)
        if request.url.host == "bad.com":
            raise httpx.ConnectError("boom")
        return httpx.Response(200, text=PAGE_A)

    _patch_client["handler"] = handler
    run_id = await run_watch_pass(tenant_id)

    session = session_factory()
    probes = session.query(Probe).filter_by(scan_run_id=run_id).all()
    assert len(probes) == 2

    run = session.get(ScanRun, run_id)
    assert run.status == "completed"


# --- the run record must survive a crash ---


@pytest.mark.asyncio
async def test_scan_run_marked_failed_when_the_pass_raises(session_factory, monkeypatch):
    tenant_id, _ = _make_tenant_and_sources(session_factory, ["https://acme.com/careers"])

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(runner_module, "fetch_all", _boom)

    with pytest.raises(RuntimeError):
        await run_watch_pass(tenant_id)

    session = session_factory()
    run = session.query(ScanRun).filter_by(tenant_id=tenant_id).one()
    assert run.status == "failed"


@pytest.mark.asyncio
async def test_scan_run_records_the_error_message(session_factory, monkeypatch):
    tenant_id, _ = _make_tenant_and_sources(session_factory, ["https://acme.com/careers"])

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(runner_module, "fetch_all", _boom)

    with pytest.raises(RuntimeError):
        await run_watch_pass(tenant_id)

    session = session_factory()
    run = session.query(ScanRun).filter_by(tenant_id=tenant_id).one()
    assert run.error is not None
    assert "simulated crash" in run.error


# --- resolve_and_store ---


@pytest.mark.asyncio
async def test_resolve_and_store_persists_resolved_sources(session_factory, monkeypatch):
    from scripts.registry.models import ResolutionReport, ResolvedSource, SourceAttempt

    async def _fake_resolve_sources(domain, client):
        return ResolutionReport(
            domain=domain,
            sources=[
                ResolvedSource(
                    source_type="careers",
                    url=f"https://{domain}/careers",
                    method="heuristic",
                    confidence=0.9,
                )
            ],
            attempts=[
                SourceAttempt(
                    source_type="careers",
                    outcome="resolved",
                    url=f"https://{domain}/careers",
                    detail="",
                )
            ],
            homepage_reachable=True,
        )

    monkeypatch.setattr(runner_module, "resolve_sources", _fake_resolve_sources)

    session = session_factory()
    tenant = Tenant(slug="t1", name="T1")
    session.add(tenant)
    session.commit()
    tenant_id = tenant.id
    session.close()

    result = await resolve_and_store(tenant_id, ["acme.com"])
    assert result.created == 1

    session = session_factory()
    assert session.query(AccountSource).count() == 1
