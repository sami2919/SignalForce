"""Export one tenant's SignalForce data as Signal Audit input CSVs.

Design: ~/.gstack/projects/sami2919-visitor-intent-pipeline/sami-main-design-20260929-205620.md,
"Outside Voice Revisions": SignalForce feeds the audit through a CSV export, not a Postgres adapter
or schema migration. Person-level fields (contact name, email, title) are never written; replies are
exported at company level only. All SignalForce sources are web-change sources, so they share one
source family, and the audit's two-family rule cannot fire on SignalForce data alone.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.storage.models import Account, AccountSource, Contact, Outreach, SignalEvent, Tenant

SEQUENCE_SPAN = timedelta(
    days=14
)  # an outreach thread counts as an active sequence for 14 days after send
FAMILY = "web_change"
COLUMNS = {
    "accounts": ["domain", "company_name", "employee_band", "country", "fit_tier"],
    "signals": [
        "domain",
        "signal_type",
        "source",
        "source_event_id",
        "observed_at",
        "ingested_at",
        "verified",
        "evidence_ref",
    ],
    "outcomes": ["domain", "outcome_type", "occurred_at"],
    "engagements": ["domain", "kind", "start_at", "end_at"],
}


def _iso(ts: datetime | None) -> str:
    if ts is None:
        return ""
    if ts.tzinfo is None:  # SQLite drops tzinfo; SignalForce stores UTC
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat()


def _verified(event: SignalEvent) -> str:
    # Step 1 of the plan checks this assumption against ADR-0014: a signal_events row
    # is only ever created from run_verify_stage, which only processes sources whose
    # body was retained via on_confirmed_change -- itself only invoked by run_watch_pass
    # when the confirm fetch's content_hash matches the original (scripts/watch/runner.py,
    # confirm_results branch). The rejected-confirm branch increments confirm_rejected
    # and never calls on_confirmed_change, so a rejected change can never reach this
    # export. Every row here is already verified.
    return "true"


def _write(path: Path, columns: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def export_tenant(session: Session, tenant_id: int, out_dir: Path) -> dict[str, int]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    accounts = [
        {
            "domain": a.domain,
            "company_name": a.name,
            "employee_band": (a.account_metadata or {}).get("employee_band", ""),
            "country": (a.account_metadata or {}).get("country", ""),
            "fit_tier": "",
        }
        for a in session.scalars(
            select(Account).where(Account.tenant_id == tenant_id).order_by(Account.domain)
        )
    ]
    events = session.execute(
        select(SignalEvent, Account.domain, AccountSource.source_type, AccountSource.url)
        .join(
            Account,
            (SignalEvent.account_id == Account.id) & (Account.tenant_id == tenant_id),
        )
        .outerjoin(
            AccountSource,
            (SignalEvent.account_source_id == AccountSource.id)
            & (AccountSource.tenant_id == tenant_id),
        )
        .where(SignalEvent.tenant_id == tenant_id)
        .order_by(SignalEvent.id)
    ).all()
    signals = [
        {
            "domain": domain,
            "signal_type": ev.signal_type,
            "source": f"signalforce_{source_type}" if source_type else "signalforce",
            "source_event_id": f"sf:{ev.id}",
            "observed_at": _iso(ev.occurred_at or ev.detected_at),
            "ingested_at": _iso(ev.detected_at),
            "verified": _verified(ev),
            "evidence_ref": url or "",
        }
        for ev, domain, source_type, url in events
    ]
    sends = session.execute(
        select(Outreach.sent_at, Outreach.replied_at, Account.domain)
        .join(
            Contact,
            (Outreach.contact_id == Contact.id) & (Contact.tenant_id == tenant_id),
        )
        .join(
            Account,
            (Contact.account_id == Account.id) & (Account.tenant_id == tenant_id),
        )
        .where(Outreach.tenant_id == tenant_id)
        .order_by(Outreach.id)
    ).all()
    outcomes = [
        {"domain": d, "outcome_type": "reply", "occurred_at": _iso(replied)}
        for _, replied, d in sends
        if replied is not None
    ]
    engagements = [
        {
            "domain": d,
            "kind": "sequence_active",
            "start_at": _iso(sent),
            "end_at": _iso(sent + SEQUENCE_SPAN),
        }
        for sent, _, d in sends
    ]
    tables = {
        "accounts": accounts,
        "signals": signals,
        "outcomes": outcomes,
        "engagements": engagements,
    }
    for name, rows in tables.items():
        _write(out / f"{name}.csv", COLUMNS[name], rows)
    families = {source: FAMILY for source in sorted({row["source"] for row in signals})}
    (out / "audit.json").write_text(
        json.dumps({"source_families": families}, indent=2, sort_keys=True) + "\n"
    )
    return {name: len(rows) for name, rows in tables.items()}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Export a tenant's data as Signal Audit input CSVs."
    )
    parser.add_argument("--tenant-slug", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    from scripts.storage.session import get_session

    with get_session() as session:
        tenant = session.scalar(select(Tenant).where(Tenant.slug == args.tenant_slug))
        if tenant is None:
            raise SystemExit(f"no tenant with slug {args.tenant_slug!r}")
        print(json.dumps(export_tenant(session, tenant.id, args.out)))


if __name__ == "__main__":
    main()
