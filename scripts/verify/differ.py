"""Turn two consecutive fact snapshots into the list of changes between them.

ADR-0007 (docs/decisions/0007-diff-based-signal-events.md), including its
2026-08-05 "Implementation note," is the spec. A `signal_event` row is a
change, not a state — Sami (Rippling interview, 13:42): "design for updates
and not rebuilds… the difference first and not snapshot first."

Five decisions, each fixing a defect in the plan's original sketch:

1. Fact identity is a declared stable key (`Fact.identity_fields`, already
   implemented in extractor.py), never the whole object. Read directly from
   the Fact instance — identity is declared once, in the extractor, not
   re-declared here.
2. Every field type is diffed: lists of Fact by identity, scalars by
   inequality, nested dicts by recursion (dotted field names). An unhandled
   type raises. A field silently skipped is a change silently missed.
3. A degraded extraction (current snapshot's list field goes fully empty
   while the previous snapshot's wasn't) never emits a removal flood —
   removals for that field are suppressed and it is named in
   `degraded_fields`. No fractional threshold: a company closing most of
   its roles is real news, not degradation.
4. No previous snapshot (`previous is None`) means this is the first-ever
   observation: record it, emit nothing, `outcome=SEEDING`.
5. One `FactChange` per change, deterministically ordered (field, kind,
   identity), with a visible cap — `truncated` and `truncated_total` must
   always be read together, never `truncated_total` alone.

Scope: this is a pure function. It does not write `SignalEvent` rows —
persistence is a wiring task for whenever fact-snapshot storage is decided.
When that lands: `SignalEvent.payload` is a plain JSON column, not
MutableDict-wrapped (Task 0.1 finding) — assign a whole new dict, never
mutate one fetched from a row in place.
"""

from __future__ import annotations

from enum import Enum
from typing import Sequence

from pydantic import BaseModel, ConfigDict

from scripts.verify.extractor import Fact

_SCALAR_TYPES = (str, int, float, bool, type(None))


class ChangeKind(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


class DiffOutcome(str, Enum):
    NORMAL = "normal"
    SEEDING = "seeding"
    DEGRADED = "degraded"


class FactChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    kind: ChangeKind
    # The fact's identity for a list-item change; (field_name,) for a scalar
    # or nested-dict change. Always a tuple, never a bare str|None, so
    # consumers don't special-case the two shapes.
    identity: tuple[str, ...]
    previous: object = None
    current: object = None
    # Populated only for MODIFIED — which sub-fields actually differ. This is
    # what ADR-0007 Decision 1's "reports … modified with the changed
    # sub-fields" concretely means.
    changed_fields: tuple[str, ...] = ()


class DiffResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: DiffOutcome
    changes: tuple[FactChange, ...]
    truncated: bool = False
    truncated_total: int | None = None
    # Which list-valued top-level fields triggered Decision 3's
    # removal-suppression. A snapshot with multiple list fields (a future
    # source type with both `jobs` and `press_releases`) must not collapse
    # "one field went empty" into an undifferentiated top-level flag.
    degraded_fields: tuple[str, ...] = ()


def _fact_identity(fact: Fact) -> tuple[str, ...]:
    return tuple(str(getattr(fact, f)) for f in fact.identity_fields)


def _diff_fact_list(
    field: str, previous: Sequence[Fact], current: Sequence[Fact]
) -> tuple[list[FactChange], bool]:
    """Diff one list-of-Fact field by identity. Returns (changes, degraded).

    degraded is True iff `current` is empty while `previous` was not — in
    that case NO removals are emitted for this field (Decision 3); the
    caller is responsible for surfacing the field name in `degraded_fields`.
    """
    prev_by_id = {_fact_identity(f): f for f in previous}
    curr_by_id = {_fact_identity(f): f for f in current}

    degraded = bool(previous) and not current
    changes: list[FactChange] = []

    for identity, curr_fact in curr_by_id.items():
        prev_fact = prev_by_id.get(identity)
        if prev_fact is None:
            changes.append(
                FactChange(
                    field=field,
                    kind=ChangeKind.ADDED,
                    identity=identity,
                    previous=None,
                    current=curr_fact.model_dump(mode="json"),
                )
            )
            continue

        prev_dump = prev_fact.model_dump(mode="json")
        curr_dump = curr_fact.model_dump(mode="json")
        changed_fields = tuple(sorted(k for k in curr_dump if curr_dump[k] != prev_dump.get(k)))
        if changed_fields:
            changes.append(
                FactChange(
                    field=field,
                    kind=ChangeKind.MODIFIED,
                    identity=identity,
                    previous=prev_dump,
                    current=curr_dump,
                    changed_fields=changed_fields,
                )
            )

    if not degraded:
        for identity, prev_fact in prev_by_id.items():
            if identity not in curr_by_id:
                changes.append(
                    FactChange(
                        field=field,
                        kind=ChangeKind.REMOVED,
                        identity=identity,
                        previous=prev_fact.model_dump(mode="json"),
                        current=None,
                    )
                )

    return changes, degraded


def _diff_scalar(field: str, previous: object, current: object) -> list[FactChange]:
    if previous == current:
        return []
    return [
        FactChange(
            field=field,
            kind=ChangeKind.MODIFIED,
            identity=(field,),
            previous=previous,
            current=current,
        )
    ]


def _diff_value(
    field: str, previous: object, current: object
) -> tuple[list[FactChange], list[str]]:
    """Dispatch one field by type. Returns (changes, degraded_field_names).

    Raises TypeError for any value that is neither a Sequence of Fact, a
    scalar, nor a dict (Decision 2: unhandled types raise, they don't skip).
    """
    if isinstance(current, dict) and isinstance(previous, dict):
        changes: list[FactChange] = []
        degraded: list[str] = []
        all_keys = set(previous) | set(current)
        for key in all_keys:
            if key not in current:
                raise KeyError(
                    f"field {field}.{key} present in previous snapshot but missing "
                    "from current — a real extractor should not drop a field between "
                    "calls; treating this as 'went empty' would be indistinguishable "
                    "from a genuine content change"
                )
            sub_changes, sub_degraded = _diff_value(
                f"{field}.{key}", previous.get(key), current[key]
            )
            changes.extend(sub_changes)
            degraded.extend(sub_degraded)
        return changes, degraded

    if _is_fact_sequence(current) or _is_fact_sequence(previous):
        prev_seq = previous if previous is not None else []
        changes, is_degraded = _diff_fact_list(field, prev_seq, current)
        return changes, [field] if is_degraded else []

    if isinstance(current, _SCALAR_TYPES) and isinstance(previous, _SCALAR_TYPES):
        return _diff_scalar(field, previous, current), []

    raise TypeError(
        f"field {field!r} has an unhandled value type for diffing: "
        f"previous={type(previous).__name__}, current={type(current).__name__}. "
        "Snapshots may only contain Sequence[Fact], scalars, or nested dicts."
    )


def _is_fact_sequence(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, bytes, dict)):
        return False
    if not isinstance(value, Sequence):
        return False
    return all(isinstance(item, Fact) for item in value) if value else True


def diff_facts(
    previous: dict[str, object] | None,
    current: dict[str, object],
    *,
    # 200 is a number to measure against, not trust blindly (Task 2.2's
    # lesson: a cap whose warning threshold doesn't match the actual cut
    # point hides a real sampling gap for as long as nobody checks).
    max_changes: int = 200,
) -> DiffResult:
    """Diff two fact snapshots. See module docstring for the five decisions
    this implements. `previous=None` means "no snapshot exists yet" and
    always seeds silently (Decision 4), regardless of what `current` holds.
    """
    if previous is None:
        return DiffResult(outcome=DiffOutcome.SEEDING, changes=())

    all_changes: list[FactChange] = []
    degraded_fields: list[str] = []
    for key in set(previous) | set(current):
        if key not in current:
            raise KeyError(
                f"field {key!r} present in previous snapshot but missing from "
                "current — a real extractor should not drop a field between calls"
            )
        sub_changes, sub_degraded = _diff_value(key, previous.get(key), current[key])
        all_changes.extend(sub_changes)
        degraded_fields.extend(sub_degraded)

    all_changes.sort(key=lambda c: (c.field, c.kind.value, c.identity))

    truncated_total = len(all_changes)
    truncated = truncated_total > max_changes
    kept = tuple(all_changes[:max_changes])

    return DiffResult(
        outcome=DiffOutcome.DEGRADED if degraded_fields else DiffOutcome.NORMAL,
        changes=kept,
        truncated=truncated,
        truncated_total=truncated_total if truncated else None,
        degraded_fields=tuple(sorted(degraded_fields)),
    )
