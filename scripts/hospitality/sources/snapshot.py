"""Daily snapshots of SLA pending applications.

Each pending application is recorded on the day we first see it, as an append-only row keyed
`(taken_on, record_id)`. This is the only way to measure true application -> opening lead time.

Schedule daily (Fly worker or cron) after the demo.
"""

from collections.abc import Sequence
from datetime import date

from scripts.hospitality.models import LicenseRecord, PendingSnapshot
from scripts.hospitality.store import DocStore

KIND = "pending_snapshots"


def take_snapshot(store: DocStore, pending: Sequence[LicenseRecord], taken_on: date) -> int:
    """Record each pending application for `taken_on`; returns rows written (idempotent per day)."""
    snaps = [PendingSnapshot(taken_on=taken_on, record_id=r.record_id) for r in pending]
    return store.save(
        KIND,
        snaps,
        key=lambda s: f"{s.taken_on}:{s.record_id}",  # type: ignore[attr-defined]
    )


def first_seen_pending(store: DocStore) -> dict[str, date]:
    """Map record_id to the earliest date it appeared in a snapshot."""
    first: dict[str, date] = {}
    for snap in store.load(KIND, PendingSnapshot):
        if snap.record_id not in first or snap.taken_on < first[snap.record_id]:
            first[snap.record_id] = snap.taken_on
    return first
