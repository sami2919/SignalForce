"""Honest backtests against known customers. Both are indicative, never a lift claim.

Case replay asks, for the few customers whose public date and new venue are known, whether an
opening signal existed before they were seen live. Fit AUC asks only whether static fit
separates customers from everyone else; it says nothing about timing.
"""

import math
from collections.abc import Sequence
from datetime import date

from scripts.hospitality.measure.recall import OPENING_SIGNAL_TYPES
from scripts.hospitality.models import CaseReplay, CustomerLabel, ScoredAccount, Signal, Venue
from scripts.hospitality.resolve.normalize import name_similarity

VENUE_NAME_THRESHOLD = 0.85


def auc(pos: Sequence[float], neg: Sequence[float]) -> float:
    """Mann-Whitney AUC: P(pos > neg), ties count 0.5. NaN when either side is empty."""
    if not pos or not neg:
        return math.nan
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def find_venue(name: str, group_id: str, venues: Sequence[Venue]) -> Venue | None:
    """Best name match >= threshold, preferring the group's own venues over the universe."""
    for pool in ([v for v in venues if v.group_id == group_id], venues):
        scored = [(name_similarity(name, v.name), v) for v in pool]
        scored = [(s, v) for s, v in scored if s >= VENUE_NAME_THRESHOLD]
        if scored:
            return max(scored, key=lambda t: t[0])[1]
    return None


def case_replay(
    labels: dict[str, CustomerLabel],
    venues: Sequence[Venue],
    signals: Sequence[Signal],
    new_venue_hints: dict[str, str],
) -> list[CaseReplay]:
    """One replay per hinted customer group with a dated label.

    Undated labels are skipped (no anchor, and none is invented). Lead is the anchor minus the
    earliest opening-family signal on the new venue observed on or before the anchor.
    """
    out: list[CaseReplay] = []
    for group_id, venue_name in new_venue_hints.items():
        label = labels.get(group_id)
        if label is None or label.first_public_date is None:
            continue
        anchor = label.first_public_date
        venue = find_venue(venue_name, group_id, venues)
        dated: list[tuple[date, str]] = []
        if venue is not None:
            dated = sorted(
                (s.observed_at.date(), s.signal_type)
                for s in signals
                if s.entity_id == venue.venue_id
                and s.signal_type in OPENING_SIGNAL_TYPES
                and s.observed_at.date() <= anchor
            )
        first = dated[0][0] if dated else None
        out.append(
            CaseReplay(
                group_id=group_id,
                customer=label.name,
                anchor_date=anchor,
                new_venue_id=venue.venue_id if venue else None,
                first_signal_date=first,
                lead_days=(anchor - first).days if first else None,
                signal_types=tuple(dict.fromkeys(t for _, t in dated)),
            )
        )
    return out


def fit_auc(accounts: Sequence[ScoredAccount]) -> float:
    """AUC of static `fit`: customer groups vs all other scored groups."""
    pos = [a.fit for a in accounts if a.is_customer]
    neg = [a.fit for a in accounts if not a.is_customer]
    return auc(pos, neg)
