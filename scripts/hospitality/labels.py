"""Customer labels: which groups already run Loyalist (public seed list + detected embeds).

Downstream steps (scoring, drafts, events) must ask `is_customer` / `cold_prospects` so a
customer is never treated as a cold prospect.
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path

import yaml

from scripts.hospitality.models import CustomerLabel, Group, Venue
from scripts.hospitality.resolve.normalize import name_similarity, registrable_domain

NAME_THRESHOLD = 0.9  # strict: a lenient match would label a namesake as a customer


def load_seed_labels(path: Path) -> list[CustomerLabel]:
    """Read the public customer list; each entry becomes a `public_list` label."""
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    entries = raw.get("customers") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise ValueError(  # noqa: TRY004
            f"{path}: expected a top-level 'customers' list"
        )
    return [CustomerLabel(**{**entry, "source": "public_list"}) for entry in entries]


def labels_from_embeds(
    embeds: dict[str, str], venues: Sequence[Venue], first_seen: dict[str, date]
) -> list[CustomerLabel]:
    """One `embed` label per venue with a detected Loyalist embed (venue_id → evidence)."""
    by_id = {v.venue_id: v for v in venues}
    out: list[CustomerLabel] = []
    for venue_id, evidence in sorted(embeds.items()):
        venue = by_id.get(venue_id)
        if venue is None:
            continue
        out.append(
            CustomerLabel(
                name=venue.name,
                website_domain=registrable_domain(venue.website) if venue.website else None,
                first_public_date=first_seen.get(venue_id),
                source="embed",
                evidence_ref=evidence,
            )
        )
    return out


def _rank(label: CustomerLabel) -> tuple[int, date, int]:
    # Dated labels beat undated; earliest date first; the public list beats an embed on a tie.
    return (
        label.first_public_date is None,
        label.first_public_date or date.max,
        label.source != "public_list",
    )


def _venue_matches(label: CustomerLabel, venue: Venue) -> bool:
    venue_domain = registrable_domain(venue.website) if venue.website else None
    if label.website_domain and venue_domain:
        return venue_domain == registrable_domain(label.website_domain)  # exact; names ignored
    return name_similarity(label.name, venue.name) >= NAME_THRESHOLD


def customer_groups(
    labels: Sequence[CustomerLabel], venues: Sequence[Venue], groups: Sequence[Group]
) -> dict[str, CustomerLabel]:
    """group_id → earliest-dated label. Matches by domain first, then strict name."""
    domains_by_group: dict[str, set[str]] = {}
    for v in venues:
        if v.website and (d := registrable_domain(v.website)):
            domains_by_group.setdefault(v.group_id, set()).add(d)
    found: dict[str, list[CustomerLabel]] = {}
    for label in labels:
        hits = {v.group_id for v in venues if _venue_matches(label, v)}
        for g in groups:
            # A group's own name counts only if its venues don't contradict the label's domain.
            known = domains_by_group.get(g.group_id)
            blocked = bool(label.website_domain and known)
            if not blocked and name_similarity(label.name, g.name) >= NAME_THRESHOLD:
                hits.add(g.group_id)
        for group_id in hits:
            found.setdefault(group_id, []).append(label)
    return {gid: min(ls, key=_rank) for gid, ls in found.items()}


def is_customer(group_id: str, customers: dict[str, CustomerLabel]) -> bool:
    return group_id in customers


def cold_prospects(group_ids: Sequence[str], customers: dict[str, CustomerLabel]) -> list[str]:
    """Drop customer groups; what remains may be prospected."""
    return [g for g in group_ids if g not in customers]
