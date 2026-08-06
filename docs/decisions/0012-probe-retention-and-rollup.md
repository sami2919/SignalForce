# ADR-0012: Probe retention and rollup

**Status:** Accepted
**Date:** 2026-08-06
**Scope:** Phase 3, Task 3.4 — `scripts/measure/retention.py`

---

## Context

`probes` is the only unbounded table in the schema. The plan's arithmetic: 5,000 accounts ×
4 sources/day = 20,000 rows/day ≈ 1.1 GB/year, blowing Neon's 0.5 GB free tier in ~5 months.
Two-tier retention (unchanged: 30 days, changed: 180 days) with rollup-before-prune keeps
storage flat, per the plan's own numbers (~144 MB steady state at 5,000 accounts).

Task 3.3 (ADR-0011) built `compute_health`/`detect_anomaly` as pure functions with no DB
table yet — deliberately deferred, since nothing had data to write. This task is partly the
wiring task ADR-0011 punted to: it needs a real, persisted `source_health` row per
`(tenant_id, source_type, run_date)` to check "does a rollup exist for this day" before
pruning.

## Decision 1 — `rollup_and_prune` computes and persists its own rollups; it does not assume a
caller already ran Task 3.3's health computation for the days it's about to prune

**The finding.** The plan's Step 3 states the algorithm as: *"1. Find distinct probe days
older than the shorter cutoff. 2. For each day: ensure a source_health row exists (compute
it if missing)."* That's unambiguous — this function is self-sufficient. But the plan's own
test, `test_never_prunes_a_day_with_no_source_health_rollup`, creates a 45-day-old probe,
calls `rollup_and_prune` with **no** `seeded_health` fixture, and asserts
`unchanged_pruned == 0` and `skipped_days_missing_rollup == 1` — i.e., it expects the function
to do *nothing* about the missing rollup, contradicting Step 2's "compute it if missing" in
the same task's own spec. This is the same shape as Task 2.3's inverted seed test (ADR-0007
Decision 4) and Task 2.2's always-`None` recency filter: a plan artifact whose test encodes
the opposite of its own stated design, evidently uncaught because nothing had run it yet.

**Chosen:** the plan's Step 3 algorithm is correct and is what gets implemented —
`rollup_and_prune` ensures a `source_health` row exists for every candidate day as part of
its own execution (idempotent upsert; see Decision 3), then prunes only days it has just
confirmed. `skipped_days_missing_rollup` is reserved for a **genuine** persistence failure —
the upsert is attempted, and the function re-reads the row back before trusting it (Decision
3's verify-after-write step); if that confirmation comes back empty for any reason, the day
is skipped and its probes are never touched, regardless of the specific cause. This is a
stronger safety property than the plan's test implies (which only ever exercised the
"nothing tried" case, not a genuine failure), so a new test replaces it: force the
`source_health` insert to fail (Decision 2), and prove the day's probes survive.

**Rejected: literally implement the plan's test as-is.** Encodes "skip a day just because
`compute_health` was never externally seeded" as correct behavior, directly contradicting the
task's own Step 3. Would make the safety property weaker than what's actually needed: the
real risk this task exists to prevent is deleting data with no aggregate to replace it, and
that risk is about **whether the rollup landed**, not about **who called it**.

## Decision 2 — The safety-property test uses genuine failure injection, not fixture omission

Per Decision 1, the replacement test for the safety property monkeypatches the `source_health`
insert step to raise, then asserts the affected day is recorded as skipped and its probes are
not pruned. This proves the "verify the rollup landed before deleting" ordering is real
enforcement, not an assumption — same evidentiary standard this project has used throughout
(e.g. Task 0.3a's mutation-tested defenses, Task 3.2's mutation-tested matching logic).

## Decision 3 — Upsert via select-then-insert-if-missing, not raw `ON CONFLICT DO NOTHING`

**The finding.** The plan's Step 3 prose suggests Postgres's
`ON CONFLICT (tenant_id, source_type, run_date) DO NOTHING`. This project's test suite runs
every `measure/` module against an in-memory SQLite engine (see `tests/measure/test_holdout.py`),
while production is Postgres — the same split flagged as a minor risk back in Task 0.2. SQLite
supports its own `ON CONFLICT` syntax, but SQLAlchemy's dialect-specific upsert helpers
(`postgresql.insert(...).on_conflict_do_nothing()` vs `sqlite.insert(...)...`) are two
different code paths for one operation, adding real complexity for a table this codebase's own
worker writes to **sequentially, not concurrently** — there is one scheduled worker machine
(Task 0.3), not a pool of them racing each other.

**Chosen:** query for an existing `(tenant_id, source_type, run_date)` row first; if absent,
`compute_health` over that day's probes and insert; catch `IntegrityError` on the insert as a
"someone else already wrote it, and it's now Decision 1's job to re-read and confirm" case
rather than a real error. This is portable across both dialects with one code path, and the
race it's guarding against (two writers inserting the same day simultaneously) isn't a
scenario this system's actual deployment produces today. The `IntegrityError` catch is a
backstop for correctness under a future concurrent-worker change, not the primary mechanism —
same "belt and suspenders, not the belt" posture as `select_holdout`'s consistent-hashing fix
(ADR-0010 Decision 0) being correct on its own merits, with the constraint as a second line.

**Rejected: the plan's `ON CONFLICT DO NOTHING`.** Correct for Postgres alone, forces a
dialect branch to keep SQLite tests meaningful, for a race this deployment doesn't have.

## Decision 4 — Candidate days are every distinct day with probes older than the *shorter*
cutoff (30 days); the longer cutoff (180 days) needs no separate day-scan

Any day old enough to make a `changed=True` probe eligible for pruning (180+ days) is, by
definition, also old enough to make an unchanged probe on that same day eligible (30+ days) —
day age is monotonic. So scanning for distinct `(tenant_id, source_type, date(fetched_at))`
groups among probes older than 30 days covers every day either retention rule could possibly
touch; no second scan at the 180-day mark is needed. Whether a given day's rollup actually
leads to any *changed* pruning still depends on that day individually passing the 180-day
check at prune time.

## Decision 5 — `ProbeOutcome.succeeded` derives from `content_hash is not None`

**Chosen:** reuses the exact success signal `scripts/watch/runner.py` already computes for
itself (`elif result.content_hash is not None: source.consecutive_failures = 0`) — a probe
"succeeded" iff a hash was actually computed. `robots_blocked` probes have no content_hash
(never fetched) and so count as not-succeeded for this aggregate, even though the runner
correctly treats robots-blocking as "not a failure" for deactivation purposes — those are two
different questions (should we penalize the source vs. did this fetch produce data), and
`fetch_success_rate` is answering the second one.

**Rejected: deriving success from `status_code`/`error` directly.** Would re-derive a rule
the watch layer has already computed and stored via its own control flow, and risks drifting
out of sync with it if that logic changes later.

## Decision 6 — `RetentionReport` counts

`rows_rolled_up` counts **newly created** `source_health` rows only (an already-existing row
found by the Decision 3 lookup does not increment it — this is what makes
`test_rollup_is_idempotent`'s "second run rolls up 0" true). `skipped_days_missing_rollup`
counts **days**, not probes. `batches` counts DELETE batches executed across the whole call
(both unchanged and changed pruning share the batch counter — `test_prune_is_batched`'s
2500 rows at `batch_size=1000` expects `batches >= 3`, matching `1000 + 1000 + 500`).

## What this does NOT decide

- **Wiring into the scheduled worker.** Per the plan's Step 5, `rollup_and_prune` runs after
  the watch pass; this task builds and tests the callable, matching this phase's established
  scoping (Task 3.1/3.2/3.3 all built callables before any scheduling task touched them).
- **A separate, explicit Task 3.3-triggered health computation in the worker.** Given Decision
  1, retention no longer strictly depends on one existing — whether the worker *also* calls
  `compute_health` daily (for health/anomaly visibility on **recent**, not-yet-prunable days)
  is a wiring-task decision, not this one's.

## Consequences

- `source_health` is now a real, persisted table — the first `measure/` table used by two
  different tasks' logic (3.3's pure functions, 3.4's persistence). A reader must know
  `compute_health` (3.3) is pure/DB-free while `rollup_and_prune` (3.4) is the thing that
  actually writes `source_health` rows in this codebase today.
- `parse_success_rate`/`zero_result_rate` are persisted as `NULL` for every rollup this task
  creates, same as ADR-0011 Decision 1 — retention doesn't change that scope, it just means
  rows written today are honestly incomplete on those two columns until the verify layer is
  wired.
