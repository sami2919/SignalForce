from unittest.mock import patch

import pytest

from scripts.hospitality import cli
from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.models import PlaceMatch
from scripts.hospitality.stack.websites import PlacesClient, attach_websites, pick_place
from tests.hospitality.factories import make_venue


def make_place(**overrides: object) -> PlaceMatch:
    base: dict[str, object] = {
        "place_id": "p",
        "display_name": "Oriana",
        "address": "x",
        "website": "https://o.com",
        "lat": 40.7,
        "lon": -74.0,
    }
    base.update(overrides)
    return PlaceMatch(**base)  # type: ignore[arg-type]


def test_pick_place_rejects_far_result() -> None:
    v = make_venue("v:1", name="Oriana", lat=40.7, lon=-74.0)
    assert pick_place(v, [make_place(lat=40.8)]) is None


def test_pick_place_accepts_close_similar_and_picks_nearest() -> None:
    v = make_venue("v:1", name="Oriana", lat=40.7, lon=-74.0)
    near = make_place(place_id="near", lat=40.70005)
    nearer = make_place(place_id="nearer", lat=40.70001)
    assert pick_place(v, [near, nearer]).place_id == "nearer"  # type: ignore[union-attr]


def test_pick_place_rejects_dissimilar_name() -> None:
    v = make_venue("v:1", name="Oriana", lat=40.7, lon=-74.0)
    assert pick_place(v, [make_place(display_name="Zzyzx Parking Garage")]) is None


def test_pick_place_requires_venue_coordinates() -> None:
    v = make_venue("v:1", name="Oriana", lat=None, lon=None)
    assert pick_place(v, [make_place()]) is None


def test_budget_stops_lookups() -> None:
    client = PlacesClient("k", CallBudget("places", limit=1))
    with patch.object(client, "_post", return_value={"places": []}) as post:
        client.search("a")
        with pytest.raises(BudgetExceeded):
            client.search("b")
    assert post.call_count == 1  # the second call never reached the network


def test_search_parses_places_and_sends_field_mask() -> None:
    client = PlacesClient("k", CallBudget("places", limit=5))
    raw = {
        "places": [
            {
                "id": "abc",
                "displayName": {"text": "Oriana"},
                "formattedAddress": "1 Main St",
                "websiteUri": "https://o.com",
                "location": {"latitude": 40.7, "longitude": -74.0},
            },
            {"id": "nolocation", "displayName": {"text": "X"}},
        ]
    }
    with patch.object(client._session, "request") as req:
        req.return_value.status_code = 200
        req.return_value.json.return_value = raw
        out = client.search("Oriana 1 Main St New York")
    assert out == [make_place(place_id="abc", address="1 Main St")]
    kwargs = req.call_args.kwargs
    assert req.call_args.args[0] == "POST"
    assert "places.websiteUri" in client._session.headers["X-Goog-FieldMask"]
    assert client._session.headers["X-Goog-Api-Key"] == "k"
    assert kwargs["json"]["textQuery"] == "Oriana 1 Main St New York"


def test_attach_websites_only_priority_and_returns_new_objects() -> None:
    a = make_venue("v:a", name="Oriana")
    b = make_venue("v:b", name="Oriana")
    client = PlacesClient("k", CallBudget("places", limit=5))
    with patch.object(client, "search", return_value=[make_place()]) as search:
        out = attach_websites([a, b], client, ["v:a"])
    assert search.call_count == 1
    assert out[0].website == "https://o.com" and a.website is None
    assert out[1] is b


def test_attach_websites_no_match_leaves_venue_and_stops_at_budget() -> None:
    vs = [make_venue(f"v:{i}", name="Oriana") for i in range(3)]
    client = PlacesClient("k", CallBudget("places", limit=2))
    with patch.object(client, "_post", return_value={"places": []}) as post:
        out = attach_websites(vs, client, [v.venue_id for v in vs])
    assert post.call_count == 2  # hard stop: third lookup never made
    assert all(v.website is None for v in out) and len(out) == 3


def test_websites_command_fails_fast_without_key(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(["websites", "--provider", "places"])
    assert "GOOGLE_PLACES_API_KEY" in str(exc.value)


def test_websites_command_uses_the_configured_match_thresholds(monkeypatch, tmp_path) -> None:
    """M2: the Places acceptance thresholds come from config, not module constants."""
    from scripts.hospitality.config import load_config
    from scripts.hospitality.store import DocStore
    from tests.hospitality.factories import make_estimate

    seed = tmp_path / "seed.yaml"
    seed.write_text("customers: []\ndismissed_embeds: []\n")
    monkeypatch.setattr(cli, "SEED_PATH", seed)
    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    store.save("venues", [make_venue("v:1", name="Oriana")], key=lambda v: v.venue_id)
    store.save("estimates", [make_estimate("v:1")], key=lambda e: e.venue_id)
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "k")
    cfg = load_config().model_copy(update={"website_match_max_distance_m": 5000.0})
    monkeypatch.setattr(cli, "load_config", lambda: cfg)

    def far_place(self, text_query):  # type: ignore[no-untyped-def]
        self.budget.spend()
        return [make_place(lat=40.71)]  # ~1.1 km away: rejected at the 75 m default

    monkeypatch.setattr(cli.PlacesClient, "search", far_place)
    assert cli.websites(provider="places")["websites_found"] == 1
