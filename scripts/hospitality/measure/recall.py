"""Recall audit: of license-matched openings, how many did opening signals catch beforehand.

The truth set is only the openings we could tie to an on-premise license, so `recall` measures
the timeliness of license signals on those, not the share of NYC openings found. The coverage
denominator (every first inspection in the window) is reported next to it.
"""

from collections import defaultdict
from collections.abc import Collection, Sequence
from datetime import date
from statistics import median

from scripts.hospitality.config import HospitalityConfig
from scripts.hospitality.models import LicenseRecord, RecallReport, Signal, Venue

# Signal types whose prior family is "opening" in the shipped config.
OPENING_SIGNAL_TYPES: tuple[str, ...] = (
    "license_pending",
    "license_issued",
    "not_yet_inspected",
    "press_opening",
)


def _is_new_opening(venue: Venue, by_id: dict[str, LicenseRecord]) -> bool:
    """False when every issued license postdates the first inspection (transfer/renewal)."""
    first = venue.first_inspection_date
    issued = [
        lic.original_issue_date
        for lid in venue.license_ids
        if (lic := by_id.get(lid)) is not None
        and lic.source in ("sla_active", "sla_inactive")
        and lic.original_issue_date is not None
    ]
    return not issued or any(d <= first for d in issued)  # type: ignore[operator]


def ground_truth_openings(
    venues: Sequence[Venue],
    start: date,
    end: date,
    cfg: HospitalityConfig,
    licenses: Sequence[LicenseRecord] | None = None,
) -> list[Venue]:
    """Venues first inspected in [start, end] with an on-premise license description.

    With `licenses`, venues whose issued licenses all postdate the first inspection are
    dropped: that is a transfer or renewal of an operating site, not a new opening.
    """
    by_id = {lic.record_id: lic for lic in licenses or ()}
    return [
        v
        for v in venues
        if v.first_inspection_date is not None
        and start <= v.first_inspection_date <= end
        and v.license_description in cfg.on_premise_descriptions
        and (licenses is None or _is_new_opening(v, by_id))
    ]


def first_inspections_in(venues: Sequence[Venue], start: date, end: date) -> list[Venue]:
    """Every venue first inspected in [start, end], license-matched or not."""
    return [
        v
        for v in venues
        if v.first_inspection_date is not None and start <= v.first_inspection_date <= end
    ]


def recall_audit(
    openings: Sequence[Venue],
    signals: Sequence[Signal],
    start: date,
    end: date,
    *,
    first_inspections: int,
    license_matched: int,
    lead_cap_days: int,
    opening_types: Collection[str] = OPENING_SIGNAL_TYPES,
) -> RecallReport:
    """Caught = an opening-family signal observed strictly before the first inspection.

    `first_inspections` and `license_matched` are the wider denominators (required, so a
    caller cannot report recall without them). Leads longer than `lead_cap_days` stay caught
    but are excluded from `median_lead_days_within_cap` and counted in `leads_over_cap`: a
    signal more than a cap's length before opening is not a buying-window lead.
    """
    by_venue: dict[str, list[date]] = defaultdict(list)
    for s in signals:
        if s.signal_type in opening_types:
            by_venue[s.entity_id].append(s.observed_at.date())
    leads: list[int] = []
    misses: list[str] = []
    for v in openings:
        first = v.first_inspection_date
        prior = [d for d in by_venue.get(v.venue_id, ()) if first is not None and d < first]
        if prior:
            leads.append((first - min(prior)).days)  # type: ignore[operator]
        else:
            misses.append(v.venue_id)
    total = len(openings)
    fresh = [d for d in leads if d <= lead_cap_days]
    return RecallReport(
        start=start,
        end=end,
        total=total,
        caught=len(leads),
        recall=len(leads) / total if total else 0.0,
        first_inspections=first_inspections,
        license_matched=license_matched,
        coverage=len(leads) / first_inspections if first_inspections else 0.0,
        median_lead_days=float(median(leads)) if leads else None,
        lead_cap_days=lead_cap_days,
        median_lead_days_within_cap=float(median(fresh)) if fresh else None,
        leads_over_cap=len(leads) - len(fresh),
        lead_days=tuple(leads),
        misses=tuple(misses),
    )
