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
    r = recall_audit([v1, v2], sigs, date(2026, 9, 1), date(2026, 10, 31))
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
    r = recall_audit([v], sigs, date(2026, 9, 1), date(2026, 10, 31))
    assert (r.caught, r.misses, r.median_lead_days) == (0, ("v:1",), None)


def test_signal_on_inspection_day_is_a_miss_and_lead_uses_earliest(cfg):
    v = make_venue("v:1", first_inspection_date=date(2026, 10, 1), license_description="Restaurant")
    same_day = [make_signal("license_issued", "v:1", observed=date(2026, 10, 1))]
    assert recall_audit([v], same_day, date(2026, 9, 1), date(2026, 10, 31)).caught == 0
    sigs = [
        make_signal("license_issued", "v:1", observed=date(2026, 9, 21), signal_id="a"),
        make_signal("not_yet_inspected", "v:1", observed=date(2026, 9, 1), signal_id="b"),
    ]
    r = recall_audit([v], sigs, date(2026, 9, 1), date(2026, 10, 31))
    assert r.lead_days == (30,) and r.median_lead_days == 30.0


def test_empty_openings_gives_zero_recall():
    r = recall_audit([], [], date(2026, 9, 1), date(2026, 10, 31))
    assert (r.total, r.caught, r.recall, r.median_lead_days) == (0, 0, 0.0, None)


def test_recall_report_frozen():
    r = recall_audit([], [], date(2026, 9, 1), date(2026, 10, 31))
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
    assert (out["total"], out["caught"], out["median_lead_days"]) == (1, 1, 92.0)
    json.dumps(out)
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
    assert (out["total"], out["caught"], out["median_lead_days"]) == (1, 1, 92.0)


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
