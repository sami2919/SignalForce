# ADR-0014: Wiring the verify layer (extractor + differ + gate) to a caller

**Status:** Accepted
**Date:** 2026-08-07
**Scope:** `scripts/verify/wiring.py` (new), `scripts/storage/models.py` (new `FactSnapshot`
table + migration), `scripts/watch/runner.py` (pass `on_confirmed_change` into
`run_watch_pass`)

---

## Context

The verify layer — `extract_careers` (Task 2.1a/2.1c), `diff_facts` (Task 2.3),
`select_for_verification` (Task 2.1/ADR-0009) — is fully built, reviewed, and
mutation-tested. It has never had a caller. No fact has ever been extracted from a real
snapshot in production; `diff_facts` has never run against two real snapshots; no
`signal_events` row driven by an actual page change has ever been written. This closes
that gap. The last open question blocking it (Task 2.1's own ledger note): *where fact
snapshots are stored, so the differ has a "previous" to compare against.*

`run_watch_pass` (`scripts/watch/runner.py`) already has the hook this needs:
`on_confirmed_change: Callable[[int, str], None]`, invoked once per source with a
**confirmed** real change, carrying `(source_id, body)`. Nothing has ever passed a
callback into it — `_cli_scan` currently calls `run_watch_pass(tenant_id)` with no
argument. The retained body exists only in memory for the duration of that call
(ADR-0008 Decision 2's memory-bounded retention); wiring must consume it inside the
same async pass, not after.

## Decision 1 — A new `fact_snapshots` table stores the CURRENT snapshot only, one row
per `account_source_id`, upserted in place

**Chosen:** `fact_snapshots(id, tenant_id FK, account_source_id FK UNIQUE, source_type,
captured_at, payload JSONB)`. `payload` holds the just-extracted `CareersFacts` in plain
JSON (`{"jobs": [...]}`, each job a plain dict via Pydantic serialization). Every verify
run for a source: read the existing row (if any) as `previous`, deserialize it back into
real `Fact` objects for `diff_facts`, then **overwrite** the row with the current
snapshot — regardless of `diff_facts`'s outcome (`SEEDING`/`NORMAL`/`DEGRADED`), since
the stored snapshot always advances to "what we most recently confirmed," never staying
pinned to an older observation.

**Rejected: an append-only snapshot history table.** `diff_facts` only ever needs the
single most recent snapshot — an append-only table would grow unboundedly (the same
shape Task 3.4 was built to cap for `probes`) for data nothing reads except the single
newest row. If a future task wants historical fact snapshots for its own reason, that's
a new, explicit decision with its own read pattern, not a speculative table now — same
reasoning ADR-0011/0013 already applied to `parse_success_rate` and recall/anomaly
persistence.

**Rejected: store the snapshot on `AccountSource` itself as a JSON column.** Works for
careers-only today but conflates "where a source is fetched from" with "what facts were
last extracted from it," and a future second source type (`pricing`, etc.) would need
its own snapshot shape sharing the same row — a separate table scales to that without
schema churn on `AccountSource`.

## Decision 2 — New `scripts/verify/wiring.py`, called from `_cli_scan` right after
`run_watch_pass` returns

**Chosen:** `_cli_scan` passes an `on_confirmed_change` callback into `run_watch_pass`
that populates a local `dict[int, str]` (`source_id -> body`) during the pass. After the
pass returns, `run_verify_stage(tenant_id, session, run_id, retained_bodies, now,
budget=...)` runs: filters retained sources to `source_type == "careers"` (Decision 3),
builds `ChangeRef`s, runs `select_for_verification`, and for each selected source:
extracts, diffs against `fact_snapshots`, emits `SignalEvent` rows, and updates the
snapshot. This is a new, focused module — same shape as `daily_postprocess.py` for
Phase 3 — not folded into `daily_postprocess.py` itself, since verify operates on
`Probe`-adjacent-but-distinct data (retained bodies, fact snapshots, signal events) with
no overlap with health/recall/retention's tables.

**Rejected: run verify as its own separately-scheduled machine.** Unlike Task 3.1's
holdout scan, verify has no reason to run at a different cadence than the watch pass —
it only has work to do on confirmed changes from that same pass, and the retained bodies
that make it cheap to run only exist for that pass's lifetime.

## Decision 3 — Careers-only scope, matching what's actually implemented

Confirmed-change sources are filtered to `source_type == "careers"` before entering the
gate. `extract_careers` is the only extractor that exists; running it against a
`pricing`/`blog`/`docs`/`changelog` page's HTML would silently misapply a careers-page
prompt. `select_for_verification`'s priority table already covers all five source types
for when a second extractor ships — Decision 2 in ADR-0009 already explains that
`_SOURCE_PRIORITY` will need new entries wired to new extractors, not new logic in the
gate itself.

## Decision 4 — Daily budget, and its real dollar cost ★ (user sign-off obtained)

**Chosen, after explicit confirmation:** `VerifyBudget(max_calls=10)` per tenant per day
— tighter than the `20` initially proposed. User's call: keep the cap lower while this
path is new and unproven, trading headroom for a lower worst-case bill. Task 2.1c's
measured post-strip cost was $0.031–$0.124 per extraction on two real pages; worst case
(10 calls/day at the higher measured figure): **~$1.24/day, ~$37/month**. Organic daily
changed-and-careers volume at today's ~20-account population is expected to be low
single digits most days, so 10 is still slack for growth, not a number the system will
usually hit — just less slack than 20 would have given.

**This is the one decision in this ADR that changes the project's ongoing cash cost, and
was asked explicitly before implementation** — the same gate ADR-0011/0013 already used
for new Fly infrastructure. `max_cost_usd` real enforcement is still out of scope
(ADR-0009 Decision 1 — no per-candidate cost estimator exists); `max_calls` is the only
lever, so the number itself carries the whole cost decision. Revisit upward once real
`cost_usd` data (Decision 5) shows actual daily spend comfortably under the cap for a
sustained period.

## Decision 5 — Cost tracked on `scan_runs`, computed from usage tokens, not measured
independently

**Chosen:** `cost_usd = input_tokens * $5/1e6 + output_tokens * $25/1e6` (Opus 5
pricing, matching the arithmetic Task 2.1a's own measured figures were checked against),
summed across every extraction this run and written to the existing
`scan_runs.cost_usd`/`verify_calls`/`signals_emitted` columns — fields the schema has
carried since Phase 0 with nothing populating them until now.

**Known approximation, stated plainly:** this formula ignores `cache_read_input_tokens`
(billed separately, at a steep discount off the base input rate). Any run that hits the
system-prompt cache slightly **undercounts** true spend by the (small) cache-read
charge. Not corrected here — getting it exactly right needs Anthropic's cache-read
per-token rate hardcoded alongside the other two, for a correction on the order of a few
percent of an already-approximate number. Worth fixing if this number is ever used for
real budget enforcement rather than visibility.

## Decision 6 — Per-source failures are isolated; nothing aborts the batch

Each selected `ChangeRef`'s extract → diff → persist sequence is wrapped independently.
An `ExtractorError` (API failure) or diff failure (`ValueError` on identity collision,
per `differ.py`'s own documented contract) is logged with full context and that source
is skipped — no `SignalEvent`s for it, no snapshot update (so tomorrow's diff still
compares against the last *successfully confirmed* snapshot, not a corrupted one). This
is the same "one bad input never aborts a pass" posture already applied at every other
call site in this codebase (`fetcher.py`, `gate.py`, `differ.py`'s own docstring
naming this exact posture as the expectation for whoever wires it).

## Decision 7 — `signal_type="hiring"`, one `SignalEvent` row per `FactChange`

Matches the schema's own documented enum (`signal_type — agent_email_repo|hiring|
funding|stack_change`) and ADR-0007 Decision 5 (one row per change, not a batch row).
`payload` carries the `FactChange`'s own fields (`field`, `kind`, `identity`,
`previous`, `current`, `changed_fields`) as a plain new dict (never mutate a dict
pulled from a row — Task 0.1's finding). `account_id` is resolved via the
`AccountSource` the change came from; `account_source_id` and `scan_run_id` (the
triggering watch pass's `run_id`) are both set, giving a full trace from signal back to
source and run.

## What this does NOT decide

- Real dollar-cost enforcement at the gate (`max_cost_usd`) — still deferred, per
  ADR-0009 Decision 1, pending a real per-candidate cost estimator.
- Extractors for any source type besides `careers`.
- Anything about how `signal_events` get consumed downstream (scoring, outreach) — Phase
  4's problem, unaffected by this task.
- `account_score`'s real value — still the `0.0` placeholder ADR-0009 already assumed.

## Consequences

- This is the first task in the project with an ongoing, usage-driven dollar cost beyond
  Fly/Neon's flat infrastructure bill. `scan_runs.cost_usd` becomes the place that cost
  is now visible, run by run.
- `fact_snapshots` is a second table (besides `AccountSource.last_hash`) tracking "what
  did we last see" for a source, at a different fidelity — a reader needs both:
  `last_hash` for hash-level watch state, `fact_snapshots` for fact-level verify state.
- A source that never has a confirmed change never gets a `fact_snapshots` row — that's
  correct (nothing to extract), not a gap, but worth remembering when reasoning about
  "why does this account have no fact snapshot yet."
