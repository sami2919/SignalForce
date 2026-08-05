"""Decide which detected changes earn an expensive extraction.

ADR-0009 (docs/decisions/0009-verify-budget-gate.md) is the spec. Budget is a hard
cap, not a target: the sort key gives source-type priority a floor contribution
independent of account_score, then lets account_score scale it up further, so a
higher-priority source still outranks a lower-priority one even before Phase 4
scoring exists and every account_score is the caller's 0.0 placeholder — a plain
product (priority x account_score) collapses to zero for every source type in
that regime and silently stops ranking by source type at all. See review fix
2026-08-05: this was caught by independent review after shipping, not before.

Deviations from the plan's Task 2.1 reference implementation, all decided in the
ADR:

1. `max_cost_usd` does not exist here. The plan's field was never read by the
   selection function — a caller setting it believed a dollar cap was enforced
   when nothing enforced it. Enforcing it for real needs a per-candidate cost
   estimate that does not exist yet (`ChangeRef` carries no size/cost field);
   build that when it exists, do not resurrect an unenforced field before then.
2. An unknown `source_type` still gets selected (one bad `ChangeRef` must not
   abort the whole batch — the same "never abort a pass over one bad input"
   posture as scripts/watch/fetcher.py) but is logged once per distinct
   unknown value, not silently downweighted with no trace.
3. Ties break deterministically on `source_id` ascending, not on whatever order
   the caller happened to pass `changes` in.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# Sources ranked by how often a change is a real signal vs. cosmetic churn.
_SOURCE_PRIORITY = {
    "careers": 1.0,
    "changelog": 0.9,
    "pricing": 0.7,
    "docs": 0.5,
    "blog": 0.3,
}
_UNKNOWN_SOURCE_PRIORITY = 0.1


class ChangeRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: int
    source_type: str
    # ge=0: the sort key's `1 + account_score` scaling factor (see
    # select_for_verification) assumes non-negative scores. A negative score
    # would invert priority ordering end-for-end rather than merely down-rank.
    account_score: float = Field(default=0.0, ge=0.0)


class VerifyBudget(BaseModel):
    """Hard cap on extraction calls. See ADR-0009 Decision 1 for why this has
    no cost field — a promise this module cannot keep is worse than no promise.

    extra="forbid": a caller passing max_cost_usd (from the plan's original
    interface, or copied from an older draft) gets a loud validation error
    instead of a silently ignored kwarg that looks like it did something.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # ge=0: a negative max_calls slices as ranked[:-1]-style "all but the last
    # N", i.e. near-maximum spend from a module whose one job is capping it.
    max_calls: int = Field(ge=0)


def _priority(source_type: str, *, warned: set[str]) -> float:
    priority = _SOURCE_PRIORITY.get(source_type)
    if priority is not None:
        return priority
    if source_type not in warned:
        logger.warning(
            "unrecognized source_type %r in verify gate, using fallback priority %s",
            source_type,
            _UNKNOWN_SOURCE_PRIORITY,
        )
        warned.add(source_type)
    return _UNKNOWN_SOURCE_PRIORITY


def select_for_verification(changes: list[ChangeRef], budget: VerifyBudget) -> list[ChangeRef]:
    """Rank by source-type priority, scaled up by account_score; ties broken by
    source_id ascending for a replayable result independent of input order.
    Take up to `budget.max_calls`.

    The key is `priority * (1 + account_score)`, not `priority * account_score`.
    A plain product is zero for every source type whenever account_score is
    zero — the common case before Phase 4 scoring exists — which would silently
    stop the gate from ranking by source type at all in exactly the regime
    ADR-0009 says is normal today. The `1 +` term gives priority a floor
    contribution independent of score; account_score >= 0 (enforced on
    ChangeRef) keeps that floor from being able to flip sign.
    """
    warned: set[str] = set()
    ranked = sorted(
        changes,
        key=lambda c: (
            -(_priority(c.source_type, warned=warned) * (1 + c.account_score)),
            c.source_id,
        ),
    )
    return ranked[: budget.max_calls]
