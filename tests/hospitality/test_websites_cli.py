"""`websites` provider selection and summary, `websites-import`, `websites-export-misses`."""

import csv
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.hospitality import cli
from scripts.hospitality.models import PlaceMatch, WebsiteLookup
from scripts.hospitality.stack.website_search import FetchedPage
from scripts.hospitality.store import DocStore
from tests.hospitality.factories import make_estimate, make_inspection, make_venue

TODAY = date(2026, 11, 16)
PHONE_PAGE = '<a href="tel:2125550100">call</a>'
ADDRESS_PAGE = "<p>9 Elm St, New York, NY 10001</p>"


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DocStore:
    seed = tmp_path / "seed.yaml"
    seed.write_text("customers: []\ndismissed_embeds: []\n")
    monkeypatch.setattr(cli, "SEED_PATH", seed)
    monkeypatch.setattr(cli, "OUT_DIR", tmp_path / "out")
    s = DocStore(f"sqlite:///{tmp_path}/m.db")
    monkeypatch.setattr(cli, "DocStore", lambda: s)
    for var in ("EXA_API_KEY", "FIRECRAWL_API_KEY", "GOOGLE_PLACES_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return s


def put_venues(store: DocStore, *venues) -> None:  # type: ignore[no-untyped-def]
    store.save("venues", list(venues), key=lambda v: v.venue_id)  # type: ignore[attr-defined]


def put_estimates(store: DocStore, *pairs: tuple[str, date]) -> None:
    store.save(
        "estimates",
        [make_estimate(vid, estimated_open=d) for vid, d in pairs],
        key=lambda e: e.venue_id,  # type: ignore[attr-defined]
    )


def fake_fetch(pages: dict[str, str]):  # type: ignore[no-untyped-def]
    requested: list[str] = []

    def fetch(urls):  # type: ignore[no-untyped-def]
        out = {}
        for u in urls:
            requested.append(u)
            body = pages.get(u)
            out[u] = FetchedPage(url=u, status="ok" if body else "failed", body=body)
        return out

    fetch.requested = requested  # type: ignore[attr-defined]
    return fetch


# --- fail fast and provider choice ---------------------------------------------------------


def test_search_provider_fails_fast_naming_both_keys(store, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SystemExit) as exc:
        cli.main(["websites"])
    assert "EXA_API_KEY" in str(exc.value) and "FIRECRAWL_API_KEY" in str(exc.value)


def test_places_provider_still_needs_its_key(store) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SystemExit) as exc:
        cli.main(["websites", "--provider", "places"])
    assert "GOOGLE_PLACES_API_KEY" in str(exc.value)


@pytest.mark.parametrize("var", ["EXA_API_KEY", "FIRECRAWL_API_KEY"])
def test_either_search_key_alone_is_enough_and_says_which(store, monkeypatch, var) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv(var, "k")
    put_venues(store, make_venue("v:1"))
    monkeypatch.setattr(cli, "fetch_pages", fake_fetch({}))
    with patch("scripts.hospitality.discover.exa.ExaClient.post", return_value={"results": []}), \
        patch("scripts.firecrawl_client.FirecrawlClient.post", return_value={"data": []}):  # fmt: skip
        out = cli.websites(today=TODAY)
    assert out["provider"] == "search"
    assert out["engines"] == ("exa" if var == "EXA_API_KEY" else "firecrawl")


# --- the search path through the command ----------------------------------------------------


def setup_search(store, monkeypatch, venues, pages, exa_results):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("EXA_API_KEY", "k")
    put_venues(store, *venues)
    put_estimates(store, *((v.venue_id, date(2027, 1, 1 + i)) for i, v in enumerate(venues)))
    fetch = fake_fetch(pages)
    monkeypatch.setattr(cli, "fetch_pages", fetch)
    calls: list[str] = []

    def post(self, endpoint, json_data=None):  # type: ignore[no-untyped-def]
        calls.append(json_data["query"])
        return {"results": [{"url": u} for u in exa_results(json_data["query"])]}

    patcher = patch("scripts.hospitality.discover.exa.ExaClient.post", post)
    patcher.start()
    return fetch, calls, patcher


def test_command_verifies_records_and_summarizes(store, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    a = make_venue("v:a", name="Alpha", address="9 Elm St", camis="1")
    b = make_venue("v:b", name="Bravo", address="5 Oak St", camis=None)
    c = make_venue("v:c", name="Charlie", address="7 Pine St", camis=None)
    store.save("inspections", [make_inspection("1", phone="212-555-0100")], key=lambda i: i.camis)  # type: ignore[attr-defined]
    pages = {"https://alpha.com/": PHONE_PAGE, "https://bravo.com/": "<p>5 Oak St New York</p>"}
    results = {"Alpha": ["https://alpha.com"], "Bravo": ["https://bravo.com"], "Charlie": []}
    _fetch, _calls, patcher = setup_search(
        store, monkeypatch, [a, b, c], pages, lambda q: results[q.split(" ")[0]]
    )
    try:
        out = cli.websites(today=TODAY)
    finally:
        patcher.stop()
    assert out["websites_found"] == 2 and out["verified_phone"] == 1
    assert out["verified_address"] == 1 and out["verified_address_no_phone_record"] == 1
    assert (
        out["misses_no_candidates"] == 1 and out["calls_exa"] == 3 and out["calls_firecrawl"] == 0
    )
    saved = {w.venue_id: w for w in store.load("websites", WebsiteLookup)}
    assert saved["v:a"].verified_by == "phone" and saved["v:b"].verified_by == "address"
    assert saved["v:c"].miss_reason == "no_candidates"
    venues = {v.venue_id: v for v in store.load("venues", type(a))}
    assert venues["v:a"].website == "https://alpha.com/"
    # the venue's camis maps to the DOHMH phone: the venue without one verifies on address only
    assert out["lookups"] == 3


def test_known_website_is_never_looked_up_again(store, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    known = make_venue("v:k", name="Known", website="https://known.com")
    new = make_venue("v:n", name="New", address="9 Elm St")
    _fetch, calls, patcher = setup_search(store, monkeypatch, [known, new], {}, lambda q: [])
    store.save(
        "websites",
        [WebsiteLookup(venue_id="v:k", website="https://known.com", looked_up_on=TODAY)],
        key=lambda w: w.venue_id,  # type: ignore[attr-defined]
    )
    try:
        cli.websites(today=TODAY)
    finally:
        patcher.stop()
    assert [q.split(" ")[0] for q in calls] == ["New"]


def test_seed_customer_venues_come_first_then_soonest_opening(store, monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    cust = make_venue("v:c", name="Cust", group_id="g:c")
    late = make_venue("v:l", name="Late")
    soon = make_venue("v:s", name="Soon")
    _fetch, calls, patcher = setup_search(store, monkeypatch, [late, soon, cust], {}, lambda q: [])
    put_estimates(store, ("v:l", date(2027, 6, 1)), ("v:s", date(2027, 1, 1)))
    monkeypatch.setattr(cli, "current_customers", lambda *a, **k: {"g:c": object()})
    try:
        cli.websites(today=TODAY)
    finally:
        patcher.stop()
    assert [q.split(" ")[0] for q in calls] == ["Cust", "Soon", "Late"]


def test_limit_caps_lookups(store, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    vs = [make_venue(f"v:{i}", name=f"V{i}") for i in range(4)]
    _fetch, calls, patcher = setup_search(store, monkeypatch, vs, {}, lambda q: [])
    try:
        out = cli.websites(limit=2, today=TODAY)
    finally:
        patcher.stop()
    assert len(calls) == 2 and out["prioritized"] == 2


def test_places_provider_still_works(store, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "k")
    put_venues(store, make_venue("v:1", name="Oriana", lat=40.7, lon=-74.0))
    put_estimates(store, ("v:1", date(2027, 1, 1)))

    def search(self, text_query):  # type: ignore[no-untyped-def]
        self.budget.spend()
        return [
            PlaceMatch(
                place_id="p", display_name="Oriana", address="x", website="https://o.com",
                lat=40.7, lon=-74.0,
            )
        ]  # fmt: skip

    monkeypatch.setattr(cli.PlacesClient, "search", search)
    out = cli.websites(provider="places", today=TODAY)
    assert out["websites_found"] == 1 and out["calls_places"] == 1 and out["provider"] == "places"
    assert store.load("websites", WebsiteLookup)[0].website == "https://o.com"


# --- run-p0 keys ----------------------------------------------------------------------------


def test_run_p0_needs_only_firecrawl_for_the_search_provider(store, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    assert cli.p0_required_keys(cli.load_config().websites) == ("FIRECRAWL_API_KEY",)
    places = cli.load_config().websites.model_copy(update={"provider": "places"})
    assert cli.p0_required_keys(places) == ("GOOGLE_PLACES_API_KEY", "FIRECRAWL_API_KEY")


# --- websites-import ------------------------------------------------------------------------


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def test_import_rules(store, tmp_path) -> None:  # type: ignore[no-untyped-def]
    put_venues(
        store,
        make_venue("v:1", camis="11"),
        make_venue("v:2"),
        make_venue("v:3"),
        make_venue("v:4"),
        make_venue("v:5"),
    )
    f = write_csv(
        tmp_path / "in.csv",
        ["venue_id", "camis", "website", "notes"],
        [
            ["v:1", "", "oriana.com", "x"],  # bare domain gets https://
            ["", "11", "https://dup.com", ""],  # camis maps to v:1 again: second row skipped
            ["", "", "", ""],  # blank
            ["v:nope", "", "https://nope.com", ""],  # unknown id
            ["v:2", "", "not a url", ""],  # malformed
            ["v:2", "", "javascript:alert(1)", ""],  # malformed scheme
            ["v:3", "", "https://www.yelp.com/biz/x", ""],  # filtered domain
            ["v:3", "", "https://www.linkedin.com/company/x", ""],  # never
            ["v:4", "", "https://loyalist.com/for/x", ""],  # never
            ["v:5", "", "https://five.com/menu?x=1#f", ""],
        ],
    )
    out = cli.websites_import(f, today=TODAY)
    assert out["imported"] == 2 and out["unknown_id"] == 1 and out["blank"] == 1
    assert out["bad_url"] == 2 and out["filtered_domain"] == 3 and out["duplicate"] == 1
    saved = {w.venue_id: w for w in store.load("websites", WebsiteLookup)}
    assert saved["v:1"].website == "https://oriana.com" and saved["v:1"].verified_by == "manual"
    assert saved["v:5"].website == "https://five.com/menu" and saved["v:5"].source == "manual"
    assert set(saved) == {"v:1", "v:5"}
    assert {v.venue_id: v.website for v in store.load("venues", type(make_venue()))}["v:1"] == (
        "https://oriana.com"
    )


def test_import_needs_an_id_column(store, tmp_path) -> None:  # type: ignore[no-untyped-def]
    f = write_csv(tmp_path / "in.csv", ["name", "website"], [["x", "https://x.com"]])
    with pytest.raises(SystemExit) as exc:
        cli.websites_import(f)
    assert "venue_id" in str(exc.value)


def test_import_never_overwrites_search_verified_sites_unless_asked(store, tmp_path) -> None:  # type: ignore[no-untyped-def]
    put_venues(store, make_venue("v:1", website="https://found.com/"), make_venue("v:2"))
    store.save(
        "websites",
        [
            WebsiteLookup(
                venue_id="v:1", website="https://found.com/", looked_up_on=TODAY,
                source="search", verified_by="phone", evidence_url="https://found.com/",
            ),
            WebsiteLookup(venue_id="v:2", website=None, looked_up_on=TODAY, source="search",
                          miss_reason="none_verified"),
        ],
        key=lambda w: w.venue_id,  # type: ignore[attr-defined]
    )  # fmt: skip
    f = write_csv(
        tmp_path / "in.csv", ["venue_id", "website"],
        [["v:1", "https://mine.com"], ["v:2", "https://two.com"]],
    )  # fmt: skip
    out = cli.websites_import(f, today=TODAY)
    assert out["protected"] == 1 and out["imported"] == 1
    saved = {w.venue_id: w for w in store.load("websites", WebsiteLookup)}
    assert saved["v:1"].website == "https://found.com/" and saved["v:2"].verified_by == "manual"
    out = cli.websites_import(f, overwrite=True, today=TODAY)
    saved = {w.venue_id: w for w in store.load("websites", WebsiteLookup)}
    assert saved["v:1"].website == "https://mine.com" and saved["v:1"].verified_by == "manual"
    assert out["replaced"] == 2 and out["protected"] == 0


def test_import_command_wires_the_flag(store, tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    put_venues(store, make_venue("v:1"))
    f = write_csv(tmp_path / "in.csv", ["venue_id", "website"], [["v:1", "https://one.com"]])
    assert cli.main(["websites-import", str(f)]) == 0
    assert "imported: 1" in capsys.readouterr().out


# --- websites-export-misses ----------------------------------------------------------------


def test_export_lists_venues_lacking_a_website_in_priority_order(
    store, monkeypatch, capsys
) -> None:  # type: ignore[no-untyped-def]
    has = make_venue("v:has", name="Has", website="https://has.com")
    late = make_venue("v:late", name="Late", address="2 B St", camis="22")
    soon = make_venue("v:soon", name="=Soon", address="1 A St")  # formula-looking name
    cust = make_venue("v:cust", name="Cust", group_id="g:c")
    nopri = make_venue("v:none", name="Unprioritized")
    put_venues(store, has, late, soon, cust, nopri)
    put_estimates(store, ("v:has", date(2027, 1, 1)), ("v:late", date(2027, 6, 1)),
                  ("v:soon", date(2027, 2, 1)))  # fmt: skip
    monkeypatch.setattr(cli, "current_customers", lambda *a, **k: {"g:c": object()})
    store.save(
        "websites",
        [WebsiteLookup(venue_id="v:soon", website=None, looked_up_on=TODAY, source="search",
                       miss_reason="ambiguous")],
        key=lambda w: w.venue_id,  # type: ignore[attr-defined]
    )  # fmt: skip
    path = cli.websites_export_misses(today=TODAY)
    assert path.parent == cli.OUT_DIR
    rows = list(csv.DictReader(path.open()))
    assert [r["venue_id"] for r in rows] == ["v:cust", "v:soon", "v:late"]
    assert rows[1]["miss_reason"] == "ambiguous" and rows[1]["name"] == "'=Soon"
    assert rows[2]["camis"] == "22" and rows[2]["website"] == ""
    assert cli.main(["websites-export-misses"]) == 0
    assert "website_misses.csv" in capsys.readouterr().out
