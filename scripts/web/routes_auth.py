"""Landing page, login and logout."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from scripts.web.auth import SESSION_KEY, authenticate

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@router.get("/", response_class=HTMLResponse)
def landing(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "landing.html", {})


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": ""})


@router.post("/login", response_model=None)
def login(request: Request, code: str = Form("")) -> HTMLResponse | RedirectResponse:
    identity = authenticate(code)
    if identity is None:
        return templates.TemplateResponse(
            request, "login.html", {"error": "That invite code is not valid."}, status_code=401
        )
    request.session.clear()  # new session on login: no fixation
    request.session[SESSION_KEY] = identity.id
    return RedirectResponse("/audit", status_code=303)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=303)
