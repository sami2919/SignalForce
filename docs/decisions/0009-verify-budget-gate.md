# ADR-0009: Verify-layer budget gate

**Status:** Accepted
**Date:** 2026-08-05
**Scope:** Task 2.1 (the gate half) — `scripts/verify/gate.py`

---

## Context

Not every detected change deserves an extraction call. The gate ranks changes and takes the top
N under a budget. The plan's reference implementation (Task 2.1, Step 3) is close to right and
is the starting point — but it makes one promise it does not keep, and this task's own history
(Task 2.1a/c measured extraction cost varying **35× per page**, $0.026 to $0.916) makes that
promise concretely dangerous rather than theoretically so.

## Decision 1 — `max_cost_usd` is a real constraint or it does not exist ★

**The finding.** The plan's `VerifyBudget` declares `max_cost_usd: float = 5.0`.
`select_for_verification` never reads it. A caller who sets `max_calls=10, max_cost_usd=1.00`
believes they are capped at a dollar; nothing enforces that, and Task 2.1a/c's own measurements
show 10 selected extractions could cost anywhere from $0.26 to $9.16 depending on which pages
they land on.

**Chosen:** `max_cost_usd` is **removed** from `VerifyBudget` for this task. `select_for_verification`
enforces `max_calls` only, and says so.

**Rejected: implement it properly now.** A real dollar cap needs a per-candidate cost estimate —
`ChangeRef` has no field for one, and nothing yet knows how to estimate extraction cost before
running it (page size is the closest proxy this project has measured, and it is not on
`ChangeRef` either). Building that estimator is real work with its own decisions, and doing it
inside this task means the gate's correctness is entangled with an estimator's correctness.

**Rejected: keep the field, document it as unenforced.** This is the shape ADR-0007 Decision 2
and this project's whole run of findings argue against: a parameter that looks like a promise and
silently isn't one. A future caller reading `VerifyBudget(max_calls=50, max_cost_usd=2.00)` has
every reason to believe both numbers bind. The field's mere presence is the defect.

**Rejected: keep the field, raise if a non-default value is passed.** Considered — it converts
silent non-enforcement into a loud one. Rejected as more code than the field is worth right now:
removing it is simpler, and the moment a real cost estimator exists, re-adding `max_cost_usd`
with actual teeth is a small, deliberate follow-up rather than un-silencing a landmine.

**Consequence:** dollar-cost budgeting is a known gap, not a hidden one. When account volume or
per-account extraction cost makes `max_calls` too blunt an instrument, add it back with a real
per-candidate cost estimate — do not resurrect the unenforced field.

## Decision 2 — Unknown source types are visible, not silently downweighted

**The finding.** `_SOURCE_PRIORITY.get(c.source_type, 0.1)` gives any unrecognized string a low
but nonzero weight. A typo'd source type (`"carrers"`) or a new source type added to the
extractor without updating this table both silently rank near the bottom — no error, no log,
indistinguishable from "we deliberately deprioritize this."

**Chosen:** an unrecognized `source_type` still gets the 0.1 fallback weight — one bad `ChangeRef`
must not abort selection for the whole batch, consistent with the fetcher's "never raise on one
input" posture (ADR-0005 Decision 1) — but it is logged at `warning` with the offending
`source_type`, once per distinct unknown value per call. Silent-and-low is the failure mode;
low-but-visible is the fix.

**Rejected: raise.** Selection is a pure, frequently-called function; one unexpected string should
not be the mechanism that surfaces a taxonomy gap. A warning that shows up in `fly logs` does the
same job without an availability risk.

## Decision 3 — Deterministic tie-break

**Chosen:** sort key is `(priority × account_score, source_id)`, both descending is wrong for the
tie-break — `source_id` ascending as the secondary key, so equal-scored changes always resolve in
the same order regardless of input list order. Before Phase 4 exists, every `account_score` is
effectively the caller's placeholder (often `0.0`), which makes ties the common case, not the
edge case, for as long as scoring is unbuilt.

**Rejected: rely on Python's stable sort over input order.** Correct today only if every caller
happens to pass `changes` in a fixed order — an accident of implementation, not a guarantee. This
project has repeatedly valued replayable output (ADR-0007 Decision 5 requires it for signal
events); a selection function feeding an eventual scoring trace should have the same property
from the start.

## What this does NOT decide

- Real dollar-cost budgeting — deferred per Decision 1, pending a cost estimator.
- Anything about `account_score`'s source or meaning — Phase 4's problem.
- Which source types exist — `_SOURCE_PRIORITY` covers what the plan named; extend it when a new
  extractor (Task 2.1's `docs`/`pricing`/etc.) ships, and Decision 2's warning is what will remind
  a future implementer to do so.

## Consequences

- `VerifyBudget`'s public shape differs from the plan's — `max_cost_usd` is gone. Anything written
  against the plan's exact interface needs updating; nothing in this codebase yet is.
- The gate now logs on bad input instead of staying silent, which is a small, deliberate deviation
  from "pure function, no side effects" — logging is not a side effect this project treats as
  disqualifying (the fetcher and extractor both log extensively from otherwise-pure-ish code).
