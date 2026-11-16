from datetime import UTC, datetime, timedelta

from scripts.hospitality.models import StackObservation
from scripts.hospitality.stack.signals import (
    disqualified_venues,
    loyalist_venues,
    stack_signals,
)
from tests.hospitality.factories import make_venue

NOW = datetime(2026, 11, 16, tzinfo=UTC)


def make_obs(venue_id: str, platforms: tuple[str, ...], at: datetime = NOW) -> StackObservation:
    return StackObservation(
        venue_id=venue_id,
        url=f"https://{venue_id}.com",
        observed_at=at,
        platforms=platforms,
        evidence=tuple(f"ev-{p}" for p in platforms),
        fetched_via="fetcher",
    )


def test_fragmented_stack_is_group_level() -> None:
    venues = [make_venue("v:1", group_id="g:1"), make_venue("v:2", group_id="g:1")]
    obs = [make_obs("v:1", ("resy",)), make_obs("v:2", ("sevenrooms",))]
    sigs = stack_signals(obs, venues, previous=[], now=NOW)
    frag = [s for s in sigs if s.signal_type == "stack_fragmented"]
    assert [s.entity_id for s in frag] == ["g:1"]
    assert frag[0].signal_id == "stack_fragmented:g:1:2026-11-16"


def test_single_platform_group_is_not_fragmented() -> None:
    venues = [make_venue("v:1", group_id="g:1"), make_venue("v:2", group_id="g:1")]
    obs = [make_obs("v:1", ("resy",)), make_obs("v:2", ("resy", "toast"))]
    assert not [
        s for s in stack_signals(obs, venues, [], NOW) if s.signal_type == "stack_fragmented"
    ]


def test_tripleseat_resy_and_private_events_are_venue_level() -> None:
    venues = [make_venue("v:1"), make_venue("v:2")]
    obs = [make_obs("v:1", ("resy", "tripleseat")), make_obs("v:2", ("perfect_venue",))]
    sigs = stack_signals(obs, venues, [], NOW)
    got = {(s.signal_type, s.entity_id) for s in sigs}
    assert got == {
        ("tripleseat_resy", "v:1"),
        ("private_events", "v:1"),
        ("private_events", "v:2"),
    }


def test_platform_switch_from_previous() -> None:
    prev = [
        make_obs("v:1", ("opentable",), at=NOW - timedelta(days=7)),
        make_obs("v:1", ("sevenrooms",), at=NOW - timedelta(days=30)),
    ]
    sigs = stack_signals([make_obs("v:1", ("resy",))], [make_venue("v:1")], prev, NOW)
    assert [s.detail for s in sigs if s.signal_type == "platform_switch"] == ["opentable→resy"]


def test_no_switch_when_same_or_no_previous() -> None:
    v = [make_venue("v:1")]
    same = [make_obs("v:1", ("resy",), at=NOW - timedelta(days=7))]
    assert not [
        s
        for s in stack_signals([make_obs("v:1", ("resy",))], v, same, NOW)
        if s.signal_type == "platform_switch"
    ]
    assert not [
        s
        for s in stack_signals([make_obs("v:1", ("resy",))], v, [], NOW)
        if s.signal_type == "platform_switch"
    ]


def test_disqualified_and_loyalist() -> None:
    obs = [
        make_obs("v:1", ("punchh", "resy")),
        make_obs("v:2", ("loyalist",)),
        make_obs("v:3", ("resy",)),
    ]
    assert disqualified_venues(obs) == {"v:1": "qsr_loyalty:punchh"}
    assert loyalist_venues(obs) == {"v:2": "ev-loyalist"}


def _switches(current: StackObservation, previous: list[StackObservation]) -> list[str]:
    sigs = stack_signals([current], [make_venue("v:1")], previous, NOW)
    return [s.detail for s in sigs if s.signal_type == "platform_switch"]


def test_detection_variance_is_not_a_platform_switch() -> None:
    """M4: none -> resy because Firecrawl ran this time (JS widget seen) is not a switch."""
    before = make_obs("v:1", (), at=NOW - timedelta(days=7))  # fetcher only: budget spent
    now = make_obs("v:1", ("resy",)).model_copy(update={"fetched_via": "firecrawl"})
    assert _switches(now, [before]) == []
    # A widget that disappears from view the same way is not a switch either.
    seen = make_obs("v:1", ("resy",), at=NOW - timedelta(days=7)).model_copy(
        update={"fetched_via": "firecrawl"}
    )
    assert _switches(make_obs("v:1", ()), [seen]) == []


def test_switch_needs_both_reservation_sets_and_the_same_fetch_path() -> None:
    before = make_obs("v:1", ("opentable",), at=NOW - timedelta(days=7))
    via_firecrawl = make_obs("v:1", ("resy",)).model_copy(update={"fetched_via": "firecrawl"})
    assert _switches(via_firecrawl, [before]) == []  # different fetch path
    assert _switches(make_obs("v:1", ("resy",)), [before]) == ["opentable→resy"]
    assert _switches(make_obs("v:1", ()), [before]) == []  # empty now: unseen, not removed
