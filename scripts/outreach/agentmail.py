"""AgentMail API client — programmatic inboxes for agent-driven outbound.

Subclasses BaseAPIClient so 429/5xx backoff behaviour is shared with every
other integration rather than reimplemented per-vendor (Task 5.1).

Every field name here is verified against AgentMail's real, live API docs
(fetched directly during this task via WebFetch against docs.agentmail.to,
not assumed from the plan's reference code), which found one real defect
before it ever shipped: the plan's `Inbox` model read `data["address"]` for
the created inbox's email address. The real `POST /v0/inboxes` response
returns that field as `email`, not `address` -- the plan's code would have
raised `KeyError` on the very first real call. `send`'s request/response
shape and `get_thread`'s path matched the plan's reference exactly, so those
are unchanged.

Scope: `send` only exposes `to`/`subject`/`text`, a subset of what the real
endpoint accepts (it also supports `html`, `cc`, `bcc`, `reply_to`, `labels`,
`attachments`, `headers`) -- deliberately minimal, matching what this task's
callers actually need today; extend when a real caller needs one of the
other fields, not speculatively now.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict

from scripts.api_client import BaseAPIClient

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.agentmail.to/v0"


class Inbox(BaseModel):
    model_config = ConfigDict(frozen=True)

    inbox_id: str
    email: str


class SentMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    thread_id: str
    message_id: str


class AgentMailClient(BaseAPIClient):
    """Thin typed wrapper over AgentMail's REST API."""

    def __init__(self, api_key: str, timeout: int = 30) -> None:
        super().__init__(
            base_url=_BASE_URL,
            auth_headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def create_inbox(self, username: str, domain: str | None = None) -> Inbox:
        payload: dict[str, str] = {"username": username}
        if domain:
            payload["domain"] = domain
        data = self.post("/inboxes", json_data=payload)
        logger.info("Created AgentMail inbox %s", data.get("inbox_id"))
        return Inbox(inbox_id=data["inbox_id"], email=data["email"])

    def send(self, inbox_id: str, to: str, subject: str, text: str) -> SentMessage:
        data = self.post(
            f"/inboxes/{inbox_id}/messages/send",
            json_data={"to": [to], "subject": subject, "text": text},
        )
        return SentMessage(thread_id=data["thread_id"], message_id=data["message_id"])

    def get_thread(self, inbox_id: str, thread_id: str) -> dict:
        return self.get(f"/inboxes/{inbox_id}/threads/{thread_id}")
