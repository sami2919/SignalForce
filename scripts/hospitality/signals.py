"""Turn licenses and inspections into dated opening signals."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from scripts.hospitality.models import LicenseRecord, Signal, Venue
from scripts.hospitality.window.survival import likely_already_open

ISSUED_LOOKBACK_DAYS = 365


def _at(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def _signal(
    signal_type: str, venue: Venue, record_id: str, observed: date, source: str, detail: str
) -> Signal:
    return Signal(
        signal_id=f"{signal_type}:{venue.venue_id}:{record_id}",
        signal_type=signal_type,  # type: ignore[arg-type]
        entity_id=venue.venue_id,
        observed_at=_at(observed),
        occurred_at=None,
        source=source,
        evidence_ref=record_id,
        detail=detail,
    )


def license_signals(
    venues: Sequence[Venue],
    licenses: Sequence[LicenseRecord],
    first_seen_pending: dict[str, date],
    today: date,
    *,
    linked: frozenset[str] = frozenset(),
    max_unmatched_age_days: float | None = None,
) -> list[Signal]:
    """Opening signals per venue.

    `linked` and `max_unmatched_age_days` apply the same match-miss rule as the window
    estimates (`likely_already_open`): a license linked to an already-inspected venue, or an
    issued license with no DOHMH record older than the cap, is not a not-yet-open venue.
    """
    by_id = {lic.record_id: lic for lic in licenses}
    cutoff = today - timedelta(days=ISSUED_LOOKBACK_DAYS)
    out: list[Signal] = []
    for venue in venues:
        lics = [lic for lid in venue.license_ids if (lic := by_id.get(lid)) is not None]
        inspected = venue.first_inspection_date
        dated: list[tuple[date, LicenseRecord]] = []
        for lic in lics:
            if lic.source == "sla_pending" and lic.received_date is not None:
                dated.append((lic.received_date, lic))
                if inspected is None and not likely_already_open(venue, 0, linked, None):
                    seen = first_seen_pending.get(lic.record_id)
                    out.append(
                        _signal(
                            "license_pending",
                            venue,
                            lic.record_id,
                            seen or lic.received_date,
                            "sla_pending",
                            f"pending since {seen or lic.received_date}",
                        )
                    )
            elif lic.source == "sla_active" and lic.original_issue_date is not None:
                issued = lic.original_issue_date
                dated.append((issued, lic))
                age = float((today - issued).days)
                if (
                    cutoff <= issued <= today
                    and (inspected is None or inspected > issued)
                    and not likely_already_open(venue, age, linked, max_unmatched_age_days)
                ):
                    out.append(
                        _signal(
                            "license_issued",
                            venue,
                            lic.record_id,
                            issued,
                            "sla_active",
                            f"issued {issued}",
                        )
                    )
        if inspected is None and dated:
            # Best license: issued preferred over pending, then latest (as the window estimate).
            actives = [(d, lic) for d, lic in dated if lic.source == "sla_active"]
            when, lic = max(actives or dated, key=lambda x: x[0])
            cap = max_unmatched_age_days if lic.source == "sla_active" else None
            if not likely_already_open(venue, float((today - when).days), linked, cap):
                out.append(
                    _signal(
                        "not_yet_inspected",
                        venue,
                        lic.record_id,
                        when,
                        lic.source,
                        f"licensed {when}, no inspection yet",
                    )
                )
    return out
