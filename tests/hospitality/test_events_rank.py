from datetime import date

import pytest

from scripts.hospitality import cli
from scripts.hospitality.events.rank import (
    ATTEND_PRIOR,
    MEETING_RATE_PRIOR,
    match_appearance,
    meeting_list,
    rank_events,
)
from scripts.hospitality.models import CustomerLabel, Event, EventAppearance
from tests.hospitality.factories import make_scored, make_venue


def event(event_id: str = "e:1", **kw: object) -> Event:
    base: dict[str, object] = {
        "event_id": event_id,
        "name": "Test Event",
        "start": date(2027, 5, 22),
        "end": date(2027, 5, 25),
        "city": "New York",
        "event_type": "curated_conference",
        "cost_usd": 500.0,
        "lineup_urls": (),
    }
    base.update(kw)
    return Event(**base)  # type: ignore[arg-type]


def app(person: str, restaurant: str, role: str = "speaker", event_id: str = "e:1"):
    return EventAppearance(
        event_id=event_id, person=person, restaurant=restaurant, role=role, source_url="https://x"
    )  # type: ignore[arg-type]


VENUES = [
    make_venue("v:1", name="Ghost Bird", group_id="g:1"),
    make_venue("v:2", name="Ember Hall", group_id="g:2"),
    make_venue("v:3", name="Old Customer Cafe", group_id="g:3"),
    make_venue("v:4", name="Shut Place", group_id="g:4"),
]


def test_priors_are_exact() -> None:
    assert ATTEND_PRIOR == {
        "speaker": 0.95,
        "panelist": 0.95,
        "festival_chef": 0.95,
        "award_nominee": 0.9,
        "exhibitor_staff": 0.7,
        "sponsor": 0.6,
        "past_recap": 0.35,
    }
    assert MEETING_RATE_PRIOR == {
        "curated_conference": 0.15,
        "festival": 0.08,
        "awards": 0.05,
        "trade_show": 0.03,
        "local_meetup": 0.20,
        "magic_dinner": 0.50,
    }


def test_match_appearance() -> None:
    assert match_appearance(app("A", "Ghost Bird"), VENUES) == "g:1"
    assert match_appearance(app("A", "Totally Other"), VENUES) is None


def test_single_speaker_exact_values() -> None:
    accounts = {"g:1": make_scored("g:1", 0.4)}
    [s] = rank_events([event()], [app("Ana", "Ghost Bird")], accounts, VENUES)
    assert s.expected_meetings == pytest.approx(0.057)
    assert s.score_per_dollar == pytest.approx(0.000114)
    assert s.matched_people == 1


def test_unmatched_uses_default_priority() -> None:
    [s] = rank_events([event()], [app("Ana", "Nowhere")], {}, VENUES)
    assert s.expected_meetings == pytest.approx(0.95 * 0.05 * 0.15)
    assert s.matched_people == 0


def test_unknown_cost_is_not_infinitely_efficient() -> None:
    accounts = {"g:1": make_scored("g:1", 0.4)}
    free = event("e:free", cost_usd=0.0)
    paid = event("e:paid", cost_usd=500.0)
    apps = [
        app("Ana", "Ghost Bird", event_id="e:free"),
        app("Ana", "Ghost Bird", event_id="e:paid"),
    ]
    ranked = rank_events([free, paid], apps, accounts, VENUES)
    by_id = {s.event_id: s for s in ranked}
    assert by_id["e:free"].score_per_dollar == 0.0
    assert by_id["e:free"].expected_meetings == pytest.approx(0.057)
    assert [s.event_id for s in ranked] == ["e:paid", "e:free"]


def test_event_without_appearances_ranks_last_with_zero() -> None:
    accounts = {"g:1": make_scored("g:1", 0.4)}
    ranked = rank_events(
        [event("e:empty"), event("e:full")],
        [app("Ana", "Ghost Bird", event_id="e:full")],
        accounts,
        VENUES,
    )
    assert [s.event_id for s in ranked] == ["e:full", "e:empty"]
    assert ranked[1].expected_meetings == 0.0 and ranked[1].matched_people == 0


def test_customers_and_disqualified_add_no_expected_meetings() -> None:
    accounts = {
        "g:3": make_scored("g:3", 0.9, is_customer=True),
        "g:4": make_scored("g:4", 0.9, disqualified_reason="contract operator"),
    }
    apps = [app("C", "Old Customer Cafe"), app("D", "Shut Place")]
    [s] = rank_events([event()], apps, accounts, VENUES)
    assert s.expected_meetings == 0.0


def test_customers_sort_after_prospects_and_are_flagged() -> None:
    accounts = {
        "g:1": make_scored("g:1", 0.2, p_window=0.7),
        "g:3": make_scored("g:3", 0.95, is_customer=True),
    }
    apps = [
        app("Cust", "Old Customer Cafe", "speaker"),
        app("Low", "Ghost Bird", "sponsor"),
        app("Unk", "Nowhere", "past_recap"),
    ]
    targets = meeting_list(event(), apps, accounts, VENUES)
    assert [t.person for t in targets] == ["Low", "Unk", "Cust"]
    cust = targets[-1]
    assert cust.is_customer and cust.reason == "warm intro / co-host"
    assert not targets[0].is_customer and targets[0].in_window
    assert targets[0].p_attend == 0.6 and targets[0].priority == 0.2
    assert targets[1].group_id is None and targets[1].priority == 0.05


def test_seed_labelled_group_without_score_is_never_cold() -> None:
    labels = {
        "g:2": CustomerLabel(
            name="Ember Hall",
            website_domain=None,
            first_public_date=date(2026, 1, 1),
            source="public_list",
            evidence_ref="seed",
        )
    }
    targets = meeting_list(event(), [app("Bo", "Ember Hall")], {}, VENUES, customers=labels)
    assert [(t.person, t.is_customer) for t in targets] == [("Bo", True)]
    [s] = rank_events([event()], [app("Bo", "Ember Hall")], {}, VENUES, customers=labels)
    assert s.expected_meetings == 0.0


def test_disqualified_never_a_target() -> None:
    accounts = {"g:4": make_scored("g:4", 0.9, disqualified_reason="closed")}
    assert meeting_list(event(), [app("D", "Shut Place")], accounts, VENUES) == []


def test_meeting_list_only_this_events_appearances() -> None:
    accounts = {"g:1": make_scored("g:1", 0.4)}
    apps = [app("A", "Ghost Bird"), app("B", "Ghost Bird", event_id="e:other")]
    assert [t.person for t in meeting_list(event(), apps, accounts, VENUES)] == ["A"]


def test_cli_events_rank(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from scripts.hospitality.store import DocStore

    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    monkeypatch.setattr(cli, "OUT_DIR", tmp_path / "out")
    store.save("venues", VENUES, key=lambda v: v.venue_id)
    store.save("scores", [make_scored("g:1", 0.4)], key=lambda a: a.group_id)
    store.save("event_appearances", [app("Ana", "Ghost Bird")], key=lambda a: a.person)
    reg = tmp_path / "events.yaml"
    reg.write_text(
        "events:\n  - {event_id: e:1, name: A, start: 2027-05-22, end: 2027-05-25, city: NYC,\n"
        "     event_type: curated_conference, cost_usd: 500, lineup_urls: []}\n"
    )
    out = cli.events_rank(reg)
    assert out["events"] == 1 and out["targets"] == 1
    assert (tmp_path / "out" / "meeting_lists.md").exists()
