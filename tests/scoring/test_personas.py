"""Tests for scripts/scoring/personas.py.

ADR-0017 Decision 3 is the spec -- the plan named this file and its purpose
("job title -> persona subcategory") but gave no implementation, no test, no
seniority heuristic. Everything here is designed from scratch, not adapted
from a plan reference.
"""

from __future__ import annotations

from scripts.scoring.personas import PersonaDefinition, classify_persona, seniority_level


# ---------------------------------------------------------------------------
# seniority_level
# ---------------------------------------------------------------------------


def test_c_suite_titles_score_highest():
    assert seniority_level("Chief Marketing Officer") == 5
    assert seniority_level("CEO") == 5
    assert seniority_level("President") == 5


def test_vp_titles_score_tier_four():
    assert seniority_level("VP of Sales") == 4
    assert seniority_level("SVP, Engineering") == 4


def test_director_and_head_of_titles_score_tier_three():
    assert seniority_level("Director of Growth") == 3
    assert seniority_level("Head of Marketing") == 3


def test_manager_lead_principal_titles_score_tier_two():
    assert seniority_level("Engineering Manager") == 2
    assert seniority_level("Lead Recruiter") == 2
    assert seniority_level("Principal Engineer") == 2


def test_unrecognized_titles_default_to_tier_one():
    assert seniority_level("Software Engineer") == 1
    assert seniority_level("Marketing Coordinator") == 1


def test_matching_is_case_insensitive():
    assert seniority_level("chief revenue officer") == 5
    assert seniority_level("vp OF sales") == 4


def test_a_title_matching_multiple_tiers_takes_the_higher_one():
    """'VP and Head of Marketing' matches both tier 4 (VP) and tier 3
    (Head of) keywords -- the title is at least as senior as its most
    senior-sounding component."""
    assert seniority_level("VP and Head of Marketing") == 4


# ---------------------------------------------------------------------------
# classify_persona
# ---------------------------------------------------------------------------


def _growth_marketer() -> PersonaDefinition:
    return PersonaDefinition(
        name="Growth Marketer", title_patterns=("growth", "demand gen"), seniority_min=1
    )


def _marketing_leader() -> PersonaDefinition:
    return PersonaDefinition(
        name="Marketing Leader", title_patterns=("marketing",), seniority_min=3
    )


def test_matches_a_persona_whose_title_pattern_is_present():
    result = classify_persona("Growth Marketing Manager", [_growth_marketer()])
    assert result is not None
    assert result.name == "Growth Marketer"


def test_no_matching_persona_returns_none():
    assert classify_persona("Software Engineer", [_growth_marketer()]) is None


def test_title_pattern_matching_is_case_insensitive():
    persona = PersonaDefinition(name="X", title_patterns=("GROWTH",), seniority_min=1)
    assert classify_persona("growth marketer", [persona]) is not None


def test_seniority_floor_excludes_a_title_below_it():
    """'Marketing Coordinator' contains 'marketing' but is tier 1, below
    Marketing Leader's seniority_min=3 -- must not match."""
    assert classify_persona("Marketing Coordinator", [_marketing_leader()]) is None


def test_seniority_floor_includes_a_title_at_or_above_it():
    assert classify_persona("Director of Marketing", [_marketing_leader()]) is not None


def test_first_match_by_input_order_wins():
    """A title matching two personas' patterns returns whichever comes
    first in the input list -- the caller controls priority via ordering."""
    growth = _growth_marketer()
    marketing = PersonaDefinition(
        name="General Marketing", title_patterns=("marketing",), seniority_min=1
    )
    result = classify_persona("Growth Marketing Manager", [growth, marketing])
    assert result.name == "Growth Marketer"

    result_reversed = classify_persona("Growth Marketing Manager", [marketing, growth])
    assert result_reversed.name == "General Marketing"


def test_empty_persona_list_returns_none():
    assert classify_persona("Anything", []) is None


def test_multiple_title_patterns_on_one_persona_any_match():
    persona = PersonaDefinition(
        name="Demand Gen",
        title_patterns=("growth", "demand gen", "performance marketing"),
        seniority_min=1,
    )
    assert classify_persona("Demand Gen Lead", [persona]) is not None
    assert classify_persona("Performance Marketing Manager", [persona]) is not None
    assert classify_persona("Brand Marketing", [persona]) is None
