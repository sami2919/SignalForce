# ADR-0007: Diff-based signal events

**Status:** Accepted
**Date:** 2026-08-04
**Scope:** Phase 2, Task 2.3 — `scripts/verify/differ.py`, `signal_events` writes

---

## Context

Sami (Rippling interview, 13:42): *"design for updates and not rebuilds… the difference first
and not snapshot first."* A `signal_event` row is a change, not a state.

The watch layer (Phase 1) tells us a page's normalized content hash moved. That is all it knows
— *something* changed. The verify layer turns a changed page into structured facts. This task
turns two consecutive fact snapshots into the list of changes between them, which is what gets
scored (Phase 4) and measured for recall and detection lag (Phase 3).

The plan (Task 2.3, Step 3) sketches `diff_facts`. Three of its properties are wrong in ways
that matter, and all three are the silent-failure shape this project keeps finding.

## Decision 1 — Fact identity is a declared stable key, not the whole object ★

**This is the decision the task turns on.**

The plan defines identity as `json.dumps(item, sort_keys=True)` — a fact *is* its full content.
Any change to any field therefore produces a `removed` of the old version plus an `added` of the
new one. There is no `modified`.

**Measured against the real Anthropic job board (2026-08-04):** 50 jobs. Applying a 6-character
cosmetic delta to one title yields `added=1, removed=1` — **two signals from zero real changes**.
And the delta is not hypothetical: Task 1.2 measured this exact page rendering an unresolved
i18n key (`tags.new` instead of `New`) in ~17% of fetches. That wobble lands in the title.
Whole-object identity converts the churn Phase 1 already fought into fake hiring signals.

**Chosen:** each fact type declares an identity key. A fact is the *same* fact across snapshots
iff its identity matches; the diff then reports `added`, `removed`, or `modified` with the
changed sub-fields. Where the source provides a stable id, use it — measured: **50 of 50**
Greenhouse jobs carry a unique numeric id in the URL (`/jobs/5023394008`). Where it does not,
fall back to a declared tuple of semantically-identifying fields (e.g. title + location),
never the whole object.

**Rejected: whole-object hashing (the plan's design).** Above.
**Rejected: fuzzy/similarity matching** (treat facts as the same if >90% similar). Handles the
no-stable-id case without a declared key, but introduces a threshold nobody can defend, makes
the diff non-deterministic under small edits, and would be unexplainable in a scoring trace.
**Rejected: positional identity** (item N in the list is the same fact as item N before).
Free, and wrong the moment a page reorders — which job boards do constantly.

**Accepted cost:** each fact type needs a declared key, so adding a fact type is not free. That
is the correct place to pay: the alternative is paying in false signals forever.

## Decision 2 — Never silently skip a field. Scalars diff too

The plan's loop does `if not isinstance(curr_items, list): continue`. Every scalar field is
therefore invisible to the diff, with no error and no log line.

For a **pricing page** the scalar *is* the entire signal — a plan moving \$20 → \$25, or a
"contact us" tier appearing, is exactly what we watch pricing for. The plan's differ would
report nothing and look perfectly healthy, which is the `pushed:`-qualifier failure (ADR-0006
Decision 2) and the soft-404 (ADR-0004 Decision 3) in a third costume.

**Chosen:** dispatch on type — lists diff by identity (Decision 1), scalars diff by inequality
and emit `modified`, dicts recurse. An unhandled type raises rather than `continue`s.

**Rejected: lists-only, documented as a limitation.** A documented silent no-op is still a
silent no-op. The project has now been bitten by this exact shape four times.

## Decision 3 — A degraded extraction must never emit removals ★

If the current snapshot is empty or radically smaller than the previous one — the extractor
failed, returned `{}`, the fetch hit a soft-404, or the page moved behind JS — then *every*
previously-known fact is absent, and a naive differ reports all of them as `removed`.

That is a flood of false "job removed" / "customer removed" signals, and it is precisely the
seeding-flood defect found in Task 2.2 wearing different clothes: a partial failure upstream
becoming confident wrong output downstream.

**Chosen:** removals are suppressed and the diff is marked degraded **only when the current
snapshot is empty while the previous was not**. Additions still emit (a page that gained facts
is not degraded). The degraded outcome is recorded on the run, not swallowed.

**No fractional threshold, deliberately.** The obvious design is "suppress if we lost more than
X% of facts", and picking X today would be inventing a defensible-*sounding* number with nothing
behind it. Worse, any fraction fires on the legitimate case that matters most: a company closing
8 of 10 roles is real news, arguably the strongest signal the page can carry. The empty-snapshot
case needs no threshold to defend — an empty extraction is a failure, not news. Phase 3 will show
whether partial-loss suppression is needed and what the number should be; ADR-0004 already
established the house rule that mitigations wait for measurement.

**Rejected: trusting the extractor.** The failure this decision exists to prevent.
**Rejected: requiring two consecutive confirmations before emitting a removal.** Robust, and it
doubles detection lag for removals — the same trade Task 1.3 rejected in favour of
confirm-on-change. Revisit only if the fraction threshold proves noisy in Phase 3.

**Accepted cost:** a company that genuinely deletes its whole careers page produces a degraded
diff rather than a removal storm. That is the right default — and it is *visible*, which
"source health" (Task 3.3) is built to act on.

## Decision 4 — The first snapshot seeds silently

Consistent with ADR-0006 Decision 5, ruled by the user for the repo ledger: the first time we
extract facts from a source, everything is "new to us" but nothing has *changed*. Emitting N
additions on first observation would mean the day we add an account is the day it looks most
active, poisoning Phase 3's detection-lag baseline with events whose `occurred_at` is unknowable.

**Chosen:** no previous snapshot ⇒ record the snapshot, emit nothing, mark the diff as seeding.

**Rejected: treat empty previous as all-added (the plan's `test_treats_empty_previous_as_all_added`).**
That test encodes the opposite behaviour and must be inverted, not kept. Noting it explicitly
because it is the kind of plan artifact that gets copied into the implementation unexamined.

## Decision 5 — One `signal_event` row per `FactChange`, with a visible cap

**Chosen:** one row per change. Scoring, recall, and detection lag all operate per change; a
batch row would force every consumer to unpack JSON and re-derive counts, which is the "every
consumer reimplements the comparison and they drift apart" failure the task docstring names.

**Cap:** a single diff emits at most N rows; beyond that the diff is truncated and **recorded as
truncated with its true count** — the lesson from Task 2.2, where a warning threshold that did
not match the actual cut point hid a real 5% sampling gap for three runs.

**`payload` is assigned as a whole new dict, never mutated in place** — carried forward from the
Task 0.1 finding: `SignalEvent.payload` is a plain `JSON` column, not `MutableDict`-wrapped, so
in-place mutation neither persists nor errors.

**Ordering is deterministic** (sort by field, then kind, then identity key) so a replayed diff
produces byte-identical output. Phase 4's scoring trace is only replayable if its inputs are.

## What this does NOT decide

- **The extractor itself.** What turns a page into facts, and its schema per source type, is
  Task 2.1's other half and needs `ANTHROPIC_API_KEY`, still blank.
- **Where fact snapshots are stored.** The differ is a pure function over two dicts; the
  snapshot store is a separate question and may reuse `probes` or need its own table.
- **Account creation for scanner-discovered orgs.** `SignalEvent.account_id` is non-nullable
  while `agent_email_scanner` finds orgs with no `accounts` row. Still open from ADR-0006, and
  it blocks persisting *those* signals — not these, which originate from `account_sources`.
- **Scoring.** Which changes matter, and how much, is Phase 4.
- **The removal-fraction threshold's value.** Set a defensible default; tune it on Phase 3 data,
  not now.

## Consequences

- Fact schemas gain a required identity key. Adding a fact type without one must fail loudly.
- `modified` becomes a first-class change kind, so downstream scoring must handle three kinds,
  not two.
- Degraded and seeding diffs are outcomes that are neither "no change" nor "error". Phase 3's
  source-health metrics must be able to tell all four apart, or the recall denominator is wrong.
- The differ is being built before its producer exists. It is a pure function and fully
  testable, but it will not be exercised end-to-end until the extractor lands — so its
  real-data validation is limited to synthetic-but-real fact structures until then. Do not
  claim end-to-end verification of this task.

## Implementation note, 2026-08-05 — the concrete interface

The decisions above leave the exact shapes unpinned. Fixing them here before writing code, since
`scripts/verify/extractor.py` (Task 2.1a) now exists and the differ must consume its actual output
rather than the plan's generic dicts.

**Input:** `diff_facts(previous: dict[str, object] | None, current: dict[str, object], *, max_changes: int = 200) -> DiffResult`.
Each dict is a **snapshot**: a mapping of field name to either a `Sequence[Fact]` (diffed by
identity, Decision 1), a scalar (`str | int | float | bool | None`, diffed by inequality,
Decision 2), or a nested `dict` (recursed, Decision 2, field names joined with `.`). Any other
value type raises `TypeError` — Decision 2's "unhandled type raises rather than continues." A key
present in `previous` but absent from `current` also raises: a real extractor should not drop a
field between calls, and silently treating a disappeared field as "went empty" would be
indistinguishable from a genuine content change.

Snapshots are `dict[str, object]`, not the extractor's Pydantic models directly, so the differ
never depends on `CareersFacts` or any other per-source-type model — a caller builds
`{"jobs": list(facts.jobs)}` and the differ works identically for a hypothetical `PricingFacts`.
This is the boundary Decision 1's "What this does NOT decide — where fact snapshots are stored"
was pointing at: storage, whenever it's built, reconstructs Fact instances from persisted JSON
and hands the differ the same shape it always took.

**Identity extraction is generic, not duplicated.** `Fact.identity_fields` (already implemented
in `extractor.py` for Decision 1) is read directly — `tuple(str(getattr(fact, f)) for f in
fact.identity_fields)` — so a fact type only declares its identity once, in the extractor, not
again in the differ.

**Output:** `DiffResult(outcome: SEEDING | DEGRADED | NORMAL, changes: tuple[FactChange, ...],
truncated: bool, truncated_total: int | None, degraded_fields: tuple[str, ...])`.
`degraded_fields` names which list-valued fields specifically triggered Decision 3's
removal-suppression, so a snapshot with multiple list fields (e.g. a future source type with
both `jobs` and `press_releases`) doesn't collapse "one field went empty" into an
undifferentiated top-level flag.

**`FactChange`** carries `field`, `kind` (`added | removed | modified`), `identity: tuple[str, ...]`
(the fact's identity for list items; `(field_name,)` for a scalar change, kept as a tuple for
type uniformity rather than a special-cased `str | None`), `previous`, `current` (full dumps,
one side `None` for `added`/`removed`), and `changed_fields: tuple[str, ...]` — populated only for
`modified`, naming which sub-fields actually differ, which is what "reports … modified with the
changed sub-fields" (Decision 1) concretely means.

**Cap default: 200.** Chosen the same way this project has chosen every other cap this
session — as a number to be measured against, not trusted blindly. Task 2.2's lesson (a warning
threshold that didn't match the actual cut point hid a real 5% sampling gap for three runs)
applies directly: `truncated` and `truncated_total` must always be checked together, never
`truncated_total` alone, since the true count is what makes a silent-looking cap visible.

**Scope: this task does not write `SignalEvent` rows.** `diff_facts` is a pure function, same
posture as the extractor and the gate — persistence (Decision 5's "payload assigned as a whole
new dict, never mutated in place," carried forward from the Task 0.1 finding) is a wiring task
for whenever fact-snapshot storage is decided, not this one.

---

## Appendix — measurements (live, 2026-08-04)

```
boards.greenhouse.io/anthropic -> 200, 69,573 bytes, 50 job links

STABLE IDENTITY AVAILABLE
  https://job-boards.greenhouse.io/anthropic/jobs/5023394008
  numeric ids extracted : 50 of 50   all unique: True

WHOLE-OBJECT IDENTITY (the plan's _key), 6-char cosmetic delta on 1 of 50 jobs
  added=1  removed=1   -> 2 signals from 0 real changes

  Task 1.2 measured this same page rendering an unresolved i18n key
  ("tags.new" instead of "New") in ~17% of fetches. That delta lands in
  the title, so this is the observed churn, not a hypothetical one.
```
