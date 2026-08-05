# ADR-0009: Verify-layer budget gate

**Status:** Accepted
**Date:** 2026-08-05
**Scope:** Task 2.1 (the gate half) — `scripts/verify/gate.py`

---

## Context

Not every detected change deserves an extraction call. The gate ranks changes and takes the top
N under a budget. The plan's reference implementation (Task 2.1, Step 3) is close to right and
is the starting point — but it makes one promise it does not keep, and this task's own history
makes that promise concretely dangerous rather than theoretically so: Task 2.1a measured raw-HTML
extraction cost ranging **$0.265 to $0.916 per page** (a ~3.5× spread across two real pages), and
Task 2.1c's href-preserving strip — now the production path — brought that down to roughly
$0.013–$0.026 on the same two pages, but did not cap it: that same review found the strip's
`LINKS:` section has no size bound, so a link-dense page can still cost far more than either
measured figure. There is no single "the" extraction cost.

> **Correction, 2026-08-05:** an earlier draft of this section quoted extraction cost as varying
> "35× per page, $0.026 to $0.916" — combining the *cheapest post-strip* figure with the
> *most-expensive pre-strip* figure from two different measurement regimes. Within either regime
> alone the spread is roughly 3.5× (raw) or 2× (stripped), not 35×. Decision 1 does not depend on
> the exact multiplier; ADR-0008 itself said "re-derive this arithmetic before quoting a
> cost-per-account figure," and this ADR did not, the first time.

## Decision 1 — `max_cost_usd` is a real constraint or it does not exist ★

**The finding.** The plan's `VerifyBudget` declares `max_cost_usd: float = 5.0`.
`select_for_verification` never reads it. A caller who sets `max_calls=10, max_cost_usd=1.00`
believes they are capped at a dollar; nothing enforces that, and per-extraction cost is neither
fixed nor fully bounded (see Context above), so no fixed multiplication of `max_calls` by an
assumed per-call cost would be honest either.

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
must not abort selection for the whole batch, the same "never abort a pass over one bad input"
posture `scripts/watch/fetcher.py` states for itself — but it is logged at `warning` with the
offending `source_type`, once per distinct unknown value per call. Silent-and-low is the failure
mode; low-but-visible is the fix.

> **Correction, 2026-08-05:** an earlier draft cited this as "ADR-0005 Decision 1's posture."
> ADR-0005 Decision 1 is about semaphore sizing for the async fetcher and says nothing about error
> handling; the citation was wrong, not just imprecise. Fixed to point at the actual source of the
> pattern — the fetcher module's own documented design point — rather than an ADR decision that
> does not contain it.

**Rejected: raise.** Selection is a pure, frequently-called function; one unexpected string should
not be the mechanism that surfaces a taxonomy gap. A warning that shows up in `fly logs` does the
same job without an availability risk.

## Decision 3 — Deterministic tie-break, and the sort key must not collapse at account_score=0

**Chosen:** sort key is `(priority × (1 + account_score), source_id)` — priority descending via
the first term, `source_id` ascending as the tie-break, so equal-ranked changes always resolve in
the same order regardless of input list order.

**Correction, 2026-08-05 — the shipped key was `priority × account_score`, and independent review
caught that this is a real bug, not a style choice.** A plain product is **zero for every source
type** whenever `account_score` is zero. This ADR's own next sentence says that regime — every
`account_score` is the caller's `0.0` placeholder before Phase 4 exists — is the *common* case,
not an edge case, for as long as scoring is unbuilt. So the original key silently stopped ranking
by source type at all in exactly the situation this document says is normal today: two `ChangeRef`
values of different source types at `account_score=0.0` degrade the whole 5-entry priority table
to a coin flip decided by `source_id`, directly contradicting the module's own docstring claim
that budget binds "on the accounts and source types you care least about." The `1 +` term gives
priority a floor contribution independent of score, so priority ordering holds even at the
all-zeros baseline, while a nonzero `account_score` still scales the ranking up further. This
composition only stays sign-safe because `account_score >= 0` is now enforced on `ChangeRef`
(Decision 4) — a negative score would otherwise flip `1 + account_score` negative and invert
everything.

Before Phase 4 exists, every `account_score` is effectively the caller's placeholder (often
`0.0`), which makes ties the common case, not the edge case, for as long as scoring is unbuilt.

**Rejected: rely on Python's stable sort over input order.** Correct today only if every caller
happens to pass `changes` in a fixed order — an accident of implementation, not a guarantee. This
project has repeatedly valued replayable output (ADR-0007 Decision 5 requires it for signal
events); a selection function feeding an eventual scoring trace should have the same property
from the start.

## Decision 4 — `account_score` and `max_calls` are constrained to non-negative, added on review

Independent review (2026-08-05) tried both fields at negative values and found two unguarded
footguns, neither exercised by the original test suite:

- **`account_score < 0`** flips `1 + account_score` negative in Decision 3's sort key, inverting
  priority ordering end-for-end — a negative score does not merely down-rank an account, it makes
  higher-priority sources rank *worse*. Reproduced: two sources at `account_score=-5.0` selected
  `blog` over `careers`, the opposite of every other test in this suite.
- **`max_calls < 0`** slices as `ranked[:-1]`-style "all but the last N" under Python's list
  slicing, not "select nothing." Reproduced: `max_calls=-1` over 5 candidates selected 4 of them —
  near-maximum spend from the one module whose job is capping it. A caller computing
  `budget - already_spent` and landing negative would get this silently.

**Chosen:** `ChangeRef.account_score: float = Field(default=0.0, ge=0.0)` and
`VerifyBudget.max_calls: int = Field(ge=0)`. Both invalid states become a loud
`pydantic.ValidationError` at construction, not a live wrong-direction selection.

**Rejected: clamp instead of reject.** `max(0, max_calls)` at the call site would also fix the
slicing footgun. Rejected because it treats a caller bug (a negative value should never have been
computed) as a valid input to silently correct, which is the opposite of every other decision in
this ADR — visibility over quiet correction.

## What this does NOT decide

- Real dollar-cost budgeting — deferred per Decision 1, pending a cost estimator.
- Anything about `account_score`'s source or meaning beyond its sign — Phase 4's problem.
- Which source types exist — `_SOURCE_PRIORITY` covers what the plan named; extend it when a new
  extractor (Task 2.1's `docs`/`pricing`/etc.) ships, and Decision 2's warning is what will remind
  a future implementer to do so.
- Duplicate `source_id` values across the input list. `AccountSource.id` is a global integer PK,
  so duplicates can only arise from a caller bug — but if they occur, Decision 3's determinism
  guarantee does not hold for the duplicated pair specifically (two fully-equal sort keys fall
  back to Python's stable-sort input order for just those two elements). Out of scope for a pure
  ranking function to defend against a caller passing malformed input; noted so this ADR does not
  overstate the determinism guarantee as unconditional.

## Consequences

- `VerifyBudget`'s public shape differs from the plan's — `max_cost_usd` is gone. Anything written
  against the plan's exact interface needs updating; nothing in this codebase yet is.
- The gate now logs on bad input instead of staying silent, which is a small, deliberate deviation
  from "pure function, no side effects" — logging is not a side effect this project treats as
  disqualifying (the fetcher and extractor both log extensively from otherwise-pure-ish code).
