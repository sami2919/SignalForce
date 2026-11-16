"""NYC DOHMH restaurant inspections: first-inspection date per venue (stands in for "opened")."""

import logging
from collections.abc import Sequence
from datetime import date
from typing import Any

from scripts.hospitality.models import InspectionVenue
from scripts.hospitality.sources.socrata import SocrataClient

logger = logging.getLogger(__name__)

DATASET_ID = "43nn-pn8j"
SENTINEL_CUTOFF = "1900-01-02"  # 1900-01-01 means "not yet inspected"
_GROUP = "camis,dba,boro,building,street,zipcode,cuisine_description,phone,latitude,longitude"


def _date(value: Any) -> date | None:
    if not value:
        return None
    parsed = date.fromisoformat(str(value)[:10])
    return None if parsed.isoformat() < SENTINEL_CUTOFF else parsed


def _coord(value: Any) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    return number or None  # DOHMH uses 0 for missing coordinates


def parse_inspection_row(row: dict[str, Any]) -> InspectionVenue | None:
    """Parse one aggregated row; return None (and log) if it is not a usable venue."""
    try:
        camis, dba = row.get("camis"), row.get("dba")
        if not camis or not dba:
            raise ValueError("missing camis or dba")
        address = f"{row.get('building') or ''} {row.get('street') or ''}".strip()
        return InspectionVenue(
            camis=str(camis),
            dba=str(dba),
            boro=str(row.get("boro") or ""),
            address=address,
            zip_code=str(row.get("zipcode") or ""),
            cuisine=str(row.get("cuisine_description") or ""),
            phone=str(row.get("phone") or ""),
            lat=_coord(row.get("latitude")),
            lon=_coord(row.get("longitude")),
            first_inspection_date=_date(row.get("first_date")),
            first_inspection_type=None,
        )
    except (ValueError, TypeError) as exc:
        logger.warning("unparseable DOHMH row (%s): %r", exc, row)
        return None


def _parse_all(rows: Any) -> list[InspectionVenue]:
    venues = (parse_inspection_row(r) for r in rows)
    return [v for v in venues if v is not None]


def _collapse_variants(rows: Any) -> list[dict[str, Any]]:
    """One row per camis: the earliest `first_date`, the newest variant's attributes (M9).

    The grouped query returns one row per (camis, dba, address, cuisine, phone, lat/lon)
    variant. A renamed or re-geocoded site therefore has several rows, and keeping any one
    variant's date can make an old site look like a new opening (Review Focus 2).
    """
    by_camis: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_camis.setdefault(str(row.get("camis") or ""), []).append(row)
    out: list[dict[str, Any]] = []
    for variants in by_camis.values():
        dated = [str(r["first_date"]) for r in variants if r.get("first_date")]
        newest = max(variants, key=lambda r: str(r.get("last_date") or ""))
        out.append({**newest, "first_date": min(dated) if dated else newest.get("first_date")})
    return out


def fetch_first_inspections(client: SocrataClient) -> list[InspectionVenue]:
    """One row per venue with its earliest real inspection date (sentinel excluded)."""
    select = f"{_GROUP},min(inspection_date) as first_date,max(inspection_date) as last_date"
    return _parse_all(
        _collapse_variants(
            client.rows(
                DATASET_ID,
                select=select,
                where=f"inspection_date > '{SENTINEL_CUTOFF}'",
                group=_GROUP,
            )
        )
    )


def fetch_never_inspected(client: SocrataClient) -> list[InspectionVenue]:
    """Venues whose only inspection date is the sentinel (first_inspection_date=None)."""
    return _parse_all(
        client.rows(
            DATASET_ID,
            select=f"{_GROUP},max(inspection_date) as last_date",
            group=_GROUP,
            having=f"max(inspection_date) < '{SENTINEL_CUTOFF}'",
        )
    )


def merge_inspection_venues(
    first: Sequence[InspectionVenue], never: Sequence[InspectionVenue]
) -> list[InspectionVenue]:
    """Unique by CAMIS; a dated record wins over a never-inspected one."""
    merged: dict[str, InspectionVenue] = {v.camis: v for v in never}
    merged.update({v.camis: v for v in first})
    return list(merged.values())
