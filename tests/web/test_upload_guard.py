import pytest
from fastapi.testclient import TestClient
from signal_audit.synth import generate, write_sample

from scripts.web import routes_audit
from scripts.web.app import create_app


@pytest.fixture(scope="module")
def sample_files(tmp_path_factory):
    root = tmp_path_factory.mktemp("guard-sample")
    write_sample(generate(seed=7, n_accounts=400), root, seed=7)
    return {p.name: p.read_bytes() for p in root.iterdir()}


def _files(sample_files):
    return {
        kind: (f"{kind}.csv", sample_files[f"{kind}.csv"], "text/csv")
        for kind in ("accounts", "signals", "outcomes")
    }


def _small_limit(monkeypatch, total: int = 1024):
    # The app's limit() adds 1 MB of overhead; subtract it to get a tiny effective limit.
    monkeypatch.setattr(routes_audit, "MAX_TOTAL_BYTES", total - 1024 * 1024)


def test_anonymous_upload_is_redirected_without_reading_the_body(patched_sessions):
    response = TestClient(create_app()).post(
        "/audit/run", files={"accounts": ("accounts.csv", b"x" * 100, "text/csv")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_declared_oversize_body_is_a_413(logged_in, sample_files, monkeypatch):
    _small_limit(monkeypatch)
    response = logged_in.post("/audit/run", files=_files(sample_files))
    assert response.status_code == 413


def test_streamed_body_without_content_length_is_a_413(logged_in, monkeypatch):
    _small_limit(monkeypatch)

    def chunks():
        for _ in range(50):
            yield b"x" * 1024

    response = logged_in.post(
        "/audit/run",
        content=chunks(),
        headers={"content-type": "multipart/form-data; boundary=zzz"},
    )
    assert response.status_code == 413


def test_normal_upload_under_the_limit_still_works(logged_in, sample_files):
    assert logged_in.post("/audit/run", files=_files(sample_files)).status_code == 200


def test_get_audit_is_unaffected(logged_in):
    assert logged_in.get("/audit").status_code == 200


def _guard(limit=100):
    from scripts.web.upload_guard import UploadGuardMiddleware

    async def inner(scope, receive, send):
        while (await receive()).get("more_body"):
            pass
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return UploadGuardMiddleware(inner, paths=("/audit/run",), limit=lambda: limit)


async def _run(guard, session, headers, chunks=(), path="/audit/run", method="POST"):
    sent, calls, queue = [], [], list(chunks)

    async def receive():
        calls.append(1)
        if not queue:
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.request", "body": queue.pop(0), "more_body": bool(queue)}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": method, "path": path,
             "headers": headers, "session": session}
    await guard(scope, receive, send)
    return [m["status"] for m in sent if m["type"] == "http.response.start"], len(calls)


@pytest.mark.anyio
async def test_guard_never_reads_the_body_for_anonymous_callers():
    statuses, reads = await _run(_guard(), {}, [(b"content-length", b"50")], [b"x" * 50])
    assert statuses == [303] and reads == 0


@pytest.mark.anyio
async def test_guard_never_reads_a_declared_oversize_body():
    statuses, reads = await _run(
        _guard(), {"invite_id": 1}, [(b"content-length", b"500")], [b"x" * 500]
    )
    assert statuses == [413] and reads == 0


@pytest.mark.anyio
async def test_guard_sends_exactly_one_response_for_streamed_oversize():
    chunks = [b"x" * 60, b"x" * 60, b"x" * 60]
    statuses, _ = await _run(_guard(), {"invite_id": 1}, [], chunks)
    assert statuses == [413]


def _capped_guard(default_cap=100, caps=None):
    from scripts.web.upload_guard import UploadGuardMiddleware

    async def inner(scope, receive, send):
        while (await receive()).get("more_body"):
            pass
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return UploadGuardMiddleware(
        inner, paths=("/audit/run",), limit=lambda: 10_000,
        caps=caps or {"/hook": 300}, default_cap=default_cap,
    )


@pytest.mark.anyio
async def test_other_posts_never_read_a_declared_oversize_body_even_anonymously():
    statuses, reads = await _run(
        _capped_guard(), {}, [(b"content-length", b"500")], [b"x" * 500], path="/login"
    )
    assert statuses == [413] and reads == 0


@pytest.mark.anyio
async def test_other_posts_send_exactly_one_413_for_streamed_oversize():
    statuses, _ = await _run(_capped_guard(), {}, [], [b"x" * 60] * 3, path="/login")
    assert statuses == [413]


@pytest.mark.anyio
async def test_a_path_specific_cap_overrides_the_default():
    ok, _ = await _run(_capped_guard(), {}, [], [b"x" * 60] * 3, path="/hook")
    over, _ = await _run(_capped_guard(), {}, [], [b"x" * 60] * 6, path="/hook")
    assert ok == [200] and over == [413]


@pytest.mark.anyio
async def test_non_post_requests_are_not_capped():
    statuses, _ = await _run(_capped_guard(), {}, [], [b"x" * 60] * 6, path="/login", method="PUT")
    assert statuses == [200]
