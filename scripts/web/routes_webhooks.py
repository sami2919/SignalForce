"""AgentMail reply webhook: records outcome data against the outreach that
triggered it (Task 5.2, ADR-0020).

Verified against the real, installed `svix` package (not just documentation
or a GitHub branch -- see ADR-0020 Decision 1): `Webhook.verify()` returns
the parsed JSON payload directly (the underlying library's default
`json_parse=True` applies), so no separate `json.loads()` is needed after a
successful verification.

Reads the RAW request body (`await request.body()`), not a Pydantic request
model -- signature verification must run against the exact bytes AgentMail
signed, before any parsing.

Response codes are NOT uniformly 200 (ADR-0020 Decision 3, a correction to
the plan's own stated "webhooks must never 500" principle, not just its
code): a permanent non-match (unknown thread, wrong event type, missing
thread_id, unparseable body) returns 200, since retrying can never fix it --
but a missing secret (500, real misconfiguration) or genuinely transient
processing failure (500, so Svix's own retry can recover it) do NOT get
silently swallowed into a fake success, which would permanently discard that
reply's outcome data.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from svix.webhooks import Webhook, WebhookVerificationError

from scripts.storage.models import Outreach
from scripts.storage.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

_MESSAGE_RECEIVED = "message.received"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _record_reply(thread_id: str, session: Session) -> None:
    """First reply wins (ADR-0020 Decision 4) -- a later reply on an
    already-answered thread is logged, not silently overwritten, since
    time-to-FIRST-reply is the outcome metric Task 5.3's cohort lift cares
    about."""
    outreach = session.execute(
        select(Outreach).where(Outreach.agentmail_thread_id == thread_id)
    ).scalar_one_or_none()

    if outreach is None:
        logger.info("no outreach found for thread_id", extra={"thread_id": thread_id})
        return

    if outreach.replied_at is not None:
        logger.info(
            "thread already has a recorded reply -- keeping the first one",
            extra={"thread_id": thread_id, "first_reply_at": outreach.replied_at.isoformat()},
        )
        return

    outreach.replied_at = _utcnow()


@router.post("/webhooks/agentmail")
async def agentmail_webhook(request: Request) -> Response:
    secret = os.environ.get("AGENTMAIL_WEBHOOK_SECRET")
    if not secret:
        logger.error("AGENTMAIL_WEBHOOK_SECRET is not set -- cannot verify webhook")
        raise HTTPException(status_code=500, detail="webhook not configured")

    raw_body = await request.body()
    headers = dict(request.headers)

    try:
        payload = Webhook(secret).verify(raw_body, headers)
    except WebhookVerificationError:
        logger.warning("AgentMail webhook signature verification failed")
        raise HTTPException(status_code=401, detail="invalid signature")

    if not isinstance(payload, dict):
        logger.error(
            "AgentMail webhook payload was not a JSON object after verification",
            extra={"payload_type": type(payload).__name__},
        )
        return Response(status_code=200)

    event_type = payload.get("event_type")
    if event_type != _MESSAGE_RECEIVED:
        logger.info(
            "ignoring non-message.received AgentMail event", extra={"event_type": event_type}
        )
        return Response(status_code=200)

    message = payload.get("message") or {}
    thread_id = message.get("thread_id")
    if not thread_id:
        logger.warning("message.received webhook had no thread_id")
        return Response(status_code=200)

    # Deliberately NOT wrapped in a broad try/except: a DB error here is a
    # transient failure, not a permanent non-match, and per ADR-0020
    # Decision 3 it must surface as a real 500 (FastAPI's default handler
    # does this for an uncaught exception) so Svix's own retry can recover
    # it -- swallowing it into a 200 would report success while silently
    # discarding this reply's outcome data forever.
    with get_session() as session:
        _record_reply(thread_id, session)

    return Response(status_code=200)
