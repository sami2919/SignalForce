"""FastAPI application factory.

The factory exists for test isolation (fresh instance per test, no shared
state). The module-level `app` exists because `uvicorn scripts.web.app:app`
needs an importable object. Both are intentional — see ADR-0002 Decision 4.
"""

from __future__ import annotations

from fastapi import FastAPI

from scripts.logging_config import configure_logging
from scripts.web.routes_dashboard import router as dashboard_router
from scripts.web.routes_health import router as health_router
from scripts.web.routes_webhooks import router as webhooks_router


def create_app() -> FastAPI:
    """Build a fresh FastAPI instance."""
    configure_logging()
    app = FastAPI(
        title="SignalForce",
        version="0.2.0",
        description="Signal detection engine — deployed instance.",
    )
    app.include_router(health_router)
    app.include_router(dashboard_router)
    app.include_router(webhooks_router)
    return app


app = create_app()
