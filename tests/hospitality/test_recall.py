import json
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from scripts.hospitality import cli
from scripts.hospitality.config import load_config
from scripts.hospitality.measure.recall import ground_truth_openings, recall_audit
from scripts.hospitality.models import RecallReport
from scripts.hospitality.store import DocStore
from tests.hospitality.factories import make_license, make_signal, make_venue

DEN = {"first_inspections": 10, "license_matched": 5, "lead_cap_days": 365}


@pytest.fixture
def cfg():
    return load_config()


def test_recall_counts_only_prior_signals(cfg):
    v1 = make_venue(
        "v:1", first_inspection_date=date(2026, 10, 1), license_description="Restaurant"
    )
    v2 = make_venue(
        "v:2", first_inspection_date=date(2026, 10, 5), license_description="Restaurant"
    )
    sigs = [
        make_signal("license_issued", "v:1", observed=date(2026, 7, 1)),
        make_signal("license_issued", "v:2", observed=date(2026, 10, 6)),  # after opening → miss
    ]
    r = recall_audit([v1, v2], sigs, date(2026, 9, 1), date(2026, 10, 31), **DEN)
    assert (r.total, r.caught, r.recall) == (2, 1, 0.5)
    assert r.lead_days == (92,) and r.misses == ("v:2",)


def test_ground_truth_excludes_grocery(cfg):
    g = make_venue(
        "v:3", first_inspection_date=date(2026, 10, 1), license_description="Grocery Store"
    )
    assert ground_truth_openings([g], date(2026, 9, 1), date(2026, 10, 31), cfg) == []


def test_ground_truth_window_bounds_inclusive_and_uninspected_excluded(cfg):
    def v(vid: str, d: date | None):
        return make_venue(vid, first_inspection_date=d, license_description="Restaurant")

    venues = [
        v("a", date(2026, 9, 1)),
        v("b", date(2026, 10, 31)),
        v("c", date(2026, 8, 31)),
        v("d", date(2026, 11, 1)),
        v("e", None),
    ]
    got = ground_truth_openings(venues, date(2026, 9, 1), date(2026, 10, 31), cfg)
    assert [x.venue_id for x in got] == ["a", "b"]


def test_license_issued_after_first_inspection_is_transfer_not_opening(cfg):
    """Review focus: a license issued after the site's first inspection is not a new opening."""
    inspected = date(2026, 10, 1)
    transfer = make_venue(
        "v:t",
        first_inspection_date=inspected,
        license_description="Restaurant",
        license_ids=("late",),
    )
    opening = make_venue(
        "v:o",
        first_inspection_date=inspected,
        license_description="Restaurant",
        license_ids=("early",),
    )
    lics = [
        make_license("late", source="sla_active", original_issue_date=date(2026, 10, 20)),
        make_license("early", source="sla_active", original_issue_date=date(2026, 7, 1)),
    ]
    got = ground_truth_openings(
        [transfer, opening], date(2026, 9, 1), date(2026, 10, 31), cfg, lics
    )
    assert [x.venue_id for x in got] == ["v:o"]


def test_non_opening_signals_do_not_count(cfg):
    v = make_venue("v:1", first_inspection_date=date(2026, 10, 1), license_description="Restaurant")
    sigs = [make_signal("stack_fragmented", "v:1", observed=date(2026, 7, 1))]
    r = recall_audit([v], sigs, date(2026, 9, 1), date(2026, 10, 31), **DEN)
    assert (r.caught, r.misses, r.median_lead_days) == (0, ("v:1",), None)


def test_signal_on_inspection_day_is_a_miss_and_lead_uses_earliest(cfg):
    v = make_venue("v:1", first_inspection_date=date(2026, 10, 1), license_description="Restaurant")
    same_day = [make_signal("license_issued", "v:1", observed=date(2026, 10, 1))]
    assert recall_audit([v], same_day, date(2026, 9, 1), date(2026, 10, 31), **DEN).caught == 0
    sigs = [
        make_signal("license_issued", "v:1", observed=date(2026, 9, 21), signal_id="a"),
        make_signal("not_yet_inspected", "v:1", observed=date(2026, 9, 1), signal_id="b"),
    ]
    r = recall_audit([v], sigs, date(2026, 9, 1), date(2026, 10, 31), **DEN)
    assert r.lead_days == (30,) and r.median_lead_days == 30.0


def test_empty_openings_gives_zero_recall():
    r = recall_audit([], [], date(2026, 9, 1), date(2026, 10, 31), **DEN)
    assert (r.total, r.caught, r.recall, r.median_lead_days) == (0, 0, 0.0, None)


def test_recall_report_frozen():
    r = recall_audit([], [], date(2026, 9, 1), date(2026, 10, 31), **DEN)
    assert isinstance(r, RecallReport)
    with pytest.raises(ValidationError):
        r.total = 3  # type: ignore[misc]


def test_recall_command_replays_signals_before_first_inspection(tmp_path, monkeypatch):
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    venues = [
        make_venue(
            "v:1",
            first_inspection_date=date(2026, 10, 1),
            license_description="Restaurant",
            license_ids=("a1",),
        ),
        make_venue(  # transfer: license issued after the first inspection
            "v:2",
            first_inspection_date=date(2026, 10, 2),
            license_description="Restaurant",
            license_ids=("a2",),
        ),
    ]
    lics = [
        make_license("a1", source="sla_active", original_issue_date=date(2026, 7, 1)),
        make_license("a2", source="sla_active", original_issue_date=date(2026, 10, 20)),
    ]
    store.save("venues", venues, key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    store.save("licenses", lics, key=lambda r: r.record_id)  # type: ignore[attr-defined]
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    out = cli.recall(weeks=12, today=date(2026, 10, 31))
    assert (out.total, out.caught, out.median_lead_days) == (1, 1, 92.0)
    json.dumps(out.model_dump(mode="json"))
    assert cli.main(["recall", "--weeks", "12"]) == 0


def test_recall_command_catches_openings_licensed_only_by_a_now_inactive_license(
    tmp_path, monkeypatch
):
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    venues = [
        make_venue(
            "v:1",
            first_inspection_date=date(2026, 10, 1),
            license_description="Restaurant",
            license_ids=("i1",),
        ),
        make_venue(  # inactive license issued after the first inspection: transfer, not opening
            "v:2",
            first_inspection_date=date(2026, 10, 2),
            license_description="Restaurant",
            license_ids=("i2",),
        ),
    ]
    lics = [
        make_license(
            "i1", source="sla_inactive", received_date=None, original_issue_date=date(2026, 7, 1)
        ),
        make_license(
            "i2", source="sla_inactive", received_date=None, original_issue_date=date(2026, 10, 20)
        ),
    ]
    store.save("venues", venues, key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    store.save("licenses", lics, key=lambda r: r.record_id)  # type: ignore[attr-defined]
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    out = cli.recall(weeks=12, today=date(2026, 10, 31))
    assert (out.total, out.caught, out.median_lead_days) == (1, 1, 92.0)


def test_live_score_does_not_signal_or_rank_a_lapsed_license_venue(tmp_path, monkeypatch):
    from scripts.hospitality.models import Group

    store = DocStore(f"sqlite:///{tmp_path}/s.db")
    venue = make_venue(
        "v:1", license_ids=("i1",), group_id="g:v:1", camis="9", license_description="Restaurant"
    )
    group = Group(
        group_id="g:v:1",
        name="Lapsed Bar",
        venue_ids=("v:1",),
        resolution="singleton",
        evidence_ref="",
    )
    lic = make_license(
        "i1", source="sla_inactive", received_date=None, original_issue_date=date(2026, 9, 1)
    )
    store.save("venues", [venue], key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    store.save("groups", [group], key=lambda g: g.group_id)  # type: ignore[attr-defined]
    store.save("licenses", [lic], key=lambda r: r.record_id)  # type: ignore[attr-defined]
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    out = cli.score(now=datetime(2026, 11, 16, tzinfo=UTC))
    assert out["license_signals"] == {}
    assert out["prospects"] == 0


# --- I5: both denominators, stale leads, and the live not_yet_inspected cap ----------------------
def _restaurant(vid: str, first: date | None, lids: tuple[str, ...] = (), **kw: object):
    return make_venue(
        vid, first_inspection_date=first, license_description="Restaurant", license_ids=lids, **kw
    )


def test_recall_reports_coverage_of_all_first_inspections(cfg):
    caught = _restaurant("v:1", date(2026, 10, 1))
    missed = _restaurant("v:2", date(2026, 10, 5))
    sigs = [make_signal("license_issued", "v:1", observed=date(2026, 7, 1))]
    r = recall_audit(
        [caught, missed],
        sigs,
        date(2026, 9, 1),
        date(2026, 10, 31),
        first_inspections=10,
        license_matched=3,
        lead_cap_days=365,
    )
    assert (r.recall, r.first_inspections, r.license_matched) == (0.5, 10, 3)
    assert r.coverage == 0.1  # 1 caught of all 10 first inspections in the window


def test_lead_median_excludes_stale_leads_and_counts_them(cfg):
    venues = [_restaurant(f"v:{i}", date(2026, 10, 1)) for i in range(3)]
    sigs = [
        make_signal("license_issued", "v:0", observed=date(2026, 9, 1)),  # 30 days
        make_signal("license_issued", "v:1", observed=date(2026, 6, 23)),  # 100 days
        make_signal("not_yet_inspected", "v:2", observed=date(2025, 5, 19)),  # 500 days
    ]
    r = recall_audit(
        venues,
        sigs,
        date(2026, 9, 1),
        date(2026, 10, 31),
        first_inspections=3,
        license_matched=3,
        lead_cap_days=365,
    )
    assert sorted(r.lead_days) == [30, 100, 500]
    assert r.median_lead_days == 100.0  # all leads, for transparency
    assert r.median_lead_days_within_cap == 65.0 and r.leads_over_cap == 1
    assert r.lead_cap_days == 365


def test_recall_audit_needs_both_denominators(cfg):
    with pytest.raises(TypeError):
        recall_audit([], [], date(2026, 9, 1), date(2026, 10, 31))  # type: ignore[call-arg]


def test_recall_command_counts_every_first_inspection_in_the_window(tmp_path, monkeypatch):
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    venues = [
        _restaurant("v:1", date(2026, 10, 1), ("a1",)),
        make_venue("v:2", first_inspection_date=date(2026, 10, 3)),  # no license matched
        make_venue(
            "v:3",
            first_inspection_date=date(2026, 10, 4),
            license_description="Grocery Store",
            license_ids=("g",),
        ),
        make_venue("v:4", first_inspection_date=date(2026, 1, 4)),  # outside the window
    ]
    lics = [make_license("a1", source="sla_active", original_issue_date=date(2026, 7, 1))]
    store.save("venues", venues, key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    store.save("licenses", lics, key=lambda r: r.record_id)  # type: ignore[attr-defined]
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    out = cli.recall(weeks=12, today=date(2026, 10, 31))
    assert (out.total, out.caught, out.first_inspections, out.license_matched) == (1, 1, 3, 2)
    assert round(out.coverage, 3) == 0.333


def test_recall_replay_applies_the_live_not_yet_inspected_cap(tmp_path, monkeypatch, cfg):
    """A license older than the live stale cap emits nothing live, so the replay must not count it."""
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    first = date(2026, 10, 1)
    old = date(2026, 10, 1).toordinal() - int(cfg.not_yet_inspected_max_age_days) - 30
    lic = make_license("a1", source="sla_active", original_issue_date=date.fromordinal(old))
    store.save("venues", [_restaurant("v:1", first, ("a1",))], key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    store.save("licenses", [lic], key=lambda r: r.record_id)  # type: ignore[attr-defined]
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    out = cli.recall(weeks=12, today=date(2026, 10, 31))
    assert (out.total, out.caught) == (1, 0)


def test_report_states_both_denominators_and_never_says_bare_recall(tmp_path, monkeypatch, cfg):
    from scripts.hospitality.report import _recall

    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    venues = [
        _restaurant("v:1", date(2026, 10, 1), ("a1",)),
        make_venue("v:2", first_inspection_date=date(2026, 10, 3)),
        make_venue("v:3", first_inspection_date=date(2026, 10, 4)),
        make_venue("v:4", first_inspection_date=date(2026, 10, 5)),
    ]
    lics = [make_license("a1", source="sla_active", original_issue_date=date(2026, 7, 1))]
    store.save("venues", venues, key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    store.save("licenses", lics, key=lambda r: r.record_id)  # type: ignore[attr-defined]
    text = "\n".join(_recall(store, cfg, date(2026, 10, 31)))
    assert "1 of 1" in text and "1 of 4" in text  # both denominators, side by side
    assert (
        "not market-wide recall" in text.lower() or "not the share of nyc openings" in text.lower()
    )
    assert "- Recall:" not in text
    assert "365" in text  # the lead cap is stated
