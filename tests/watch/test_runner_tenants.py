import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.registry.store import ensure_account, ensure_tenant
from scripts.storage.models import AccountSource, Base
from scripts.watch import runner


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


def _seed(session, slug: str, *, active: bool = True) -> None:
    tenant_id = ensure_tenant(slug, slug, session)
    account_id = ensure_account(tenant_id, f"{slug}.example", session)
    session.add(
        AccountSource(
            tenant_id=tenant_id,
            account_id=account_id,
            source_type="careers",
            url=f"https://{slug}.example/careers",
            active=active,
        )
    )
    session.commit()


def test_all_mode_returns_tenants_with_an_active_source_sorted(session, monkeypatch):
    for slug in ("zeta", "alpha"):
        _seed(session, slug)
    _seed(session, "dormant", active=False)
    ensure_tenant("empty", "empty", session)
    monkeypatch.setenv("SCAN_TENANTS", "all")
    monkeypatch.setenv("TENANT_SLUG", "ignored")
    assert runner._tenant_slugs_to_scan(session) == ["alpha", "zeta"]


def test_single_tenant_mode_is_unchanged(session, monkeypatch):
    monkeypatch.delenv("SCAN_TENANTS", raising=False)
    monkeypatch.setenv("TENANT_SLUG", "agentmail")
    assert runner._tenant_slugs_to_scan(session) == ["agentmail"]


def test_nothing_configured_scans_nothing(session, monkeypatch):
    monkeypatch.delenv("SCAN_TENANTS", raising=False)
    monkeypatch.delenv("TENANT_SLUG", raising=False)
    assert runner._tenant_slugs_to_scan(session) == []


def test_one_tenant_crashing_does_not_stop_the_others(monkeypatch):
    seen: list[str] = []

    def fake_scan(slug: str) -> int:
        seen.append(slug)
        if slug == "alpha":
            raise RuntimeError("boom")
        return 0

    monkeypatch.setattr(runner, "_scan_tenant", fake_scan)
    monkeypatch.setattr(runner, "_tenant_slugs_to_scan", lambda session: ["alpha", "bravo"])
    monkeypatch.setattr(runner, "get_session", lambda: _NullSession())
    assert runner._cli_scan() == 1
    assert seen == ["alpha", "bravo"]


def test_exit_code_is_zero_only_when_every_tenant_succeeds(monkeypatch):
    monkeypatch.setattr(runner, "_scan_tenant", lambda slug: 0)
    monkeypatch.setattr(runner, "_tenant_slugs_to_scan", lambda session: ["alpha", "bravo"])
    monkeypatch.setattr(runner, "get_session", lambda: _NullSession())
    assert runner._cli_scan() == 0


def test_no_tenants_is_an_error_exit(monkeypatch):
    monkeypatch.setattr(runner, "_tenant_slugs_to_scan", lambda session: [])
    monkeypatch.setattr(runner, "get_session", lambda: _NullSession())
    assert runner._cli_scan() == 1


class _NullSession:
    def __enter__(self):
        return object()

    def __exit__(self, *exc):
        return False
