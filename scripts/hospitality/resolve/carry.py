"""Carry durable state across a re-resolve: websites, press venues, moved and merged ids.

`resolve` rebuilds venues from free public data. Everything that is not derivable from that
data (a paid website lookup, a press-only venue, press / job-board group evidence) or that is
keyed to a venue or group id (observations, signals, embed labels, contacts, drafts) is carried
over here, so a re-resolve neither loses nor re-buys it.

Ids:
- A venue id is stable while its source is: `v:<camis>` for a DOHMH site, `v:lic:<record>` for
  a license with no site yet, `v:press:<hash>` for a press-only venue. When a licensed venue
  gets its DOHMH site, `v:lic:<record>` becomes `v:<camis>`; `venue_moves` finds that move and
  every venue-keyed record follows it.
- A group id is `g:<smallest member venue id>`, so it changes when groups merge. Every group id
  ever minted names one of its member venues, so `canonical_group_id` maps any old group id to
  that venue's current group.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date

from scripts.hospitality.models import GroupEvidence, Venue, WebsiteLookup

PRESS_VENUE_PREFIX = "v:press:"


def venue_moves(old: Sequence[Venue], new: Sequence[Venue]) -> dict[str, str]:
    """old venue id -> new venue id, for old venues that no longer exist under their id.

    A venue moves when its DOHMH site (same camis) or one of its licenses now lives under
    another id. Ambiguous moves (licenses split across several new venues) are skipped.
    """
    new_ids = {v.venue_id for v in new}
    by_camis = {v.camis: v.venue_id for v in new if v.camis}
    by_license: dict[str, str] = {}
    for v in new:
        for lid in v.license_ids:
            by_license[lid] = v.venue_id
    moves: dict[str, str] = {}
    for v in old:
        if v.venue_id in new_ids:
            continue
        targets = {by_license[lid] for lid in v.license_ids if lid in by_license}
        if v.camis and v.camis in by_camis:
            targets.add(by_camis[v.camis])
        if len(targets) == 1:
            moves[v.venue_id] = targets.pop()
    return moves


def chain_moves(earlier: Mapping[str, str], latest: Mapping[str, str]) -> dict[str, str]:
    """Compose stored aliases with this run's moves so every old id points at a current id."""
    out = {old: latest.get(new, new) for old, new in earlier.items()}
    out.update(latest)
    return {old: new for old, new in out.items() if old != new}


def carried_press_venues(old: Sequence[Venue], rebuilt_ids: Iterable[str]) -> list[Venue]:
    """Press-only venues from the previous store (not derivable from public data), ungrouped."""
    rebuilt = set(rebuilt_ids)
    return [
        v.model_copy(update={"group_id": f"g:{v.venue_id}"})
        for v in old
        if v.venue_id.startswith(PRESS_VENUE_PREFIX) and v.venue_id not in rebuilt
    ]


def merge_lookups(
    stored: Sequence[WebsiteLookup], old_venues: Sequence[Venue], today: date
) -> list[WebsiteLookup]:
    """Stored lookups plus websites that exist only on old venue rows (pre-`websites`-kind)."""
    by_id = {w.venue_id: w for w in stored}
    for v in old_venues:
        if v.website and (v.venue_id not in by_id or by_id[v.venue_id].website is None):
            by_id[v.venue_id] = WebsiteLookup(
                venue_id=v.venue_id, website=v.website, looked_up_on=today, source="carried"
            )
    return list(by_id.values())


def remap_lookups(
    lookups: Sequence[WebsiteLookup], moves: Mapping[str, str]
) -> list[WebsiteLookup]:
    """Lookups re-keyed to moved venue ids; a hit wins over a miss, then the latest."""
    out: dict[str, WebsiteLookup] = {}
    for w in sorted(lookups, key=lambda w: (w.website is not None, w.looked_up_on)):
        vid = moves.get(w.venue_id, w.venue_id)
        out[vid] = w.model_copy(update={"venue_id": vid})
    return list(out.values())


def apply_websites(venues: Sequence[Venue], lookups: Sequence[WebsiteLookup]) -> list[Venue]:
    """Venues with the website from their lookup (a hit), else unchanged."""
    found = {w.venue_id: w.website for w in lookups if w.website}
    return [
        v.model_copy(update={"website": found[v.venue_id]}) if v.venue_id in found else v
        for v in venues
    ]


def remap_evidence(
    evidence: Sequence[GroupEvidence], moves: Mapping[str, str]
) -> list[GroupEvidence]:
    return [
        e.model_copy(update={"venue_ids": tuple(sorted({moves.get(v, v) for v in e.venue_ids}))})
        for e in evidence
    ]


def canonical_group_id(
    entity_id: str, group_of: Mapping[str, str], moves: Mapping[str, str]
) -> str | None:
    """The current group of a venue id or of any group id ever minted; None if unknown."""
    vid = entity_id.removeprefix("g:")
    vid = moves.get(vid, vid)
    return group_of.get(vid)


def canonical_entity(entity_id: str, group_of: Mapping[str, str], moves: Mapping[str, str]) -> str:
    """A signal's entity after a re-resolve: venue ids follow moves, group ids follow merges."""
    if entity_id.startswith("g:"):
        return canonical_group_id(entity_id, group_of, moves) or entity_id
    return moves.get(entity_id, entity_id)
