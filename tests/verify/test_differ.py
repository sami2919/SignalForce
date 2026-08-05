"""Tests for scripts/verify/differ.py.

ADR-0007 (docs/decisions/0007-diff-based-signal-events.md), including its
2026-08-05 "Implementation note," is the spec. Five decisions, each with a
measured or reproduced failure mode it exists to prevent:

  1. Fact identity is a declared stable key (Fact.identity_fields from
     extractor.py), never the whole object — a plain-content diff produced
     2 signals from 0 real changes on the live Anthropic job board.
  2. Every field type is diffed, not just lists — a scalar field silently
     skipped would miss a pricing change entirely, the exact "looks healthy,
     reports nothing" shape this project keeps finding.
  3. A degraded extraction (current snapshot empty, previous wasn't) must
     never emit a flood of false "removed" signals — the Task 2.2 seeding-
     flood defect wearing different clothes.
  4. A first-ever snapshot (previous is None) seeds silently — emitting N
     additions on day one would poison Phase 3's detection-lag baseline.
  5. One FactChange per change, deterministically ordered, with a visible
     truncation cap (not a threshold that silently doesn't match the cut
     point, per Task 2.2's lesson).
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import ConfigDict

from scripts.verify.extractor import Fact
from scripts.verify.differ import ChangeKind, DiffOutcome, diff_facts


class Item(Fact):
    """A minimal Fact subclass for differ tests — independent of any real
    source type, so these tests don't couple to CareersFacts/JobFact."""

    model_config = ConfigDict(frozen=True)
    identity_fields: ClassVar[tuple[str, ...]] = ("key",)

    key: str
    value: str = ""
    other: str = ""


def _item(key: str, value: str = "v", other: str = "o") -> Item:
    return Item(key=key, value=value, other=other)


# ---------------------------------------------------------------------------
# Decision 1 — identity, not whole-object content
# ---------------------------------------------------------------------------


def test_added_and_removed_by_identity():
    previous = {"items": [_item("1"), _item("2")]}
    current = {"items": [_item("2"), _item("3")]}
    result = diff_facts(previous, current)

    kinds = {(c.kind, c.identity) for c in result.changes}
    assert (ChangeKind.ADDED, ("3",)) in kinds
    assert (ChangeKind.REMOVED, ("1",)) in kinds
    assert not any(c.identity == ("2",) for c in result.changes)


def test_content_change_on_same_identity_is_modified_not_removed_plus_added():
    """The measured defect: a cosmetic delta must produce ONE 'modified',
    never a removed+added pair for the same real-world fact."""
    previous = {"items": [_item("1", value="Engineer")]}
    current = {"items": [_item("1", value="Engineer (New)")]}
    result = diff_facts(previous, current)

    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.kind == ChangeKind.MODIFIED
    assert change.identity == ("1",)


def test_modified_reports_which_subfields_changed():
    previous = {"items": [_item("1", value="A", other="X")]}
    current = {"items": [_item("1", value="B", other="X")]}
    result = diff_facts(previous, current)

    change = result.changes[0]
    assert change.changed_fields == ("value",)
    assert "other" not in change.changed_fields


def test_no_change_when_identical():
    previous = {"items": [_item("1")]}
    current = {"items": [_item("1")]}
    result = diff_facts(previous, current)
    assert result.changes == ()
    assert result.outcome == DiffOutcome.NORMAL


def test_identity_key_uses_declared_field_not_whole_object():
    # Same identity, every other field different -> still ONE modified,
    # never a removed+added pair. This is the direct regression test for
    # the measured Greenhouse defect (2 signals from 0 real changes).
    previous = {"items": [Item(key="5023394008", value="Old Title", other="A")]}
    current = {"items": [Item(key="5023394008", value="New Title", other="B")]}
    result = diff_facts(previous, current)
    assert len(result.changes) == 1
    assert result.changes[0].kind == ChangeKind.MODIFIED


# ---------------------------------------------------------------------------
# Decision 2 — scalars diff too; dicts recurse; unhandled types raise
# ---------------------------------------------------------------------------


def test_scalar_field_change_is_detected():
    previous = {"price": 20.0}
    current = {"price": 25.0}
    result = diff_facts(previous, current)

    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.field == "price"
    assert change.kind == ChangeKind.MODIFIED
    assert change.previous == 20.0
    assert change.current == 25.0


def test_scalar_field_no_change_emits_nothing():
    previous = {"price": 20.0}
    current = {"price": 20.0}
    result = diff_facts(previous, current)
    assert result.changes == ()


def test_nested_dict_field_recurses_with_dotted_field_name():
    previous = {"pricing": {"tier1": 10.0, "tier2": 20.0}}
    current = {"pricing": {"tier1": 10.0, "tier2": 25.0}}
    result = diff_facts(previous, current)

    assert len(result.changes) == 1
    assert result.changes[0].field == "pricing.tier2"


def test_unhandled_field_type_raises():
    previous = {"weird": object()}
    current = {"weird": object()}
    with pytest.raises(TypeError):
        diff_facts(previous, current)


def test_field_disappearing_between_snapshots_raises():
    """A real extractor should not drop a field between calls. Silently
    treating a vanished field as 'went empty' would be indistinguishable
    from a genuine content change."""
    previous = {"jobs": [_item("1")], "price": 20.0}
    current = {"jobs": [_item("1")]}
    with pytest.raises(KeyError):
        diff_facts(previous, current)


def test_new_field_appearing_in_current_is_handled_not_an_error():
    previous = {"jobs": [_item("1")]}
    current = {"jobs": [_item("1")], "price": 20.0}
    result = diff_facts(previous, current)
    assert len(result.changes) == 1
    assert result.changes[0].field == "price"
    assert result.changes[0].previous is None
    assert result.changes[0].current == 20.0


# ---------------------------------------------------------------------------
# Decision 3 — degraded extraction never emits a removal flood
# ---------------------------------------------------------------------------


def test_current_empty_when_previous_was_not_suppresses_removals():
    previous = {"items": [_item("1"), _item("2"), _item("3")]}
    current = {"items": []}
    result = diff_facts(previous, current)

    assert result.outcome == DiffOutcome.DEGRADED
    assert result.changes == ()
    assert "items" in result.degraded_fields


def test_degraded_does_not_suppress_additions_on_other_fields():
    previous = {"items": [_item("1")], "price": 20.0}
    current = {"items": [], "price": 25.0}
    result = diff_facts(previous, current)

    assert result.outcome == DiffOutcome.DEGRADED
    assert "items" in result.degraded_fields
    # The price change is real and must still be reported.
    assert any(c.field == "price" for c in result.changes)
    assert not any(c.field == "items" for c in result.changes)


def test_current_smaller_but_nonempty_is_not_degraded():
    """Decision 3: no fractional threshold. A company closing most of its
    roles is real news, not degradation — only a fully empty current
    snapshot triggers suppression."""
    previous = {"items": [_item("1"), _item("2"), _item("3"), _item("4")]}
    current = {"items": [_item("1")]}
    result = diff_facts(previous, current)

    assert result.outcome == DiffOutcome.NORMAL
    removed = [c for c in result.changes if c.kind == ChangeKind.REMOVED]
    assert len(removed) == 3


def test_both_empty_is_not_degraded():
    previous = {"items": []}
    current = {"items": []}
    result = diff_facts(previous, current)
    assert result.outcome == DiffOutcome.NORMAL
    assert result.changes == ()


# ---------------------------------------------------------------------------
# Decision 4 — first-ever snapshot seeds silently
# ---------------------------------------------------------------------------


def test_no_previous_snapshot_seeds_silently():
    current = {"items": [_item("1"), _item("2")]}
    result = diff_facts(None, current)

    assert result.outcome == DiffOutcome.SEEDING
    assert result.changes == ()


def test_seeding_with_empty_current_is_still_seeding_not_degraded():
    result = diff_facts(None, {"items": []})
    assert result.outcome == DiffOutcome.SEEDING
    assert result.changes == ()


# ---------------------------------------------------------------------------
# Decision 5 — one FactChange per change, deterministic order, visible cap
# ---------------------------------------------------------------------------


def test_changes_are_sorted_deterministically():
    # Three ADDED items (same kind) so ordering AMONG them is only decided
    # by the sort, not by there being just one of each kind — the earlier
    # version of this test had exactly that gap and did not catch removing
    # the sort call (confirmed by mutation: it survived).
    previous = {"items": []}
    current = {"items": [_item("30"), _item("10"), _item("20")]}
    result = diff_facts(previous, current)
    assert [c.identity for c in result.changes] == [("10",), ("20",), ("30",)]

    # Same content, scrambled input order -> identical output order.
    current_scrambled = {"items": [_item("20"), _item("30"), _item("10")]}
    result2 = diff_facts(previous, current_scrambled)
    assert [c.identity for c in result2.changes] == [c.identity for c in result.changes]


def test_truncation_caps_changes_and_reports_true_count():
    previous = {"items": []}
    current = {"items": [_item(str(i)) for i in range(10)]}
    result = diff_facts(previous, current, max_changes=3)

    assert len(result.changes) == 3
    assert result.truncated is True
    assert result.truncated_total == 10


def test_no_truncation_below_cap_reports_untruncated():
    previous = {"items": []}
    current = {"items": [_item("1"), _item("2")]}
    result = diff_facts(previous, current, max_changes=200)

    assert result.truncated is False
    assert result.truncated_total is None


def test_payload_dumps_are_full_facts_not_partial():
    previous = {"items": []}
    current = {"items": [_item("1", value="X")]}
    result = diff_facts(previous, current)
    change = result.changes[0]
    assert change.previous is None
    assert change.current["key"] == "1"
    assert change.current["value"] == "X"


# ---------------------------------------------------------------------------
# Fix round (review of a2ee4c1) — duplicate identity, nested-dict new key,
# None reaching a fact-list field, negative max_changes, cap boundary,
# sort-order determinism on ties.
# ---------------------------------------------------------------------------


def test_duplicate_identity_in_current_raises():
    # Two facts sharing one identity — the degraded title+location fallback
    # collides by construction whenever two real facts share both fields.
    # A pure reorder must never silently report a false MODIFIED, and a
    # real removal must never silently report as a no-op modification —
    # both were the shipped (pre-fix) behavior.
    a = _item("dup", value="A")
    b = Item(key="dup", value="B", other="o")
    with pytest.raises(ValueError, match="duplicate identity"):
        diff_facts({"items": [a, b]}, {"items": [b, a]})


def test_duplicate_identity_in_previous_raises():
    a = _item("dup", value="A")
    b = Item(key="dup", value="B", other="o")
    with pytest.raises(ValueError, match="duplicate identity"):
        diff_facts({"items": [a, b]}, {"items": [a]})


def test_new_nested_dict_field_is_handled_not_a_type_error():
    previous = {"a": 1}
    current = {"a": 1, "pricing": {"tier1": 10.0}}
    result = diff_facts(previous, current)
    assert len(result.changes) == 1
    assert result.changes[0].field == "pricing.tier1"
    assert result.changes[0].previous is None
    assert result.changes[0].current == 10.0


def test_new_key_inside_a_nested_dict_is_handled():
    previous = {"pricing": {"tier1": 10.0}}
    current = {"pricing": {"tier1": 10.0, "tier2": 20.0}}
    result = diff_facts(previous, current)
    assert len(result.changes) == 1
    assert result.changes[0].field == "pricing.tier2"
    assert result.changes[0].previous is None


def test_fact_list_field_going_to_none_is_treated_as_degraded_not_a_crash():
    previous = {"items": [_item("1")]}
    current = {"items": None}
    result = diff_facts(previous, current)
    assert result.outcome == DiffOutcome.DEGRADED
    assert "items" in result.degraded_fields
    assert result.changes == ()


def test_fact_list_field_replaced_with_wrong_type_raises_with_field_name():
    previous = {"items": []}
    current = {"items": 5}
    with pytest.raises(TypeError, match="'items'"):
        diff_facts(previous, current)


def test_negative_max_changes_raises():
    with pytest.raises(ValueError, match="max_changes"):
        diff_facts({"items": []}, {"items": [_item("1")]}, max_changes=-1)


def test_truncation_boundary_exactly_at_cap_is_not_truncated():
    previous = {"items": []}
    current = {"items": [_item(str(i)) for i in range(3)]}
    result = diff_facts(previous, current, max_changes=3)
    assert result.truncated is False
    assert result.truncated_total is None
    assert len(result.changes) == 3


def test_truncation_boundary_one_over_cap_is_truncated():
    previous = {"items": []}
    current = {"items": [_item(str(i)) for i in range(4)]}
    result = diff_facts(previous, current, max_changes=3)
    assert result.truncated is True
    assert result.truncated_total == 4
    assert len(result.changes) == 3


def test_degraded_fields_are_sorted_deterministically():
    previous = {
        "zzz_field": [_item("1")],
        "aaa_field": [_item("2")],
    }
    current = {"zzz_field": [], "aaa_field": []}
    result = diff_facts(previous, current)
    assert result.degraded_fields == ("aaa_field", "zzz_field")


def test_changed_fields_are_sorted_deterministically():
    previous = {"items": [Item(key="1", value="A", other="A")]}
    current = {"items": [Item(key="1", value="B", other="B")]}
    result = diff_facts(previous, current)
    assert result.changes[0].changed_fields == ("other", "value")


def test_sort_key_includes_kind_not_just_field_and_identity():
    # A REMOVED with a SMALL identity and an ADDED with a LARGE identity —
    # identity-only sorting would put REMOVED("1") first; kind-inclusive
    # sorting ("added" < "removed") puts ADDED("9") first regardless. This
    # is the disagreeing case; a same-direction case (e.g. ADDED("1") vs
    # REMOVED("9")) would pass even with kind dropped from the sort key.
    previous = {"items": [_item("1")]}  # only in previous -> REMOVED "1"
    current = {"items": [_item("9")]}  # only in current -> ADDED "9"
    result = diff_facts(previous, current)
    assert [(c.kind, c.identity) for c in result.changes] == [
        (ChangeKind.ADDED, ("9",)),
        (ChangeKind.REMOVED, ("1",)),
    ]
