"""Tests for scripts/scoring/audiences.py.

ADR-0017 is the spec. Decisions 1-2 correct two real gaps found in the plan's
reference `evaluate`: a predicate with more than one recognized key silently
evaluated only the first one found (a merged-fragment predicate would silently
drop half its condition), and a malformed non-dict predicate would fail with a
confusing error several frames away from the actual mistake.
"""

from __future__ import annotations

import pytest

from scripts.scoring.audiences import AccountFacts, evaluate


def _facts(**kw) -> AccountFacts:
    return AccountFacts(account_id=1, signals=kw.get("signals", []), score=kw.get("score", 0.0))


# ---------------------------------------------------------------------------
# From the plan -- kept as regression tests for what did not change.
# ---------------------------------------------------------------------------


def test_and_requires_both_predicates():
    pred = {"and": [{"has_signal": "hiring"}, {"has_signal": "funding"}]}
    assert evaluate(pred, _facts(signals=["hiring", "funding"])) is True
    assert evaluate(pred, _facts(signals=["hiring"])) is False


def test_or_requires_either():
    pred = {"or": [{"has_signal": "hiring"}, {"has_signal": "funding"}]}
    assert evaluate(pred, _facts(signals=["funding"])) is True


def test_not_inverts():
    assert evaluate({"not": {"has_signal": "hiring"}}, _facts(signals=[])) is True


def test_min_score_gate():
    assert evaluate({"min_score": 70}, _facts(score=85.0)) is True
    assert evaluate({"min_score": 70}, _facts(score=50.0)) is False


def test_min_score_is_inclusive_at_the_boundary():
    """>= not > -- a score exactly equal to the floor must pass."""
    assert evaluate({"min_score": 70}, _facts(score=70.0)) is True


def test_nested_composition():
    pred = {
        "and": [
            {"or": [{"has_signal": "hiring"}, {"has_signal": "agent_email_repo"}]},
            {"min_score": 60},
        ]
    }
    assert evaluate(pred, _facts(signals=["agent_email_repo"], score=75.0)) is True


def test_unknown_predicate_key_raises():
    with pytest.raises(ValueError, match="[Uu]nknown"):
        evaluate({"totally_bogus": True}, _facts())


def test_empty_predicate_raises():
    with pytest.raises(ValueError):
        evaluate({}, _facts())


# ---------------------------------------------------------------------------
# ADR-0017 Decision 1 -- a predicate with more than one recognized key raises,
# rather than silently evaluating only the first one the if-chain reaches.
# ---------------------------------------------------------------------------


def test_and_and_min_score_together_raises_not_silently_picks_and():
    """The exact reproduced bug from ADR-0017: a predicate merging two
    fragments into one dict must raise, not silently evaluate only 'and'
    and drop 'min_score'."""
    pred = {"and": [{"has_signal": "hiring"}], "min_score": 999}
    with pytest.raises(ValueError, match="[Mm]ultiple|more than one"):
        evaluate(pred, _facts(signals=["hiring"], score=0.0))


def test_has_signal_and_not_together_raises():
    pred = {"has_signal": "hiring", "not": {"has_signal": "funding"}}
    with pytest.raises(ValueError):
        evaluate(pred, _facts(signals=["hiring"]))


def test_or_alone_still_works_after_the_multi_key_check():
    """Confirms the multi-key check doesn't false-positive on a predicate
    with exactly one recognized key plus non-predicate metadata is NOT
    supported either -- only the five recognized keys count, and this
    predicate has exactly one of them."""
    pred = {"or": [{"has_signal": "hiring"}]}
    assert evaluate(pred, _facts(signals=["hiring"])) is True


# ---------------------------------------------------------------------------
# ADR-0017 Decision 2 -- a non-dict predicate raises TypeError at the point
# of recursion, not a confusing downstream error.
# ---------------------------------------------------------------------------


def test_a_bare_string_predicate_raises_type_error_with_a_clear_message():
    """Asserts on message content, not just exception type -- mutation-
    confirmed that removing the explicit isinstance check still raises
    SOME TypeError in this exact case (Python's own string-indexing
    failure happens to fire too), so a type-only assertion can't tell the
    explicit, clear check apart from an incidental Python error."""
    with pytest.raises(TypeError, match="must be a dict"):
        evaluate("has_signal", _facts())  # type: ignore[arg-type]


def test_a_malformed_nested_predicate_raises_type_error_at_the_right_level():
    """The malformed value lives inside 'and' -- the error must be raised
    from the recursive call that actually hit it, not a generic failure at
    the top level."""
    pred = {"and": ["not-a-dict"]}
    with pytest.raises(TypeError, match="must be a dict"):
        evaluate(pred, _facts())
