"""The holdout deep scan: ground-truth data for measuring watch-layer recall.

Same shape as `scripts/watch/runner.py`'s `run_watch_pass` (sync DB read ->
async fetch -> sync DB write), with one deliberate difference (ADR-0010
Decision 1): **no confirm-on-change**. Every fetch's hash is compared
directly against the most recent prior `HoldoutScan` row for that source --
one fetch, one hash, no second confirming fetch. The watch layer's own
confirm-on-change exists to protect the expensive verify layer from cosmetic
churn; the deep scan is ground truth and must not inherit that filtering, or
it would just be measuring itself.

`run_deep_scan` selects a small, deterministic holdout of the tenant's
active accounts (`select_holdout`) and deep-scans every active
`AccountSource` belonging to them. It NEVER writes to
`AccountSource.last_hash` -- that field is the watch layer's own
confirm-on-change state (ADR-0005 Decision 2), and holdout accounts are not
excluded from the normal watch pass, so a write there would corrupt the
watch layer's own operational data. `HoldoutScan` is a dedicated table
(ADR-0010 Decision 2), not tied to a `ScanRun` -- the deep scan has no
concept of a watch-layer scan run.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.logging_config import configure_logging
from scripts.registry.store import ensure_tenant
from scripts.storage.models import AccountSource, HoldoutScan
from scripts.storage.session import get_session
from scripts.watch.fetcher import ProbeResult, SourceRef, fetch_all

logger = logging.getLogger(__name__)

_ROBOTS_BLOCKED_ERROR = "blocked_by_robots"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def select_holdout(account_ids: list[int], size: int, seed: int) -> list[int]:
    """Deterministically select up to `size` account ids for the holdout, by
    consistent hashing rather than `random.Random(seed).sample()`.

    Fixed on review, 2026-08-06: the plan's `random.sample()` version passed
    its own three tests (fixed population, same seed -> same result) but does
    NOT have the stability property ADR-0010 and the plan's own docstring
    require -- "the holdout must be stable across runs, or you are measuring
    a different population every month and the trend is meaningless."
    `random.sample`'s draws map to INDICES in the population array, so adding
    or removing *any* account anywhere -- even one never selected, even one
    completely unrelated to the holdout -- can reshuffle the entire
    selection. Measured: removing one unrelated account out of 20 changed 3
    of 5 holdout members (2/5 overlap) under the old implementation.

    Consistent hashing avoids this: each account's inclusion is decided by
    its own hash rank relative to the *current* population, independent of
    every other account's presence, order, or count. Measured under the same
    scenario: 5/5 overlap (fully stable) when an unrelated account is
    removed; overlap degrades gracefully, not catastrophically, as the
    population grows. It is not perfectly stable under arbitrary growth (a
    newly added account can rank into the top `size` and displace an
    existing member -- an unavoidable property of any *k best of N* rule),
    but only a genuine near-boundary case moves, not an unrelated one.
    """

    def _score(account_id: int) -> str:
        return hashlib.sha256(f"{seed}:{account_id}".encode()).hexdigest()

    ranked = sorted(account_ids, key=_score)
    return sorted(ranked[:size])


def load_active_account_ids(tenant_id: int, session: Session) -> list[int]:
    """Distinct account ids with at least one active AccountSource, for this tenant."""
    rows = session.execute(
        select(AccountSource.account_id)
        .where(
            AccountSource.tenant_id == tenant_id,
            AccountSource.active.is_(True),
        )
        .distinct()
    ).all()
    return sorted(r.account_id for r in rows)


def _load_sources_for_accounts(
    tenant_id: int, account_ids: list[int], session: Session
) -> list[tuple[int, int, str]]:
    """Return (source_id, account_id, url) for every active source belonging
    to the given accounts."""
    if not account_ids:
        return []
    rows = session.execute(
        select(AccountSource.id, AccountSource.account_id, AccountSource.url).where(
            AccountSource.tenant_id == tenant_id,
            AccountSource.account_id.in_(account_ids),
            AccountSource.active.is_(True),
        )
    ).all()
    return [(r.id, r.account_id, r.url) for r in rows]


def _most_recent_prior_scan(source_id: int, session: Session) -> HoldoutScan | None:
    """The most recent scan for this source that actually succeeded.

    Fixed on review, 2026-08-06: the original query ordered by fetched_at
    with no filter, so a failed fetch (content_hash=None) between two real
    content states reset the comparison baseline to nothing instead of
    falling back to the last known-good hash. Reproduced: scan N-1 succeeds
    with hash A, scan N fails, scan N+1 succeeds with hash B (a genuine
    change) -- the unfiltered query returned scan N's row, whose
    content_hash is None, so `changed` computed False for a real A->B
    change. That is the deep scan silently UNDER-counting the exact thing
    it exists to catch, and it is not rare: a transient fetch failure
    between two successful scans is routine over an indefinite hourly
    cadence, not an edge case.
    """
    return (
        session.execute(
            select(HoldoutScan)
            .where(
                HoldoutScan.account_source_id == source_id,
                HoldoutScan.content_hash.is_not(None),
            )
            .order_by(HoldoutScan.fetched_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


async def run_deep_scan(tenant_id: int, *, holdout_size: int = 5, seed: int = 42) -> int:
    """Deep-scan the tenant's holdout accounts once. Returns the number of
    sources scanned this run.

    No `ScanRun`-style row is created (ADR-0010 Decision 2 -- `HoldoutScan`
    has no `scan_run_id` and no run-tracking table of its own), so unlike
    `run_watch_pass` there is no run id to return; the source count is the
    closest useful "how big was this run" signal for the CLI and for
    callers checking a scan actually did something.
    """
    # --- Phase 1: sync DB read ---
    with get_session() as session:
        account_ids = load_active_account_ids(tenant_id, session)
        holdout_account_ids = select_holdout(account_ids, size=holdout_size, seed=seed)
        sources = _load_sources_for_accounts(tenant_id, holdout_account_ids, session)

    # --- Phase 2: async fetch (no confirm phase -- ADR-0010 Decision 1) ---
    refs = [SourceRef(source_id=sid, url=url) for sid, _, url in sources]
    results: list[ProbeResult] = []
    if refs:
        async with httpx.AsyncClient() as client:
            results = await fetch_all(refs, client=client)

    # --- Phase 3: sync DB write ---
    now = _utcnow()
    with get_session() as session:
        for result in results:
            prior = _most_recent_prior_scan(result.source_id, session)

            error = _ROBOTS_BLOCKED_ERROR if result.robots_blocked else result.error

            changed = False
            if (
                result.content_hash is not None
                and prior is not None
                and prior.content_hash is not None
            ):
                changed = result.content_hash != prior.content_hash

            session.add(
                HoldoutScan(
                    tenant_id=tenant_id,
                    account_source_id=result.source_id,
                    fetched_at=now,
                    content_hash=result.content_hash,
                    changed=changed,
                    status_code=result.status_code,
                    latency_ms=result.latency_ms,
                    bytes=result.bytes,
                    error=error,
                )
            )
        session.commit()

    return len(sources)


# --- CLI ---


def _cli_deep_scan(tenant_slug: str, holdout_size: int, seed: int) -> int:
    with get_session() as session:
        tenant_id = ensure_tenant(tenant_slug, tenant_slug, session)

    try:
        sources_scanned = asyncio.run(
            run_deep_scan(tenant_id, holdout_size=holdout_size, seed=seed)
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("deep scan failed", extra={"error": str(exc)})
        return 1

    print(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "holdout_size": holdout_size,
                "seed": seed,
                "sources_scanned": sources_scanned,
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="python -m scripts.measure.holdout")
    parser.add_argument(
        "--tenant-slug",
        default=os.environ.get("TENANT_SLUG"),
        required=os.environ.get("TENANT_SLUG") is None,
        help="tenant slug (defaults to TENANT_SLUG env var)",
    )
    parser.add_argument("--holdout-size", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args(argv)
    return _cli_deep_scan(args.tenant_slug, args.holdout_size, args.seed)


if __name__ == "__main__":
    sys.exit(main())
