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


def test_not_yet_inspected_older_than_the_age_cap_is_stale() -> None:
    """M11: a site licensed long ago and still uninspected is not an upcoming opening.

    The camis is set (a DOHMH record awaiting inspection), so the match-miss rule keeps it;
    without an age cap a 2024 license got full window weight forever.
    """
    old = make_license("p-old", received_date=date(2024, 6, 1))  # ~900 days
    recent = make_license("p-new", received_date=date(2025, 11, 1))  # ~380 days
    venues = [
        make_venue("v:old", camis="1", license_ids=("p-old",)),
        make_venue("v:new", camis="2", license_ids=("p-new",)),
    ]
    sigs = license_signals(venues, [old, recent], {}, TODAY, not_yet_inspected_max_age_days=730)
    nyi = {s.entity_id for s in sigs if s.signal_type == "not_yet_inspected"}
    assert nyi == {"v:new"}


def test_issued_lookback_is_a_parameter() -> None:
    lic = make_license(
        "a1", source="sla_active", received_date=None, original_issue_date=date(2026, 3, 1)
    )
    venue = make_venue("v:1", license_ids=("a1",), camis="1")
    assert "license_issued" in _types(license_signals([venue], [lic], {}, TODAY))
    short = license_signals([venue], [lic], {}, TODAY, issued_lookback_days=180)
    assert "license_issued" not in _types(short)


def test_live_score_applies_the_configured_caps(tmp_path, monkeypatch) -> None:
    from scripts.hospitality import cli
    from scripts.hospitality.config import load_config
    from scripts.hospitality.models import Group, Signal
    from scripts.hospitality.store import DocStore

    seed = tmp_path / "seed.yaml"
    seed.write_text("customers: []\ndismissed_embeds: []\n")
    monkeypatch.setattr(cli, "SEED_PATH", seed)
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    store.save(
        "licenses",
        [make_license("p-old", received_date=date(2024, 6, 1))],
        key=lambda r: r.record_id,  # type: ignore[attr-defined]
    )
    venue = make_venue("v:old", camis="1", license_ids=("p-old",))
    store.save("venues", [venue], key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    store.save(
        "groups",
        [Group(group_id=venue.group_id, name="Old", venue_ids=("v:old",), resolution="singleton")],
        key=lambda g: g.group_id,  # type: ignore[attr-defined]
    )
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    cfg = load_config()
    assert cfg.not_yet_inspected_max_age_days == 730 and cfg.issued_lookback_days == 365
    cli.score(datetime(2026, 11, 16, tzinfo=UTC))
    kinds = {s.signal_type for s in store.load("license_signals", Signal)}
    assert "not_yet_inspected" not in kinds
