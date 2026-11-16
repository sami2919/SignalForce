"""Website lookup for prioritized venues via Google Places (New) Text Search.

Billing (verify before a live run; pricing changes): requesting `places.websiteUri` moves a
Text Search call from the Pro SKU to the Enterprise SKU, which bills at a higher rate and has
its own monthly free allowance (about 1,000 calls/month when last checked, from memory, not
re-verified in this offline environment). One search = one billable call, so `CallBudget`
counts calls 1:1 and `budgets.places` in the config should stay at or below the free allowance
unless you intend to pay.
"""

import logging
from collections.abc import Iterator, Sequence
from datetime import date

from scripts.api_client import BaseAPIClient
from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.models import PlaceMatch, Venue, WebsiteLookup
from scripts.hospitality.resolve.normalize import haversine_m, name_similarity

logger = logging.getLogger(__name__)

SEARCH_ENDPOINT = "v1/places:searchText"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.websiteUri,places.location"
)
# Defaults only; the websites command passes cfg.website_match_max_distance_m / _min_name_similarity.
MAX_DISTANCE_M = 75.0
MIN_NAME_SIMILARITY = 0.6


class PlacesClient(BaseAPIClient):
    def __init__(self, api_key: str, budget: CallBudget) -> None:
        super().__init__(
            "https://places.googleapis.com",
            auth_headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": FIELD_MASK},
        )
        self.budget = budget

    def _post(self, body: dict) -> dict:
        return self.post(SEARCH_ENDPOINT, json_data=body)

    def search(self, text_query: str) -> list[PlaceMatch]:
        """Text Search; spends one budget call first and raises BudgetExceeded when spent."""
        self.budget.spend()
        raw = self._post({"textQuery": text_query})
        matches: list[PlaceMatch] = []
        for p in raw.get("places", []):
            loc = p.get("location") or {}
            if "latitude" not in loc or "longitude" not in loc or not p.get("id"):
                logger.warning("Skipping place without id/location: %s", p.get("id"))
                continue
            matches.append(
                PlaceMatch(
                    place_id=p["id"],
                    display_name=(p.get("displayName") or {}).get("text", ""),
                    address=p.get("formattedAddress", ""),
                    website=p.get("websiteUri"),
                    lat=loc["latitude"],
                    lon=loc["longitude"],
                )
            )
        return matches


def pick_place(
    venue: Venue,
    candidates: Sequence[PlaceMatch],
    max_distance_m: float = MAX_DISTANCE_M,
    min_name_similarity: float = MIN_NAME_SIMILARITY,
) -> PlaceMatch | None:
    """Nearest candidate within `max_distance_m` with name similarity >= the minimum, else None."""
    if venue.lat is None or venue.lon is None:
        return None
    best: tuple[float, PlaceMatch] | None = None
    for c in candidates:
        dist = haversine_m(venue.lat, venue.lon, c.lat, c.lon)
        if (
            dist > max_distance_m
            or name_similarity(venue.name, c.display_name) < min_name_similarity
        ):
            continue
        if best is None or dist < best[0]:
            best = (dist, c)
    return best[1] if best else None


def iter_website_lookups(
    venues: Sequence[Venue],
    client: PlacesClient,
    priority_ids: Sequence[str],
    today: date,
    max_distance_m: float = MAX_DISTANCE_M,
    min_name_similarity: float = MIN_NAME_SIMILARITY,
) -> Iterator[WebsiteLookup]:
    """One `WebsiteLookup` (hit or miss) per priority venue looked up, in venue order.

    Stops (yielding nothing more) once the budget is spent. A generator, so a caller can keep
    every paid lookup made before an unexpected error ends the run.
    """
    priority = set(priority_ids)
    for v in venues:
        if v.venue_id not in priority:
            continue
        try:
            candidates = client.search(f"{v.name} {v.address} New York")
        except BudgetExceeded as exc:
            logger.warning("Stopping website lookups: %s", exc)
            return
        match = pick_place(v, candidates, max_distance_m, min_name_similarity)
        yield WebsiteLookup(
            venue_id=v.venue_id, website=match.website if match else None, looked_up_on=today
        )


def attach_websites(
    venues: Sequence[Venue], client: PlacesClient, priority_ids: Sequence[str]
) -> list[Venue]:
    """Return venues with `website` set for matched priority venues; others unchanged.

    Stops looking up (leaving remaining venues unchanged) once the budget is spent.
    """
    found = {
        w.venue_id: w.website
        for w in iter_website_lookups(venues, client, priority_ids, date.today())
        if w.website
    }
    return [
        v.model_copy(update={"website": found[v.venue_id]}) if v.venue_id in found else v
        for v in venues
    ]
