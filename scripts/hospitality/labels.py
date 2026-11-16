"""Customer labels: which groups already run Loyalist (public seed list + detected embeds).

Every consumer (scoring, contacts, drafts, Clay, events, lookalikes, report) asks
`current_customers`, which decides at the point of use from durable evidence: the seed YAML
plus every embed observation ever stored. Neither the latest crawl alone, the order commands ran
in, nor a stored `is_customer` flag can turn a customer back into a cold prospect.
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path

import yaml

from scripts.hospitality.models import (
    CustomerLabel,
    Group,
    ScoredAccount,
    StackObservation,
    Venue,
)
from scripts.hospitality.resolve.normalize import (
    name_prefix_match,
    registrable_domain,
    strict_name_match,
)
from scripts.hospitality.stack.signals import loyalist_venues
from scripts.hospitality.store import DocStore


def _read_seed(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict) or not isinstance(raw.get("customers"), list):
        raise ValueError(f"{path}: expected a top-level 'customers' list")  # noqa: TRY004
    return raw


def load_seed_labels(path: Path) -> list[CustomerLabel]:
    """Read the public customer list; each entry becomes a `public_list` label."""
    entries: list[dict[str, object]] = _read_seed(path)["customers"]  # type: ignore[assignment]
    return [CustomerLabel(**{**entry, "source": "public_list"}) for entry in entries]  # type: ignore[arg-type]


def load_dismissed_embeds(path: Path) -> frozenset[str]:
    """Venue ids whose detected embed a human reviewed and rejected (`dismissed_embeds`)."""
    raw = _read_seed(path).get("dismissed_embeds") or []
    if not isinstance(raw, list):
        raise ValueError(f"{path}: 'dismissed_embeds' must be a list")  # noqa: TRY004
    return frozenset(str(e["venue_id"] if isinstance(e, dict) else e) for e in raw)


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
                venue_id=venue_id,
            )
        )
    return out


def embed_first_seen(observations: Sequence[StackObservation]) -> dict[str, date]:
    """venue_id → the date a Loyalist embed was first observed there."""
    out: dict[str, date] = {}
    for o in sorted(observations, key=lambda o: o.observed_at):
        if "loyalist" in o.platforms:
            out.setdefault(o.venue_id, o.observed_at.date())
    return out


def customer_evidence(
    seed_path: Path,
    venues: Sequence[Venue],
    observations: Sequence[StackObservation],
    stored: Sequence[CustomerLabel] = (),
) -> list[CustomerLabel]:
    """Seed labels + an embed label per venue ever observed with Loyalist + stored embed labels.

    Embed evidence is sticky: a later crawl that misses the embed (Firecrawl budget spent, a
    JS-only widget) never removes it, and a stored embed label outlives its observation rows.
    Only a human removes one, via `dismissed_embeds` in the seed. Seed labels come from the YAML
    alone (stored copies are ignored), so deleting a wrong seed entry takes effect at once.
    """
    dismissed = load_dismissed_embeds(seed_path)
    embeds = {v: e for v, e in loyalist_venues(observations).items() if v not in dismissed}
    labels = [
        *load_seed_labels(seed_path),
        *labels_from_embeds(embeds, venues, embed_first_seen(observations)),
        *(s for s in stored if s.source == "embed" and s.venue_id not in dismissed),
    ]
    return list(dict.fromkeys(labels))  # stored copies of the same label collapse


def current_customers(
    store: DocStore,
    seed_path: Path,
    *,
    venues: Sequence[Venue] | None = None,
    groups: Sequence[Group] | None = None,
    observations: Sequence[StackObservation] | None = None,
) -> dict[str, CustomerLabel]:
    """THE customer gate: group_id → label, from durable evidence, computed now.

    Pass `venues` / `groups` / `observations` only to reuse what the caller already loaded (or
    an as-of view); omitted ones are read from the store in full.
    """
    venues = store.load("venues", Venue) if venues is None else venues
    groups = store.load("groups", Group) if groups is None else groups
    if observations is None:
        observations = store.load("stack_observations", StackObservation)
    stored = store.load("customer_labels", CustomerLabel)
    evidence = customer_evidence(seed_path, venues, observations, stored)
    return customer_groups(evidence, venues, groups)


def with_customer_flags(
    accounts: Sequence[ScoredAccount], customers: dict[str, CustomerLabel]
) -> list[ScoredAccount]:
    """Accounts with `is_customer` recomputed from `customers` (a stored flag can be stale)."""
    return [
        a
        if a.is_customer == (a.group_id in customers)
        else a.model_copy(update={"is_customer": a.group_id in customers})
        for a in accounts
    ]


def _rank(label: CustomerLabel) -> tuple[int, date, int]:
    # Dated labels beat undated; earliest date first; the public list beats an embed on a tie.
    return (
        label.first_public_date is None,
        label.first_public_date or date.max,
        label.source != "public_list",
    )


def _segments(name: str) -> list[str]:
    """A name plus each part of a "/"-separated trade-name list ("A / B" is two venues)."""
    parts = [p.strip() for p in name.split("/")]
    return [name, *(p for p in parts if p and len(parts) > 1)]


def matches_seed_name(pattern: str, name: str) -> bool:
    """Strict seed-name match on `name` or any "/" part; a trailing "*" is a brand prefix."""
    if pattern.endswith("*"):
        return any(name_prefix_match(pattern[:-1], seg) for seg in _segments(name))
    return any(strict_name_match(pattern, seg) for seg in _segments(name))


def _name_matches(label: CustomerLabel, name: str) -> bool:
    # Strict on purpose: a lenient match labels a namesake as a customer and drops a prospect.
    return any(matches_seed_name(p, name) for p in (label.name, *label.venue_names))


def _label_domains(label: CustomerLabel) -> frozenset[str]:
    raw = (label.website_domain, *label.venue_domains)
    return frozenset(d for r in raw if r and (d := registrable_domain(r)))


def _venue_matches(label: CustomerLabel, venue: Venue) -> bool:
    """Domain first; the label's own name only when no domain contradicts it.

    A venue a human listed in the seed (`venue_names`) matches by name even when its website
    domain is not one the seed records: that list names the customer's other venues, whose sites
    the research often did not capture (La Tête d'Or under Dinex's danielnyc.com).
    """
    venue_domain = registrable_domain(venue.website) if venue.website else None
    domains = _label_domains(label)
    if venue_domain and venue_domain in domains:
        return True
    if any(matches_seed_name(p, venue.name) for p in label.venue_names):
        return True
    if domains and venue_domain:
        return False  # a contradicting domain beats a namesake of the label's own name
    return matches_seed_name(label.name, venue.name)


def customer_groups(
    labels: Sequence[CustomerLabel], venues: Sequence[Venue], groups: Sequence[Group]
) -> dict[str, CustomerLabel]:
    """group_id → earliest-dated label. Matches by domain first, then strict name."""
    domains_by_group: dict[str, set[str]] = {}
    for v in venues:
        if v.website and (d := registrable_domain(v.website)):
            domains_by_group.setdefault(v.group_id, set()).add(d)
    group_of = {v.venue_id: v.group_id for v in venues}
    found: dict[str, list[CustomerLabel]] = {}
    for label in labels:
        hits = {v.group_id for v in venues if _venue_matches(label, v)}
        if label.venue_id in group_of:  # an embed seen on this very venue: its group, whatever
            hits.add(group_of[label.venue_id])  # the venue's name or website is now
        for g in groups:
            # A group's own name counts only if its venues don't contradict the label's domain.
            known = domains_by_group.get(g.group_id)
            blocked = bool(_label_domains(label) and known)
            if not blocked and _name_matches(label, g.name):
                hits.add(g.group_id)
        for group_id in hits:
            found.setdefault(group_id, []).append(label)
    return {gid: min(ls, key=_rank) for gid, ls in found.items()}


def is_customer(group_id: str, customers: dict[str, CustomerLabel]) -> bool:
    return group_id in customers


def cold_prospects(group_ids: Sequence[str], customers: dict[str, CustomerLabel]) -> list[str]:
    """Drop customer groups; what remains may be prospected."""
    return [g for g in group_ids if g not in customers]
