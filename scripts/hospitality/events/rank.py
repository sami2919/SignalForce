"""Rank events by expected qualified meetings per dollar and build per-event meeting lists.

Existing Loyalist customers (seed label or detected embed) and disqualified groups are never
targets: they add nothing to an event's expected meetings and are left off every meeting list.
"""

from collections.abc import Sequence

from scripts.hospitality.config import EventsConfig
from scripts.hospitality.models import (
    CustomerLabel,
    Event,
    EventAppearance,
    EventScore,
    MeetingTarget,
    ScoredAccount,
    Venue,
)
from scripts.hospitality.resolve.normalize import name_similarity, strict_name_match


def match_appearance(app: EventAppearance, venues: Sequence[Venue]) -> str | None:
    """group_id of the best strictly matching venue, else None.

    Strict (near-exact on distinctive tokens): the match decides whether the person is a
    known customer (left off) or a cold target, so a subset namesake ("FOOD" for "Major Food
    Group") must never win. Ties go to the higher similarity, then the smaller venue_id.
    """
    best: tuple[float, str, str] | None = None
    for v in venues:
        if not strict_name_match(app.restaurant, v.name):
            continue
        cand = (-name_similarity(app.restaurant, v.name), v.venue_id, v.group_id)
        if best is None or cand < best:
            best = cand
    return best[2] if best else None


def _is_customer(
    group_id: str | None,
    accounts: dict[str, ScoredAccount],
    customers: dict[str, CustomerLabel],
) -> bool:
    if group_id is None:
        return False
    acct = accounts.get(group_id)
    return (acct is not None and acct.is_customer) or group_id in customers


def _cold_priority(
    group_id: str | None,
    accounts: dict[str, ScoredAccount],
    customers: dict[str, CustomerLabel],
    unmatched: float,
) -> float:
    """Priority of a cold target; 0.0 for customers and disqualified groups."""
    if group_id is None:
        return unmatched
    if _is_customer(group_id, accounts, customers):
        return 0.0
    acct = accounts.get(group_id)
    if acct is None:
        return unmatched  # matched venue, no score yet: same prior as unmatched
    return 0.0 if acct.disqualified_reason is not None else acct.priority


def rank_events(
    events: Sequence[Event],
    appearances: Sequence[EventAppearance],
    accounts: dict[str, ScoredAccount],
    venues: Sequence[Venue],
    customers: dict[str, CustomerLabel],
    *,
    priors: EventsConfig,
) -> list[EventScore]:
    """Events by expected meetings per dollar, best first.

    An unknown cost (`cost_usd <= 0`) gets `score_per_dollar = 0.0`, never expected / 1, so an
    event of unknown price cannot look infinitely efficient; it sorts by expected meetings after
    every event with a known cost. Events with no appearances score zero and sort last.
    """
    by_event: dict[str, list[EventAppearance]] = {}
    for a in appearances:
        by_event.setdefault(a.event_id, []).append(a)
    scores: list[EventScore] = []
    for ev in events:
        rate = priors.meeting_rate_prior[ev.event_type]
        expected = 0.0
        matched = 0
        for a in by_event.get(ev.event_id, []):
            group_id = match_appearance(a, venues)
            matched += group_id is not None
            prior = priors.attend_prior[a.role] * rate
            expected += prior * _cold_priority(
                group_id, accounts, customers, priors.unmatched_priority
            )
        per_dollar = expected / max(ev.cost_usd, 1.0) if ev.cost_usd > 0 else 0.0
        scores.append(
            EventScore(
                event_id=ev.event_id,
                expected_meetings=expected,
                score_per_dollar=per_dollar,
                matched_people=matched,
            )
        )
    return sorted(scores, key=lambda s: (-s.score_per_dollar, -s.expected_meetings, s.event_id))


def meeting_list(
    event: Event,
    appearances: Sequence[EventAppearance],
    accounts: dict[str, ScoredAccount],
    venues: Sequence[Venue],
    customers: dict[str, CustomerLabel],
    *,
    priors: EventsConfig,
) -> list[MeetingTarget]:
    """Who to meet at `event`: cold prospects by p_attend * priority; customers left off."""
    prospects: list[MeetingTarget] = []
    for a in appearances:
        if a.event_id != event.event_id:
            continue
        group_id = match_appearance(a, venues)
        acct = accounts.get(group_id) if group_id else None
        p_attend = priors.attend_prior[a.role]
        if _is_customer(group_id, accounts, customers):
            continue  # already a Loyalist customer: never a meeting target
        if acct is not None and acct.disqualified_reason is not None:
            continue
        prospects.append(
            MeetingTarget(
                event_id=event.event_id,
                person=a.person,
                group_id=group_id,
                p_attend=p_attend,
                priority=acct.priority if acct else priors.unmatched_priority,
                in_window=acct is not None and acct.p_window >= priors.in_window_p,
                is_customer=False,
                reason=f"{a.role} at {a.restaurant}",
            )
        )

    def key(t: MeetingTarget) -> tuple[float, str]:
        return (-t.p_attend * t.priority, t.person)

    return sorted(prospects, key=key)
