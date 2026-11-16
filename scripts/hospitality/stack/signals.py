"""Turn stack observations into signals, disqualifiers and Loyalist-customer evidence."""

from collections.abc import Sequence
from datetime import datetime

from scripts.hospitality.models import Signal, StackObservation, Venue
from scripts.hospitality.stack.fingerprints import EVENTS, QSR_LOYALTY, RESERVATION

SOURCE = "stack_crawl"


def _latest(observations: Sequence[StackObservation]) -> dict[str, StackObservation]:
    out: dict[str, StackObservation] = {}
    for o in sorted(observations, key=lambda o: o.observed_at):
        out[o.venue_id] = o
    return out


def _signal(
    signal_type: str, entity_id: str, now: datetime, evidence_ref: str, detail: str
) -> Signal:
    return Signal(
        signal_id=f"{signal_type}:{entity_id}:{now.date()}",
        signal_type=signal_type,  # type: ignore[arg-type]
        entity_id=entity_id,
        observed_at=now,
        occurred_at=None,
        source=SOURCE,
        evidence_ref=evidence_ref,
        detail=detail,
    )


def _reservation(obs: StackObservation) -> frozenset[str]:
    return RESERVATION & set(obs.platforms)


def _label(platforms: frozenset[str]) -> str:
    return "+".join(sorted(platforms)) or "none"


def stack_signals(
    observations: Sequence[StackObservation],
    venues: Sequence[Venue],
    previous: Sequence[StackObservation],
    now: datetime,
) -> list[Signal]:
    latest = _latest(observations)
    before = _latest(previous)
    group_of = {v.venue_id: v.group_id for v in venues}
    signals: list[Signal] = []

    by_group: dict[str, list[StackObservation]] = {}
    for venue_id, obs in latest.items():
        if venue_id in group_of:
            by_group.setdefault(group_of[venue_id], []).append(obs)
    for group_id, group_obs in sorted(by_group.items()):
        platforms = frozenset().union(*(_reservation(o) for o in group_obs))
        if len(platforms) >= 2:
            signals.append(
                _signal(
                    "stack_fragmented",
                    group_id,
                    now,
                    " ".join(sorted(o.url for o in group_obs)),
                    _label(platforms),
                )
            )

    for venue_id, obs in sorted(latest.items()):
        have = set(obs.platforms)
        if {"tripleseat", "resy"} <= have:
            signals.append(_signal("tripleseat_resy", venue_id, now, obs.url, "tripleseat+resy"))
        if EVENTS & have:
            signals.append(_signal("private_events", venue_id, now, obs.url, _label(EVENTS & have)))
        prev = before.get(venue_id)
        if prev is not None and _reservation(prev) != _reservation(obs):
            detail = f"{_label(_reservation(prev))}→{_label(_reservation(obs))}"
            signals.append(_signal("platform_switch", venue_id, now, obs.url, detail))
    return signals


def disqualified_venues(observations: Sequence[StackObservation]) -> dict[str, str]:
    """venue_id → reason for venues running a QSR loyalty platform."""
    out: dict[str, str] = {}
    for venue_id, obs in _latest(observations).items():
        hit = sorted(QSR_LOYALTY & set(obs.platforms))
        if hit:
            out[venue_id] = f"qsr_loyalty:{hit[0]}"
    return out


def loyalist_venues(observations: Sequence[StackObservation]) -> dict[str, str]:
    """venue_id → embed evidence (earliest sighting) for venues EVER observed running Loyalist.

    Sticky on purpose: a later observation without the embed (Firecrawl budget spent, so only
    the plain fetcher ran and a JS-injected widget went unseen) is not proof it was removed, and
    unlabelling would turn a customer into a cold prospect. See `lapsed_loyalist_venues`.
    """
    out: dict[str, str] = {}
    for obs in sorted(observations, key=lambda o: o.observed_at):
        if "loyalist" in obs.platforms and obs.venue_id not in out:
            out[obs.venue_id] = obs.evidence[obs.platforms.index("loyalist")]
    return out


def lapsed_loyalist_venues(observations: Sequence[StackObservation]) -> list[str]:
    """Venues once seen with Loyalist whose latest observation lacks it: review for churn."""
    ever = loyalist_venues(observations)
    latest = _latest(observations)
    return sorted(v for v in ever if "loyalist" not in latest[v].platforms)
