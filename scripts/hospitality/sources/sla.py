"""NY State Liquor Authority license ingest (pending, active, inactive datasets)."""

import logging
import re
from datetime import date
from typing import Any

from scripts.hospitality.config import HospitalityConfig
from scripts.hospitality.models import LicenseRecord, LicenseSource
from scripts.hospitality.sources.socrata import SocrataClient

logger = logging.getLogger(__name__)

# Field-name variants per logical field. Pending uses snake_case with its own names, active
# squashes words together, inactive is snake_case. The first key present wins.
_ALIASES: dict[str, tuple[str, ...]] = {
    "id": ("application_id", "license_permit_id", "licensepermitid"),
    "county": ("premises_county", "premisescounty"),
    "address": ("actual_address_of_premises", "actualaddressofpremises"),
    "zip": ("zip_code", "zipcode"),
    "received": ("received_date",),
    "issued": ("original_issue_date", "originalissuedate"),
}
_COUNTY_FIELD: dict[str, str] = {
    "sla_pending": "premises_county",
    "sla_active": "premisescounty",
    "sla_inactive": "premises_county",
}


def _first(row: dict[str, Any], logical: str) -> Any:
    for key in _ALIASES[logical]:
        if row.get(key) not in (None, ""):
            return row[key]
    return None


def _date(value: Any) -> date | None:
    return date.fromisoformat(str(value)[:10]) if value else None


_NUMBER_YEAR = re.compile(r"^\d{4}-(\d{2})-\d+$")


def is_renewal(lic: LicenseRecord) -> bool:
    """True for an issued licence that is a renewal, not a new licence.

    The SLA resets `originalissuedate` every time a licence renews, but the licence number
    (0340-22-109336) keeps the two-digit year it was first applied for. A licence "issued"
    more than a year after that year is an existing venue renewing, not a venue opening.
    Unparseable numbers and pending applications (NA-...) are never called renewals.
    """
    if lic.source == "sla_pending" or lic.original_issue_date is None:
        return False
    match = _NUMBER_YEAR.match(lic.record_id.split(":", 1)[-1])
    if match is None:
        return False
    return lic.original_issue_date.year - (2000 + int(match.group(1))) > 1


def parse_license_row(row: dict[str, Any], source: LicenseSource) -> LicenseRecord | None:
    """Parse one Socrata row; return None (and log) for rows that do not look like licenses."""
    try:
        raw_id = _first(row, "id")
        legal_name = row.get("legalname")
        if raw_id is None or not legal_name:
            raise ValueError("missing id or legalname")
        coords = (row.get("georeference") or {}).get("coordinates")
        lon, lat = (float(coords[0]), float(coords[1])) if coords else (None, None)
        return LicenseRecord(
            source=source,
            record_id=f"{source}:{raw_id}",
            legal_name=str(legal_name),
            dba=str(row.get("dba") or ""),
            address=str(_first(row, "address") or ""),
            city=str(row.get("city") or ""),
            zip_code=str(_first(row, "zip") or ""),
            county=str(_first(row, "county") or ""),
            license_class=str(row.get("class") or ""),
            description=str(row.get("description") or ""),
            received_date=_date(_first(row, "received")),
            original_issue_date=_date(_first(row, "issued")),
            lat=lat,
            lon=lon,
        )
    except (ValueError, TypeError, IndexError) as exc:
        logger.warning("unparseable SLA row (%s): %r", exc, row)
        return None


def _quote(values: tuple[str, ...]) -> str:
    return ",".join("'" + v.replace("'", "''") + "'" for v in values)


def fetch_licenses(
    client: SocrataClient, cfg: HospitalityConfig, source: LicenseSource
) -> list[LicenseRecord]:
    """Fetch NYC on-premise licenses for one source, filtered server-side."""
    county_field = _COUNTY_FIELD[source]
    where = (
        f"{county_field} in({_quote(cfg.nyc_counties)})"
        f" AND description in({_quote(cfg.on_premise_descriptions)})"
    )
    records = (
        parse_license_row(row, source) for row in client.rows(cfg.datasets[source], where=where)
    )
    return [r for r in records if r is not None]
