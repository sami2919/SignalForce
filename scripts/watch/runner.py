"""The watch pass: fetch every active source, confirm-on-change, record results.

Four phases, deliberately not interleaved (ADR-0005 Decision 3):

    1. SYNC DB READ    create the scan_runs row (status="running"), load active
                        sources for the tenant and their last_hash, close the
                        session.
    2. ASYNC FETCH      fetch_all() over every active source.
    3. ASYNC CONFIRM     re-fetch only sources whose hash differs from
                        last_hash (and that have a last_hash to differ from)
                        once, and require agreement before treating it as a
                        real change (ADR-0005 Decision 2).
    4. SYNC DB WRITE    one Probe row per phase-2 result, batched 500/commit;
                        update each source's last_fetched_at,
                        consecutive_failures, active, and last_hash (only on
                        a confirmed change or a first-ever probe); finalise
                        scan_runs with counts, latencies, status="completed".

Phases 2-4 are wrapped so that if anything raises, the scan_runs row is
still finalised as status="failed" with the error recorded before
re-raising — a run stuck at "running" forever is the silent failure
ADR-0005 Decision 5 exists to prevent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.logging_config import configure_logging
from scripts.measure.daily_postprocess import run_daily_postprocess
from scripts.net.guard import guarded_client
from scripts.registry.resolver import resolve_sources
from scripts.registry.store import StoreResult, ensure_tenant, store_resolution
from scripts.scoring.wiring import run_scoring_stage
from scripts.storage.models import AccountSource, Probe, ScanRun, Tenant
from scripts.storage.session import get_session
from scripts.verify.wiring import run_verify_stage
from scripts.watch.fetcher import ProbeResult, SourceRef, fetch_all

logger = logging.getLogger(__name__)

_DEACTIVATE_AFTER_FAILURES = 5
_WRITE_BATCH_SIZE = 500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = min(int(len(ordered) * pct), len(ordered) - 1)
    return ordered[idx]


async def resolve_and_store(tenant_id: int, domains: list[str]) -> StoreResult:
    """Resolve each domain and persist the result. Aggregates counts across all domains."""
    created = 0
    updated = 0
    deactivated = 0
    async with guarded_client() as client:
        for domain in domains:
            report = await resolve_sources(domain, client)
            with get_session() as session:
                result = store_resolution(tenant_id, report, session)
            created += result.created
            updated += result.updated
            deactivated += result.deactivated
            logger.info(
                "resolution stored",
                extra={
                    "domain": domain,
                    "rows_created": result.created,
                    "rows_updated": result.updated,
                },
            )
    return StoreResult(created=created, updated=updated, deactivated=deactivated)


def _load_active_sources(
    tenant_id: int, session: Session
) -> list[tuple[int, int, str, str | None]]:
    """Return (source_id, account_id, url, last_hash) for every active source of the tenant."""
    rows = session.execute(
        select(
            AccountSource.id,
            AccountSource.account_id,
            AccountSource.url,
            AccountSource.last_hash,
        ).where(
            AccountSource.tenant_id == tenant_id,
            AccountSource.active.is_(True),
        )
    ).all()
    return [(r.id, r.account_id, r.url, r.last_hash) for r in rows]


async def run_watch_pass(
    tenant_id: int,
    concurrency: int = 100,
    on_confirmed_change: Callable[[int, str], None] | None = None,
) -> int:
    """Run one watch pass for a tenant. Returns the scan_runs id.

    Raises whatever exception the pass hit, after marking the scan_runs row
    status="failed" with the error recorded — a dead run must be visible,
    not silently stuck at "running".

    `on_confirmed_change`, if provided, is invoked once per source with
    `(source_id, body)` for every CONFIRMED content change (ADR-0008
    Decision 2 amendment) — never for a phase-2-only mismatch that phase 3's
    confirm fetch rejects, and never for a first-ever baseline probe.
    `_cli_scan` is the real consumer (ADR-0014): it collects these bodies
    and hands them to `scripts.verify.wiring.run_verify_stage` after this
    pass returns.
    """
    # --- Phase 1: sync DB read ---
    with get_session() as session:
        run = ScanRun(tenant_id=tenant_id, status="running")
        session.add(run)
        session.commit()
        run_id = run.id
        sources = _load_active_sources(tenant_id, session)

    try:
        # --- Phase 2: async fetch ---
        refs = [SourceRef(source_id=sid, url=url) for sid, _, url, _ in sources]
        last_hash_by_id = {sid: h for sid, _, _, h in sources}
        url_by_id = {sid: url for sid, _, url, _ in sources}
        account_id_by_source_id = {sid: account_id for sid, account_id, _, _ in sources}

        async with guarded_client() as client:
            first_results = await fetch_all(refs, client=client, concurrency=concurrency)

            # --- Phase 3: async confirm ---
            # Re-fetch only sources whose hash differs from a known last_hash.
            # A first-ever probe (last_hash is None) has nothing to confirm
            # against — it is a baseline, not a change.
            changed_refs = [
                SourceRef(source_id=r.source_id, url=url_by_id[r.source_id])
                for r in first_results
                if r.content_hash is not None
                and last_hash_by_id.get(r.source_id) is not None
                and r.content_hash != last_hash_by_id[r.source_id]
            ]
            confirm_results: dict[int, ProbeResult] = {}
            if changed_refs:
                confirmed = await fetch_all(
                    changed_refs, client=client, concurrency=concurrency, retain_bodies=True
                )
                confirm_results = {r.source_id: r for r in confirmed}

        # --- Phase 4: sync DB write ---
        run_id = _write_results(
            tenant_id=tenant_id,
            run_id=run_id,
            first_results=first_results,
            confirm_results=confirm_results,
            last_hash_by_id=last_hash_by_id,
            account_id_by_source_id=account_id_by_source_id,
            on_confirmed_change=on_confirmed_change,
        )
        return run_id
    except Exception as exc:  # noqa: BLE001
        with get_session() as session:
            failed = session.get(ScanRun, run_id)
            if failed is not None:
                failed.status = "failed"
                failed.finished_at = _utcnow()
                failed.error = str(exc)
            session.commit()
        raise


_ROBOTS_BLOCKED_ERROR = "blocked_by_robots"


def _write_results(
    *,
    tenant_id: int,
    run_id: int,
    first_results: list[ProbeResult],
    confirm_results: dict[int, ProbeResult],
    last_hash_by_id: dict[int, str | None],
    account_id_by_source_id: dict[int, int],
    on_confirmed_change: Callable[[int, str], None] | None = None,
) -> int:
    """Phase 4: write probes and update source/run state. Batched 500/commit."""
    changes_detected = 0
    confirm_rejected = 0
    deactivated_count = 0
    robots_blocked_count = 0
    latencies: list[int] = []
    accounts_probed: set[int] = set()
    now = _utcnow()

    with get_session() as session:
        pending = 0
        for result in first_results:
            source = session.get(AccountSource, result.source_id)
            if source is None:
                continue

            latencies.append(result.latency_ms)
            account_id = account_id_by_source_id.get(result.source_id)
            if account_id is not None:
                accounts_probed.add(account_id)

            prior_hash = last_hash_by_id.get(result.source_id)
            changed = False
            new_last_hash: str | None = None
            probe_error = result.error

            if result.robots_blocked:
                # Not a failure — we are simply not permitted to fetch it
                # right now. robots.txt is re-checked every run (ADR-0005
                # Decision 4), so this can reverse on its own. Do NOT touch
                # consecutive_failures or active; do make it visible so it
                # is queryable and distinguishable from a benign no-op.
                robots_blocked_count += 1
                probe_error = _ROBOTS_BLOCKED_ERROR
            elif result.error is not None:
                source.consecutive_failures += 1
                if source.consecutive_failures >= _DEACTIVATE_AFTER_FAILURES:
                    source.active = False
                    deactivated_count += 1
                    logger.error(
                        "source deactivated after repeated failures",
                        extra={
                            "source_id": source.id,
                            "consecutive_failures": source.consecutive_failures,
                        },
                    )
            elif result.content_hash is not None:
                source.consecutive_failures = 0
                if prior_hash is None:
                    # First-ever probe: baseline, not a change. No confirmation needed.
                    new_last_hash = result.content_hash
                elif result.content_hash == prior_hash:
                    changed = False
                else:
                    confirm = confirm_results.get(result.source_id)
                    if confirm is not None and confirm.content_hash == result.content_hash:
                        changed = True
                        new_last_hash = result.content_hash
                        changes_detected += 1
                        source.last_changed_at = now
                        if on_confirmed_change is not None and confirm.body is not None:
                            on_confirmed_change(result.source_id, confirm.body)
                        elif confirm.body is None:
                            logger.debug(
                                "confirmed change had no retained body",
                                extra={"source_id": result.source_id},
                            )
                    else:
                        # Unconfirmed change: record changed=False, leave
                        # last_hash untouched so the next run re-evaluates
                        # from the same baseline (ADR-0005 Decision 2).
                        confirm_rejected += 1

            source.last_fetched_at = now
            if new_last_hash is not None:
                source.last_hash = new_last_hash

            probe = Probe(
                tenant_id=tenant_id,
                account_source_id=result.source_id,
                scan_run_id=run_id,
                fetched_at=now,
                content_hash=result.content_hash,
                changed=changed,
                status_code=result.status_code,
                latency_ms=result.latency_ms,
                bytes=result.bytes,
                error=probe_error,
            )
            session.add(probe)
            pending += 1

            if pending >= _WRITE_BATCH_SIZE:
                session.commit()
                pending = 0

        if pending:
            session.commit()

        run = session.get(ScanRun, run_id)
        run.finished_at = now
        run.status = "completed"
        run.accounts_probed = len(accounts_probed)
        run.sources_probed = len(first_results)
        run.changes_detected = changes_detected
        run.confirm_rejected = confirm_rejected
        run.robots_blocked = robots_blocked_count
        run.p50_latency_ms = _percentile(latencies, 0.50)
        run.p95_latency_ms = _percentile(latencies, 0.95)
        session.commit()

    return run_id


# --- CLI ---


def _scan_tenant(tenant_slug: str) -> int:
    with get_session() as session:
        tenant_id = ensure_tenant(tenant_slug, tenant_slug, session)

    retained_bodies: dict[int, str] = {}
    try:
        run_id = asyncio.run(
            run_watch_pass(tenant_id, on_confirmed_change=retained_bodies.__setitem__)
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("watch pass failed", extra={"error": str(exc)})
        return 1

    with get_session() as session:
        run = session.get(ScanRun, run_id)
        payload = {
            "id": run.id,
            "tenant_id": run.tenant_id,
            "status": run.status,
            "accounts_probed": run.accounts_probed,
            "sources_probed": run.sources_probed,
            "changes_detected": run.changes_detected,
            "confirm_rejected": run.confirm_rejected,
            "robots_blocked": run.robots_blocked,
            "p50_latency_ms": run.p50_latency_ms,
            "p95_latency_ms": run.p95_latency_ms,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "error": run.error,
        }
    print(json.dumps(payload, indent=2))
    watch_ok = payload["status"] == "completed"

    # Verify layer (ADR-0014): extraction + diff + signal_events for
    # confirmed careers-page changes, bounded by a daily budget. Each
    # source is independently isolated inside run_verify_stage itself;
    # this try/except is the outer safety net for anything structural
    # (e.g. a DB error) escaping that -- must not affect the watch pass's
    # own already-recorded status above.
    verify_ok = True
    with get_session() as session:
        try:
            verify_report = run_verify_stage(tenant_id, session, run_id, retained_bodies, _utcnow())
            print(json.dumps(verify_report.model_dump(), indent=2))
        except Exception as exc:  # noqa: BLE001
            logger.error("verify stage failed", extra={"error": str(exc)})
            verify_ok = False

    # Scoring (ADR-0016): scores every account from a trailing window of
    # signal_events -- including whatever the verify stage above just
    # emitted. Runs after verify for that reason. One more independently
    # wrapped stage, same posture as verify and Phase 3 postprocess below.
    scoring_ok = True
    with get_session() as session:
        try:
            scoring_report = run_scoring_stage(tenant_id, session, _utcnow())
            print(json.dumps(scoring_report.model_dump(), indent=2))
        except Exception as exc:  # noqa: BLE001
            logger.error("scoring stage failed", extra={"error": str(exc)})
            scoring_ok = False

    # Phase 3 wiring (ADR-0013): health rollup + anomaly check, recall
    # report, retention pruning. Independently wrapped inside
    # run_daily_postprocess -- a failure here must not retroactively affect
    # the watch pass's own already-finalized scan_runs status above, but
    # must still be visible in the exit code.
    with get_session() as session:
        postprocess_report = run_daily_postprocess(tenant_id, session, now=_utcnow())
    print(
        json.dumps(
            {
                "health_ok": postprocess_report.health_ok,
                "recall_ok": postprocess_report.recall_ok,
                "retention_ok": postprocess_report.retention_ok,
            },
            indent=2,
        )
    )

    return 0 if (watch_ok and verify_ok and scoring_ok and postprocess_report.all_ok) else 1


def _tenant_slugs_to_scan(session: Session) -> list[str]:
    """SCAN_TENANTS=all scans every tenant with an active source; else TENANT_SLUG; else nothing."""
    if os.environ.get("SCAN_TENANTS") == "all":
        rows = session.execute(
            select(Tenant.slug)
            .join(AccountSource, AccountSource.tenant_id == Tenant.id)
            .where(AccountSource.active.is_(True))
            .distinct()
            .order_by(Tenant.slug)
        )
        return list(rows.scalars())
    slug = os.environ.get("TENANT_SLUG")
    return [slug] if slug else []


def _scan_tenant_safely(tenant_slug: str) -> int:
    try:
        return _scan_tenant(tenant_slug)
    except Exception as exc:  # noqa: BLE001 -- one tenant must never stop the rest
        logger.error("tenant scan crashed", extra={"tenant": tenant_slug, "error": str(exc)})
        return 1


def _cli_scan() -> int:
    with get_session() as session:
        slugs = _tenant_slugs_to_scan(session)
    if not slugs:
        logger.error("nothing to scan: set TENANT_SLUG or SCAN_TENANTS=all")
        return 1
    codes = [_scan_tenant_safely(slug) for slug in slugs]
    return 0 if all(code == 0 for code in codes) else 1


def _cli_resolve(domains: list[str]) -> int:
    tenant_slug = os.environ.get("TENANT_SLUG")
    if not tenant_slug:
        logger.error("TENANT_SLUG is not set")
        return 1

    with get_session() as session:
        tenant_id = ensure_tenant(tenant_slug, tenant_slug, session)

    try:
        result = asyncio.run(resolve_and_store(tenant_id, domains))
    except Exception as exc:  # noqa: BLE001
        logger.error("resolution failed", extra={"error": str(exc)})
        return 1

    print(
        json.dumps(
            {
                "domains": domains,
                "created": result.created,
                "updated": result.updated,
                "deactivated": result.deactivated,
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="python -m scripts.watch.runner")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan")
    resolve_parser = sub.add_parser("resolve")
    resolve_parser.add_argument("--domains", required=True, help="comma-separated domain list")

    args = parser.parse_args(argv)

    if args.command == "scan":
        return _cli_scan()
    if args.command == "resolve":
        domains = [d.strip() for d in args.domains.split(",") if d.strip()]
        return _cli_resolve(domains)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
