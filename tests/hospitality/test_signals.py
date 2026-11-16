from datetime import UTC, date, datetime

from scripts.hospitality.signals import license_signals
from tests.hospitality.factories import make_license, make_venue

TODAY = date(2026, 11, 16)


def _types(signals) -> list[str]:
    return sorted(s.signal_type for s in signals)


def test_pending_uses_first_seen_snapshot_date_over_received() -> None:
    lic = make_license("p1", received_date=date(2026, 10, 1))
    venue = make_venue("v:1", license_ids=("p1",))
    sigs = license_signals([venue], [lic], {"p1": date(2026, 10, 20)}, TODAY)
    [sig] = [s for s in sigs if s.signal_type == "license_pending"]
    assert sig.signal_type == "license_pending"
    assert sig.entity_id == "v:1"
    assert sig.observed_at == datetime(2026, 10, 20, tzinfo=UTC)


def test_pending_falls_back_to_received_date() -> None:
    lic = make_license("p1", received_date=date(2026, 10, 1))
    venue = make_venue("v:1", license_ids=("p1",))
    sigs = license_signals([venue], [lic], {}, TODAY)
    [sig] = [s for s in sigs if s.signal_type == "license_pending"]
    assert sig.observed_at == datetime(2026, 10, 1, tzinfo=UTC)


def test_pending_for_already_inspected_venue_is_skipped() -> None:
    lic = make_license("p1")
    venue = make_venue("v:1", license_ids=("p1",), first_inspection_date=date(2025, 1, 1))
    assert license_signals([venue], [lic], {}, TODAY) == []


def test_issued_recent_and_uninspected_fires_issued_and_not_yet_inspected() -> None:
    lic = make_license(
        "a1", source="sla_active", received_date=None, original_issue_date=date(2026, 9, 1)
    )
    venue = make_venue("v:1", license_ids=("a1",), camis="9")
    sigs = license_signals([venue], [lic], {}, TODAY)
    assert _types(sigs) == ["license_issued", "not_yet_inspected"]
    assert {s.observed_at for s in sigs} == {datetime(2026, 9, 1, tzinfo=UTC)}


def test_issued_fires_when_first_inspection_is_after_issue_date() -> None:
    lic = make_license(
        "a1", source="sla_active", received_date=None, original_issue_date=date(2026, 9, 1)
    )
    venue = make_venue("v:1", license_ids=("a1",), first_inspection_date=date(2026, 10, 1))
    assert _types(license_signals([venue], [lic], {}, TODAY)) == ["license_issued"]


def test_issued_skipped_when_inspected_before_issue_or_older_than_a_year() -> None:
    renewal = make_license(
        "a1", source="sla_active", received_date=None, original_issue_date=date(2026, 9, 1)
    )
    old = make_license(
        "a2", source="sla_active", received_date=None, original_issue_date=date(2025, 10, 1)
    )
    v1 = make_venue("v:1", license_ids=("a1",), first_inspection_date=date(2025, 1, 1))
    v2 = make_venue("v:2", license_ids=("a2",), camis="2")
    sigs = license_signals([v1, v2], [renewal, old], {}, TODAY)
    assert [s for s in sigs if s.signal_type == "license_issued"] == []


def test_match_miss_licenses_fire_no_opening_signals() -> None:
    # linked to an inspected venue, or unmatched (no camis) and older than the censor cap
    linked = make_license(
        "a1", source="sla_active", received_date=None, original_issue_date=date(2026, 10, 1)
    )
    stale = make_license(
        "a2", source="sla_active", received_date=None, original_issue_date=date(2026, 6, 1)
    )
    awaiting = make_license(
        "a3", source="sla_active", received_date=None, original_issue_date=date(2026, 6, 1)
    )
    v1 = make_venue("v:1", license_ids=("a1",))
    v2 = make_venue("v:2", license_ids=("a2",))
    v3 = make_venue("v:3", license_ids=("a3",), camis="3")  # DOHMH record awaiting inspection
    sigs = license_signals(
        [v1, v2, v3],
        [linked, stale, awaiting],
        {},
        TODAY,
        linked=frozenset({"a1"}),
        max_unmatched_age_days=90,
    )
    assert {s.entity_id for s in sigs} == {"v:3"}
    assert _types(sigs) == ["license_issued", "not_yet_inspected"]


def test_not_yet_inspected_for_pending_only_venue() -> None:
    lic = make_license("p1", received_date=date(2026, 10, 1))
    venue = make_venue("v:1", license_ids=("p1",))
    assert _types(license_signals([venue], [lic], {}, TODAY)) == [
        "license_pending",
        "not_yet_inspected",
    ]


def _inactive(record_id: str, issued: date):
    return make_license(
        record_id, source="sla_inactive", received_date=None, original_issue_date=issued
    )


def test_historical_inactive_license_emits_license_issued_at_its_issue_date() -> None:
    lic = _inactive("i1", date(2026, 9, 1))
    venue = make_venue("v:1", license_ids=("i1",), camis="9")
    sigs = license_signals([venue], [lic], {}, TODAY, historical=True)
    assert _types(sigs) == ["license_issued"]  # lapsed licence is not "awaiting inspection"
    [sig] = sigs
    assert sig.observed_at == datetime(2026, 9, 1, tzinfo=UTC)
    assert sig.source == "sla_inactive"
    assert sig.evidence_ref == "i1"


def test_historical_inactive_keeps_the_active_exclusions() -> None:
    transfer = _inactive("i1", date(2026, 9, 1))  # first inspection precedes issue
    old = _inactive("i2", date(2025, 10, 1))  # older than the 365-day lookback
    future = _inactive("i3", date(2026, 12, 1))  # not yet issued as of the as-of date
    v1 = make_venue("v:1", license_ids=("i1",), first_inspection_date=date(2025, 1, 1))
    v2 = make_venue("v:2", license_ids=("i2",), camis="2")
    v3 = make_venue("v:3", license_ids=("i3",), camis="3")
    sigs = license_signals([v1, v2, v3], [transfer, old, future], {}, TODAY, historical=True)
    assert sigs == []


def test_historical_inactive_obeys_match_miss_rule() -> None:
    linked = _inactive("i1", date(2026, 10, 1))
    v1 = make_venue("v:1", license_ids=("i1",))
    assert (
        license_signals([v1], [linked], {}, TODAY, linked=frozenset({"i1"}), historical=True) == []
    )


def test_live_inactive_license_emits_no_opening_signal() -> None:
    lic = _inactive("i1", date(2026, 9, 1))
    venue = make_venue("v:1", license_ids=("i1",), camis="9")
    assert license_signals([venue], [lic], {}, TODAY) == []
    assert license_signals([venue], [lic], {}, TODAY, historical=False) == []


def test_live_venue_with_active_and_inactive_licenses_signals_only_the_active() -> None:
    active = make_license(
        "a1", source="sla_active", received_date=None, original_issue_date=date(2026, 9, 1)
    )
    lapsed = _inactive("i1", date(2026, 9, 5))
    venue = make_venue("v:1", license_ids=("a1", "i1"), camis="9")
    sigs = license_signals([venue], [active, lapsed], {}, TODAY)
    assert {s.evidence_ref for s in sigs} == {"a1"}
