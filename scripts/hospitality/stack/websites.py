"""Website lookup for prioritized venues via Google Places (New) Text Search.

Billing (verify before a live run; pricing changes): requesting `places.websiteUri` moves a
Text Search call from the Pro SKU to the Enterprise SKU, which bills at a higher rate and has
its own monthly free allowance (about 1,000 calls/month when last checked, from memory, not
re-verified in this offline environment). One search = one billable call, so `CallBudget`
counts calls 1:1 and `budgets.places` in the config should stay at or below the free allowance
unless you intend to pay.
"""

import logging
from collections.abc import Sequence

from scripts.api_client import BaseAPIClient
from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.models import PlaceMatch, Venue
from scripts.hospitality.resolve.normalize import haversine_m, name_similarity

logger = logging.getLogger(__name__)

SEARCH_ENDPOINT = "v1/places:searchText"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.websiteUri,places.location"
)
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


def pick_place(venue: Venue, candidates: Sequence[PlaceMatch]) -> PlaceMatch | None:
    """Nearest candidate within 75 m with name similarity >= 0.6, else None."""
    if venue.lat is None or venue.lon is None:
        return None
    best: tuple[float, PlaceMatch] | None = None
    for c in candidates:
        dist = haversine_m(venue.lat, venue.lon, c.lat, c.lon)
        if (
            dist > MAX_DISTANCE_M
            or name_similarity(venue.name, c.display_name) < MIN_NAME_SIMILARITY
        ):
            continue
        if best is None or dist < best[0]:
            best = (dist, c)
    return best[1] if best else None


def attach_websites(
    venues: Sequence[Venue], client: PlacesClient, priority_ids: Sequence[str]
) -> list[Venue]:
    """Return venues with `website` set for matched priority venues; others unchanged.

    Stops looking up (leaving remaining venues unchanged) once the budget is spent.
    """
    priority = set(priority_ids)
    out: list[Venue] = []
    exhausted = False
    for v in venues:
        if v.venue_id not in priority or exhausted:
            out.append(v)
            continue
        try:
            candidates = client.search(f"{v.name} {v.address} New York")
        except BudgetExceeded as exc:
            logger.warning("Stopping website lookups: %s", exc)
            exhausted = True
            out.append(v)
            continue
        match = pick_place(v, candidates)
        if match and match.website:
            out.append(v.model_copy(update={"website": match.website}))
        else:
            out.append(v)
    return out
