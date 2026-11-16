"""Clay hand-off: push prospect rows to a Clay table by webhook, import its enriched CSV.

The webhook gets prospect rows only: customers and disqualified groups are never pushed. The
webhook URL is a secret (it carries the table's token): it is never logged and never placed in
an error message or a stored record. One POST per row, each preceded by a budget spend.

The CSV export is untrusted input: missing or extra columns and blank rows are tolerated, rows
not tied to a known group are skipped and logged, and an email is kept only if it parses as one
as given, never constructed.
"""

import csv
import logging
import re
from collections.abc import Collection, Sequence
from pathlib import Path
from urllib.parse import urlparse

import requests

from scripts.hospitality.budget import CallBudget
from scripts.hospitality.contacts.waterfall import _contact_id, role_priority
from scripts.hospitality.models import Contact, ScoredAccount, Venue

logger = logging.getLogger(__name__)

TOP_EVIDENCE_COUNT = 3
POST_TIMEOUT_S = 30
_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


class ClayPushError(RuntimeError):
    """A Clay webhook push failed. The message never contains the webhook URL."""


def _domain(url: str | None) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    return host.removeprefix("www.")


def _top_evidence(account: ScoredAccount) -> str:
    counted = sorted(
        (c for c in account.contributions if c.contribution > 0), key=lambda c: -c.contribution
    )
    return "; ".join(f"{c.signal_type}={c.contribution:.2f}" for c in counted[:TOP_EVIDENCE_COUNT])


def clay_rows(
    accounts: Sequence[ScoredAccount],
    venues: Sequence[Venue],
    contacts: Sequence[Contact],
) -> list[dict[str, str]]:
    """One row per cold-prospect group. Customers and disqualified groups yield no row."""
    by_group: dict[str, list[Venue]] = {}
    for v in sorted(venues, key=lambda v: v.venue_id):
        by_group.setdefault(v.group_id, []).append(v)
    best: dict[str, Contact] = {}
    for c in sorted(contacts, key=lambda c: (role_priority(c.role), c.email is None, c.name)):
        best.setdefault(c.group_id, c)
    rows: list[dict[str, str]] = []
    for a in accounts:
        if a.is_customer or a.disqualified_reason is not None:
            continue
        members = by_group.get(a.group_id, [])
        site = next((v.website for v in members if v.website), None)
        c = best.get(a.group_id)
        rows.append(
            {
                "group_id": a.group_id,
                "name": members[0].name if members else a.group_id,
                "domain": _domain(site),
                "priority": f"{a.priority:.3f}",
                "top_evidence": _top_evidence(a),
                "contact_name": c.name if c else "",
                "contact_role": c.role if c else "",
                "contact_email": (c.email or "") if c else "",
            }
        )
    return rows


def push_to_clay(webhook_url: str, rows: Sequence[dict[str, str]], budget: CallBudget) -> int:
    """POST each row to the Clay webhook; returns the number pushed.

    Spends one budget call before each POST (BudgetExceeded stops the push). Failures raise
    ClayPushError carrying only the status code or exception type, never the URL.
    """
    if not webhook_url:
        raise ValueError("CLAY_WEBHOOK_URL is not set; cannot push to Clay")
    pushed = 0
    for row in rows:
        budget.spend()  # spend first: the call over the limit never goes out
        try:
            resp = requests.post(webhook_url, json=row, timeout=POST_TIMEOUT_S)
        except requests.RequestException as exc:
            logger.error(
                "clay push failed: group=%s error=%s", row.get("group_id"), type(exc).__name__
            )
            raise ClayPushError(f"Clay webhook request failed ({type(exc).__name__})") from None
        if not 200 <= resp.status_code < 300:
            logger.error(
                "clay push rejected: group=%s status=%s", row.get("group_id"), resp.status_code
            )
            raise ClayPushError(f"Clay webhook returned HTTP {resp.status_code}")
        pushed += 1
    return pushed


def _confidence(raw: str | None) -> float | None:
    try:
        return float(raw) if raw and raw.strip() else None
    except ValueError:
        return None


def _better(new: Contact, old: Contact) -> bool:
    return (new.email_confidence or -1.0) > (old.email_confidence or -1.0)


def import_clay_csv(path: Path, known_group_ids: Collection[str] | None = None) -> list[Contact]:
    """Contacts from Clay's CSV export (`group_id, name, role, email, email_confidence`).

    Rows without a group id or name, or (when `known_group_ids` is given) for an unknown group,
    are skipped and logged. Duplicate people within the file keep the best email.
    """
    out: dict[str, Contact] = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        for n, raw in enumerate(csv.DictReader(fh), start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            gid, name = row.get("group_id", ""), row.get("name", "")
            if not gid or not name:
                logger.info("clay csv line %d skipped: missing group_id or name", n)
                continue
            if known_group_ids is not None and gid not in known_group_ids:
                logger.warning("clay csv line %d skipped: unknown group %s", n, gid)
                continue
            email = row.get("email") or None
            if email is not None and not _EMAIL.match(email):
                logger.warning("clay csv line %d: dropped malformed email for %s", n, name)
                email = None
            contact = Contact(
                contact_id=_contact_id(gid, name),
                group_id=gid,
                name=name,
                role=row.get("role", ""),
                email=email,
                email_confidence=_confidence(row.get("email_confidence")) if email else None,
                instagram=None,
                phone=None,
                source="clay",
                evidence_ref=f"clay_csv:{Path(path).name}",
            )
            prev = out.get(contact.contact_id)
            if prev is None or (contact.email and (prev.email is None or _better(contact, prev))):
                out[contact.contact_id] = contact
    return list(out.values())


def merge_contact(existing: Contact, imported: Contact) -> Contact:
    """Keep the existing contact unless the import adds an email or a higher-confidence one.

    A page-sourced email (no confidence score) is never replaced. Existing channels are kept.
    """
    if not imported.email:
        return existing
    replace = existing.email is None or (
        existing.email_confidence is not None
        and imported.email_confidence is not None
        and imported.email_confidence > existing.email_confidence
    )
    if not replace:
        return existing
    return imported.model_copy(
        update={
            "role": existing.role or imported.role,
            "instagram": existing.instagram,
            "phone": existing.phone,
        }
    )


if __name__ == "__main__":
    import sys

    print("Run: python -m scripts.hospitality.cli clay-push --top 25", file=sys.stderr)
