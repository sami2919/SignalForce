"""Decide which detected changes earn an expensive extraction.

ADR-0009 (docs/decisions/0009-verify-budget-gate.md) is the spec. Budget is a hard
cap, not a target: sorting by (source priority x account score) means when the
budget binds, it binds on the accounts and source types you care least about.

Deviations from the plan's Task 2.1 reference implementation, all decided in the
ADR:

1. `max_cost_usd` does not exist here. The plan's field was never read by the
   selection function — a caller setting it believed a dollar cap was enforced
   when nothing enforced it. Task 2.1a/c measured extraction cost varying 35x per
   page ($0.026-$0.916), which makes that gap concretely dangerous rather than
   theoretical. Enforcing it for real needs a per-candidate cost estimate that
   does not exist yet (`ChangeRef` carries no size/cost field); build that when it
   exists, do not resurrect an unenforced field before then.
2. An unknown `source_type` still gets selected (one bad `ChangeRef` must not
   abort the whole batch — ADR-0005 Decision 1's posture) but is logged once per
   distinct unknown value, not silently downweighted with no trace.
3. Ties break deterministically on `source_id` ascending, not on whatever order
   the caller happened to pass `changes` in.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict

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
    account_score: float = 0.0


class VerifyBudget(BaseModel):
    """Hard cap on extraction calls. See ADR-0009 Decision 1 for why this has
    no cost field — a promise this module cannot keep is worse than no promise.

    extra="forbid": a caller passing max_cost_usd (from the plan's original
    interface, or copied from an older draft) gets a loud validation error
    instead of a silently ignored kwarg that looks like it did something.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_calls: int


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
    """Rank by (source priority x account score), descending; ties broken by
    source_id ascending for a replayable result independent of input order.
    Take up to `budget.max_calls`."""
    warned: set[str] = set()
    ranked = sorted(
        changes,
        key=lambda c: (-(_priority(c.source_type, warned=warned) * c.account_score), c.source_id),
    )
    return ranked[: budget.max_calls]
