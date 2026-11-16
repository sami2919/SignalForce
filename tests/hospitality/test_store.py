import pytest

from scripts.hospitality.models import LicenseRecord
from scripts.hospitality.store import DocStore
from tests.hospitality.factories import make_license


def test_docstore_upsert_is_idempotent(tmp_path) -> None:
    store = DocStore(f"sqlite:///{tmp_path}/t.db")
    rec = make_license("sla:1")
    store.save("licenses", [rec, rec], key=lambda r: r.record_id)
    assert store.load("licenses", LicenseRecord) == [rec]


def test_docstore_upsert_updates_and_clear(tmp_path) -> None:
    store = DocStore(f"sqlite:///{tmp_path}/sub/t.db")
    store.save("licenses", [make_license("sla:1", dba="A")], key=lambda r: r.record_id)
    store.save("licenses", [make_license("sla:1", dba="B")], key=lambda r: r.record_id)
    assert [r.dba for r in store.load("licenses", LicenseRecord)] == ["B"]
    store.clear("licenses")
    assert store.load("licenses", LicenseRecord) == []


def test_docstore_rejects_bad_kind(tmp_path) -> None:
    store = DocStore(f"sqlite:///{tmp_path}/t.db")
    with pytest.raises(ValueError):
        store.load("x; drop table y", LicenseRecord)
