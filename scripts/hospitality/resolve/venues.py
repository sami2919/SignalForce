"""Build canonical Venue records from license/inspection matches."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from scripts.hospitality.models import InspectionVenue, LicenseRecord, MatchResult, Venue


def _license_date(lic: LicenseRecord) -> date:
    return lic.original_issue_date or lic.received_date or date.min


def _latest(licenses: Sequence[LicenseRecord]) -> LicenseRecord | None:
    """Most recent license; ties broken by record_id so the choice is deterministic."""
    if not licenses:
        return None
    return max(licenses, key=lambda lic: (_license_date(lic), lic.record_id))


def build_venues(
    licenses: Sequence[LicenseRecord],
    inspections: Sequence[InspectionVenue],
    match: MatchResult,
) -> list[Venue]:
    """One Venue per DOHMH site plus one per license that matched no site.

    Only auto pairs merge records; `possibly_same` links never do.
    """
    by_id = {lic.record_id: lic for lic in licenses}
    known_camis = {ins.camis for ins in inspections}
    by_camis: dict[str, list[LicenseRecord]] = defaultdict(list)
    assigned: set[str] = set()
    for pair in match.pairs:
        lic = by_id.get(pair.license_id)
        if lic is None or pair.camis not in known_camis or pair.license_id in assigned:
            continue
        by_camis[pair.camis].append(lic)
        assigned.add(pair.license_id)

    venues: list[Venue] = []
    for ins in inspections:
        lics = sorted(by_camis.get(ins.camis, []), key=lambda lic: lic.record_id)
        latest = _latest(lics)
        venue_id = f"v:{ins.camis}"
        venues.append(
            Venue(
                venue_id=venue_id,
                name=ins.dba,
                address=ins.address,
                zip_code=ins.zip_code,
                lat=ins.lat,
                lon=ins.lon,
                camis=ins.camis,
                license_ids=tuple(lic.record_id for lic in lics),
                license_class=latest.license_class if latest else None,
                license_description=latest.description if latest else None,
                first_inspection_date=ins.first_inspection_date,
                website=None,
                group_id=f"g:{venue_id}",
            )
        )
    for lic in licenses:
        if lic.record_id in assigned:
            continue
        venue_id = f"v:lic:{lic.record_id}"
        venues.append(
            Venue(
                venue_id=venue_id,
                name=lic.dba or lic.legal_name,
                address=lic.address,
                zip_code=lic.zip_code,
                lat=lic.lat,
                lon=lic.lon,
                camis=None,
                license_ids=(lic.record_id,),
                license_class=lic.license_class,
                license_description=lic.description,
                first_inspection_date=None,
                website=None,
                group_id=f"g:{venue_id}",
            )
        )
    return venues
