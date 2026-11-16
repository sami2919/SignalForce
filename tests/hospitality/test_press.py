from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from scripts.hospitality import cli
from scripts.hospitality.discover import press
from scripts.hospitality.discover.press import (
    PRESS_QUERIES,
    extract_press,
    press_to_records,
)
from scripts.hospitality.models import (
    ExaResult,
    Group,
    PressFacts,
    PressPerson,
    PressVenue,
    Venue,
)
from tests.hospitality.factories import make_venue

URL = "https://eater.com/2026/11/ghost-bird-opens"
ARTICLE = (
    "Chef Ana Reyes, formerly of Eleven Madison Park, is opening Ghost Bird at 10 Bleecker St "
    "this winter. Meanwhile Ember Hall, the Kings County Hospitality second spot, opens in "
    "Williamsburg. Sam Lee joins as general manager. A partnership with The Standard hotel."
)
ALUMNI = frozenset({"Eleven Madison Park", "Momofuku"})


def _pv(name: str, area: str = "", group: str | None = None, status: str = "announced"):
    return PressVenue(
        name=name, address_or_area=area, status=status, expected_open=None, group_name=group
    )


def _facts(**kw) -> PressFacts:
    base = {"venues": (), "people": (), "hotel_partner": None}
    base.update(kw)
    return PressFacts(**base)


def test_extract_press_uses_structured_and_drops_names_not_in_text() -> None:
    parsed = _facts(
        venues=(_pv("Ghost Bird", "10 Bleecker St"), _pv("Phantom Diner")),
        people=(
            PressPerson(name="Ana Reyes", role="chef", prior_employers=("Eleven Madison Park",)),
            PressPerson(name="Zed Nobody", role="chef", prior_employers=()),
        ),
        hotel_partner="The Standard",
    )
    with patch.object(press, "structured", return_value=parsed) as st:
        out = extract_press(ARTICLE, URL)
    assert st.call_args.args[0] is PressFacts
    assert st.call_args.kwargs["role"] == "extract"
    assert [v.name for v in out.venues] == ["Ghost Bird"]
    assert [p.name for p in out.people] == ["Ana Reyes"]
    assert out.hotel_partner == "The Standard"
    bad = _facts(hotel_partner="The Invented Hotel")
    with patch.object(press, "structured", return_value=bad):
        assert extract_press(ARTICLE, URL).hotel_partner is None


def test_known_venue_matched_unknown_created_with_press_id() -> None:
    known = make_venue("v:known", name="Ghost Bird", address="10 Bleecker Street")
    facts = _facts(venues=(_pv("Ghost Bird", "10 Bleecker St"), _pv("Ember Hall", "Williamsburg")))
    sigs, new, ev = press_to_records(facts, URL, date(2026, 11, 1), [known], [], ALUMNI)
    opening = [s for s in sigs if s.signal_type == "press_opening"]
    assert {s.entity_id for s in opening} >= {"v:known"}
    assert len(new) == 1 and new[0].venue_id.startswith("v:press:") and new[0].name == "Ember Hall"
    assert new[0].group_id == f"g:{new[0].venue_id}"
    assert {s.entity_id for s in opening} == {"v:known", new[0].venue_id}
    assert all(s.evidence_ref == URL for s in sigs)
    assert all(s.observed_at == datetime(2026, 11, 1, tzinfo=UTC) for s in sigs)
    assert len({s.signal_id for s in sigs}) == len(sigs)
    assert ev == []


def test_press_venue_id_is_stable() -> None:
    facts = _facts(venues=(_pv("Ember Hall", "Williamsburg"),))
    a = press_to_records(facts, URL, None, [], [], ALUMNI)[1][0]
    b = press_to_records(facts, "https://other.com/x", None, [], [], ALUMNI)[1][0]
    assert a.venue_id == b.venue_id


def test_different_address_same_name_is_a_new_location() -> None:
    known = make_venue("v:known", name="Ghost Bird", address="10 Bleecker Street")
    facts = _facts(venues=(_pv("Ghost Bird", "55 Court St, Brooklyn"),))
    sigs, new, _ = press_to_records(facts, URL, None, [known], [], ALUMNI)
    assert len(new) == 1 and sigs[0].entity_id == new[0].venue_id != "v:known"


def test_ambiguous_name_match_never_lands_on_an_arbitrary_venue() -> None:
    a = make_venue("v:a", name="Ghost Bird", address="1 A St")
    b = make_venue("v:b", name="Ghost Bird", address="2 B St")
    facts = _facts(venues=(_pv("Ghost Bird", "Manhattan"),))
    sigs, new, _ = press_to_records(facts, URL, None, [a, b], [], ALUMNI)
    assert len(new) == 1 and sigs[0].entity_id == new[0].venue_id


def test_loose_subset_name_does_not_match() -> None:
    v = make_venue("v:1", name="Momofuku Noodle Bar Extra Long")
    facts = _facts(venues=(_pv("Momofuku"),))
    _, new, _ = press_to_records(facts, URL, None, [v], [], ALUMNI)
    assert len(new) == 1


def test_alumni_hotel_and_people_signals() -> None:
    known = make_venue("v:known", name="Ghost Bird", address="10 Bleecker Street")
    facts = _facts(
        venues=(_pv("Ghost Bird", "10 Bleecker St"),),
        people=(
            PressPerson(
                name="Ana Reyes",
                role="Executive chef",
                prior_employers=("eleven madison park", "Nowhere Cafe"),
            ),
            PressPerson(name="Sam Lee", role="General Manager", prior_employers=()),
        ),
        hotel_partner="The Standard",
    )
    sigs, _, _ = press_to_records(facts, URL, None, [known], [], ALUMNI)
    types = sorted(s.signal_type for s in sigs)
    assert types == ["alumni_edge", "hotel_partnership", "new_gm", "press_opening", "role_hire"]
    assert all(s.entity_id == "v:known" and s.evidence_ref == URL for s in sigs)
    assert "Eleven Madison Park" in next(s for s in sigs if s.signal_type == "alumni_edge").detail


def test_people_without_attributable_venue_are_dropped() -> None:
    person = PressPerson(name="Ana", role="chef", prior_employers=("Momofuku",))
    assert press_to_records(_facts(people=(person,)), URL, None, [], [], ALUMNI)[0] == []
    two = _facts(venues=(_pv("Alpha Bar"), _pv("Beta Grill")), people=(person,))
    sigs, _, _ = press_to_records(two, URL, None, [], [], ALUMNI)
    assert {s.signal_type for s in sigs} == {"press_opening"}


def test_group_evidence_links_venues_sharing_group_name() -> None:
    known = make_venue("v:known", name="Ghost Bird", address="10 Bleecker Street")
    facts = _facts(
        venues=(
            _pv("Ghost Bird", "10 Bleecker St", group="Kings County Hospitality"),
            _pv("Ember Hall", "Williamsburg", group="kings county hospitality"),
            _pv("Solo Spot", "Soho", group="Other Group"),
        )
    )
    _, new, ev = press_to_records(facts, URL, None, [known], [], ALUMNI)
    assert len(ev) == 1
    e = ev[0]
    ember = next(v for v in new if v.name == "Ember Hall")
    assert e.resolution == "press" and e.evidence_ref == URL
    assert set(e.venue_ids) == {"v:known", ember.venue_id}


def test_group_name_matching_known_group_links_its_venues() -> None:
    a = make_venue("v:a", name="Alpha")
    b = make_venue("v:b", name="Beta")
    g = Group(
        group_id="g:v:a",
        name="Kings County Hospitality",
        venue_ids=("v:a", "v:b"),
        resolution="shared_legal_name",
    )
    facts = _facts(venues=(_pv("Ember Hall", "Williamsburg", group="Kings County Hospitality"),))
    _, new, ev = press_to_records(facts, URL, None, [a, b], [g], ALUMNI)
    assert len(ev) == 1 and set(ev[0].venue_ids) == {"v:a", "v:b", new[0].venue_id}


def test_cli_press_fails_fast_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    with pytest.raises(SystemExit, match="EXA_API_KEY"):
        cli.press(120)
    monkeypatch.setenv("EXA_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        cli.press(120)


def test_cli_press_end_to_end_mocked(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from scripts.hospitality.store import DocStore

    monkeypatch.setenv("EXA_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    known = make_venue("v:known", name="Ghost Bird", address="10 Bleecker Street")
    store.save("venues", [known], key=lambda v: v.venue_id)
    store.save(
        "groups",
        [
            Group(
                group_id="g:v:known",
                name="Ghost Bird",
                venue_ids=("v:known",),
                resolution="singleton",
            )
        ],
        key=lambda g: g.group_id,
    )
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    result = ExaResult(url=URL, title="t", published_date=date(2026, 11, 1), text=ARTICLE)
    empty = ExaResult(url="https://x.com/none", title="t", published_date=None, text=None)
    searches: list[tuple] = []

    class FakeExa:
        def search(self, query, **kw):
            searches.append((query, kw))
            return [result, empty]

    monkeypatch.setattr(cli.ExaClient, "from_env", classmethod(lambda c, b: FakeExa()))
    facts = _facts(
        venues=(
            _pv("Ghost Bird", "10 Bleecker St", group="Kings County Hospitality"),
            _pv("Ember Hall", "Williamsburg", group="Kings County Hospitality"),
        )
    )
    monkeypatch.setattr(press, "structured", lambda *a, **k: facts)
    monkeypatch.setattr(cli, "score", lambda: {"scored_groups": 2})
    out = cli.press(120)
    assert len(searches) == len(PRESS_QUERIES)
    assert out["articles"] == 1  # deduped across queries; text-less result skipped
    assert out["new_venues"] == 1
    venues = store.load("venues", Venue)
    assert len(venues) == 2 and len({v.group_id for v in venues}) == 1
    assert len(store.load("groups", Group)) == 1


def test_cli_press_stops_cleanly_when_exa_budget_is_spent(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from scripts.hospitality.budget import BudgetExceeded
    from scripts.hospitality.store import DocStore

    monkeypatch.setenv("EXA_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    monkeypatch.setattr(cli, "DocStore", lambda: store)

    class Spent:
        def search(self, query, **kw):
            raise BudgetExceeded("exa budget exhausted")

    monkeypatch.setattr(cli.ExaClient, "from_env", classmethod(lambda c, b: Spent()))
    monkeypatch.setattr(cli, "score", lambda: {"scored_groups": 0})
    out = cli.press(30)
    assert "exhausted" in out["stopped"] and out["articles"] == 0


# C1 residual: press group / venue names merge groups, so a token subset must never match.
@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Major Food Group", "FOOD GROUP"),
        ("Hotel Chelsea", "GEM HOTEL CHELSEA"),
        ("Union Square Hospitality Group", "AT Hospitality Group LLC"),
        ("Le Bernardin", "LE LE"),
    ],
)
def test_press_names_never_match_by_token_subset(a: str, b: str) -> None:
    from scripts.hospitality.discover.press import _same_name

    assert not _same_name(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [("Major Food Group", "MAJOR FOOD GROUP LLC"), ("Rezdôra", "REZDORA"), ("Carbone", "CARBONE")],
)
def test_press_names_still_match_near_exact(a: str, b: str) -> None:
    from scripts.hospitality.discover.press import _same_name

    assert _same_name(a, b)
