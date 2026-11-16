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
