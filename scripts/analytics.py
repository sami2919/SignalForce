"""Analytics queries and deterministic optimization hints for SignalForce."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.engine import Engine

from scripts.db import OutcomeEvent, OutreachEvent, TrackedSignal, get_session

DateRange = Optional[Tuple[datetime, datetime]]

POSITIVE_OUTCOMES = {
    "positive_reply",
    "meeting_scheduled",
    "meeting_completed",
    "deal_closed",
}
MEETING_OUTCOMES = {"meeting_scheduled", "meeting_completed"}
REPLY_OUTCOMES = {"reply", "positive_reply", "negative_reply"}

BREAKDOWN_FIELDS = {
    "signal_type": TrackedSignal.signal_type,
    "scanner_name": TrackedSignal.scanner_name,
    "icp_grade": TrackedSignal.icp_grade,
    "channel": OutreachEvent.channel,
    "template_used": OutreachEvent.template_used,
    "template_variant": OutreachEvent.template_variant,
    "experiment_tag": OutreachEvent.experiment_tag,
}


def get_funnel_metrics(
    engine: Engine,
    *,
    campaign_id: Optional[int] = None,
    date_range: DateRange = None,
) -> Dict[str, Any]:
    """Return funnel totals and rates for the selected campaign/date window."""
    with get_session(engine) as session:
        signals_q = session.query(func.count(TrackedSignal.id))
        outreach_q = session.query(func.count(OutreachEvent.id)).join(
            TrackedSignal,
            OutreachEvent.tracked_signal_id == TrackedSignal.id,
        )

        signals_q = _apply_signal_filters(signals_q, campaign_id, date_range)
        outreach_q = _apply_signal_filters(outreach_q, campaign_id, date_range)

        total_signals = signals_q.scalar() or 0
        total_outreach = outreach_q.scalar() or 0
        outcomes = _count_outcomes(session, campaign_id=campaign_id, date_range=date_range)

    delivered = outcomes.get("delivered", 0)
    opened = outcomes.get("opened", 0)
    clicked = outcomes.get("clicked", 0)
    bounced = outcomes.get("bounced", 0)
    unsubscribed = outcomes.get("unsubscribed", 0)
    replies = sum(outcomes.get(name, 0) for name in REPLY_OUTCOMES)
    positive_replies = outcomes.get("positive_reply", 0)
    meetings = sum(outcomes.get(name, 0) for name in MEETING_OUTCOMES)
    deals = outcomes.get("deal_closed", 0)
    delivery_denominator = delivered if delivered > 0 else total_outreach

    return {
        "totals": {
            "signals": total_signals,
            "outreach": total_outreach,
            "delivered": delivered,
            "opened": opened,
            "clicked": clicked,
            "bounced": bounced,
            "unsubscribed": unsubscribed,
            "replies": replies,
            "positive_replies": positive_replies,
            "meetings": meetings,
            "deals": deals,
        },
        "outcomes": outcomes,
        "rates": {
            "signal_to_outreach": _rate(total_outreach, total_signals),
            "delivery_rate": _rate(delivered, total_outreach),
            "open_rate": _rate(opened, delivery_denominator),
            "click_rate": _rate(clicked, delivery_denominator),
            "reply_rate": _rate(replies, delivery_denominator),
            "positive_reply_rate": _rate(positive_replies, delivery_denominator),
            "meeting_rate": _rate(meetings, delivery_denominator),
            "deal_rate": _rate(deals, delivery_denominator),
            "bounce_rate": _rate(bounced, total_outreach),
            "unsubscribe_rate": _rate(unsubscribed, delivery_denominator),
        },
    }


def get_breakdown(
    engine: Engine,
    *,
    group_by: str,
    campaign_id: Optional[int] = None,
    date_range: DateRange = None,
    min_outreach: int = 0,
) -> List[Dict[str, Any]]:
    """Return conversion metrics grouped by a supported signal/outreach field."""
    if group_by not in BREAKDOWN_FIELDS:
        supported = ", ".join(sorted(BREAKDOWN_FIELDS))
        raise ValueError(f"group_by must be one of: {supported}")

    group_column = BREAKDOWN_FIELDS[group_by]

    with get_session(engine) as session:
        rows_q = (
            session.query(
                group_column.label("group_value"),
                func.count(func.distinct(TrackedSignal.id)).label("signals"),
                func.count(func.distinct(OutreachEvent.id)).label("outreach"),
            )
            .select_from(TrackedSignal)
            .outerjoin(OutreachEvent, OutreachEvent.tracked_signal_id == TrackedSignal.id)
            .group_by(group_column)
        )
        rows_q = _apply_signal_filters(rows_q, campaign_id, date_range)
        rows = rows_q.all()

        results: List[Dict[str, Any]] = []
        for row in rows:
            value = row.group_value or "(none)"
            outcomes = _count_outcomes(
                session,
                campaign_id=campaign_id,
                date_range=date_range,
                group_column=group_column,
                group_value=row.group_value,
            )
            replies = sum(outcomes.get(name, 0) for name in REPLY_OUTCOMES)
            positives = sum(outcomes.get(name, 0) for name in POSITIVE_OUTCOMES)
            meetings = sum(outcomes.get(name, 0) for name in MEETING_OUTCOMES)
            outreach = row.outreach or 0
            if outreach < min_outreach:
                continue
            results.append(
                {
                    "group_by": group_by,
                    "value": value,
                    "signals": row.signals or 0,
                    "outreach": outreach,
                    "replies": replies,
                    "positive_outcomes": positives,
                    "meetings": meetings,
                    "reply_rate": _rate(replies, outreach),
                    "positive_outcome_rate": _rate(positives, outreach),
                    "meeting_rate": _rate(meetings, outreach),
                }
            )

    return sorted(
        results,
        key=lambda item: (
            item["meeting_rate"],
            item["positive_outcome_rate"],
            item["outreach"],
        ),
        reverse=True,
    )


def get_stale_signals(
    engine: Engine,
    *,
    older_than_hours: int = 72,
    campaign_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return detected signals that have not generated outreach after the age threshold."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    with get_session(engine) as session:
        q = (
            session.query(TrackedSignal)
            .outerjoin(OutreachEvent, OutreachEvent.tracked_signal_id == TrackedSignal.id)
            .filter(OutreachEvent.id.is_(None))
            .filter(TrackedSignal.detected_at <= cutoff)
            .order_by(TrackedSignal.detected_at.asc())
        )
        if campaign_id is not None:
            q = q.filter(TrackedSignal.campaign_id == campaign_id)

        return [
            {
                "id": row.id,
                "company_name": row.company_name,
                "company_domain": row.company_domain,
                "signal_type": row.signal_type,
                "icp_grade": row.icp_grade,
                "detected_at": _to_iso(row.detected_at),
                "age_hours": round(
                    (_now_aware() - _ensure_aware(row.detected_at)).total_seconds() / 3600, 2
                ),
            }
            for row in q.all()
        ]


def get_recommendations(
    engine: Engine,
    *,
    campaign_id: Optional[int] = None,
    date_range: DateRange = None,
    min_sample_size: int = 5,
) -> List[Dict[str, Any]]:
    """Generate rule-based optimization recommendations from analytics results."""
    recommendations: List[Dict[str, Any]] = []

    signal_breakdown = get_breakdown(
        engine,
        group_by="signal_type",
        campaign_id=campaign_id,
        date_range=date_range,
        min_outreach=min_sample_size,
    )
    if signal_breakdown:
        best = signal_breakdown[0]
        recommendations.append(
            {
                "severity": "info",
                "category": "signal_source",
                "message": (
                    f"{best['value']} is the strongest signal source in this window "
                    f"with a {best['meeting_rate']:.1%} meeting rate."
                ),
            }
        )

    for row in get_breakdown(
        engine,
        group_by="template_used",
        campaign_id=campaign_id,
        date_range=date_range,
        min_outreach=min_sample_size,
    ):
        if row["positive_outcomes"] == 0:
            recommendations.append(
                {
                    "severity": "warning",
                    "category": "template",
                    "message": (
                        f"Template {row['value']} has {row['outreach']} sends and no "
                        "positive outcomes. Pause or rewrite before more volume."
                    ),
                }
            )

    for row in get_breakdown(
        engine,
        group_by="icp_grade",
        campaign_id=campaign_id,
        date_range=date_range,
        min_outreach=min_sample_size,
    ):
        if row["value"] in {"C", "D"} and row["positive_outcomes"] == 0:
            recommendations.append(
                {
                    "severity": "warning",
                    "category": "icp_grade",
                    "message": (
                        f"ICP grade {row['value']} consumed {row['outreach']} sends "
                        "with no positive outcomes. Suppress or lower priority."
                    ),
                }
            )

    slow = _get_slow_outreach_summary(
        engine,
        campaign_id=campaign_id,
        date_range=date_range,
        threshold_hours=168,
    )
    if slow["count"] >= min_sample_size:
        recommendations.append(
            {
                "severity": "warning",
                "category": "speed_to_lead",
                "message": (
                    f"{slow['count']} outreach events were sent more than 7 days after "
                    "signal detection. Test a tighter follow-up SLA."
                ),
            }
        )

    return recommendations


def _count_outcomes(
    session: Any,
    *,
    campaign_id: Optional[int],
    date_range: DateRange,
    group_column: Any = None,
    group_value: Any = None,
) -> Dict[str, int]:
    q = (
        session.query(OutcomeEvent.outcome_type, func.count(OutcomeEvent.id))
        .join(OutreachEvent, OutcomeEvent.outreach_event_id == OutreachEvent.id)
        .join(TrackedSignal, OutreachEvent.tracked_signal_id == TrackedSignal.id)
        .group_by(OutcomeEvent.outcome_type)
    )
    q = _apply_signal_filters(q, campaign_id, date_range)
    if group_column is not None:
        if group_value is None:
            q = q.filter(group_column.is_(None))
        else:
            q = q.filter(group_column == group_value)
    return {row[0]: row[1] for row in q.all()}


def _get_slow_outreach_summary(
    engine: Engine,
    *,
    campaign_id: Optional[int],
    date_range: DateRange,
    threshold_hours: int,
) -> Dict[str, Any]:
    with get_session(engine) as session:
        q = (
            session.query(func.count(OutreachEvent.id))
            .join(TrackedSignal, OutreachEvent.tracked_signal_id == TrackedSignal.id)
            .filter(OutreachEvent.detected_to_sent_hours > threshold_hours)
        )
        q = _apply_signal_filters(q, campaign_id, date_range)
        return {"count": q.scalar() or 0}


def _apply_signal_filters(
    query: Any,
    campaign_id: Optional[int],
    date_range: DateRange,
) -> Any:
    if campaign_id is not None:
        query = query.filter(TrackedSignal.campaign_id == campaign_id)
    if date_range is not None:
        start, end = date_range
        query = query.filter(TrackedSignal.detected_at.between(start, end))
    return query


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator > 0 else 0.0


def _now_aware() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _to_iso(value: datetime) -> str:
    return _ensure_aware(value).isoformat()
