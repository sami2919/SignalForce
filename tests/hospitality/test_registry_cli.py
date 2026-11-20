"""`registry --top N`: look up the licence companies behind the top cold prospects."""

from pathlib import Path

import pytest

from scripts.api_client import APIError
from scripts.hospitality import cli
from scripts.hospitality.models import Group, LicenseRecord, RegistryRecord
from scripts.hospitality.sources.registry import RECORDS
from scripts.hospitality.store import DocStore
from tests.hospitality.factories import make_scored, make_venue


def lic(record_id: str, legal: str) -> LicenseRecord:
    return LicenseRecord(
        source="sla_active", record_id=record_id, legal_name=legal, dba="", address="1 A St",
        city="NEW YORK", zip_code="10001", county="New York", license_class="252",
        description="Restaurant", received_date=None, original_issue_date=None, lat=None,
        lon=None,
    )  # fmt: skip


class FakeClient:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_on = fail_on

    def rows(self, dataset_id: str, *, where: str | None = None, **_):
        self.calls.append(where or "")
        if self.fail_on and self.fail_on in (where or ""):
            raise APIError(status_code=500, message="boom", url="https://data.ny.gov")
        return iter([])

    def count(self, dataset_id: str, *, where: str) -> int:
        self.calls.append(where)
        return 1


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DocStore:
    s = DocStore(f"sqlite:///{tmp_path}/m.db")
    monkeypatch.setattr(cli, "DocStore", lambda: s)
    seed = tmp_path / "seed.yaml"
    seed.write_text("customers: []\ndismissed_embeds: []\n")
    monkeypatch.setattr(cli, "SEED_PATH", seed)
    venues = [make_venue(f"v:{i}", group_id=f"g:{i}") for i in (1, 2, 3)]
    venues = [v.model_copy(update={"license_ids": (f"sla_active:{i}",)}) for i, v in
              zip((1, 2, 3), venues, strict=True)]  # fmt: skip
    s.save("venues", venues, key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    s.save("groups", [Group(group_id=f"g:{i}", name=f"G{i}", venue_ids=(f"v:{i}",),
                            resolution="singleton") for i in (1, 2, 3)],
           key=lambda g: g.group_id)  # type: ignore[attr-defined]  # fmt: skip
    s.save("licenses", [lic("sla_active:1", "One LLC"), lic("sla_active:2", "Two LLC"),
                        lic("sla_active:3", "Three LLC")],
           key=lambda r: r.record_id)  # type: ignore[attr-defined]  # fmt: skip
    s.save("scores", [make_scored("g:1", priority=0.9), make_scored("g:2", priority=0.5),
                      make_scored("g:3", priority=0.1)],
           key=lambda a: a.group_id)  # type: ignore[attr-defined]  # fmt: skip
    return s


def looked_up(store: DocStore) -> set[str]:
    return {r.legal_name for r in store.load(RECORDS, RegistryRecord)}


def test_registry_looks_up_licence_companies_of_top_prospects_only(store, monkeypatch) -> None:
    out = cli.registry(top=2, client=FakeClient())
    assert looked_up(store) == {"One LLC", "Two LLC"}
    assert out["prospect_groups"] == 2 and out["looked_up"] == 2 and out["not_found"] == 2


def test_registry_skips_customers(store, monkeypatch) -> None:
    monkeypatch.setattr(cli, "current_customers", lambda *a, **k: {"g:1": object()})
    out = cli.registry(top=2, client=FakeClient())
    # The customer's company is looked up too (so a cluster sharing its operator can be
    # dropped), but the customer is never one of the prospect groups.
    assert out["prospect_groups"] == 2
    assert looked_up(store) == {"One LLC", "Two LLC", "Three LLC"}


def test_registry_reports_stopped_on_budget_and_keeps_lookups(store) -> None:
    out = cli.registry(top=3, client=FakeClient(), budget=1)
    assert out["stopped"].startswith("budget")
    assert looked_up(store) == {"One LLC"}


def test_registry_reports_stopped_on_api_error_and_keeps_lookups(store) -> None:
    out = cli.registry(top=3, client=FakeClient(fail_on="TWO LLC"))
    assert out["stopped"].startswith("api error")
    assert looked_up(store) == {"One LLC"}


def test_registry_reports_stopped_on_network_error_and_keeps_lookups(store) -> None:
    import requests

    class Dropping(FakeClient):
        def rows(self, dataset_id: str, *, where: str | None = None, **_):
            if "TWO LLC" in (where or ""):
                raise requests.exceptions.ConnectionError("proxy closed the connection")
            return super().rows(dataset_id, where=where)

    out = cli.registry(top=3, client=Dropping())
    assert out["stopped"].startswith("network error")
    assert looked_up(store) == {"One LLC"}


def test_registry_counts_companies_per_named_person(store) -> None:
    row = {"dos_id": "1", "current_entity_name": "ONE LLC", "dos_process_name": "Pat Owner",
           "dos_process_address_1": "1 Main Street", "dos_process_zip": "10001"}  # fmt: skip

    class Found(FakeClient):
        def rows(self, dataset_id: str, *, where: str | None = None, **_):
            self.calls.append(where or "")
            return iter([row] if "'ONE LLC'" in (where or "") else [])

    client = Found()
    cli.registry(top=1, client=client)
    assert any("dos_process_name" in c for c in client.calls)
