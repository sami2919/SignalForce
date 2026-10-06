"""FastAPI application factory.

The factory exists for test isolation (fresh instance per test, no shared
state). The module-level `app` exists because `uvicorn scripts.web.app:app`
needs an importable object. Both are intentional — see ADR-0002 Decision 4.
"""

from __future__ import annotations

import os
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from scripts.logging_config import configure_logging
from scripts.web.auth import LoginRequired
from scripts.web.routes_auth import router as auth_router
from scripts.web.routes_dashboard import router as dashboard_router
from scripts.web.routes_health import router as health_router
from scripts.web.routes_webhooks import router as webhooks_router

_SESSION_DAYS = 14


def _is_production() -> bool:
    return os.environ.get("APP_ENV") == "production"


def _session_secret() -> str:
    secret = os.environ.get("SESSION_SECRET")
    if secret:
        return secret
    if _is_production():
        raise RuntimeError("SESSION_SECRET must be set when APP_ENV=production")
    return secrets.token_urlsafe(32)  # dev and tests: sessions reset on restart


async def _redirect_to_login(request: Request, exc: LoginRequired) -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


def create_app() -> FastAPI:
    """Build a fresh FastAPI instance."""
    configure_logging()
    app = FastAPI(
        title="SignalForce",
        version="0.3.0",
        description="Signal detection engine and Signal Audit — invite-only.",
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=_session_secret(),
        session_cookie="sf_session",
        same_site="lax",
        https_only=_is_production(),
        max_age=_SESSION_DAYS * 24 * 3600,
    )
    app.add_exception_handler(LoginRequired, _redirect_to_login)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(webhooks_router)
    return app


app = create_app()
