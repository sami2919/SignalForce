# ADR-0013: Wiring Phase 3 into the scheduled worker

**Status:** Accepted
**Date:** 2026-08-06
**Scope:** Phase 3 wiring — `scripts/measure/recall_report.py`, `scripts/measure/daily_postprocess.py`,
`scripts/watch/runner.py` (extend `_cli_scan`), new Fly scheduled machine, `fly.toml` documentation

---

## Context

Tasks 3.1-3.4 are built, tested, mutation-tested, and demonstrated on real/realistic data —
but every one of their own ADRs explicitly deferred scheduling/deployment as a follow-on
task requiring separate sign-off (ADR-0010 Decision 1's scope exclusion is the clearest
statement of this). This is that task. Four callables need real cadences:

| Task | Callable | Needs |
|---|---|---|
| 3.1 | `run_deep_scan` | its own cadence, **more frequent than daily** (ADR-0010 Decision 1) |
| 3.2 | `compute_recall` | no caller anywhere yet — needs a loader that turns `Probe`/`HoldoutScan` rows into `DetectedChange` lists over a bounded window |
| 3.3 | `compute_health` / `detect_anomaly` | a caller that persists today's rollup and checks it against trailing history |
| 3.4 | `rollup_and_prune` | plan's own Step 5: "runs after the watch pass and after Task 3.3's health computation, never before" |

## Decision 1 — Tasks 3.2, 3.3, 3.4 ride the existing daily worker; only Task 3.1 gets new infra

**Chosen:** extend `scripts/watch/runner.py`'s `_cli_scan()` — the entrypoint the existing
daily Fly scheduled machine (`signalforce-worker`, `--schedule daily`) already runs — to
call, after `run_watch_pass` completes: (a) today's health rollup + anomaly check per
source_type (3.3), (b) a trailing-window recall report (3.2), (c) `rollup_and_prune` (3.4),
in that order. None of these need their own cadence — they all operate on data the daily
watch pass and the (separately scheduled) holdout scan have already produced, and the
plan's own Step 5 for 3.4 states this exact ordering. **Task 3.1 is the only one that
needs genuinely new Fly infrastructure**: `run_deep_scan` must run more often than daily
(ADR-0010 Decision 1's whole point — a same-cadence deep scan can only measure lag in
multiples of 24h), so it needs its own scheduled machine at `--schedule hourly`,
entrypoint `python -m scripts.measure.holdout` (built and CLI-ready since Task 3.1).

**Rejected: a second new scheduled machine for 3.2/3.3/3.4 too.** Would double the
machines to reason about (ADR-0003's own "Consequences" section already flags this as a
cost) for no capability gain — nothing about health/recall/retention needs sub-daily
resolution, and bundling them into the existing worker costs zero new infrastructure.

## Decision 2 — Each post-processing stage is independently wrapped; one failing does not
block the others or retroactively corrupt the watch pass's own recorded status

**Chosen:** health, recall, and retention each run inside their own try/except. The
`scan_runs` row — the primary artifact ADR-0005 Decision 5 already protects — is finalized
by `run_watch_pass` before any of this runs and is never touched by it. If a post-processing
stage raises, it's logged with full context and the CLI still returns exit code 1 at the
end (visible in `fly machine list` / logs), but a failure in, say, retention does not
prevent that day's health rollup or recall report from having already run and logged
successfully.

**Rejected: let any stage's exception propagate and abort the rest.** Exactly the silent-
gap failure mode ADR-0003's own context section names as the worker's serious risk ("no
data for that day") — except here it would be worse, silently dropping THREE kinds of data
instead of one, from an unrelated stage's bug.

**Rejected: swallow all stage failures silently (exit 0 regardless).** Reintroduces the
invisible-failure shape this entire phase exists to catch, at the wiring layer this time.
A failed post-processing run must be visible, even though the watch pass itself succeeded.

## Decision 3 — Recall computation window is a trailing 7 days

**Chosen:** `compute_recall_for_tenant` loads `DetectedChange` lists from both `Probe` and
`HoldoutScan` over `[now - 7 days, now]`, for the **same holdout account selection**
`run_deep_scan` uses (`select_holdout` with the same `seed`/`holdout_size`, so the two
sides being compared are the same population — ADR-0010 Decision 1's "doubly
instrumented" requirement). Seven days gives multiple watch-layer cycles (daily cadence)
and many holdout cycles (hourly cadence) inside one bounded query, without letting the
scanned range grow unbounded as the system accumulates history.

**Rejected: an unbounded "all history" window.** ADR-0010's own Consequences section
already warns against this: *"compute_recall's per-key sequential matching means its
inputs must be genuinely representative of one coherent measurement window — mixing events
from non-overlapping windows into one call would misattribute matches across window
boundaries."* An ever-growing window is exactly that mixing, and the query cost grows
without bound as a bonus problem.

**Rejected: matching the retention window (30 days).** No reason recall's measurement
window should be coupled to the unrelated storage-retention constant; 7 days is chosen on
its own merits (cycle coverage), and happens to comfortably fit inside the 30-day floor
either way — no risk of retention pruning data recall still needs.

## Decision 4 — Recall and anomaly results are logged (structured JSON), not persisted to
a new table

**Chosen:** `RecallReport` and any `Anomaly` found are logged via the existing structured
JSON logger (`scripts.logging_config`, already in place per ADR-0003 Decision 5) with full
field detail as `extra=`. `fly logs` is already the established debugging surface for this
worker; nothing here needs to be queried relationally yet.

**Rejected: a new `recall_reports` / `anomalies` table.** Neither the plan nor any prior
ADR in this phase specifies one, and building persistence for data nobody has a query
pattern for yet repeats the exact mistake Task 3.3 (ADR-0011) explicitly avoided for
`parse_success_rate`/`zero_result_rate` — don't build storage ahead of a real read need.
If a future task wants a trend view across days, that's a new, explicit decision with its
own read pattern in hand, not a speculative table today.

## Decision 5 — Anomaly detection runs per active `source_type`, on `fetch_success_rate`
only, matching ADR-0011's scope

Iterates the tenant's distinct active `source_type`s, computes+persists each one's
`SourceHealthRecord` for today, then calls `detect_anomaly` against that source_type's
trailing (up to 14) prior `SourceHealthRecord.fetch_success_rate` values with
`direction="low_is_bad"` — the only metric ADR-0011 populates with real data today.
`parse_success_rate`/`zero_result_rate` stay `None` and are not checked, consistent with
that ADR's explicit scope.

## Decision 6 — New Fly machine requires explicit deploy sign-off before execution

Per this session's standing practice for shared-system/production changes: the code and
tests for this task proceed without further confirmation (local, reversible, no
production contact). Creating the new `signalforce-holdout` scheduled machine and
redeploying the worker with the extended `_cli_scan` are **shared-system actions** and
require explicit user confirmation immediately before execution, the same gate applied to
every prior deploy in this project (Task 0.3b, the Phase 1 worker schedule, Neon password
rotation).

## What this does NOT decide

- **A dashboard or alert delivery surface for anomalies/recall reports.** Decision 4 logs
  them; reading those logs today is manual (`fly logs`), same as every other operational
  signal in this project so far.
- **Multi-tenant fan-out.** Both the existing worker and this wiring operate on the single
  `TENANT_SLUG` env var, matching every existing entrypoint in this codebase.
- **The holdout scan machine's exact cost at scale.** Estimated cheap (5 accounts, hourly,
  sub-5s runs per Task 3.1's own measurement) but not re-measured against a live Fly bill
  here — a verification step for after deployment, same posture ADR-0003 Decision 4 took
  for the web machine's suspend behavior.

## Consequences

- Three machine-days of infrastructure become two Fly scheduled machines total (`signalforce-worker`
  daily, `signalforce-holdout` hourly) plus the existing web machine — a modest, bounded
  increase, not a new category of infra.
- The daily worker's single run now does more work and can fail in more places; Decision 2's
  independent-stage wrapping is what keeps that from becoming a bigger single point of failure
  than before.
- `fly logs` becomes the only durable record of recall/anomaly findings until Decision 4 is
  revisited — a real limitation worth stating plainly if this wiring is referenced as
  "Phase 3 is live."
