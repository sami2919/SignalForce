"""Test factories for hospitality models."""

from datetime import date

from scripts.hospitality.models import LicenseRecord


def make_license(record_id: str = "sla:1", **overrides: object) -> LicenseRecord:
    base: dict[str, object] = {
        "source": "sla_pending",
        "record_id": record_id,
        "legal_name": "ACME HOSPITALITY LLC",
        "dba": "Acme",
        "address": "1 Main St",
        "city": "New York",
        "zip_code": "10001",
        "county": "New York",
        "license_class": "OP",
        "description": "Restaurant",
        "received_date": date(2026, 1, 1),
        "original_issue_date": None,
        "lat": 40.7,
        "lon": -74.0,
    }
    base.update(overrides)
    return LicenseRecord(**base)  # type: ignore[arg-type]


def make_inspection(camis: str = "1", first: date | None = None, **overrides: object):
    from scripts.hospitality.models import InspectionVenue

    base: dict[str, object] = {
        "camis": camis,
        "dba": "Acme",
        "boro": "Manhattan",
        "address": "1 MAIN ST",
        "zip_code": "10001",
        "cuisine": "American",
        "phone": "",
        "lat": 40.7,
        "lon": -74.0,
        "first_inspection_date": first,
        "first_inspection_type": None,
    }
    base.update(overrides)
    return InspectionVenue(**base)  # type: ignore[arg-type]
