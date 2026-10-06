"""Pure-ASGI guard that vets upload requests before the multipart body is parsed.

FastAPI parses (and spools to disk) a multipart body before dependencies run,
so without this an anonymous client could stream unlimited bytes at an upload
route. The guard sits inside SessionMiddleware: it rejects anonymous callers
without reading the body, rejects a declared oversize body, and counts bytes
as they stream so chunked bodies are cut off too.
"""

from __future__ import annotations

from collections.abc import Callable

from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from scripts.web.auth import SESSION_KEY


class _TooLarge(Exception):
    pass


class UploadGuardMiddleware:
    def __init__(self, app: ASGIApp, paths: tuple[str, ...], limit: Callable[[], int]) -> None:
        self.app = app
        self.paths = paths
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in self.paths:
            await self.app(scope, receive, send)
            return
        if not scope.get("session", {}).get(SESSION_KEY):
            await RedirectResponse("/login", status_code=303)(scope, receive, send)
            return
        limit = self.limit()
        if _declared_length(scope) > limit:
            await _too_large()(scope, receive, send)
            return
        await self._stream(scope, receive, send, limit)

    async def _stream(self, scope: Scope, receive: Receive, send: Send, limit: int) -> None:
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
            await _too_large()(scope, receive, send)


def _declared_length(scope: Scope) -> int:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return 0
    return 0


def _too_large() -> PlainTextResponse:
    return PlainTextResponse("Upload too large.", status_code=413)
