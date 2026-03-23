"""Feedback loop tracker: log signals, outreach, and outcomes; query conversion rates.

All functions take an explicit SQLAlchemy Engine so callers control the database
connection (production file-based DB vs. in-memory test DB).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, func
from sqlalchemy.engine import Engine

from scripts.db import (
    Campaign,
    OutcomeEvent,
    OutreachEvent,
    TrackedSignal,
    _VALID_OUTCOME_TYPES,
    get_session,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------


def log_signal(
    engine: Engine,
    campaign_id: int,
    *,
    signal_type: str,
    company_name: str,
    company_domain: Optional[str] = None,
    signal_strength: int,
    source_url: str = "",
    detected_at: Optional[datetime] = None,
) -> int:
    """Record a detected signal in the feedback loop.

    Returns:
        The id of the newly created TrackedSignal row.
    """
    with get_session(engine) as session:
        row = TrackedSignal(
            campaign_id=campaign_id,
            signal_type=signal_type,
            company_name=company_name,
            company_domain=company_domain,
            signal_strength=signal_strength,
            source_url=source_url,
            detected_at=detected_at or _utcnow(),
        )
        session.add(row)
        session.flush()
        return int(row.id)  # type: ignore[arg-type]


def log_outreach(
    engine: Engine,
    tracked_signal_id: int,
    *,
    channel: str,
    template: str = "",
    angle: str = "",
    sent_at: Optional[datetime] = None,
) -> int:
    """Record an outreach event linked to a tracked signal.

    Returns:
        The id of the newly created OutreachEvent row.
    """
    if channel not in {"email", "linkedin"}:
        raise ValueError(f"channel must be 'email' or 'linkedin', got '{channel}'")

    with get_session(engine) as session:
        row = OutreachEvent(
            tracked_signal_id=tracked_signal_id,
            channel=channel,
            template_used=template,
            angle_used=angle,
            sent_at=sent_at or _utcnow(),
        )
        session.add(row)
        session.flush()
        return int(row.id)  # type: ignore[arg-type]


def log_outcome(
    engine: Engine,
    outreach_event_id: int,
    *,
    outcome_type: str,
    notes: str = "",
    occurred_at: Optional[datetime] = None,
) -> int:
    """Record an outcome event linked to an outreach event.

    Returns:
        The id of the newly created OutcomeEvent row.
    """
    if outcome_type not in _VALID_OUTCOME_TYPES:
        raise ValueError(
            f"outcome_type must be one of {sorted(_VALID_OUTCOME_TYPES)}, got '{outcome_type}'"
        )

    with get_session(engine) as session:
        row = OutcomeEvent(
            outreach_event_id=outreach_event_id,
            outcome_type=outcome_type,
            notes=notes,
            occurred_at=occurred_at or _utcnow(),
        )
        session.add(row)
        session.flush()
        return int(row.id)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Read / analytics helpers
# ---------------------------------------------------------------------------


def create_campaign(
    engine: Engine,
    *,
    client_name: str,
    icp_description: str = "",
) -> int:
    """Create a new campaign and return its id."""
    with get_session(engine) as session:
        row = Campaign(
            client_name=client_name,
            icp_description=icp_description,
        )
        session.add(row)
        session.flush()
        return int(row.id)  # type: ignore[arg-type]


def get_conversion_rates(
    engine: Engine,
    *,
    campaign_id: Optional[int] = None,
    signal_type: Optional[str] = None,
    date_range: Optional[Tuple[datetime, datetime]] = None,
) -> Dict[str, Any]:
    """Calculate conversion rates across the funnel.

    Returns a dict like::

        {
            "total_signals": 100,
            "total_outreach": 80,
            "outcomes": {
                "deal_closed": 1,
                "meeting_completed": 3,
                "meeting_scheduled": 5,
                "positive_reply": 10,
                "reply": 20,
            },
            "rates": {
                "signal_to_outreach": 0.8,
                "outreach_to_reply": 0.25,
                "outreach_to_meeting": 0.0625,
                "outreach_to_deal": 0.0125,
            },
        }
    """
    with get_session(engine) as session:
        # Base query for signals
        signals_q = session.query(func.count(TrackedSignal.id))
        outreach_q = session.query(func.count(OutreachEvent.id)).join(
            TrackedSignal, OutreachEvent.tracked_signal_id == TrackedSignal.id
        )

        # Apply filters
        if campaign_id is not None:
            signals_q = signals_q.filter(TrackedSignal.campaign_id == campaign_id)
            outreach_q = outreach_q.filter(TrackedSignal.campaign_id == campaign_id)

        if signal_type is not None:
            signals_q = signals_q.filter(TrackedSignal.signal_type == signal_type)
            outreach_q = outreach_q.filter(TrackedSignal.signal_type == signal_type)

        if date_range is not None:
            start, end = date_range
            signals_q = signals_q.filter(TrackedSignal.detected_at.between(start, end))
            outreach_q = outreach_q.filter(TrackedSignal.detected_at.between(start, end))

        total_signals: int = signals_q.scalar() or 0
        total_outreach: int = outreach_q.scalar() or 0

        # Count outcomes by type
        outcomes: Dict[str, int] = {}
        for otype in sorted(_VALID_OUTCOME_TYPES):
            outcome_q = (
                session.query(func.count(OutcomeEvent.id))
                .join(OutreachEvent, OutcomeEvent.outreach_event_id == OutreachEvent.id)
                .join(TrackedSignal, OutreachEvent.tracked_signal_id == TrackedSignal.id)
                .filter(OutcomeEvent.outcome_type == otype)
            )
            if campaign_id is not None:
                outcome_q = outcome_q.filter(TrackedSignal.campaign_id == campaign_id)
            if signal_type is not None:
                outcome_q = outcome_q.filter(TrackedSignal.signal_type == signal_type)
            if date_range is not None:
                start, end = date_range
                outcome_q = outcome_q.filter(TrackedSignal.detected_at.between(start, end))
            outcomes[otype] = outcome_q.scalar() or 0

        # Derive rates (safe division)
        def _rate(numerator: int, denominator: int) -> float:
            return round(numerator / denominator, 4) if denominator > 0 else 0.0

        reply_count = outcomes.get("reply", 0) + outcomes.get("positive_reply", 0)
        meeting_count = outcomes.get("meeting_scheduled", 0) + outcomes.get(
            "meeting_completed", 0
        )
        deal_count = outcomes.get("deal_closed", 0)

        rates = {
            "signal_to_outreach": _rate(total_outreach, total_signals),
            "outreach_to_reply": _rate(reply_count, total_outreach),
            "outreach_to_meeting": _rate(meeting_count, total_outreach),
            "outreach_to_deal": _rate(deal_count, total_outreach),
        }

        return {
            "total_signals": total_signals,
            "total_outreach": total_outreach,
            "outcomes": outcomes,
            "rates": rates,
        }


def get_best_performing_signals(
    engine: Engine,
    *,
    campaign_id: Optional[int] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return signal types ranked by conversion to positive outcomes.

    A positive outcome is any of: positive_reply, meeting_scheduled,
    meeting_completed, deal_closed.

    Returns a list of dicts::

        [
            {"signal_type": "github_repo", "total_signals": 40,
             "positive_outcomes": 8, "conversion_rate": 0.2},
            ...
        ]
    """
    positive_types = [
        "positive_reply",
        "meeting_scheduled",
        "meeting_completed",
        "deal_closed",
    ]

    with get_session(engine) as session:
        positive_case = func.count(
            func.distinct(
                case(
                    (OutcomeEvent.outcome_type.in_(positive_types), OutcomeEvent.id),
                )
            )
        )

        q = (
            session.query(
                TrackedSignal.signal_type,
                func.count(func.distinct(TrackedSignal.id)).label("total_signals"),
                positive_case.label("positive_outcomes"),
            )
            .outerjoin(OutreachEvent, OutreachEvent.tracked_signal_id == TrackedSignal.id)
            .outerjoin(OutcomeEvent, OutcomeEvent.outreach_event_id == OutreachEvent.id)
            .group_by(TrackedSignal.signal_type)
        )

        if campaign_id is not None:
            q = q.filter(TrackedSignal.campaign_id == campaign_id)

        q = q.order_by(positive_case.desc(), func.count(func.distinct(TrackedSignal.id)).desc())
        q = q.limit(limit)

        rows = q.all()

        results: List[Dict[str, Any]] = []
        for row in rows:
            total = row[1]
            positive = row[2]
            results.append(
                {
                    "signal_type": row[0],
                    "total_signals": total,
                    "positive_outcomes": positive,
                    "conversion_rate": round(positive / total, 4) if total > 0 else 0.0,
                }
            )

        return results
