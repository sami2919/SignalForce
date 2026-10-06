from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from signal_audit.synth import generate, write_sample

from scripts.web import routes_audit
from scripts.web.app import create_app
from scripts.web.invites import create_invite


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    root = tmp_path_factory.mktemp("bridge-sample")
    write_sample(generate(seed=7, n_accounts=400), root, seed=7)
    return {p.name: p.read_bytes() for p in root.iterdir()}


@pytest.fixture
def exported(monkeypatch, sample):
    """Replace the exporter with one that writes the sample and records which tenant it was asked for."""
    calls: list[int] = []

    def fake_export(session, tenant_id: int, out_dir: Path) -> dict[str, int]:
        calls.append(tenant_id)
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        for name in ("accounts.csv", "signals.csv", "outcomes.csv", "engagements.csv", "audit.json"):
            (Path(out_dir) / name).write_bytes(sample[name])
        return {"accounts": 400, "signals": 50, "outcomes": 10, "engagements": 5}

    monkeypatch.setattr(routes_audit, "export_tenant", fake_export)
    return calls


def _client(patched_sessions, slug: str | None):
    with patched_sessions() as session:
        code = create_invite(session, label=slug or "no-tenant", tenant_slug=slug)
        session.commit()
    client = TestClient(create_app())
    client.post("/login", data={"code": code}, follow_redirects=False)
    return client


def _outcomes(sample):
    return {"outcomes": ("outcomes.csv", sample["outcomes.csv"], "text/csv")}


def test_audits_the_tenants_exported_signals_with_uploaded_outcomes(patched_sessions, exported, sample):
    client = _client(patched_sessions, "alpha")
    response = client.post("/audit/from-watchlist", files=_outcomes(sample))
    assert response.status_code == 200 and response.text.startswith("<!DOCTYPE html>")
    assert len(exported) == 1


def test_the_export_is_scoped_to_the_invites_own_tenant_and_ignores_a_forged_field(
    patched_sessions, exported, sample
):
    alpha = _client(patched_sessions, "alpha")
    _client(patched_sessions, "bravo")
    alpha.post("/audit/from-watchlist", files=_outcomes(sample), data={"tenant_id": "2"})
    from sqlalchemy import select

    from scripts.storage.models import Tenant

    with patched_sessions() as session:
        alpha_id = session.scalar(select(Tenant.id).where(Tenant.slug == "alpha"))
    assert exported == [alpha_id]


def test_outcomes_are_required(patched_sessions, exported):
    client = _client(patched_sessions, "alpha")
    response = client.post("/audit/from-watchlist", files={})
    assert response.status_code == 422 and "outcomes" in response.text


def test_no_signals_yet_is_a_clear_422(patched_sessions, monkeypatch, sample):
    monkeypatch.setattr(
        routes_audit, "export_tenant",
        lambda session, tenant_id, out_dir: {"accounts": 3, "signals": 0, "outcomes": 0, "engagements": 0},
    )
    client = _client(patched_sessions, "alpha")
    response = client.post("/audit/from-watchlist", files=_outcomes(sample))
    assert response.status_code == 422 and "no signals yet" in response.text.lower()


def test_an_invite_with_no_tenant_is_refused(patched_sessions, exported, sample):
    client = _client(patched_sessions, None)
    response = client.post("/audit/from-watchlist", files=_outcomes(sample))
    assert response.status_code == 403 and exported == []
