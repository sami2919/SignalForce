"""Rank events by expected qualified meetings per dollar and build per-event meeting lists.

Customers (seed label or detected Loyalist embed) never count as cold targets: they add nothing
to an event's expected meetings and appear in a meeting list only as `is_customer=True`
(warm intro / co-host), after every prospect. Disqualified groups are not targets at all.
"""

from collections.abc import Sequence

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

ATTEND_PRIOR: dict[str, float] = {
    "speaker": 0.95,
    "panelist": 0.95,
    "festival_chef": 0.95,
    "award_nominee": 0.9,
    "exhibitor_staff": 0.7,
    "sponsor": 0.6,
    "past_recap": 0.35,
}
MEETING_RATE_PRIOR: dict[str, float] = {
    "curated_conference": 0.15,
    "festival": 0.08,
    "awards": 0.05,
    "trade_show": 0.03,
    "local_meetup": 0.20,
    "magic_dinner": 0.50,
}
UNMATCHED_PRIORITY = 0.05
IN_WINDOW_P = 0.5  # p_window at or above this counts as "in a buying window"
CUSTOMER_REASON = "warm intro / co-host"


def match_appearance(app: EventAppearance, venues: Sequence[Venue]) -> str | None:
    """group_id of the best strictly matching venue, else None.

    Strict (near-exact on distinctive tokens): the match decides whether the person is a
    customer's warm intro or a cold target, so a subset namesake ("FOOD" for "Major Food
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
) -> float:
    """Priority of a cold target; 0.0 for customers and disqualified groups."""
    if group_id is None:
        return UNMATCHED_PRIORITY
    if _is_customer(group_id, accounts, customers):
        return 0.0
    acct = accounts.get(group_id)
    if acct is None:
        return UNMATCHED_PRIORITY  # matched venue, no score yet: same prior as unmatched
    return 0.0 if acct.disqualified_reason is not None else acct.priority


def rank_events(
    events: Sequence[Event],
    appearances: Sequence[EventAppearance],
    accounts: dict[str, ScoredAccount],
    venues: Sequence[Venue],
    customers: dict[str, CustomerLabel],
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
        rate = MEETING_RATE_PRIOR[ev.event_type]
        expected = 0.0
        matched = 0
        for a in by_event.get(ev.event_id, []):
            group_id = match_appearance(a, venues)
            matched += group_id is not None
            prior = ATTEND_PRIOR[a.role] * rate
            expected += prior * _cold_priority(group_id, accounts, customers)
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
) -> list[MeetingTarget]:
    """Who to meet at `event`: prospects by p_attend * priority, then customers (warm intro)."""
    prospects: list[MeetingTarget] = []
    warm: list[MeetingTarget] = []
    for a in appearances:
        if a.event_id != event.event_id:
            continue
        group_id = match_appearance(a, venues)
        acct = accounts.get(group_id) if group_id else None
        p_attend = ATTEND_PRIOR[a.role]
        if _is_customer(group_id, accounts, customers):
            warm.append(
                MeetingTarget(
                    event_id=event.event_id,
                    person=a.person,
                    group_id=group_id,
                    p_attend=p_attend,
                    priority=acct.priority if acct else 0.0,
                    in_window=False,
                    is_customer=True,
                    reason=CUSTOMER_REASON,
                )
            )
            continue
        if acct is not None and acct.disqualified_reason is not None:
            continue
        prospects.append(
            MeetingTarget(
                event_id=event.event_id,
                person=a.person,
                group_id=group_id,
                p_attend=p_attend,
                priority=acct.priority if acct else UNMATCHED_PRIORITY,
                in_window=acct is not None and acct.p_window >= IN_WINDOW_P,
                is_customer=False,
                reason=f"{a.role} at {a.restaurant}",
            )
        )

    def key(t: MeetingTarget) -> tuple[float, str]:
        return (-t.p_attend * t.priority, t.person)

    return sorted(prospects, key=key) + sorted(warm, key=key)
