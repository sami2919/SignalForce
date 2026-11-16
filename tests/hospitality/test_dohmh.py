import json
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.hospitality.sources.dohmh import (
    fetch_first_inspections,
    fetch_never_inspected,
    merge_inspection_venues,
    parse_inspection_row,
)
from tests.hospitality.factories import make_inspection

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hospitality"


def load_fixture(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())


def test_sentinel_date_becomes_none() -> None:
    v = parse_inspection_row(
        {
            "camis": "1",
            "dba": "X",
            "boro": "Manhattan",
            "building": "1",
            "street": "BLEECKER ST",
            "zipcode": "10012",
            "first_date": "1900-01-01T00:00:00.000",
        }
    )
    assert v is not None and v.first_inspection_date is None


def test_dated_record_wins_on_merge() -> None:
    dated = make_inspection("1", first=date(2026, 9, 1))
    never = make_inspection("1", first=None)
    assert merge_inspection_venues([dated], [never]) == [dated]


def test_never_only_kept_on_merge() -> None:
    never = make_inspection("2", first=None)
    assert merge_inspection_venues([], [never]) == [never]


def test_address_is_building_plus_street() -> None:
    v = parse_inspection_row(
        {
            "camis": "2",
            "dba": "Y",
            "boro": "Brooklyn",
            "building": "289",
            "street": "BLEECKER STREET",
            "zipcode": "10014",
            "first_date": "2026-01-05T00:00:00.000",
        }
    )
    assert v is not None and v.address == "289 BLEECKER STREET"


def test_parse_fixture_fields_and_zero_coords() -> None:
    rows = load_fixture("dohmh_first_inspections.json")
    v = parse_inspection_row(rows[0])
    assert v is not None
    assert (v.lat, v.lon) == (40.731, -74.003)
    assert v.first_inspection_date == date(2026, 1, 5)
    assert v.cuisine == "American" and v.phone == "2125550101"
    never = parse_inspection_row(load_fixture("dohmh_never_inspected.json")[0])
    assert never is not None and (never.lat, never.lon) == (None, None)
    assert never.first_inspection_date is None


def test_parse_bad_row_returns_none_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    assert parse_inspection_row({"foo": "bar"}) is None
    assert parse_inspection_row({"camis": "1", "dba": "X", "first_date": "garbage"}) is None
    assert "unparseable DOHMH row" in caplog.text


def test_fetch_first_inspections_query() -> None:
    client = Mock(rows=Mock(return_value=iter(load_fixture("dohmh_first_inspections.json"))))
    venues = fetch_first_inspections(client)
    assert len(venues) == 2
    assert client.rows.call_args.args[0] == "43nn-pn8j"
    kw = client.rows.call_args.kwargs
    assert "min(inspection_date) as first_date" in kw["select"]
    assert kw["where"] == "inspection_date > '1900-01-02'"
    assert kw["group"].startswith("camis,dba,boro")


def test_fetch_never_inspected_query() -> None:
    client = Mock(rows=Mock(return_value=iter(load_fixture("dohmh_never_inspected.json"))))
    venues = fetch_never_inspected(client)
    assert [v.first_inspection_date for v in venues] == [None]
    kw = client.rows.call_args.kwargs
    assert "max(inspection_date)" in kw["having"]


def test_ingest_dohmh_cli_saves_merged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from scripts.hospitality import cli
    from scripts.hospitality.store import DocStore

    monkeypatch.setattr(cli, "SocrataClient", lambda *a, **k: Mock())
    monkeypatch.setattr(
        cli, "fetch_first_inspections", lambda c: [make_inspection("1", first=date(2026, 1, 1))]
    )
    monkeypatch.setattr(
        cli,
        "fetch_never_inspected",
        lambda c: [make_inspection("1"), make_inspection("2")],
    )
    saved: list = []
    monkeypatch.setattr(DocStore, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(
        DocStore, "save", lambda self, kind, items, key: saved.append((kind, list(items))) or 2
    )
    assert cli.ingest_dohmh() == {"venues": 2, "dated": 1, "never_inspected": 1}
    assert saved[0][0] == "inspections"


def test_grouped_query_orders_by_group_columns_and_sends_having() -> None:
    from scripts.hospitality.sources.socrata import SocrataClient

    client = SocrataClient("example.com")
    client.get_list = Mock(return_value=[])  # type: ignore[method-assign]
    list(client.rows("abcd-1234", group="camis,dba", having="max(x) < 1"))
    params = client.get_list.call_args.kwargs["params"]
    assert params["$order"] == "camis,dba" and params["$having"] == "max(x) < 1"


def _variant(dba: str, first: str, last: str, lat: str) -> dict:
    return {
        "camis": "50000001",
        "dba": dba,
        "boro": "Manhattan",
        "building": "1",
        "street": "MAIN ST",
        "zipcode": "10001",
        "cuisine_description": "American",
        "phone": "2125550100",
        "latitude": lat,
        "longitude": "-74.0",
        "first_date": first,
        "last_date": last,
    }


def test_a_renamed_or_regeocoded_site_keeps_its_true_first_inspection() -> None:
    """M9: rows group by camis plus mutable attributes; the earliest date must win.

    The site opened (first inspection) in 2019 as OLD NAME, then was renamed and re-geocoded
    in 2026. The grouped query returns one row per variant; the 2026 variant's min date must
    not make the site look like a 2026 opening.
    """
    rows = [
        _variant("OLD NAME", "2019-03-01T00:00:00.000", "2025-12-01T00:00:00.000", "40.70"),
        _variant("NEW NAME", "2026-09-01T00:00:00.000", "2026-11-01T00:00:00.000", "40.71"),
    ]
    client = Mock(rows=Mock(return_value=iter(rows)))
    venues = fetch_first_inspections(client)
    assert len(venues) == 1
    assert venues[0].first_inspection_date == date(2019, 3, 1)
    assert venues[0].dba == "NEW NAME" and venues[0].lat == 40.71  # current attributes
    assert "max(inspection_date) as last_date" in client.rows.call_args.kwargs["select"]
