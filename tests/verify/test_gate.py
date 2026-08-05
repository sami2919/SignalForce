"""Tests for scripts/verify/gate.py.

ADR-0009 (docs/decisions/0009-verify-budget-gate.md) is the spec. Three deviations
from the plan's reference implementation, all decided there:
  1. max_cost_usd is REMOVED — the plan's field was never enforced, and this
     project's own measurements (Task 2.1a/c: $0.026-$0.916 per extraction, 35x
     spread) make an unenforced dollar cap actively misleading, not harmless.
  2. Unknown source_type gets the fallback weight but is LOGGED, not silent.
  3. Ties break deterministically on source_id, not on input order.
"""

from __future__ import annotations

import logging

import pytest

from scripts.verify.gate import ChangeRef, VerifyBudget, select_for_verification


# ---------------------------------------------------------------------------
# From the plan (Task 2.1, Step 1) — kept as regression tests for the parts
# of the spec that did not change.
# ---------------------------------------------------------------------------


def test_respects_max_calls_budget():
    changes = [
        ChangeRef(source_id=i, source_type="careers", account_score=50.0) for i in range(100)
    ]
    selected = select_for_verification(changes, VerifyBudget(max_calls=10))
    assert len(selected) == 10


def test_prioritizes_higher_scoring_accounts():
    changes = [
        ChangeRef(source_id=1, source_type="careers", account_score=10.0),
        ChangeRef(source_id=2, source_type="careers", account_score=90.0),
    ]
    selected = select_for_verification(changes, VerifyBudget(max_calls=1))
    assert selected[0].source_id == 2


def test_empty_budget_selects_nothing():
    changes = [ChangeRef(source_id=1, source_type="careers", account_score=99.0)]
    assert select_for_verification(changes, VerifyBudget(max_calls=0)) == []


def test_empty_changes_list_selects_nothing():
    assert select_for_verification([], VerifyBudget(max_calls=10)) == []


def test_source_priority_breaks_ties_at_equal_account_score():
    changes = [
        ChangeRef(source_id=1, source_type="blog", account_score=50.0),
        ChangeRef(source_id=2, source_type="careers", account_score=50.0),
    ]
    selected = select_for_verification(changes, VerifyBudget(max_calls=2))
    # careers (1.0) outranks blog (0.3) at equal account_score.
    assert selected[0].source_id == 2
    assert selected[1].source_id == 1


# ---------------------------------------------------------------------------
# ADR-0009 Decision 1 — max_cost_usd does not exist. A field that looks like
# a promise and isn't one is worse than no field at all.
# ---------------------------------------------------------------------------


def test_verify_budget_has_no_cost_field():
    assert not hasattr(VerifyBudget(max_calls=1), "max_cost_usd")


def test_verify_budget_rejects_unknown_fields():
    # frozen + extra="forbid" (implicit default) — a caller trying to pass
    # max_cost_usd gets a loud validation error, not a silently ignored kwarg.
    with pytest.raises(Exception):  # pydantic.ValidationError
        VerifyBudget(max_calls=1, max_cost_usd=5.0)


# ---------------------------------------------------------------------------
# ADR-0009 Decision 2 — unknown source_type is visible, not silently downweighted.
# ---------------------------------------------------------------------------


def test_unknown_source_type_still_gets_selected_not_dropped():
    """One bad ChangeRef must not abort selection for the whole batch
    (ADR-0005 Decision 1's 'never raise on one input' posture)."""
    changes = [ChangeRef(source_id=1, source_type="carrers", account_score=100.0)]
    selected = select_for_verification(changes, VerifyBudget(max_calls=1))
    assert len(selected) == 1
    assert selected[0].source_id == 1


def test_unknown_source_type_logs_a_warning(caplog):
    changes = [ChangeRef(source_id=1, source_type="carrers", account_score=100.0)]
    with caplog.at_level(logging.WARNING):
        select_for_verification(changes, VerifyBudget(max_calls=1))
    assert any("carrers" in rec.getMessage() for rec in caplog.records)


def test_unknown_source_type_logs_once_per_distinct_value_not_per_change(caplog):
    changes = [ChangeRef(source_id=i, source_type="carrers", account_score=1.0) for i in range(20)]
    with caplog.at_level(logging.WARNING):
        select_for_verification(changes, VerifyBudget(max_calls=20))
    unknown_warnings = [rec for rec in caplog.records if "carrers" in rec.getMessage()]
    assert len(unknown_warnings) == 1


def test_unknown_source_type_ranks_below_every_known_source_type():
    """Proves the fallback weight's VALUE matters, not just that a fallback
    exists. An unknown type must rank below the lowest known priority (blog,
    0.3) at equal account_score — it must not be treated as ordinary."""
    changes = [
        ChangeRef(source_id=1, source_type="unknown-type", account_score=50.0),
        ChangeRef(source_id=2, source_type="blog", account_score=50.0),
    ]
    selected = select_for_verification(changes, VerifyBudget(max_calls=2))
    assert [c.source_id for c in selected] == [2, 1]


def test_known_source_type_does_not_log_a_warning(caplog):
    changes = [ChangeRef(source_id=1, source_type="careers", account_score=100.0)]
    with caplog.at_level(logging.WARNING):
        select_for_verification(changes, VerifyBudget(max_calls=1))
    assert caplog.records == []


# ---------------------------------------------------------------------------
# ADR-0009 Decision 3 — deterministic tie-break on source_id.
# ---------------------------------------------------------------------------


def test_ties_break_deterministically_on_source_id_ascending():
    # All three carry identical (priority x account_score); input order is
    # deliberately NOT source_id order, to prove the sort key drives the
    # result rather than incidental stability over the input.
    changes = [
        ChangeRef(source_id=30, source_type="careers", account_score=0.0),
        ChangeRef(source_id=10, source_type="careers", account_score=0.0),
        ChangeRef(source_id=20, source_type="careers", account_score=0.0),
    ]
    selected = select_for_verification(changes, VerifyBudget(max_calls=3))
    assert [c.source_id for c in selected] == [10, 20, 30]


def test_result_is_identical_regardless_of_input_order():
    a = ChangeRef(source_id=1, source_type="careers", account_score=0.0)
    b = ChangeRef(source_id=2, source_type="careers", account_score=0.0)
    r1 = select_for_verification([a, b], VerifyBudget(max_calls=2))
    r2 = select_for_verification([b, a], VerifyBudget(max_calls=2))
    assert [c.source_id for c in r1] == [c.source_id for c in r2]
