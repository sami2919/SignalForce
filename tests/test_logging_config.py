"""Deployed logs are the only debugging surface. They must be machine-parseable."""

from __future__ import annotations

import json
import logging

from scripts.logging_config import JsonFormatter, configure_logging


def _emit(record_factory) -> dict:
    formatter = JsonFormatter()
    return json.loads(formatter.format(record_factory()))


def _record(**kwargs) -> logging.LogRecord:
    record = logging.LogRecord(
        name="scripts.test",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg=kwargs.pop("msg", "hello"),
        args=kwargs.pop("args", ()),
        exc_info=None,
    )
    for key, value in kwargs.items():
        setattr(record, key, value)
    return record


def test_output_is_valid_json() -> None:
    payload = _emit(lambda: _record())
    assert payload["msg"] == "hello"


def test_includes_level_logger_and_timestamp() -> None:
    payload = _emit(lambda: _record())
    assert payload["level"] == "INFO"
    assert payload["logger"] == "scripts.test"
    assert payload["ts"].endswith("+00:00")


def test_includes_extra_fields() -> None:
    """Structured extras are the point — filtering by scan_run_id must work."""
    payload = _emit(lambda: _record(scan_run_id=42, scanner="github"))
    assert payload["scan_run_id"] == 42
    assert payload["scanner"] == "github"


def test_formats_message_args() -> None:
    payload = _emit(lambda: _record(msg="scanned %d sources", args=(17,)))
    assert payload["msg"] == "scanned 17 sources"


def test_includes_exception_on_one_line() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _record()
        record.exc_info = sys.exc_info()
        line = JsonFormatter().format(record)
    assert "\n" not in line, "a multi-line log record breaks line-based aggregation"
    assert "boom" in json.loads(line)["exc"]


def test_non_serializable_extra_does_not_raise() -> None:
    """A logging call must never crash the thing it is reporting on."""
    payload = _emit(lambda: _record(obj=object()))
    assert "obj" in payload


def test_configure_logging_is_idempotent() -> None:
    """The app factory may run many times in tests; handlers must not stack."""
    configure_logging()
    first = len(logging.getLogger().handlers)
    configure_logging()
    assert len(logging.getLogger().handlers) == first


def test_configure_logging_respects_log_level(monkeypatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    configure_logging(force=True)
    assert logging.getLogger().level == logging.WARNING
