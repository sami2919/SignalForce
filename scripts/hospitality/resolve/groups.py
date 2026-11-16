"""Deterministic group formation and evidence-driven group merging (union-find)."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence

from scripts.hospitality.models import (
    Group,
    GroupEvidence,
    GroupResolution,
    LicenseRecord,
    Venue,
)
from scripts.hospitality.resolve.normalize import normalize_name, registrable_domain

logger = logging.getLogger(__name__)

# A legal name made only of these words says nothing about common ownership.
GENERIC_LEGAL_NAME_WORDS = frozenset({"restaurant", "hospitality", "management"})

# Strongest first.
RESOLUTION_ORDER: tuple[GroupResolution, ...] = (
    "manual",
    "website_locations",
    "press",
    "shared_domain",
    "shared_legal_name",
    "agent",
    "singleton",
)
_RANK = {r: i for i, r in enumerate(RESOLUTION_ORDER)}


class _UnionFind:
    def __init__(self, items: Sequence[str]) -> None:
        self._parent = {i: i for i in items}

    def find(self, x: str) -> str:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)

    def components(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for item in self._parent:
            out[self.find(item)].append(item)
        return out


def _group_id(venue_ids: Sequence[str]) -> str:
    return "g:" + min(venue_ids)


def _is_generic(normalized: str) -> bool:
    words = normalized.split()
    return not words or all(w in GENERIC_LEGAL_NAME_WORDS for w in words)


def _apply(venues: Sequence[Venue], groups: Sequence[Group]) -> tuple[list[Venue], list[Group]]:
    group_of = {vid: g.group_id for g in groups for vid in g.venue_ids}
    new_venues = [
        v.model_copy(update={"group_id": group_of.get(v.venue_id, v.group_id)}) for v in venues
    ]
    return new_venues, list(groups)


def form_groups(
    venues: Sequence[Venue], licenses: Sequence[LicenseRecord]
) -> tuple[list[Venue], list[Group]]:
    """Group-of-one by default; merge on identical normalized legal name or shared domain."""
    legal_by_license = {lic.record_id: lic.legal_name for lic in licenses}
    ids = [v.venue_id for v in venues]
    uf = _UnionFind(ids)
    name_keys: dict[str, list[str]] = defaultdict(list)
    domain_keys: dict[str, list[str]] = defaultdict(list)
    display: dict[str, str] = {}
    for v in venues:
        for lid in v.license_ids:
            raw = legal_by_license.get(lid)
            norm = normalize_name(raw) if raw else ""
            if raw and not _is_generic(norm):
                name_keys[norm].append(v.venue_id)
                display.setdefault(norm, raw)
        domain = registrable_domain(v.website) if v.website else None
        if domain:
            domain_keys[domain].append(v.venue_id)

    name_linked: set[str] = set()
    domain_linked: set[str] = set()
    for members in name_keys.values():
        for other in members[1:]:
            uf.union(members[0], other)
        if len(set(members)) > 1:
            name_linked.update(members)
    for members in domain_keys.values():
        for other in members[1:]:
            uf.union(members[0], other)
        if len(set(members)) > 1:
            domain_linked.update(members)

    venue_by_id = {v.venue_id: v for v in venues}
    groups: list[Group] = []
    for members in uf.components().values():
        vids = tuple(sorted(members))
        if len(vids) == 1:
            resolution: GroupResolution = "singleton"
            name = venue_by_id[vids[0]].name
        else:
            in_domain = any(m in domain_linked for m in vids)
            resolution = "shared_domain" if in_domain else "shared_legal_name"
            name = _component_name(vids, venue_by_id, legal_by_license)
        groups.append(
            Group(group_id=_group_id(vids), name=name, venue_ids=vids, resolution=resolution)
        )
    groups.sort(key=lambda g: g.group_id)
    return _apply(venues, groups)


def _component_name(
    vids: Sequence[str], venue_by_id: dict[str, Venue], legal_by_license: dict[str, str]
) -> str:
    for vid in vids:
        for lid in venue_by_id[vid].license_ids:
            if lid in legal_by_license:
                return legal_by_license[lid]
    return venue_by_id[vids[0]].name


def merge_groups(
    venues: Sequence[Venue], groups: Sequence[Group], evidence: Sequence[GroupEvidence]
) -> tuple[list[Venue], list[Group]]:
    """Union groups linked by evidence; the merged group keeps the strongest resolution."""
    known = {v.venue_id for v in venues}
    uf = _UnionFind(sorted(known))
    for g in groups:
        members = [vid for vid in g.venue_ids if vid in known]
        for other in members[1:]:
            uf.union(members[0], other)
    usable: list[GroupEvidence] = []
    for ev in evidence:
        members = [vid for vid in ev.venue_ids if vid in known]
        if len(members) != len(ev.venue_ids):
            logger.warning("evidence %s references unknown venues; ignoring them", ev.evidence_ref)
        if not members:
            continue
        usable.append(ev)
        for other in members[1:]:
            uf.union(members[0], other)

    resolutions: dict[str, list[tuple[int, GroupResolution, str]]] = defaultdict(list)
    for g in groups:
        members = [vid for vid in g.venue_ids if vid in known]
        if members:
            resolutions[uf.find(members[0])].append((_RANK[g.resolution], g.resolution, g.name))
    for ev in usable:
        root = uf.find(next(vid for vid in ev.venue_ids if vid in known))
        resolutions[root].append((_RANK[ev.resolution], ev.resolution, ev.name))

    out: list[Group] = []
    for root, members in uf.components().items():
        vids = tuple(sorted(members))
        options = resolutions.get(root)
        if options:
            _, resolution, name = min(options, key=lambda o: o[0])
        else:
            resolution = "singleton"
            name = next(v.name for v in venues if v.venue_id == vids[0])
        out.append(
            Group(group_id=_group_id(vids), name=name, venue_ids=vids, resolution=resolution)
        )
    out.sort(key=lambda g: g.group_id)
    return _apply(venues, out)
