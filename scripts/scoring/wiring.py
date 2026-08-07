"""Wires the scoring engine (Task 4.1) to real signal_events data (ADR-0016).

Scores every account belonging to a tenant once per run, from a bounded
trailing window of signal_events -- one new Score row per account per run,
append-only (ADR-0016 Decision 3; Score has no unique constraint, unlike
SourceHealthRecord/FactSnapshot -- the whole point of this table is a
replayable history, not "current state").

Also exposes `load_latest_account_score`, the read side of ADR-0016
Decision 5: scripts/verify/wiring.py's gate needs an account_score to
prioritize today's extraction candidates BEFORE today's Score exists (this
module's own write happens after verify, since it scores from signals verify
just emitted) -- so the gate always reads the most recently stored score,
never a same-run one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.scoring.engine import SignalInput, score_account
from scripts.storage.models import Account, Score, SignalEvent

logger = logging.getLogger(__name__)

_DEFAULT_WINDOW_DAYS = 90

# ADR-0016 Decision 1: (base_weight, is_icp) per signal_type.
_SIGNAL_WEIGHTS: dict[str, tuple[float, bool]] = {
    "agent_email_repo": (0.6, True),
    "hiring": (0.8, False),
    "funding": (0.7, False),
    "stack_change": (0.6, False),
}
_UNKNOWN_SIGNAL_WEIGHT = (0.5, False)


class ScoringStageReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    accounts_scored: int
    scores_persisted: int


def _weight_for(signal_type: str, *, warned: set[str]) -> tuple[float, bool]:
    weight = _SIGNAL_WEIGHTS.get(signal_type)
    if weight is not None:
        return weight
    if signal_type not in warned:
        logger.warning(
            "unrecognized signal_type in scoring, using fallback weight",
            extra={"signal_type": signal_type, "fallback_weight": _UNKNOWN_SIGNAL_WEIGHT[0]},
        )
        warned.add(signal_type)
    return _UNKNOWN_SIGNAL_WEIGHT


def _load_account_ids(tenant_id: int, session: Session) -> list[int]:
    rows = session.execute(select(Account.id).where(Account.tenant_id == tenant_id)).scalars().all()
    return sorted(rows)


def _load_signal_inputs(
    tenant_id: int,
    account_id: int,
    window_start: datetime,
    session: Session,
    *,
    warned: set[str],
) -> list[SignalInput]:
    rows = session.execute(
        select(SignalEvent.signal_type, SignalEvent.detected_at, SignalEvent.confidence).where(
            SignalEvent.tenant_id == tenant_id,
            SignalEvent.account_id == account_id,
            SignalEvent.detected_at >= window_start,
        )
    ).all()
    inputs: list[SignalInput] = []
    for signal_type, detected_at, confidence in rows:
        base_weight, is_icp = _weight_for(signal_type, warned=warned)
        if detected_at.tzinfo is None:
            # SQLite (tests only -- Postgres always returns tz-aware) drops
            # tzinfo on retrieval even though the column is DateTime(timezone=True).
            detected_at = detected_at.replace(tzinfo=timezone.utc)
        inputs.append(
            SignalInput(
                signal_type=signal_type,
                detected_at=detected_at,
                base_weight=base_weight * confidence,
                is_icp=is_icp,
            )
        )
    return inputs


def run_scoring_stage(
    tenant_id: int,
    session: Session,
    now: datetime,
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> ScoringStageReport:
    window_start = now - timedelta(days=window_days)
    account_ids = _load_account_ids(tenant_id, session)

    warned: set[str] = set()
    scores_persisted = 0
    for account_id in account_ids:
        signals = _load_signal_inputs(tenant_id, account_id, window_start, session, warned=warned)
        result = score_account(signals, now=now)
        session.add(
            Score(
                tenant_id=tenant_id,
                account_id=account_id,
                score=result.score,
                computed_at=now,
                trace=result.trace,
            )
        )
        scores_persisted += 1

    return ScoringStageReport(accounts_scored=len(account_ids), scores_persisted=scores_persisted)


def load_latest_account_score(tenant_id: int, account_id: int, session: Session) -> float:
    """Most recently stored Score.score, or 0.0 for an account with no Score
    row yet (cold start -- same "first observation" fallback this project
    uses everywhere else: ADR-0006 Decision 5, ADR-0007 Decision 4)."""
    row = session.execute(
        select(Score.score)
        .where(Score.tenant_id == tenant_id, Score.account_id == account_id)
        .order_by(Score.computed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row if row is not None else 0.0
