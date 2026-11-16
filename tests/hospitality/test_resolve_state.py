"""I1 / M3: a re-resolve keeps durable state (websites, press venues, merges, ids).

`resolve` is a recompute of what free public data says. Paid lookups (websites), press-only
venues, group evidence and records keyed to venue or group ids must survive it, and a website
already known must never be looked up (and billed) again.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.hospitality import cli
from scripts.hospitality.models import (
    Contact,
    CustomerLabel,
    Group,
    GroupEvidence,
    PlaceMatch,
    PressFacts,
    PressVenue,
    Signal,
    StackObservation,
    Venue,
    WebsiteLookup,
)
from scripts.hospitality.store import DocStore
from tests.hospitality.factories import (
    make_embed_label,
    make_inspection,
    make_license,
    make_signal,
    make_venue,
)

DAY1 = date(2026, 11, 1)


def _obs(venue_id: str, platforms: tuple[str, ...]) -> StackObservation:
    return StackObservation(
        venue_id=venue_id,
        url=f"https://{venue_id}.test",
        observed_at=datetime(2026, 11, 2, tzinfo=UTC),
        platforms=platforms,
        evidence=tuple(f"ev:{p}" for p in platforms),
        fetched_via="firecrawl",
    )


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DocStore:
    seed = tmp_path / "seed.yaml"
    seed.write_text("customers: []\ndismissed_embeds: []\n")
    monkeypatch.setattr(cli, "SEED_PATH", seed)
    s = DocStore(f"sqlite:///{tmp_path}/m.db")
    s.save(
        "licenses",
        [
            make_license("l1", legal_name="ALPHA ONE LLC", dba="Alpha", address="1 Main St"),
            make_license(
                "l2",
                legal_name="BRAVO TWO LLC",
                dba="Bravo",
                address="99 Far Ave",
                zip_code="10099",
                lat=40.8,
                lon=-73.9,
            ),
            make_license(
                "l3",
                legal_name="CHARLIE THREE LLC",
                dba="Charlie",
                address="5 Elm St",
                zip_code="10005",
                lat=40.6,
                lon=-74.1,
            ),
        ],
        key=lambda r: r.record_id,  # type: ignore[attr-defined]
    )
    s.save(
        "inspections",
        [make_inspection("c1", dba="ALPHA", address="1 MAIN ST")],
        key=lambda r: r.camis,  # type: ignore[attr-defined]
    )
    monkeypatch.setattr(cli, "DocStore", lambda: s)
    return s


def _venues(s: DocStore) -> dict[str, Venue]:
    return {v.venue_id: v for v in s.load("venues", Venue)}


def _group_of(s: DocStore) -> dict[str, str]:
    return {v.venue_id: v.group_id for v in s.load("venues", Venue)}


def test_resolve_keeps_a_website_found_before_it(store: DocStore) -> None:
    cli.resolve()
    first = _venues(store)
    assert set(first) == {"v:c1", "v:lic:l2", "v:lic:l3"}
    store.save(
        "venues",
        [first["v:c1"].model_copy(update={"website": "https://alpha.test"})],
        key=lambda v: v.venue_id,  # type: ignore[attr-defined]
    )  # a pre-fix store: the website lives only on the venue row
    cli.resolve()
    assert _venues(store)["v:c1"].website == "https://alpha.test"
    lookups = {w.venue_id: w for w in store.load("websites", WebsiteLookup)}
    assert lookups["v:c1"].website == "https://alpha.test"  # now durable on its own
    cli.resolve()
    assert _venues(store)["v:c1"].website == "https://alpha.test"


def test_resolve_runs_the_shared_domain_merge(store: DocStore) -> None:
    store.save(
        "websites",
        [
            WebsiteLookup(venue_id="v:c1", website="https://alpha.test/", looked_up_on=DAY1),
            WebsiteLookup(
                venue_id="v:lic:l2", website="https://www.alpha.test/b", looked_up_on=DAY1
            ),
        ],
        key=lambda w: w.venue_id,  # type: ignore[attr-defined]
    )
    cli.resolve()
    groups = store.load("groups", Group)
    merged = [g for g in groups if len(g.venue_ids) == 2]
    assert len(merged) == 1 and merged[0].resolution == "shared_domain"
    assert set(merged[0].venue_ids) == {"v:c1", "v:lic:l2"}


def test_shared_host_domains_never_merge_groups(store: DocStore) -> None:
    store.save(
        "websites",
        [
            WebsiteLookup(
                venue_id="v:c1", website="https://instagram.com/alpha", looked_up_on=DAY1
            ),
            WebsiteLookup(
                venue_id="v:lic:l2", website="https://www.instagram.com/bravo", looked_up_on=DAY1
            ),
        ],
        key=lambda w: w.venue_id,  # type: ignore[attr-defined]
    )
    cli.resolve()
    assert all(len(g.venue_ids) == 1 for g in store.load("groups", Group))


def test_resolve_keeps_press_venues_and_reapplies_group_evidence(store: DocStore) -> None:
    cli.resolve()
    press_venue = make_venue("v:press:abc", name="Delta", address="SoHo")
    store.save("venues", [press_venue], key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    store.save(
        "group_evidence",
        [
            GroupEvidence(
                venue_ids=("v:c1", "v:lic:l3", "v:press:abc"),
                name="Alpha Hospitality",
                resolution="press",
                evidence_ref="https://press.test/a",
            )
        ],
        key=lambda e: f"{e.evidence_ref}|{e.name}",  # type: ignore[attr-defined]
    )
    store.save(
        "signals",
        [make_signal("press_opening", "v:press:abc")],
        key=lambda x: x.signal_id,  # type: ignore[attr-defined]
    )
    cli.resolve()
    venues = _venues(store)
    assert "v:press:abc" in venues
    gid = venues["v:press:abc"].group_id
    assert venues["v:c1"].group_id == gid == venues["v:lic:l3"].group_id
    group = next(g for g in store.load("groups", Group) if g.group_id == gid)
    assert group.resolution == "press" and group.name == "Alpha Hospitality"
    cli.score(datetime(2026, 11, 16, tzinfo=UTC))  # the press signal still reaches its group
    from scripts.hospitality.models import ScoredAccount

    scored = {a.group_id: a for a in store.load("scores", ScoredAccount)}
    assert any(c.signal_type == "press_opening" for c in scored[gid].contributions)


def test_state_follows_a_licensed_venue_when_it_gets_its_inspection(store: DocStore) -> None:
    cli.resolve()
    assert "v:lic:l2" in _venues(store)
    store.save(
        "websites",
        [WebsiteLookup(venue_id="v:lic:l2", website="https://bravo.test", looked_up_on=DAY1)],
        key=lambda w: w.venue_id,  # type: ignore[attr-defined]
    )
    store.save(
        "stack_observations",
        [_obs("v:lic:l2", ("resy", "loyalist"))],
        key=lambda o: f"{o.venue_id}|{o.observed_at.isoformat()}",  # type: ignore[attr-defined]
    )
    store.save(
        "customer_labels",
        [make_embed_label("v:lic:l2", name="Bravo")],
        key=lambda c: f"{c.source}|{c.name}|{c.website_domain}|{c.venue_id}",  # type: ignore[attr-defined]
    )
    store.save(
        "signals",
        [make_signal("tripleseat_resy", "v:lic:l2")],
        key=lambda x: x.signal_id,  # type: ignore[attr-defined]
    )
    # Bravo opens: DOHMH now has a site that the license matches, so its venue id changes.
    store.save(
        "inspections",
        [
            make_inspection(
                "c2",
                dba="BRAVO",
                address="99 FAR AVE",
                zip_code="10099",
                lat=40.8,
                lon=-73.9,
                first=date(2026, 11, 10),
            )
        ],
        key=lambda r: r.camis,  # type: ignore[attr-defined]
    )
    cli.resolve()
    venues = _venues(store)
    assert "v:lic:l2" not in venues and venues["v:c2"].website == "https://bravo.test"
    assert [o.venue_id for o in store.load("stack_observations", StackObservation)] == ["v:c2"]
    labels = store.load("customer_labels", CustomerLabel)
    assert [c.venue_id for c in labels] == ["v:c2"]
    sigs = [s for s in store.load("signals", Signal) if s.signal_type == "tripleseat_resy"]
    assert [s.entity_id for s in sigs] == ["v:c2"]
    from scripts.hospitality.labels import current_customers

    assert set(current_customers(store, cli.SEED_PATH)) == {venues["v:c2"].group_id}


def test_records_keyed_by_a_merged_away_group_follow_the_merge(store: DocStore) -> None:
    """M3: contacts, drafts and group-level signals keyed by g:v:B move to the merged id."""
    cli.resolve()
    store.save(
        "contacts",
        [
            Contact(
                contact_id="k1",
                group_id="g:v:lic:l3",
                name="Pat Doe",
                role="GM",
                email=None,
                email_confidence=None,
                instagram=None,
                phone=None,
                source="team_page",
                evidence_ref="https://charlie.test/team",
            )
        ],
        key=lambda c: c.contact_id,  # type: ignore[attr-defined]
    )
    store.save(
        "signals",
        [make_signal("stack_fragmented", "g:v:lic:l3", signal_id="sf:1")],
        key=lambda x: x.signal_id,  # type: ignore[attr-defined]
    )
    store.save(
        "group_evidence",
        [
            GroupEvidence(
                venue_ids=("v:c1", "v:lic:l3"),
                name="Alpha Group",
                resolution="press",
                evidence_ref="https://press.test/b",
            )
        ],
        key=lambda e: f"{e.evidence_ref}|{e.name}",  # type: ignore[attr-defined]
    )
    cli.resolve()
    merged = _group_of(store)["v:lic:l3"]
    assert merged == _group_of(store)["v:c1"] != "g:v:lic:l3"
    assert [c.group_id for c in store.load("contacts", Contact)] == [merged]
    sig = next(s for s in store.load("signals", Signal) if s.signal_id == "sf:1")
    assert sig.entity_id == merged


def test_websites_never_looks_up_a_known_website_again(
    store: DocStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.hospitality.window.survival import linked_to_inspected  # noqa: F401

    cli.resolve()
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "k")
    from tests.hospitality.factories import make_estimate

    store.save(
        "estimates",
        [make_estimate("v:lic:l2"), make_estimate("v:lic:l3")],
        key=lambda e: e.venue_id,  # type: ignore[attr-defined]
    )
    store.save(
        "websites",
        [WebsiteLookup(venue_id="v:lic:l2", website="https://bravo.test", looked_up_on=DAY1)],
        key=lambda w: w.venue_id,  # type: ignore[attr-defined]
    )
    cli.resolve()
    searched: list[str] = []

    def fake_search(self: object, text_query: str) -> list[PlaceMatch]:
        searched.append(text_query)
        self.budget.spend()  # type: ignore[attr-defined]
        return []  # a miss

    monkeypatch.setattr(cli.PlacesClient, "search", fake_search)
    out = cli.websites(today=date(2026, 11, 16))
    assert searched == ["Charlie 5 Elm St New York"]  # Bravo's known site was not re-bought
    assert out["lookups"] == 1
    # The miss is recorded too: a rerun within the retry window buys nothing.
    misses = {w.venue_id: w for w in store.load("websites", WebsiteLookup)}
    assert misses["v:lic:l3"].website is None
    cli.websites(today=date(2026, 11, 20))
    assert len(searched) == 1
    cli.websites(today=date(2027, 1, 30))  # past website_miss_retry_days: retried once
    assert len(searched) == 2


def test_websites_regroups_on_a_shared_domain(
    store: DocStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.resolve()
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "k")
    from tests.hospitality.factories import make_estimate

    store.save(
        "estimates",
        [make_estimate("v:lic:l2"), make_estimate("v:lic:l3")],
        key=lambda e: e.venue_id,  # type: ignore[attr-defined]
    )
    places = {
        "Bravo": PlaceMatch(
            place_id="b",
            display_name="Bravo",
            address="",
            website="https://ab.test/b",
            lat=40.8,
            lon=-73.9,
        ),
        "Charlie": PlaceMatch(
            place_id="c",
            display_name="Charlie",
            address="",
            website="https://ab.test/c",
            lat=40.6,
            lon=-74.1,
        ),
    }

    def fake_search(self: object, text_query: str) -> list[PlaceMatch]:
        self.budget.spend()  # type: ignore[attr-defined]
        return [places[text_query.split()[0]]]

    monkeypatch.setattr(cli.PlacesClient, "search", fake_search)
    cli.websites(today=date(2026, 11, 16))
    group_of = _group_of(store)
    assert group_of["v:lic:l2"] == group_of["v:lic:l3"]
    groups = {g.group_id: g for g in store.load("groups", Group)}
    assert groups[group_of["v:lic:l2"]].resolution == "shared_domain"


def test_pipeline_sequence_keeps_customers_out_and_state_intact(
    store: DocStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """resolve -> websites -> crawl (Loyalist embed) -> press (merge) -> resolve -> score -> draft.

    The embed customer never reaches a cold output; websites and merges survive the re-resolve.
    """
    from scripts.hospitality.models import ExaResult, ScoredAccount
    from tests.hospitality.factories import make_estimate

    for var in ("GOOGLE_PLACES_API_KEY", "FIRECRAWL_API_KEY", "EXA_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(var, "k")
    cli.resolve()
    store.save(
        "estimates",
        [make_estimate("v:lic:l2"), make_estimate("v:lic:l3")],
        key=lambda e: e.venue_id,  # type: ignore[attr-defined]
    )
    sites = {
        "Alpha": "https://alpha.test",
        "Bravo": "https://bravo.test",
        "Charlie": "https://charlie.test",
    }
    coords = {"Alpha": (40.7, -74.0), "Bravo": (40.8, -73.9), "Charlie": (40.6, -74.1)}
    calls: list[str] = []

    def fake_search(self: object, text_query: str) -> list[PlaceMatch]:
        self.budget.spend()  # type: ignore[attr-defined]
        name = text_query.split()[0].title()
        calls.append(name)
        lat, lon = coords[name]
        return [
            PlaceMatch(
                place_id=name, display_name=name, address="", website=sites[name], lat=lat, lon=lon
            )
        ]

    monkeypatch.setattr(cli.PlacesClient, "search", fake_search)
    cli.websites(today=date(2026, 11, 16))
    assert sorted(calls) == ["Bravo", "Charlie"]

    async def fake_crawl(venues, now, **_: object) -> list[StackObservation]:
        return [
            StackObservation(
                venue_id=v.venue_id,
                url=v.website or "",
                observed_at=now,
                platforms=("resy", "loyalist") if v.venue_id == "v:lic:l2" else ("resy",),
                evidence=("ev:resy", "ev:loyalist") if v.venue_id == "v:lic:l2" else ("ev:resy",),
                fetched_via="firecrawl",
            )
            for v in venues
            if v.website
        ]

    monkeypatch.setattr(cli, "crawl_stacks", fake_crawl)
    monkeypatch.setattr(cli, "FirecrawlClient", Mock())
    cli.crawl(datetime(2026, 11, 16, tzinfo=UTC))

    exa = Mock()
    exa.search.return_value = [
        ExaResult(url="https://press.test/x", title="t", published_date=DAY1, text="article")
    ]
    monkeypatch.setattr(cli.ExaClient, "from_env", lambda budget: exa)
    facts = PressFacts(
        venues=(
            PressVenue(
                name="Charlie",
                address_or_area="5 Elm St",
                status="opening_soon",
                expected_open=None,
                group_name="Echo Hospitality",
            ),
            PressVenue(
                name="Foxtrot",
                address_or_area="Tribeca",
                status="announced",
                expected_open=None,
                group_name="Echo Hospitality",
            ),
        ),
        people=(),
        hotel_partner=None,
    )
    monkeypatch.setattr(cli, "extract_press", lambda text, url: facts)
    cli.press(today=date(2026, 11, 16))
    cli.resolve()  # day 2

    venues = _venues(store)
    assert venues["v:lic:l2"].website == "https://bravo.test"
    assert venues["v:lic:l3"].website == "https://charlie.test"
    press_ids = [vid for vid in venues if vid.startswith("v:press:")]
    assert len(press_ids) == 1
    assert venues[press_ids[0]].group_id == venues["v:lic:l3"].group_id

    cli.score(datetime(2026, 11, 16, tzinfo=UTC))
    bravo_group = venues["v:lic:l2"].group_id
    scores = {a.group_id: a for a in store.load("scores", ScoredAccount)}
    assert scores[bravo_group].is_customer

    drafted: list[str] = []

    def fake_draft(acct, evidence, contact, angle):  # type: ignore[no-untyped-def]
        drafted.append(acct.group_id)
        from tests.hospitality.test_drafts import make_draft

        return make_draft((), group_id=acct.group_id, draft_id=f"d:{acct.group_id}")

    monkeypatch.setattr(cli, "draft", fake_draft)
    from scripts.hospitality.models import Judgement

    verdict = Judgement(
        score=8.0,
        hyper_specific=True,
        factually_grounded=True,
        non_obvious=True,
        deletion_reason="",
        what_would_make_me_reply="",
        grounding_violations=(),
        passed=True,
    )
    monkeypatch.setattr(cli, "judge", lambda d, evidence, *, account_text, pass_score: verdict)
    cli.draft_command(top=10)
    assert bravo_group not in drafted and drafted
