"""Wires the verify layer (extractor + differ + gate) to real data (ADR-0014).

Consumes the retained bodies `run_watch_pass`'s `on_confirmed_change` hook
collects during the watch pass -- never re-fetches (a second observation
would corrupt detection lag, the same reasoning ADR-0008 Decision 2 already
used to reject re-fetch over retention).

Careers-only (Decision 3): `extract_careers` is the only extractor that
exists; a confirmed change on any other source_type is left untouched here.

Each selected source's extract -> diff -> persist sequence is independently
wrapped (Decision 6) -- one bad extraction or diff must never abort the
whole stage, the same posture already applied at every other call site in
this codebase.
"""

from __future__ import annotations

import logging
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.scoring.wiring import load_latest_account_score
from scripts.storage.models import AccountSource, FactSnapshot, ScanRun, SignalEvent
from scripts.verify.differ import DiffOutcome, diff_facts
from scripts.verify.extractor import (
    CareersFacts,
    ExtractorError,
    JobFact,
    extract_careers_with_usage,
)
from scripts.verify.gate import ChangeRef, VerifyBudget, select_for_verification

logger = logging.getLogger(__name__)

# Opus 5 pricing (matches the arithmetic Task 2.1a's measured figures were
# checked against). Ignores cache_read_input_tokens' discounted rate, so a
# cache hit makes this a slight UNDERESTIMATE of true spend -- see ADR-0014
# Decision 5.
_INPUT_PRICE_PER_TOKEN = 5.0 / 1_000_000
_OUTPUT_PRICE_PER_TOKEN = 25.0 / 1_000_000

# ADR-0014 Decision 4, confirmed with the user: 10/day, not the 20 first
# proposed -- a deliberately tighter cap while this path is new.
DEFAULT_BUDGET = VerifyBudget(max_calls=10)


class VerifyStageReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidates: int
    selected: int
    extracted: int
    failed: int
    signals_emitted: int
    cost_usd: float


def _careers_sources(
    tenant_id: int, retained_source_ids: list[int], session: Session
) -> dict[int, AccountSource]:
    if not retained_source_ids:
        return {}
    rows = (
        session.execute(
            select(AccountSource).where(
                AccountSource.tenant_id == tenant_id,
                AccountSource.id.in_(retained_source_ids),
                AccountSource.source_type == "careers",
            )
        )
        .scalars()
        .all()
    )
    return {src.id: src for src in rows}


def _load_snapshot(account_source_id: int, session: Session) -> FactSnapshot | None:
    return session.execute(
        select(FactSnapshot).where(FactSnapshot.account_source_id == account_source_id)
    ).scalar_one_or_none()


def _snapshot_to_previous(snapshot: FactSnapshot | None) -> dict[str, object] | None:
    """None means "no snapshot exists yet" -- diff_facts's own SEEDING case.
    A row with an empty payload (never actually produced by this module, but
    defensively handled) is NOT the same as no row at all."""
    if snapshot is None:
        return None
    jobs = [JobFact(**job) for job in snapshot.payload.get("jobs", [])]
    return {"jobs": jobs}


def _current_snapshot_dict(facts: CareersFacts) -> dict[str, object]:
    return {"jobs": list(facts.jobs)}


def _payload_for_storage(facts: CareersFacts) -> dict[str, object]:
    return {"jobs": [job.model_dump(mode="json") for job in facts.jobs]}


def _extraction_cost(usage: object) -> float:
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    return input_tokens * _INPUT_PRICE_PER_TOKEN + output_tokens * _OUTPUT_PRICE_PER_TOKEN


def _fact_change_payload(change) -> dict[str, object]:
    return {
        "field": change.field,
        "kind": change.kind.value,
        "identity": list(change.identity),
        "previous": change.previous,
        "current": change.current,
        "changed_fields": list(change.changed_fields),
    }


def run_verify_stage(
    tenant_id: int,
    session: Session,
    run_id: int,
    retained_bodies: dict[int, str],
    now: datetime,
    *,
    budget: VerifyBudget = DEFAULT_BUDGET,
) -> VerifyStageReport:
    sources_by_id = _careers_sources(tenant_id, list(retained_bodies.keys()), session)

    # ADR-0016 Decision 5: the gate uses the most recently STORED score --
    # never a same-run one. Today's Score doesn't exist until the scoring
    # stage runs (after this one), computed from signals this very stage is
    # about to emit -- there is no way to close that loop same-run.
    changes = [
        ChangeRef(
            source_id=src_id,
            source_type="careers",
            account_score=load_latest_account_score(tenant_id, source.account_id, session),
        )
        for src_id, source in sources_by_id.items()
    ]
    selected = select_for_verification(changes, budget)

    extracted = 0
    failed = 0
    signals_emitted = 0
    cost_usd = 0.0

    for change_ref in selected:
        source = sources_by_id[change_ref.source_id]
        html = retained_bodies[change_ref.source_id]

        try:
            facts, usage = extract_careers_with_usage(html)
        except ExtractorError:
            logger.error(
                "verify extraction failed",
                extra={"tenant_id": tenant_id, "account_source_id": source.id},
                exc_info=True,
            )
            failed += 1
            continue

        cost_usd += _extraction_cost(usage)

        snapshot = _load_snapshot(source.id, session)
        previous = _snapshot_to_previous(snapshot)
        current = _current_snapshot_dict(facts)

        try:
            result = diff_facts(previous, current)
        except (ValueError, KeyError):
            logger.error(
                "verify diff failed",
                extra={"tenant_id": tenant_id, "account_source_id": source.id},
                exc_info=True,
            )
            failed += 1
            continue

        if result.degraded_fields:
            logger.warning(
                "degraded extraction suppressed removals",
                extra={
                    "tenant_id": tenant_id,
                    "account_source_id": source.id,
                    "degraded_fields": list(result.degraded_fields),
                },
            )

        if result.outcome != DiffOutcome.SEEDING:
            for change in result.changes:
                session.add(
                    SignalEvent(
                        tenant_id=tenant_id,
                        account_id=source.account_id,
                        account_source_id=source.id,
                        signal_type="hiring",
                        payload=_fact_change_payload(change),
                        detected_at=now,
                        scan_run_id=run_id,
                    )
                )
                signals_emitted += 1

        payload = _payload_for_storage(facts)
        if snapshot is None:
            session.add(
                FactSnapshot(
                    tenant_id=tenant_id,
                    account_source_id=source.id,
                    source_type="careers",
                    captured_at=now,
                    payload=payload,
                )
            )
        else:
            snapshot.captured_at = now
            snapshot.payload = payload

        extracted += 1

    run = session.get(ScanRun, run_id)
    if run is not None:
        run.verify_calls = extracted + failed
        run.signals_emitted = signals_emitted
        run.cost_usd = cost_usd

    return VerifyStageReport(
        candidates=len(changes),
        selected=len(selected),
        extracted=extracted,
        failed=failed,
        signals_emitted=signals_emitted,
        cost_usd=cost_usd,
    )
