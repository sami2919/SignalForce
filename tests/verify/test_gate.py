"""Tests for scripts/verify/gate.py.

ADR-0009 (docs/decisions/0009-verify-budget-gate.md) is the spec. Deviations from
the plan's reference implementation, all decided there:
  1. max_cost_usd is REMOVED — the plan's field was never enforced, which is
     actively misleading (a caller believes a dollar cap is enforced), not harmless.
  2. Unknown source_type gets the fallback weight but is LOGGED, not silent.
  3. Ties break deterministically on source_id, not on input order.
  4. account_score and max_calls are constrained to non-negative (added on
     independent review, 2026-08-05) — a negative account_score inverts priority
     ordering via the sort key's `1 + account_score` term, and a negative
     max_calls slices as "all but the last N" under Python's list slicing rather
     than "select nothing."

Also fixed on review: the sort key is `priority * (1 + account_score)`, not
`priority * account_score`. The plain-product form is zero for every source type
whenever account_score is 0.0, which silently stops the gate from ranking by
source type at all in the pre-Phase-4 regime where every account_score is a
0.0 placeholder — exactly the regime this ADR says is the common case today.
"""

from __future__ import annotations

import logging

import pydantic
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
    # extra="forbid" — NOT pydantic's default (pydantic v2 defaults to "ignore",
    # as ChangeRef in this same module demonstrates). Set explicitly on
    # VerifyBudget so a caller trying to pass max_cost_usd (copied from the
    # plan's original interface) gets a loud validation error, not a silently
    # ignored kwarg that looks like it did something.
    with pytest.raises(pydantic.ValidationError):
        VerifyBudget(max_calls=1, max_cost_usd=5.0)


# ---------------------------------------------------------------------------
# ADR-0009 Decision 2 — unknown source_type is visible, not silently downweighted.
# ---------------------------------------------------------------------------


def test_unknown_source_type_still_gets_selected_not_dropped():
    """One bad ChangeRef must not abort selection for the whole batch — the
    same posture scripts/watch/fetcher.py states for itself."""
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


# ---------------------------------------------------------------------------
# ADR-0009 Decision 3 correction — the sort key must not collapse to a
# source_id coin-flip at account_score=0.0, the pre-Phase-4 common case.
# ---------------------------------------------------------------------------


def test_source_priority_still_ranks_at_zero_account_score():
    """The bug independent review caught: priority * account_score is zero
    for every source type when account_score is 0.0, so a plain product
    silently stops ranking by source type in exactly the regime ADR-0009
    says is normal before Phase 4 exists. Reproduced pre-fix: blog (lower
    priority, lower source_id) won over careers here."""
    changes = [
        ChangeRef(source_id=1, source_type="blog", account_score=0.0),
        ChangeRef(source_id=9, source_type="careers", account_score=0.0),
    ]
    selected = select_for_verification(changes, VerifyBudget(max_calls=1))
    assert selected[0].source_type == "careers"


def test_higher_account_score_can_still_outrank_a_lower_priority_source():
    # Sanity: the score term still contributes once it's nonzero, not just
    # the priority floor from the `1 +` term.
    changes = [
        ChangeRef(source_id=1, source_type="blog", account_score=100.0),
        ChangeRef(source_id=2, source_type="docs", account_score=0.0),
    ]
    selected = select_for_verification(changes, VerifyBudget(max_calls=1))
    assert selected[0].source_type == "blog"


# ---------------------------------------------------------------------------
# ADR-0009 Decision 4 — non-negative constraints, added on review.
# ---------------------------------------------------------------------------


def test_negative_account_score_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        ChangeRef(source_id=1, source_type="careers", account_score=-5.0)


def test_negative_max_calls_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        VerifyBudget(max_calls=-1)


def test_zero_account_score_and_zero_max_calls_are_still_valid():
    # ge=0 must not reject the legitimate boundary values.
    ref = ChangeRef(source_id=1, source_type="careers", account_score=0.0)
    assert select_for_verification([ref], VerifyBudget(max_calls=0)) == []


def test_ranking_formula_is_multiplicative_not_additive():
    """Pins the exact formula, not just 'there is some ordering.' At these
    scores, priority * (1 + score) and priority + score disagree on the
    winner — careers(score=1) beats blog(score=5) under multiplication
    (2.0 vs 1.8) but loses under addition (2.0 vs 5.3). If this test ever
    breaks, check whether the formula changed before assuming it's the test."""
    changes = [
        ChangeRef(source_id=1, source_type="careers", account_score=1.0),
        ChangeRef(source_id=2, source_type="blog", account_score=5.0),
    ]
    selected = select_for_verification(changes, VerifyBudget(max_calls=1))
    assert selected[0].source_type == "careers"
