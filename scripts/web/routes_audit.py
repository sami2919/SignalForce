"""Signal Audit pages: upload CSVs, get the report. Nothing is stored."""

from __future__ import annotations

import io
import logging
import tempfile
import threading
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from signal_audit.errors import AuditError
from signal_audit.service import audit_uploads
from signal_audit.synth import generate, write_sample
from starlette.concurrency import run_in_threadpool

from scripts.web.auth import InviteIdentity, require_invite

logger = logging.getLogger(__name__)
router = APIRouter(tags=["audit"])
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

_MB = 1024 * 1024
MAX_FILE_BYTES = 5 * _MB
MAX_TOTAL_BYTES = 15 * _MB
_slots = threading.BoundedSemaphore(2)  # audits run at once; extra requests get a 429

# The report is built from the uploader's own data and served from our origin,
# so it gets a policy that allows nothing but inline styles.
REPORT_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

_EXTENSIONS = {"config": ".json"}  # every other field is a .csv


class UploadRejected(Exception):
    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


class Busy(Exception):
    pass


def _form(request: Request, error: str = "", status: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "audit_form.html",
        {"error": error, "max_mb": MAX_FILE_BYTES // _MB},
        status_code=status,
    )


async def _collect(files: dict[str, UploadFile | None]) -> dict[str, bytes]:
    """Read each upload with a hard size cap. Field names, not filenames, decide the kind."""
    collected: dict[str, bytes] = {}
    total = 0
    for kind, upload in files.items():
        if upload is None or not upload.filename:
            continue
        wanted = _EXTENSIONS.get(kind, ".csv")
        if not upload.filename.lower().endswith(wanted):
            raise UploadRejected(f"{kind}: please upload a {wanted} file", 422)
        data = await upload.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise UploadRejected(f"{kind}: file is larger than {MAX_FILE_BYTES // _MB} MB", 413)
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise UploadRejected(f"files together exceed {MAX_TOTAL_BYTES // _MB} MB", 413)
        collected[kind] = data
    return collected


def _run_guarded(uploads: dict[str, bytes], config_bytes: bytes | None) -> str:
    if not _slots.acquire(blocking=False):
        raise Busy()
    try:
        return audit_uploads(uploads, config_bytes)
    finally:
        _slots.release()


@router.get("/audit", response_class=HTMLResponse)
def audit_form(request: Request, invite: InviteIdentity = Depends(require_invite)) -> HTMLResponse:
    return _form(request)


@router.post("/audit/run", response_model=None)
async def run_audit_page(
    request: Request,
    accounts: UploadFile | None = File(None),
    signals: UploadFile | None = File(None),
    outcomes: UploadFile | None = File(None),
    engagements: UploadFile | None = File(None),
    holdout_lag: UploadFile | None = File(None),
    config: UploadFile | None = File(None),
    invite: InviteIdentity = Depends(require_invite),
) -> Response:
    try:
        uploads = await _collect(
            {
                "accounts": accounts, "signals": signals, "outcomes": outcomes,
                "engagements": engagements, "holdout_lag": holdout_lag, "config": config,
            }
        )
        config_bytes = uploads.pop("config", None)
        html = await run_in_threadpool(_run_guarded, uploads, config_bytes)
    except UploadRejected as exc:
        return _form(request, str(exc), exc.status)
    except Busy:
        return _form(request, "The audit is busy with other runs. Try again in a minute.", 429)
    except AuditError as exc:
        return _form(request, str(exc), 422)
    except Exception as exc:  # noqa: BLE001 -- log the type only: messages can contain row data
        logger.error("audit failed", extra={"invite_id": invite.id, "error_type": type(exc).__name__})
        return _form(request, "Something went wrong running the audit. Nothing was stored.", 500)
    logger.info(
        "audit run", extra={"invite_id": invite.id, "bytes": sum(len(b) for b in uploads.values())}
    )
    return HTMLResponse(html, headers=REPORT_HEADERS)


@router.get("/audit/sample.zip")
def sample_zip(invite: InviteIdentity = Depends(require_invite)) -> Response:
    with tempfile.TemporaryDirectory(prefix="signal-audit-sample-") as tmp:
        root = Path(tmp)
        write_sample(generate(seed=7, n_accounts=400), root, seed=7)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.iterdir()):
                archive.write(path, arcname=path.name)
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="signal-audit-sample.zip"'},
    )
