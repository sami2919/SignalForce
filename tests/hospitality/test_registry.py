"""NY company registry lookup: exact-name matching, caching and a hard budget."""

from pathlib import Path

import pytest

from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.sources.registry import (
    count_companies_at,
    lookup_companies,
    normalize_company,
    registry_link,
)
from scripts.hospitality.store import DocStore

MADDY = {
    "dos_id": "111",
    "current_entity_name": "RIP RAF LLC",
    "initial_dos_filing_date": "2023-01-05T00:00:00.000",
    "dos_process_name": "Matthew Maddy",
    "dos_process_address_1": "716 Marcy Avenue",
    "dos_process_zip": "11206",
}


class FakeClient:
    """Answers `rows` from a dict of exact entity name -> rows; counts every call."""

    def __init__(self, by_name: dict[str, list[dict]], count: int = 3) -> None:
        self.by_name = by_name
        self.count_value = count
        self.calls: list[dict] = []

    def count(self, dataset_id: str, *, where: str) -> int:
        self.calls.append({"dataset": dataset_id, "where": where, "select": "count(*)"})
        return self.count_value

    def rows(self, dataset_id: str, *, where: str | None = None, select: str | None = None, **_):
        self.calls.append({"dataset": dataset_id, "where": where, "select": select})
        for name, rows in self.by_name.items():
            if f"'{name}'" in (where or ""):
                return iter(rows)
        return iter([])


@pytest.fixture
def store(tmp_path: Path) -> DocStore:
    return DocStore(f"sqlite:///{tmp_path}/m.db")


def test_normalize_company_equates_llc_and_inc_forms() -> None:
    assert normalize_company("Rip Raf, L.L.C.") == normalize_company("RIP RAF LLC")
    assert normalize_company("HTNY 1 Inc.") == normalize_company("HTNY 1 INC")
    assert normalize_company("Rip Raff LLC") != normalize_company("Rip Raf LLC")


def test_lookup_returns_found_and_not_found(store: DocStore) -> None:
    client = FakeClient({"RIP RAF LLC": [MADDY]})
    out = lookup_companies(["Rip Raf LLC", "HTNY 1 Inc"], client, CallBudget("registry", 10), store)
    by = {r.legal_name: r for r in out}
    rip = by["Rip Raf LLC"]
    assert rip.found and rip.dos_id == "111" and rip.process_name == "Matthew Maddy"
    assert rip.process_address == "716 Marcy Avenue" and rip.process_zip == "11206"
    assert not by["HTNY 1 Inc"].found and by["HTNY 1 Inc"].dos_id is None


def test_several_matches_take_newest_filing_and_note_it(store: DocStore) -> None:
    old = {**MADDY, "dos_id": "100", "initial_dos_filing_date": "2010-01-01T00:00:00.000"}
    client = FakeClient({"RIP RAF LLC": [old, MADDY]})
    [rec] = lookup_companies(["Rip Raf LLC"], client, CallBudget("registry", 10), store)
    assert rec.dos_id == "111"
    assert "2" in rec.note


def test_cached_names_make_no_request(store: DocStore) -> None:
    client = FakeClient({"RIP RAF LLC": [MADDY]})
    lookup_companies(["Rip Raf LLC", "HTNY 1 Inc"], client, CallBudget("registry", 10), store)
    client.calls.clear()
    again = lookup_companies(["RIP RAF, L.L.C.", "HTNY 1 Inc"], client, CallBudget("r", 10), store)
    assert client.calls == []
    assert len(again) == 2


def test_budget_stops_before_the_request_over_the_limit(store: DocStore) -> None:
    client = FakeClient({"RIP RAF LLC": [MADDY]})
    with pytest.raises(BudgetExceeded):
        lookup_companies(["Rip Raf LLC", "HTNY 1 Inc"], client, CallBudget("registry", 1), store)
    assert len(client.calls) == 1
    cached = lookup_companies(["Rip Raf LLC"], FakeClient({}), CallBudget("r", 0), store)
    assert cached[0].found


def test_count_companies_at_is_cached(store: DocStore) -> None:
    client = FakeClient({}, count=40)
    budget = CallBudget("registry", 10)
    assert count_companies_at("716 Marcy Avenue", "11206", client, budget, store) == 40
    assert count_companies_at("716 Marcy Avenue", "11206", client, budget, store) == 40
    assert len(client.calls) == 1


def test_registry_link_format() -> None:
    assert registry_link("111") == "https://data.ny.gov/resource/n9v6-gdp6.json?dos_id=111"


def test_lookup_finds_a_punctuation_variant_of_the_suffix(store: DocStore) -> None:
    row = {**MADDY, "current_entity_name": "HTNY 1 INC.", "dos_id": "222"}
    client = FakeClient({"HTNY 1 INC.": [row]})
    [rec] = lookup_companies(["HTNY 1 Inc"], client, CallBudget("registry", 10), store)
    assert rec.found and rec.dos_id == "222"


def test_socrata_count_sends_no_sort_order() -> None:
    # A count(*) query is an aggregate: Socrata rejects it with the `$order=:id` rows() adds.
    from unittest.mock import patch

    from scripts.hospitality.sources.socrata import SocrataClient

    client = SocrataClient("data.ny.gov")
    with patch.object(client, "get_list", return_value=[{"count": "7"}]) as get:
        assert client.count("n9v6-gdp6", where="x = 1") == 7
    params = get.call_args.kwargs.get("params") or get.call_args.args[1]
    assert "$order" not in params and params["$select"] == "count(*)"


def test_lookup_keeps_the_first_address_line_for_counting(store: DocStore) -> None:
    row = {
        **MADDY,
        "dos_process_address_1": "Attn: J. Doe",
        "dos_process_address_2": "711 Third Ave",
    }
    [rec] = lookup_companies(["Rip Raf LLC"], FakeClient({"RIP RAF LLC": [row]}),
                             CallBudget("registry", 10), store)  # fmt: skip
    assert rec.process_address == "Attn: J. Doe 711 Third Ave"
    assert rec.process_address_1 == "Attn: J. Doe"


def test_i4_name_with_punctuation_matches_a_suffix_spelling_variant(store: DocStore) -> None:
    row = {**MADDY, "current_entity_name": "NICK & DOMS PIZZERIA, INC.", "dos_id": "333"}
    client = FakeClient({"NICK & DOMS PIZZERIA, INC.": [row]})
    [rec] = lookup_companies(["NICK & DOMS PIZZERIA INC"], client, CallBudget("r", 10), store)
    assert rec.found and rec.dos_id == "333"


def test_config_is_read_as_utf8_on_every_platform(monkeypatch) -> None:
    # Windows defaults to cp1252, which cannot read accented names in the config (Shmoné).
    import pathlib

    from scripts.hospitality.config import load_config

    seen: list[str | None] = []
    real_open = pathlib.Path.open

    def spy(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self.suffix in {".yaml", ".yml"}:
            seen.append(kwargs.get("encoding"))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", spy)
    cfg = load_config()
    assert seen and all(e == "utf-8" for e in seen)
    assert any("Shmon" in a for a in cfg.accolades)
