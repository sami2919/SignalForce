from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from scripts.hospitality import cli
from scripts.hospitality.labels import (
    cold_prospects,
    customer_groups,
    is_customer,
    labels_from_embeds,
    load_seed_labels,
)
from scripts.hospitality.models import CustomerLabel, Group, StackObservation, Venue
from scripts.hospitality.store import DocStore
from tests.hospitality.factories import make_venue

SEED = Path(__file__).resolve().parents[2] / "examples/magic-loyalist/customers_seed.yaml"


def groups_for(venues: list[Venue]) -> list[Group]:
    ids = sorted({v.group_id for v in venues})
    return [
        Group(
            group_id=g,
            name=next(v.name for v in venues if v.group_id == g),
            venue_ids=tuple(v.venue_id for v in venues if v.group_id == g),
            resolution="singleton",
        )
        for g in ids
    ]


def label(**kw: object) -> CustomerLabel:
    base: dict[str, object] = {
        "name": "Bluebird",
        "website_domain": None,
        "first_public_date": None,
        "source": "public_list",
        "evidence_ref": "x",
    }
    base.update(kw)
    return CustomerLabel(**base)  # type: ignore[arg-type]


def test_domain_match_beats_name() -> None:
    venues = [
        make_venue(
            "v:1", name="Bluebird", website="https://bluebirdchapelhill.com", group_id="g:1"
        ),
        make_venue("v:2", name="Bluebird", website="https://bluebird-nyc.com", group_id="g:2"),
    ]
    labels = [label(website_domain="bluebirdchapelhill.com")]
    assert set(customer_groups(labels, venues, groups_for(venues))) == {"g:1"}


def test_domain_match_ignores_www_and_name() -> None:
    venues = [
        make_venue("v:1", name="Totally Different", website="https://www.a.com/x", group_id="g:1")
    ]
    out = customer_groups([label(website_domain="a.com")], venues, groups_for(venues))
    assert set(out) == {"g:1"}


def test_name_match_when_no_domain_and_strict_threshold() -> None:
    venues = [
        make_venue("v:1", name="The Bluebird LLC", group_id="g:1"),
        make_venue("v:2", name="Blue Heron", group_id="g:2"),
    ]
    assert set(customer_groups([label()], venues, groups_for(venues))) == {"g:1"}


def test_name_fallback_for_venue_without_website_when_label_has_domain() -> None:
    venues = [make_venue("v:1", name="Bluebird", website=None, group_id="g:1")]
    out = customer_groups(
        [label(website_domain="bluebirdchapelhill.com")], venues, groups_for(venues)
    )
    assert set(out) == {"g:1"}


def test_group_name_match() -> None:
    venues = [make_venue("v:1", name="Carbone", group_id="g:1")]
    groups = [
        Group(group_id="g:1", name="Major Food Group", venue_ids=("v:1",), resolution="manual")
    ]
    assert set(customer_groups([label(name="Major Food Group")], venues, groups)) == {"g:1"}


def test_earliest_label_wins() -> None:
    venues = [make_venue("v:1", name="Acme", website="https://acme.com", group_id="g:1")]
    seed = label(name="Acme", website_domain="acme.com", first_public_date=date(2025, 10, 20))
    embed = label(
        name="Acme",
        website_domain="acme.com",
        first_public_date=date(2026, 11, 16),
        source="embed",
    )
    for order in ([seed, embed], [embed, seed]):
        out = customer_groups(order, venues, groups_for(venues))
        assert out["g:1"] == seed


def test_dated_label_preferred_over_undated_and_seed_over_embed_on_tie() -> None:
    venues = [make_venue("v:1", name="Acme", website="https://acme.com", group_id="g:1")]
    undated = label(name="Acme", website_domain="acme.com", source="embed")
    dated = label(name="Acme", website_domain="acme.com", first_public_date=date(2026, 1, 1))
    assert customer_groups([undated, dated], venues, groups_for(venues))["g:1"] == dated
    other = label(name="Acme", website_domain="acme.com", source="embed")
    assert (
        customer_groups(
            [other, undated.model_copy(update={"source": "public_list"})],
            venues,
            groups_for(venues),
        )["g:1"].source
        == "public_list"
    )


def test_labels_from_embeds() -> None:
    venues = [
        make_venue("v:1", name="Oriana", website="https://www.oriananewyork.com/", group_id="g:1"),
        make_venue("v:2", name="Other", website=None, group_id="g:2"),
    ]
    out = labels_from_embeds(
        {"v:1": "api.eatloyalist.com/signup", "v:9": "gone"},
        venues,
        {"v:1": date(2026, 11, 16)},
    )
    assert out == [
        CustomerLabel(
            name="Oriana",
            website_domain="oriananewyork.com",
            first_public_date=date(2026, 11, 16),
            source="embed",
            evidence_ref="api.eatloyalist.com/signup",
            venue_id="v:1",
        )
    ]


def test_embed_labels_make_group_a_customer_end_to_end() -> None:
    venues = [
        make_venue("v:1", name="Oriana", website="https://oriananewyork.com", group_id="g:1"),
        make_venue("v:2", name="Noortwyck", website="https://noortwyck.com", group_id="g:1"),
        make_venue("v:3", name="Cold", website="https://cold.com", group_id="g:3"),
    ]
    embeds = labels_from_embeds({"v:1": "e"}, venues, {})
    customers = customer_groups(embeds, venues, groups_for(venues))
    assert set(customers) == {"g:1"}
    assert customers["g:1"].first_public_date is None


def test_customers_never_cold_prospects() -> None:
    customers = {"g:1": label()}
    assert is_customer("g:1", customers) and not is_customer("g:2", customers)
    assert cold_prospects(["g:1", "g:2", "g:3"], customers) == ["g:2", "g:3"]


def test_load_seed_labels_real_file() -> None:
    labels = load_seed_labels(SEED)
    by_name = {lbl.name: lbl for lbl in labels}
    assert all(
        lbl.source == "public_list" and lbl.evidence_ref.startswith("http") for lbl in labels
    )
    assert by_name["The Noortwyck"].first_public_date == date(2024, 11, 2)
    assert by_name["Le Bernardin"].first_public_date == date(2025, 10, 20)
    assert by_name["Rezdôra"].first_public_date == date(2025, 10, 29)
    assert by_name["Hogsalt"].first_public_date is None


def test_load_seed_labels_rejects_bad_file(tmp_path: Path) -> None:
    bad = tmp_path / "s.yaml"
    bad.write_text("customers: [{name: X}]\n")
    with pytest.raises(ValueError):
        load_seed_labels(bad)


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DocStore:
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        "customers:\n"
        "  - {name: Acme, website_domain: acme.com, first_public_date: 2025-10-20,"
        " evidence_ref: 'https://x'}\n"
    )
    monkeypatch.setattr(cli, "SEED_PATH", seed)
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    venues = [
        make_venue("v:1", name="Acme", website="https://acme.com", group_id="g:1"),
        make_venue("v:2", name="Oriana", website="https://oriana.com", group_id="g:2"),
        make_venue("v:3", name="Cold", website="https://cold.com", group_id="g:3"),
    ]
    store.save("venues", venues, key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    store.save("groups", groups_for(venues), key=lambda g: g.group_id)  # type: ignore[attr-defined]
    obs = StackObservation(
        venue_id="v:2",
        url="https://oriana.com",
        observed_at=datetime(2026, 11, 16, tzinfo=UTC),
        platforms=("resy", "loyalist"),
        evidence=("resy.com", "api.eatloyalist.com/signup"),
        fetched_via="fetcher",
    )
    store.save("stack_observations", [obs], key=lambda o: f"{o.venue_id}|{o.observed_at}")  # type: ignore[attr-defined]
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    return store


def test_labels_command_counts_by_source_and_saves(tmp_path, monkeypatch, capsys) -> None:
    store = _setup(tmp_path, monkeypatch)
    assert cli.main(["labels"]) == 0
    out = capsys.readouterr().out
    assert "public_list: 1" in out and "embed: 1" in out
    saved = store.load("customer_labels", CustomerLabel)
    assert {lbl.source for lbl in saved} == {"public_list", "embed"}
    assert cli.labels() == {"public_list": 1, "embed": 1, "embeds_lapsed": 0}  # idempotent rerun


def test_websites_includes_seed_customer_venues(tmp_path, monkeypatch) -> None:
    store = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "k")
    venues = [
        make_venue("v:1", name="Acme", website=None, group_id="g:1"),  # seed customer, no estimate
        make_venue("v:3", name="Cold", website=None, group_id="g:3"),  # neither
    ]
    store.save("venues", venues, key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    looked_up: list[list[str]] = []

    def fake_lookups(vs, client, priority, today, *thresholds):  # type: ignore[no-untyped-def]
        looked_up.append(list(priority))
        return iter(())

    monkeypatch.setattr(cli, "iter_website_lookups", fake_lookups)
    monkeypatch.setattr(cli, "PlacesClient", lambda key, budget: object())
    out = cli.websites(provider="places")
    assert looked_up == [["v:1"]] and out["prioritized"] == 1


# --- C1: a name match must be near-exact on distinctive tokens, never a token subset ---

# (seed label, live venue/group name) pairs the old token-set matcher scored 1.0 (or >= 0.9).
LIVE_FALSE_MATCHES = [
    ("Major Food Group", "FOOD"),
    ("Le Bernardin", "LE LE"),
    ("Eleven Madison Park", "THE PARK"),
    ("Hotel Chelsea", "DOUBLETREE HOTEL MANHATTAN-CHELSEA"),
    ("Hotel Chelsea", "THE GEM HOTEL CHELSEA"),
    ("Hotel Chelsea", "RENAISSANCE NEW YORK CHELSEA HOTEL SOMEWHERE NOWHE"),
    ("Happy Cooking Hospitality", "HOSPITALITY LLC"),
    ("Union Square Hospitality Group", "AT Hospitality Group LLC"),
    ("Union Square Hospitality Group", "37 HOSPITALITY GROUP INC."),
    ("COTE", "L'ABEILLE / L'ABEILLE A COTE / SUSHI ICHIMURA"),
    ("COTE", "LE BISTRO D'A COTE"),
    ("El Quijote", "QUIJOTE"),  # a Queens namesake of the Hotel Chelsea outlet
]


@pytest.mark.parametrize(("label_name", "other"), LIVE_FALSE_MATCHES)
def test_generic_or_subset_names_never_match_a_customer_label(label_name: str, other: str) -> None:
    venues = [make_venue("v:1", name=other, group_id="g:1")]
    groups = [Group(group_id="g:1", name=other, venue_ids=("v:1",), resolution="singleton")]
    assert customer_groups([label(name=label_name)], venues, groups) == {}


@pytest.mark.parametrize(
    ("label_name", "other"),
    [
        ("The Noortwyck", "NOORTWYCK LLC, THE"),
        ("The Noortwyck", "THE NOORT WYCK"),
        ("Le Bernardin", "LE BERNARDIN"),
        ("Major Food Group", "Major Food Group LLC"),
        ("Rezdôra", "REZDORA"),
        ("Hotel Chelsea", "HOTEL CHELSEA"),
    ],
)
def test_near_exact_names_still_match(label_name: str, other: str) -> None:
    venues = [make_venue("v:1", name=other, group_id="g:1")]
    assert set(customer_groups([label(name=label_name)], venues, groups_for(venues))) == {"g:1"}


def test_a_label_made_only_of_generic_words_never_matches_by_name() -> None:
    venues = [make_venue("v:1", name="The Food Group", group_id="g:1")]
    assert customer_groups([label(name="Food Group")], venues, groups_for(venues)) == {}


# --- I3: a customer's other venues (seed data) gate their groups too ---


def test_seed_venue_names_and_domains_gate_other_venues() -> None:
    venues = [
        make_venue("v:1", name="REZDORA", group_id="g:1"),
        make_venue("v:2", name="MASSARA", group_id="g:2"),  # same owner, own singleton group
        make_venue("v:3", name="Other", website="https://www.massara.nyc/", group_id="g:3"),
        make_venue("v:4", name="Cold", group_id="g:4"),
    ]
    rez = label(
        name="Rezdôra",
        website_domain="rezdora.nyc",
        venue_names=("Massara",),
        venue_domains=("massara.nyc",),
    )
    assert set(customer_groups([rez], venues, groups_for(venues))) == {"g:1", "g:2", "g:3"}


def test_prefix_venue_name_covers_brand_venues_only_when_marked() -> None:
    venues = [
        make_venue("v:1", name="MOMOFUKU NOODLE BAR/BANG BAR", group_id="g:1"),
        make_venue("v:2", name="MOMOFUKU SSAM BAR", group_id="g:2"),
        make_venue("v:3", name="NOODLE BAR MOMOFUKU STYLE", group_id="g:3"),  # not a prefix
    ]
    plain = label(name="Momofuku")
    assert customer_groups([plain], venues, groups_for(venues)) == {}
    marked = label(name="Momofuku", venue_names=("Momofuku*",))
    assert set(customer_groups([marked], venues, groups_for(venues))) == {"g:1", "g:2"}


def test_generic_prefix_is_ignored() -> None:
    venues = [make_venue("v:1", name="THE FOOD STOP", group_id="g:1")]
    marked = label(name="Food Co", venue_names=("The Food*",))
    assert customer_groups([marked], venues, groups_for(venues)) == {}


def test_real_seed_gates_known_customer_venues() -> None:
    names = {
        "v:1": "LA TETE D'OR",
        "v:2": "MASSARA",
        "v:3": "CARBONE",
        "v:4": "BAR KABAWA",
        "v:5": "MOMOFUKU NOODLE BAR/BANG BAR",
        "v:6": "THE NOORT WYCK",
        "v:7": "COTE KOREAN STEAKHOUSE",
        "v:8": "EL QUIJOTE / LOBBY BAR AT THE HOTEL CHELSEA",
    }
    venues = [make_venue(vid, name=n, group_id=f"g:{vid}") for vid, n in names.items()]
    got = customer_groups(load_seed_labels(SEED), venues, groups_for(venues))
    assert set(got) == {f"g:{vid}" for vid in names}
    assert got["g:v:2"].name == "Rezdôra" and got["g:v:1"].name == "Dinex Group"


def test_case_hint_venues_are_seed_venues_of_their_customer() -> None:
    by_name = {lbl.name: lbl for lbl in load_seed_labels(SEED)}
    for customer, venue in cli.CASE_HINTS.items():
        lbl = by_name[customer]
        assert venue in (lbl.name, *lbl.venue_names), (customer, venue)
