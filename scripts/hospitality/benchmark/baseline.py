"""Plain-Claude baseline: web-search for upcoming NYC openings, then structure the answer."""

import logging
import re
from collections.abc import Sequence
from datetime import date
from typing import Any

from anthropic import Anthropic
from pydantic import BaseModel, ConfigDict

from scripts.hospitality import llm
from scripts.hospitality.config import load_config
from scripts.hospitality.labels import matches_seed_name
from scripts.hospitality.models import BaselineItem, BaselineRun, Venue

logger = logging.getLogger(__name__)

BASELINE_PROMPT = (
    "Today is {cutoff}. List as many New York City full-service restaurants, bars or "
    "hospitality venues as you can that are expected to open in the next 8 weeks, especially "
    "new locations from existing restaurant groups. For each give the venue name, "
    "neighborhood or address, the group that owns it if known, and the expected opening "
    "timing. Use web search."
)
WEB_SEARCH_TOOL_TYPE = "web_search_20260209"

_STRUCTURE_SYSTEM = (
    "Extract the venues listed in the text into structured items. Copy only venues that the "
    "text names; never add, infer or invent a venue. Use an empty string for an unknown "
    "location and null for an unknown group or opening timing."
)
_ZIP = re.compile(r"\b(1[0-1]\d{3})\b")
_BOROUGH_WORDS: dict[str, str] = {
    "manhattan": "manhattan",
    "new york city": "manhattan",
    "brooklyn": "brooklyn",
    "queens": "queens",
    "bronx": "bronx",
    "staten island": "staten island",
}
_ZIP_BOROUGH_PREFIX: tuple[tuple[tuple[str, ...], str], ...] = (
    (("100", "101", "102"), "manhattan"),
    (("103",), "staten island"),
    (("104",), "bronx"),
    (("112",), "brooklyn"),
    (("110", "111", "113", "114", "116"), "queens"),
)


class BaselineList(BaseModel):
    """Structured-output wrapper for the second step."""

    model_config = ConfigDict(frozen=True)

    items: tuple[BaselineItem, ...]


def _text(response: Any) -> str:
    return "\n".join(
        b.text for b in response.content if getattr(b, "type", None) == "text" and b.text
    )


def _searches(response: Any) -> int:
    tool_use = getattr(getattr(response, "usage", None), "server_tool_use", None)
    return int(getattr(tool_use, "web_search_requests", 0) or 0)


def _search_once(client: Anthropic, cutoff: date, max_searches: int) -> tuple[str, int]:
    """Step 1: search and write the list. Continues `pause_turn`, never past `max_searches`."""
    cfg = load_config()
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": BASELINE_PROMPT.format(cutoff=cutoff.isoformat())}
    ]
    texts: list[str] = []
    used = 0
    while True:
        llm.spend_call()  # shared hard budget: stops the run, never just warns
        response = client.messages.create(
            model=cfg.models["baseline"],
            max_tokens=16000,
            tools=[
                {
                    "type": WEB_SEARCH_TOOL_TYPE,
                    "name": "web_search",
                    "max_uses": max_searches - used,
                }
            ],
            messages=messages,
        )
        used += _searches(response)
        texts.append(_text(response))
        if response.stop_reason != "pause_turn" or used >= max_searches:
            return "\n\n".join(t for t in texts if t), used
        messages.append({"role": "assistant", "content": response.content})


def run_baseline(
    client: Anthropic, cutoff: date, runs: int = 3, max_searches: int = 20
) -> list[BaselineRun]:
    """Run plain Claude + web search `runs` times (two steps each) to expose variance."""
    out: list[BaselineRun] = []
    for index in range(runs):
        text, used = _search_once(client, cutoff, max_searches)
        parsed = llm.structured(
            BaselineList, system=_STRUCTURE_SYSTEM, user=text, role="baseline", client=client
        )
        out.append(BaselineRun(run_index=index, items=parsed.items, searches_used=used))
    return out


def _borough_of_zip(zip_code: str) -> str | None:
    for prefixes, borough in _ZIP_BOROUGH_PREFIX:
        if zip_code.startswith(prefixes):
            return borough
    return None


def _location_agrees(location: str, venue: Venue) -> bool:
    """A ZIP in the location must equal the venue's; else a borough must match its ZIP's.

    A location with neither (a bare neighborhood) cannot be checked and does not block.
    """
    zips = _ZIP.findall(location)
    if zips:
        return venue.zip_code in zips
    lowered = location.lower()
    boroughs = {b for word, b in _BOROUGH_WORDS.items() if word in lowered}
    if boroughs:
        return _borough_of_zip(venue.zip_code) in boroughs
    return True


def match_items(
    items: Sequence[BaselineItem], universe: Sequence[Venue]
) -> dict[int, frozenset[str]]:
    """Item index -> every venue_id the item strictly names (location agreeing), else empty.

    Deterministic: this is what catches venues the model invented. The match is the same strict
    near-exact name rule as the customer gate (`matches_seed_name`: a token subset such as
    "Lola" for "LOLA TAQUERIA" never matches; a "/" part of a trade name does). All tied
    candidates are returned, so a namesake with an older id cannot hide a true hit.
    """
    out: dict[int, frozenset[str]] = {}
    for i, it in enumerate(items):
        out[i] = frozenset(
            v.venue_id
            for v in universe
            if it.name.strip()
            and matches_seed_name(it.name, v.name)
            and (not it.location or _location_agrees(it.location, v))
        )
    return out
