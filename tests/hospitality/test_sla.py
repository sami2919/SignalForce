import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.hospitality.config import load_config
from scripts.hospitality.sources.sla import fetch_licenses, parse_license_row
from scripts.hospitality.sources.socrata import SocrataClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hospitality"


def load_fixture(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())


def test_parse_pending_row_uses_snake_case_fields() -> None:
    rec = parse_license_row(load_fixture("sla_pending_rows.json")[0], "sla_pending")
    assert rec is not None
    assert rec.source == "sla_pending"
    assert rec.received_date is not None and rec.original_issue_date is None
    assert rec.county == "New York"
    assert rec.record_id == "sla_pending:NA-0340-26-124979"
    assert (rec.lat, rec.lon) == (40.75011, -73.98453)


def test_parse_active_row_uses_squashed_fields() -> None:
    rec = parse_license_row(load_fixture("sla_active_rows.json")[0], "sla_active")
    assert rec is not None
    assert rec.original_issue_date is not None
    assert rec.record_id.startswith("sla_active:")
    assert rec.address == "202 LEONARD STREET A"
    assert rec.zip_code == "11206"


def test_parse_row_without_dba_defaults_empty() -> None:
    rec = parse_license_row(load_fixture("sla_pending_rows.json")[1], "sla_pending")
    assert rec is not None and rec.dba == ""


def test_parse_unknown_row_returns_none_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    assert parse_license_row({"foo": "bar"}, "sla_active") is None
    assert "unparseable SLA row" in caplog.text


def test_parse_bad_date_returns_none(caplog: pytest.LogCaptureFixture) -> None:
    row = {**load_fixture("sla_active_rows.json")[0], "originalissuedate": "not-a-date"}
    assert parse_license_row(row, "sla_active") is None
    assert "unparseable SLA row" in caplog.text


def test_fetch_licenses_filters_to_nyc() -> None:
    client = Mock(rows=Mock(return_value=iter(load_fixture("sla_active_rows.json"))))
    recs = fetch_licenses(client, load_config(), "sla_active")
    assert len(recs) == 2
    assert client.rows.call_args.args[0] == "9s3h-dpkz"
    where = client.rows.call_args.kwargs["where"]
    assert "premisescounty in(" in where and "'Kings'" in where


def test_fetch_licenses_pending_uses_snake_county_and_skips_bad_rows() -> None:
    rows = [*load_fixture("sla_pending_rows.json"), {"foo": "bar"}]
    client = Mock(rows=Mock(return_value=iter(rows)))
    recs = fetch_licenses(client, load_config(), "sla_pending")
    assert len(recs) == 2
    assert "premises_county in(" in client.rows.call_args.kwargs["where"]


def test_socrata_rows_pages_until_short_page(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SocrataClient("data.ny.gov", app_token="tok")
    pages = [[{"a": 1}, {"a": 2}], [{"a": 3}]]
    calls: list[dict] = []

    def fake_get_list(endpoint: str, params: dict | None = None) -> list[dict]:
        calls.append({"endpoint": endpoint, "params": params})
        return pages[len(calls) - 1]

    monkeypatch.setattr(client, "get_list", fake_get_list)
    out = list(client.rows("abcd-1234", where="x=1", page_size=2))
    assert out == [{"a": 1}, {"a": 2}, {"a": 3}]
    assert calls[0]["endpoint"] == "resource/abcd-1234.json"
    assert calls[0]["params"]["$offset"] == 0 and calls[1]["params"]["$offset"] == 2
    assert calls[0]["params"]["$order"] == ":id" and calls[0]["params"]["$where"] == "x=1"
    assert client._session.headers["X-App-Token"] == "tok"


def test_cli_ingest_sla_saves_each_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from scripts.hospitality import cli
    from scripts.hospitality.models import LicenseRecord
    from scripts.hospitality.store import DocStore

    store = DocStore(f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    monkeypatch.setattr(
        cli,
        "fetch_licenses",
        lambda c, cfg, source: [parse_license_row(load_fixture("sla_active_rows.json")[0], source)],
    )
    assert cli.main(["ingest-sla"]) == 0
    assert len(store.load("licenses", LicenseRecord)) == 3
