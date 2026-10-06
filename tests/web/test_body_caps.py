"""Every POST route gets a bounded body, not only the upload routes.

FastAPI parses a Form(...) body before any dependency runs, so without a cap
an anonymous client could make the server read megabytes at /login.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scripts.web.app import create_app

ONE_MIB = 1024 * 1024


def _chunks(total: int, size: int = 8192):
    sent = 0
    while sent < total:
        yield b"x" * size
        sent += size


@pytest.fixture
def anon(patched_sessions):
    return TestClient(create_app(), follow_redirects=False)


def test_caps_are_explicit_config():
    from scripts.web.upload_guard import DEFAULT_POST_CAP, POST_CAPS

    assert DEFAULT_POST_CAP == 64 * 1024
    assert POST_CAPS["/webhooks/agentmail"] == ONE_MIB


@pytest.mark.parametrize("path", ["/login", "/watchlist", "/logout"])
def test_declared_oversize_post_is_a_413_for_anonymous_callers(anon, path):
    response = anon.post(
        path,
        content=b"code=" + b"x" * ONE_MIB,
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 413


@pytest.mark.parametrize("path", ["/login", "/watchlist"])
def test_streamed_oversize_post_without_content_length_is_a_413(anon, path):
    response = anon.post(
        path,
        content=_chunks(ONE_MIB),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 413


def test_oversize_watchlist_post_is_a_413_when_logged_in(logged_in):
    declared = logged_in.post(
        "/watchlist",
        content=b"domains=" + b"x" * ONE_MIB,
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    streamed = logged_in.post(
        "/watchlist",
        content=_chunks(ONE_MIB),
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert declared.status_code == 413
    assert streamed.status_code == 413


def test_multipart_oversize_login_is_a_413(anon):
    response = anon.post("/login", files={"code": ("big.bin", b"x" * ONE_MIB, "application/octet-stream")})
    assert response.status_code == 413


def test_normal_login_still_works(anon, patched_sessions):
    from scripts.web.invites import create_invite

    with patched_sessions() as session:
        code = create_invite(session, label="cap", tenant_slug="cap")
        session.commit()
    assert anon.post("/login", data={"code": "wrong"}).status_code == 401
    assert anon.post("/login", data={"code": code}).status_code == 303


def test_get_requests_are_unaffected(anon):
    assert anon.get("/login").status_code == 200
