import glob
import io
import logging
import os
import tempfile
import threading
import zipfile

import pytest
from signal_audit.synth import generate, write_sample

from scripts.web import routes_audit


@pytest.fixture(scope="module")
def sample_files(tmp_path_factory):
    root = tmp_path_factory.mktemp("web-sample")
    write_sample(generate(seed=7, n_accounts=400), root, seed=7)
    return {p.name: p.read_bytes() for p in root.iterdir()}


def _files(sample_files, **overrides):
    files = {
        kind: (f"{kind}.csv", sample_files[f"{kind}.csv"], "text/csv")
        for kind in ("accounts", "signals", "outcomes", "engagements")
    }
    files["config"] = ("audit.json", sample_files["audit.json"], "application/json")
    files.update(overrides)
    return files


def _tmp_dirs() -> set[str]:
    return set(glob.glob(os.path.join(tempfile.gettempdir(), "signal-audit-*")))


def test_form_requires_login(patched_sessions):
    from fastapi.testclient import TestClient

    from scripts.web.app import create_app

    response = TestClient(create_app()).get("/audit", follow_redirects=False)
    assert response.status_code == 303


def test_form_states_the_data_promise(logged_in):
    body = logged_in.get("/audit").text
    assert "Nothing is stored" in body


def test_happy_path_returns_the_report_with_safe_headers(logged_in, sample_files):
    response = logged_in.post("/audit/run", files=_files(sample_files))
    assert response.status_code == 200
    assert response.text.startswith("<!DOCTYPE html>")
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_run_leaves_nothing_behind(logged_in, sample_files):
    before = _tmp_dirs()
    logged_in.post("/audit/run", files=_files(sample_files))
    assert _tmp_dirs() == before


def test_missing_required_file_is_a_422_that_names_it(logged_in, sample_files):
    files = _files(sample_files)
    del files["signals"]
    response = logged_in.post("/audit/run", files=files)
    assert response.status_code == 422 and "missing required file(s): signals" in response.text


def test_wrong_extension_is_rejected(logged_in, sample_files):
    files = _files(sample_files, signals=("signals.xlsx", b"x", "application/octet-stream"))
    response = logged_in.post("/audit/run", files=files)
    assert response.status_code == 422 and "please upload a .csv file" in response.text


def test_non_utf8_csv_gets_the_clear_error_not_a_traceback(logged_in, sample_files):
    files = _files(sample_files, signals=("signals.csv", b"\xff\xfe\x00bad", "text/csv"))
    response = logged_in.post("/audit/run", files=files)
    assert response.status_code == 422
    assert "UTF-8" in response.text and "Traceback" not in response.text


def test_oversized_file_is_a_413(logged_in, sample_files, monkeypatch):
    monkeypatch.setattr(routes_audit, "MAX_FILE_BYTES", 1024)
    response = logged_in.post("/audit/run", files=_files(sample_files))
    assert response.status_code == 413


def test_hostile_markup_in_the_csv_is_escaped_in_the_report(logged_in, sample_files):
    payload = "<script>alert(1)</script>"
    header, *rows = sample_files["signals.csv"].decode().splitlines()
    columns = header.split(",")
    type_at, source_at = columns.index("signal_type"), columns.index("source")
    poisoned_rows = []
    for row in rows[:20]:
        cells = row.split(",")
        cells[type_at] = payload
        cells[source_at] = payload
        poisoned_rows.append(",".join(cells))
    poisoned = "\n".join([header, *poisoned_rows, *rows[20:]]).encode()
    files = _files(sample_files, signals=("signals.csv", poisoned, "text/csv"))
    response = logged_in.post("/audit/run", files=files)
    assert response.status_code == 200
    assert "&lt;script&gt;" in response.text
    assert "<script>alert(1)" not in response.text


def test_busy_server_says_so_with_a_429(logged_in, sample_files, monkeypatch):
    monkeypatch.setattr(routes_audit, "_slots", threading.BoundedSemaphore(0))
    response = logged_in.post("/audit/run", files=_files(sample_files))
    assert response.status_code == 429


def test_internal_error_is_generic_and_never_logs_the_data(
    logged_in, sample_files, monkeypatch, caplog
):
    def boom(*args, **kwargs):
        raise RuntimeError("row data: ACME-SECRET-ROW")

    monkeypatch.setattr(routes_audit, "audit_uploads", boom)
    with caplog.at_level(logging.DEBUG):
        response = logged_in.post("/audit/run", files=_files(sample_files))
    assert response.status_code == 500
    assert "ACME-SECRET-ROW" not in response.text
    assert "ACME-SECRET-ROW" not in caplog.text


def test_sample_zip_contains_a_runnable_dataset(logged_in, sample_files):
    response = logged_in.get("/audit/sample.zip")
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    names = set(zipfile.ZipFile(io.BytesIO(response.content)).namelist())
    assert {"accounts.csv", "signals.csv", "outcomes.csv", "audit.json"} <= names
