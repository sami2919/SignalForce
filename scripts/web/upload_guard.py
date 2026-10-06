"""Pure-ASGI guard that bounds every POST body before FastAPI parses it.

FastAPI parses (and spools to disk) a form or multipart body before
dependencies run, so without this an anonymous client could stream unlimited
bytes at any POST route. The guard sits inside SessionMiddleware.

- Upload paths (`paths`): anonymous callers are redirected to /login without
  reading the body; the cap is `limit()`, read per request.
- Every other POST: the cap is `caps[path]`, else `default_cap`
  (64 KiB; the Svix-signed AgentMail webhook gets 1 MiB). No auth gate here:
  /login is anonymous by design.

In both cases a declared oversize body (Content-Length) is a 413 without
reading anything, and bytes are counted as they stream so chunked bodies are
cut off too. Non-POST requests pass straight through.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from scripts.web.auth import SESSION_KEY


DEFAULT_POST_CAP = 64 * 1024
POST_CAPS: Mapping[str, int] = {
    "/webhooks/agentmail": 1024 * 1024,  # a Svix-signed JSON event
}


class _TooLarge(Exception):
    pass


class UploadGuardMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        paths: tuple[str, ...],
        limit: Callable[[], int],
        caps: Mapping[str, int] = POST_CAPS,
        default_cap: int = DEFAULT_POST_CAP,
    ) -> None:
        self.app = app
        self.paths = paths
        self.limit = limit
        self.caps = caps
        self.default_cap = default_cap

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        if path in self.paths:
            if not scope.get("session", {}).get(SESSION_KEY):
                await RedirectResponse("/login", status_code=303)(scope, receive, send)
                return
            limit, reason = self.limit(), "Upload too large."
        else:
            limit, reason = self.caps.get(path, self.default_cap), "Request body too large."
        if _declared_length(scope) > limit:
            await _too_large(reason)(scope, receive, send)
            return
        await self._stream(scope, receive, send, limit, reason)

    async def _stream(
        self, scope: Scope, receive: Receive, send: Send, limit: int, reason: str
    ) -> None:
        seen = 0
        exceeded = False
        started = False

        async def counting_receive() -> Message:
            nonlocal seen, exceeded
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    exceeded = True
                    raise _TooLarge()
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if exceeded and not started:
                return  # the app's reaction (often a 400) is replaced by our 413
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _TooLarge:
            pass
        if exceeded and not started:
            await _too_large(reason)(scope, receive, send)


def _declared_length(scope: Scope) -> int:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return 0
    return 0


def _too_large(reason: str) -> PlainTextResponse:
    return PlainTextResponse(reason, status_code=413)
