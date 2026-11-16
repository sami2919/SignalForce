"""I8: an honest, deterministic tie-break and a data-driven non-restaurant premises rule."""

from datetime import UTC, date, datetime

import pytest

from scripts.hospitality.config import load_config
from scripts.hospitality.models import Group
from scripts.hospitality.scoring import (
    non_restaurant_name_reason,
    premises_reason,
    rank_prospects,
    score_group,
    tie_blocks,
)
from tests.hospitality.factories import (
    make_estimate,
    make_license,
    make_scored,
    make_signal,
    make_venue,
)

NOW = datetime(2026, 11, 16, tzinfo=UTC)


@pytest.fixture
def cfg():
    return load_config()


def _opened_group(gid: str, vid: str, inspected: date, issued: date):
    """A singleton group whose venue opened (first inspection) after its license issued."""
    venue = make_venue(vid, group_id=gid, first_inspection_date=inspected)
    group = Group(group_id=gid, name=gid, venue_ids=(vid,), resolution="singleton")
    sig = make_signal("license_issued", vid, observed=issued)
    return group, venue, sig


def test_score_group_records_the_tie_break_facts(cfg) -> None:
    group, venue, sig = _opened_group("g:a", "v:a", date(2026, 10, 1), date(2026, 3, 1))
    unopened = make_venue("v:b", group_id="g:a")
    group = group.model_copy(update={"venue_ids": ("v:a", "v:b")})
    pending = make_signal("license_pending", "v:b", observed=date(2026, 9, 1))
    est = {"v:b": make_estimate("v:b", estimated_open=date(2026, 12, 1))}
    scored = score_group(
        group,
        [sig, pending],
        est,
        [venue, unopened],
        [],
        cfg,
        NOW,
        is_customer=False,
        disqualified_reason=None,
    )
    # Nearest opening to today among counted opening venues: 2026-12-01 is 15 days away;
    # 2026-10-01 was 46 days ago.
    assert scored.opening_date == date(2026, 12, 1) and scored.opening_gap_days == 15
    assert scored.latest_signal_on == date(2026, 9, 1)


def test_tied_priorities_break_on_opening_nearest_today_then_signal_recency(cfg) -> None:
    rows = [
        _opened_group("g:1", "v:1", date(2026, 3, 1), date(2026, 1, 10)),  # opened 260d ago
        _opened_group("g:2", "v:2", date(2026, 11, 1), date(2026, 6, 1)),  # opened 15d ago
        _opened_group("g:3", "v:3", date(2026, 11, 1), date(2026, 8, 1)),  # same, newer signal
    ]
    accounts = [
        score_group(g, [s], {}, [v], [], cfg, NOW, is_customer=False, disqualified_reason=None)
        for g, v, s in rows
    ]
    assert len({a.priority for a in accounts}) == 1  # one score: a genuine tie
    assert [a.group_id for a in rank_prospects(accounts)] == ["g:3", "g:2", "g:1"]


def test_tie_blocks_group_equal_priorities() -> None:
    ranked = [
        make_scored("g:1", 0.5),
        make_scored("g:2", 0.3),
        make_scored("g:3", 0.3 + 1e-12),  # float noise is still a tie
        make_scored("g:4", 0.3),
        make_scored("g:5", 0.1),
    ]
    assert tie_blocks(ranked) == {"g:2": (2, 4), "g:3": (2, 4), "g:4": (2, 4)}


def _members(*venues):
    return [v.model_copy(update={"group_id": "g:p"}) for v in venues]


def test_all_catering_establishment_group_is_disqualified(cfg) -> None:
    lics = {
        "c1": make_license("c1", description="Catering Establishment", license_class="346"),
        "c2": make_license("c2", description="Catering Establishment", license_class="246"),
    }
    members = _members(
        make_venue("v:1", license_ids=("c1",)), make_venue("v:2", license_ids=("c2",))
    )
    assert premises_reason(members, lics, cfg) == "non_restaurant_premises:catering_establishment"


def test_airport_zip_group_is_disqualified(cfg) -> None:
    members = _members(make_venue("v:1", zip_code="11430"), make_venue("v:2", zip_code="11371"))
    assert premises_reason(members, {}, cfg) == "non_restaurant_premises:airport"


def test_one_airport_outpost_does_not_disqualify_a_restaurant_group(cfg) -> None:
    lics = {"r1": make_license("r1", description="Restaurant", license_class="340")}
    members = _members(make_venue("v:1", zip_code="11430"), make_venue("v:2", license_ids=("r1",)))
    assert premises_reason(members, lics, cfg) is None


@pytest.mark.parametrize(
    ("description", "license_class"),
    [("Restaurant", "340"), ("Hotel", "343"), ("Food & Beverage Business", "370")],
)
def test_restaurant_hotel_and_bar_premises_are_not_disqualified(
    cfg, description: str, license_class: str
) -> None:
    """Hotel restaurants can be Magic's buyer (Hotel Chelsea is a Loyalist customer)."""
    lics = {"x": make_license("x", description=description, license_class=license_class)}
    assert premises_reason(_members(make_venue("v:1", license_ids=("x",))), lics, cfg) is None


def test_catering_plus_restaurant_licenses_on_one_venue_is_not_disqualified(cfg) -> None:
    lics = {
        "c": make_license("c", description="Catering Establishment"),
        "r": make_license("r", description="Restaurant"),
    }
    members = _members(make_venue("v:1", license_ids=("c", "r")))
    assert premises_reason(members, lics, cfg) is None


def test_venue_without_premises_evidence_is_never_called_non_restaurant(cfg) -> None:
    assert premises_reason(_members(make_venue("v:press:1", zip_code="")), {}, cfg) is None
    assert premises_reason([], {}, cfg) is None


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("WILDLIFE CONSERVATION SOCIETY", "non_restaurant_name:institution"),
        ("BRONX ZOO CATERERS", "non_restaurant_name:institution"),
        ("CAFETERIA NEW YORK AQUARIUM", "non_restaurant_name:institution"),
        ("MASTERPIECE CATERERS CORP", "non_restaurant_name:caterer"),
        ("MARRIOTT RESORTS HOSPITALITY CORPORATION", "non_restaurant_name:hotel_chain"),
        ("& HILTON MANAGEMENT LLC/DBA:ONE UN NEW YORK", "non_restaurant_name:hotel_chain"),
        ("HYATT EQUITIES LLC", "non_restaurant_name:hotel_chain"),
    ],
)
def test_non_restaurant_names_data_cannot_express(cfg, name: str, reason: str) -> None:
    assert non_restaurant_name_reason([name], cfg) == reason


@pytest.mark.parametrize(
    "name",
    [
        "Chama Mama at Morgan LLC & Chama Mama Catering & Events LLC",  # restaurant + catering
        "Cornbread and Caviar Restaurant & Catering LLC",
        "THE MUSEUM BAR",
        "BAR SOCIETY",
        "Lightning Society",
        "Host 367 LLC",
        "Hilton's Deli Corp",
        "ZOOBA NYC LLC",
        "Hotel Chelsea",
        "Sushi Noz LLC",
        "Marriott Street Pizza",  # a namesake, not the chain's legal entity
    ],
)
def test_restaurants_with_lookalike_names_are_not_non_restaurant(cfg, name: str) -> None:
    assert non_restaurant_name_reason([name], cfg) is None


def test_disqualifier_lists_are_required_config(cfg) -> None:
    """M2: a YAML that omits a disqualifier list must fail loudly, not disqualify nothing."""
    from pydantic import ValidationError

    from scripts.hospitality.config import HospitalityConfig

    raw = cfg.model_dump()
    for key in (
        "disqualify_name_patterns",
        "non_restaurant_name_patterns",
        "non_restaurant_premises",
    ):
        partial = {k: v for k, v in raw.items() if k != key}
        with pytest.raises(ValidationError):
            HospitalityConfig.model_validate(partial)


def test_score_command_disqualifies_non_restaurant_premises(tmp_path, monkeypatch) -> None:
    from scripts.hospitality import cli
    from scripts.hospitality.models import LicenseRecord, ScoredAccount, Venue
    from scripts.hospitality.store import DocStore

    seed = tmp_path / "seed.yaml"
    seed.write_text("customers: []\ndismissed_embeds: []\n")
    monkeypatch.setattr(cli, "SEED_PATH", seed)
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    lics: list[LicenseRecord] = [
        make_license("c1", description="Catering Establishment", legal_name="GALA HALL LLC"),
        make_license("r1", description="Restaurant", legal_name="NOODLE BAR LLC"),
    ]
    store.save("licenses", lics, key=lambda r: r.record_id)  # type: ignore[attr-defined]
    venues: list[Venue] = [
        make_venue("v:c", license_ids=("c1",), name="Gala Hall"),
        make_venue("v:r", license_ids=("r1",), name="Noodle Bar"),
    ]
    store.save("venues", venues, key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    store.save(
        "groups",
        [
            Group(group_id=v.group_id, name=v.name, venue_ids=(v.venue_id,), resolution="singleton")
            for v in venues
        ],
        key=lambda g: g.group_id,  # type: ignore[attr-defined]
    )
    store.save(
        "signals",
        [make_signal("press_opening", "v:c"), make_signal("press_opening", "v:r")],
        key=lambda s: s.signal_id,  # type: ignore[attr-defined]
    )
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    cli.score(NOW)
    scores = {a.group_id: a for a in store.load("scores", ScoredAccount)}
    assert scores["g:v:c"].disqualified_reason == "non_restaurant_premises:catering_establishment"
    assert scores["g:v:r"].disqualified_reason is None
