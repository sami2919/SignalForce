"""Email open tracking helpers.

Open tracking works by embedding a 1x1 image URL in an email. When the email
client requests that image, SignalForce records a single unique ``opened``
outcome for the matching outreach event and returns a transparent GIF.
"""

from __future__ import annotations

import argparse
import base64
import html
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

from sqlalchemy.engine import Engine

from scripts.db import OutcomeEvent, OutreachEvent, create_db_engine, get_session, init_db
from scripts.outcome_tracker import log_outcome

TRACKING_PIXEL_BYTES = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==")
TRACKING_PIXEL_HEADERS = {
    "Content-Type": "image/gif",
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}


def get_tracking_token(engine: Engine, outreach_event_id: int) -> Optional[str]:
    """Return the open tracking token for an outreach event, if one exists."""
    with get_session(engine) as session:
        row = session.query(OutreachEvent).filter(OutreachEvent.id == outreach_event_id).first()
        return str(row.tracking_token) if row is not None and row.tracking_token else None


def build_open_tracking_url(
    engine: Engine,
    outreach_event_id: int,
    *,
    base_url: str,
    path: str = "/track/open.gif",
) -> str:
    """Build the tracking pixel URL for an outreach event."""
    token = get_tracking_token(engine, outreach_event_id)
    if not token:
        raise ValueError(f"outreach event {outreach_event_id} does not have a tracking token")

    normalized_base = base_url.rstrip("/")
    normalized_path = "/" + path.lstrip("/")
    return f"{normalized_base}{normalized_path}?{urlencode({'t': token})}"


def build_tracking_pixel_html(
    engine: Engine,
    outreach_event_id: int,
    *,
    base_url: str,
    path: str = "/track/open.gif",
) -> str:
    """Return a minimal HTML img tag for open tracking."""
    url = build_open_tracking_url(
        engine,
        outreach_event_id,
        base_url=base_url,
        path=path,
    )
    return (
        f'<img src="{html.escape(url, quote=True)}" width="1" height="1" '
        'alt="" style="display:none" />'
    )


def log_email_open(
    engine: Engine,
    tracking_token: str,
    *,
    occurred_at: Optional[datetime] = None,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Optional[int]:
    """Record a unique email open for the outreach event matching ``tracking_token``.

    Returns the ``outcome_events.id`` for the created or existing open event.
    Invalid tokens return ``None`` so tracking endpoints can still return the
    transparent pixel without leaking whether a token was valid.
    """
    with get_session(engine) as session:
        outreach = (
            session.query(OutreachEvent)
            .filter(OutreachEvent.tracking_token == tracking_token)
            .filter(OutreachEvent.channel == "email")
            .first()
        )
        if outreach is None:
            return None

        existing = (
            session.query(OutcomeEvent)
            .filter(OutcomeEvent.outreach_event_id == outreach.id)
            .filter(OutcomeEvent.outcome_type == "opened")
            .first()
        )
        if existing is not None:
            return int(existing.id)

        outreach_id = int(outreach.id)

    notes = _open_notes(user_agent=user_agent, ip_address=ip_address)
    return log_outcome(
        engine,
        outreach_id,
        outcome_type="opened",
        notes=notes,
        occurred_at=occurred_at,
        external_id=tracking_token,
    )


def tracking_pixel_response(
    engine: Engine,
    tracking_token: str,
    *,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> tuple[int, dict[str, str], bytes]:
    """Record an open and return an HTTP-style transparent pixel response."""
    log_email_open(
        engine,
        tracking_token,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    return 200, dict(TRACKING_PIXEL_HEADERS), TRACKING_PIXEL_BYTES


def run_tracking_server(
    engine: Engine,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    path: str = "/track/open.gif",
) -> None:
    """Run a tiny local HTTP server for tracking pixel requests."""

    class TrackingHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            if parsed.path != path:
                self.send_error(404)
                return

            token = parse_qs(parsed.query).get("t", [""])[0]
            status, headers, body = tracking_pixel_response(
                engine,
                token,
                user_agent=self.headers.get("User-Agent"),
                ip_address=self.client_address[0],
            )
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), TrackingHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _open_notes(*, user_agent: Optional[str], ip_address: Optional[str]) -> str:
    parts = []
    if user_agent:
        parts.append(f"user_agent={user_agent[:200]}")
    if ip_address:
        parts.append(f"ip={ip_address}")
    return "; ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SignalForce email open tracker.")
    parser.add_argument("--db-url", default=None, help="SQLAlchemy DB URL. Defaults to local DB.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8080, help="Bind port.")
    parser.add_argument("--path", default="/track/open.gif", help="Tracking pixel path.")
    args = parser.parse_args()

    engine = create_db_engine(args.db_url)
    init_db(engine)
    run_tracking_server(engine, host=args.host, port=args.port, path=args.path)


if __name__ == "__main__":
    main()
