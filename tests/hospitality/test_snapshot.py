from datetime import date

import pytest

from scripts.hospitality.sources.snapshot import first_seen_pending, take_snapshot
from scripts.hospitality.store import DocStore
from tests.hospitality.factories import make_license


@pytest.fixture
def tmp_store(tmp_path) -> DocStore:
    return DocStore(f"sqlite:///{tmp_path}/t.db")


def test_first_seen_is_earliest_snapshot(tmp_store: DocStore) -> None:
    a = make_license("sla_pending:1", source="sla_pending")
    take_snapshot(tmp_store, [a], date(2026, 11, 16))
    take_snapshot(tmp_store, [a], date(2026, 11, 17))
    assert first_seen_pending(tmp_store) == {"sla_pending:1": date(2026, 11, 16)}


def test_snapshot_is_idempotent_per_day_and_counts_rows(tmp_store: DocStore) -> None:
    recs = [make_license("sla_pending:1"), make_license("sla_pending:2")]
    assert take_snapshot(tmp_store, recs, date(2026, 11, 16)) == 2
    assert take_snapshot(tmp_store, recs, date(2026, 11, 16)) == 2
    assert len(first_seen_pending(tmp_store)) == 2


def test_empty_store_has_no_first_seen(tmp_store: DocStore) -> None:
    assert first_seen_pending(tmp_store) == {}
