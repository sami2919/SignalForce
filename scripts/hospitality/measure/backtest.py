"""Honest backtests against known customers. Both are indicative, never a lift claim.

Case replay asks, for the few customers with a known new venue, whether an opening signal
existed before they were seen live. A case whose anchor is unknown, or whose venue appears only
after the anchor, is reported as not evaluable rather than as a miss. Fit AUC asks only whether static fit
separates customers from everyone else; it says nothing about timing.
"""

import math
from collections.abc import Callable, Sequence
from datetime import date

from scripts.hospitality.labels import matches_seed_name
from scripts.hospitality.measure.recall import OPENING_SIGNAL_TYPES
from scripts.hospitality.models import (
    CaseReplay,
    CustomerLabel,
    LicenseRecord,
    ScoredAccount,
    Signal,
    Venue,
)


def auc(pos: Sequence[float], neg: Sequence[float]) -> float:
    """Mann-Whitney AUC: P(pos > neg), ties count 0.5. NaN when either side is empty."""
    if not pos or not neg:
        return math.nan
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def find_venue(name: str, group_ids: Sequence[str], venues: Sequence[Venue]) -> Venue | None:
    """A venue whose name (or a "/" part of it) strictly matches `name`; a token subset never
    matches. The customer's own groups are searched first, then the universe; smallest id wins.
    """
    own = set(group_ids)
    for pool in ([v for v in venues if v.group_id in own], venues):
        hits = sorted(
            (v for v in pool if matches_seed_name(name, v.name)), key=lambda v: v.venue_id
        )
        if hits:
            return hits[0]
    return None


def earliest_record(venue: Venue, licenses: dict[str, LicenseRecord]) -> date | None:
    """The first date the venue appears in public data: a license filed or issued, or its
    first inspection."""
    days = [venue.first_inspection_date] + [
        d
        for lid in venue.license_ids
        if (lic := licenses.get(lid)) is not None
        for d in (lic.received_date, lic.original_issue_date)
    ]
    known = [d for d in days if d is not None]
    return min(known) if known else None


def case_anchor(
    customer: CustomerLabel,
    venue: Venue,
    seeds: Sequence[CustomerLabel],
    licenses: dict[str, LicenseRecord],
) -> tuple[date | None, str | None, str]:
    """(anchor, basis, reason-if-not-evaluable) for one case.

    - The venue has its own seed entry: its own date is the anchor (the venue's go-live);
      undated means not evaluable.
    - Otherwise the case asks whether the opening preceded the customer's purchase, so the
      customer's date is the anchor, but only for a venue that already appears in public data
      by then. A venue first seen after the customer's date cannot have preceded the purchase,
      so "no prior signal" would be guaranteed: not evaluable, never a miss (I6).
    """
    own = [s for s in seeds if s.name != customer.name and matches_seed_name(s.name, venue.name)]
    if own:
        when = own[0].first_public_date
        if when is None:
            return None, None, "undated: the venue's own seed entry has no public date"
        return when, "venue", ""
    if customer.first_public_date is None:
        return None, None, "undated: the customer has no public date"
    anchor = customer.first_public_date
    first = earliest_record(venue, licenses)
    if first is not None and first > anchor:
        return (
            anchor,
            "customer",
            (
                f"venue first appears in public data on {first}, after the customer's date "
                f"{anchor}, so it cannot have preceded the purchase"
            ),
        )
    return anchor, "customer", ""


def case_replay(
    labels: dict[str, CustomerLabel],
    venues: Sequence[Venue],
    signals_for: Callable[[Venue, date], Sequence[Signal]],
    hints: dict[str, str],
    *,
    seeds: Sequence[CustomerLabel],
    licenses: Sequence[LicenseRecord],
) -> list[CaseReplay]:
    """One case per hinted customer (customer name -> its new venue's name).

    `labels` is the customer gate (group id -> label); `signals_for(venue, anchor)` returns the
    as-of signals for a venue. Every hinted customer that is a current customer yields a case;
    a case that cannot be evaluated says why instead of reading as a miss. Lead is the anchor
    minus the earliest opening-family signal observed on or before it.
    """
    by_lic = {lic.record_id: lic for lic in licenses}
    out: list[CaseReplay] = []
    for customer_name, venue_name in hints.items():
        gids = sorted(g for g, lab in labels.items() if lab.name == customer_name)
        if not gids:
            continue
        label = labels[gids[0]]
        venue = find_venue(venue_name, gids, venues)
        base = {"customer": customer_name, "first_signal_date": None, "lead_days": None}
        if venue is None:
            out.append(
                CaseReplay(
                    **base,  # type: ignore[arg-type]
                    group_id=gids[0],
                    anchor_date=label.first_public_date,
                    new_venue_id=None,
                    signal_types=(),
                    status="not_evaluable",
                    reason=f"venue {venue_name!r} not found in the data",
                )
            )
            continue
        group_id = venue.group_id if venue.group_id in gids else gids[0]
        anchor, basis, reason = case_anchor(label, venue, seeds, by_lic)
        if anchor is None or reason:
            out.append(
                CaseReplay(
                    **base,  # type: ignore[arg-type]
                    group_id=group_id,
                    anchor_date=anchor,
                    new_venue_id=venue.venue_id,
                    signal_types=(),
                    status="not_evaluable",
                    anchor_basis=basis,  # type: ignore[arg-type]
                    reason=reason,
                )
            )
            continue
        dated = sorted(
            (s.observed_at.date(), s.signal_type)
            for s in signals_for(venue, anchor)
            if s.entity_id == venue.venue_id
            and s.signal_type in OPENING_SIGNAL_TYPES
            and s.observed_at.date() <= anchor
        )
        first = dated[0][0] if dated else None
        out.append(
            CaseReplay(
                group_id=group_id,
                customer=customer_name,
                anchor_date=anchor,
                new_venue_id=venue.venue_id,
                first_signal_date=first,
                lead_days=(anchor - first).days if first else None,
                signal_types=tuple(dict.fromkeys(t for _, t in dated)),
                status="replayed",
                anchor_basis=basis,  # type: ignore[arg-type]
            )
        )
    return out


def fit_auc(accounts: Sequence[ScoredAccount]) -> float:
    """AUC of static `fit`: customer groups vs all other scored groups."""
    pos = [a.fit for a in accounts if a.is_customer]
    neg = [a.fit for a in accounts if not a.is_customer]
    return auc(pos, neg)
