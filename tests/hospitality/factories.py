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


def make_embed_label(venue_id: str, name: str = "Embed Customer"):
    """A stored embed label: evidence that `venue_id`'s group already runs Loyalist."""
    from scripts.hospitality.models import CustomerLabel

    return CustomerLabel(
        name=name,
        website_domain=None,
        first_public_date=None,
        source="embed",
        evidence_ref="api.eatloyalist.com/signup",
        venue_id=venue_id,
    )


def make_venue(venue_id: str = "v:1", **overrides: object):
    from scripts.hospitality.models import Venue

    base: dict[str, object] = {
        "venue_id": venue_id,
        "name": "Acme",
        "address": "1 Main St",
        "zip_code": "10001",
        "lat": 40.7,
        "lon": -74.0,
        "camis": None,
        "license_ids": (),
        "license_class": None,
        "license_description": None,
        "first_inspection_date": None,
        "website": None,
        "group_id": f"g:{venue_id}",
    }
    base.update(overrides)
    return Venue(**base)  # type: ignore[arg-type]


def make_estimate(venue_id: str = "v:1", **overrides: object):
    from datetime import date as _date

    from scripts.hospitality.models import WindowEstimate

    base: dict[str, object] = {
        "venue_id": venue_id,
        "estimated_open": _date(2027, 2, 1),
        "p_open_90d": 0.4,
        "p_open_180d": 0.7,
        "basis": "test",
    }
    base.update(overrides)
    return WindowEstimate(**base)  # type: ignore[arg-type]


def make_signal(signal_type: str = "license_pending", entity_id: str = "v:1", **overrides: object):
    from datetime import UTC, datetime

    from scripts.hospitality.models import Signal

    observed = overrides.pop("observed", None)  # a date, as shorthand for observed_at
    base: dict[str, object] = {
        "signal_id": f"{signal_type}:{entity_id}",
        "signal_type": signal_type,
        "entity_id": entity_id,
        "observed_at": datetime(2026, 11, 16, tzinfo=UTC),
        "occurred_at": None,
        "source": "test",
        "evidence_ref": "ref",
        "detail": "",
    }
    if observed is not None:
        base["observed_at"] = datetime(observed.year, observed.month, observed.day, tzinfo=UTC)  # type: ignore[attr-defined]
    base.update(overrides)
    return Signal(**base)  # type: ignore[arg-type]


def make_scored(group_id: str = "g:1", priority: float = 0.5, **overrides: object):
    from scripts.hospitality.models import ScoredAccount

    base: dict[str, object] = {
        "group_id": group_id,
        "p_window": min(priority, 1.0),
        "fit": 0.5,
        "relationship": 1.0,
        "priority": priority,
        "contributions": (),
        "disqualified_reason": None,
        "is_customer": False,
    }
    base.update(overrides)
    return ScoredAccount(**base)  # type: ignore[arg-type]


def make_observation(venue_id: str = "v:1", platforms: tuple[str, ...] = (), **overrides: object):
    from datetime import UTC, datetime

    from scripts.hospitality.models import StackObservation

    base: dict[str, object] = {
        "venue_id": venue_id,
        "url": "https://example.com",
        "observed_at": datetime(2026, 11, 1, tzinfo=UTC),
        "platforms": platforms,
        "evidence": tuple("e" for _ in platforms),
        "fetched_via": "fetcher",
    }
    base.update(overrides)
    return StackObservation(**base)  # type: ignore[arg-type]
