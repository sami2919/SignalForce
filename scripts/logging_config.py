"""Structured JSON logging for deployed environments.

Fly captures stdout, so that is where logs go. JSON rather than prose because
`fly logs` output needs filtering by fields like scan_run_id and scanner —
which prose cannot support. Exceptions are folded onto a single line so that
line-based aggregation is not broken by tracebacks.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

# Structural LogRecord attributes. Anything else on the record came from an
# `extra=` argument and is a field the caller wants preserved.
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

_configured = False


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as one line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value

        # default=str so an unserialisable extra degrades to its repr rather
        # than raising. A logging call must never crash its caller.
        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None, force: bool = False) -> None:
    """Install the JSON formatter on the root logger, writing to stdout.

    Idempotent: repeated calls are no-ops unless `force` is set. The app factory
    calls this, and the factory runs once per test.
    """
    global _configured
    if _configured and not force:
        return

    resolved = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()
    root = logging.getLogger()

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(resolved)

    _configured = True
