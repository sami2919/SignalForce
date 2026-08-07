# ADR-0016: Wiring the scoring engine to a caller

**Status:** Accepted
**Date:** 2026-08-07
**Scope:** `scripts/scoring/wiring.py` (new), `scripts/watch/runner.py` (add a scoring
stage), `scripts/verify/wiring.py` (feed a real `account_score` into the gate)

---

## Context

`score_account`/`zero_out` (Task 4.1, ADR-0015) are pure functions with no caller —
same starting state every other `measure`/`verify` pure function has had before its
own wiring task. Two real gaps this closes: no `Score` row has ever been persisted
from real `signal_events`, and `scripts/verify/gate.py`'s `ChangeRef.account_score` has
been a hardcoded `0.0` placeholder since ADR-0009, because nothing computed a real one.

Unlike ADR-0011/0013/0014, this introduces **no new cost or infrastructure** — pure
computation, no LLM calls, riding the existing daily worker. No deploy sign-off gate
applies here the way it did for those; this ADR still precedes code per this project's
standing practice, but proceeds straight to implementation once written.

## Decision 1 — `signal_type -> (base_weight, is_icp)` mapping table

**The gap.** `SignalInput` needs `base_weight` and `is_icp` per signal; `SignalEvent`
carries neither — it has `signal_type`, `payload`, `confidence`. Something has to map
one to the other, the same shape `scripts/verify/gate.py`'s `_SOURCE_PRIORITY` already
solved for `source_type -> priority`.

**Chosen:**

| signal_type | base_weight | is_icp | Why |
|---|---|---|---|
| `agent_email_repo` | 0.6 | **True** | Task 2.2's own framing: this is "the bullseye" — finding an org whose *codebase* already uses an agent framework + an email-sending library identifies **fit** (they match the target profile structurally), not a timing event. It says nothing about *when* they became a good fit. |
| `hiring` | 0.8 | False | A new job posting is a concrete, dated **intent** signal — a buying window indicator, not a fit indicator. |
| `funding` | 0.7 | False | A funding event is timing/intent — new budget, a reason to act now. |
| `stack_change` | 0.6 | False | Adopting or dropping a tool is intent, weighted slightly below hiring/funding since it's a weaker, more inferential signal today. |

`base_weight` is further multiplied by `SignalEvent.confidence` (default `1.0` today,
since nothing sets it otherwise yet — but free to wire in once something does, same
"leave the column real, not fake" posture ADR-0011 used for `parse_success_rate`).

An unrecognized `signal_type` gets a `0.5`/`is_icp=False` fallback, logged once per
distinct unknown value — same posture as `gate.py`'s Decision 2 for unrecognized
`source_type`, not silently downweighted with no trace.

**Rejected: derive weight purely from `confidence`.** `confidence` is a per-event
quality signal (how sure the extraction was), not a per-type importance signal (how
much a hiring event matters vs. a stack-change event). Conflating them would make an
uncertain hiring signal indistinguishable from a confident stack-change signal, when
they answer different questions.

**Explicitly a starting point, not a calibrated model** — same footing `_SOURCE_PRIORITY`
was accepted on: a defensible table given the domain narrative, extend/tune it once
enough real signal volume exists to see whether it predicts anything.

## Decision 2 — Scoring reads a 90-day trailing window of `signal_events`

**Chosen:** load signals for an account from `[now - 90 days, now]`. `HALF_LIFE_DAYS =
14` means a 90-day-old signal has decayed to `0.5^(90/14) ≈ 1.2%` of its original
weight — functionally inert. Bounding the query window keeps cost flat as
`signal_events` accumulates history, the same reasoning ADR-0013 Decision 3 used for
the 7-day recall window, tuned to this decay curve instead of that one's cadence.

**Rejected: unbounded history.** Would scan every signal ever recorded for query cost
that buys nothing — anything past ~90 days contributes a rounding error to the score.

## Decision 3 — `Score` rows are append-only, one per scoring run, never upserted

**Chosen:** every scoring run inserts a **new** `Score` row (`Score` has no unique
constraint on `(tenant_id, account_id)` in the schema, unlike `SourceHealthRecord` or
`FactSnapshot` — deliberately, since the plan's own schema comment calls this
"Replayable trace" and a dashboard (Task 4.3) will eventually want score-over-time, not
just latest-score). Volume: one row per account per day (~20/day today) — two orders
of magnitude below `probes`, no retention concern at this scale, unlike Task 3.4.

**Rejected: upsert-in-place, matching `SourceHealthRecord`/`FactSnapshot`.** Those
tables intentionally hold only "the current state." A score's whole value is in its
history — zeroing out old scores would defeat "replayable," the property this table
was built for.

## Decision 4 — New `scoring` stage in the daily worker, after verify, before Phase 3
postprocess

**Chosen:** `scripts/scoring/wiring.py`'s `run_scoring_stage` is called from
`_cli_scan` after the verify stage (ADR-0014) and before Phase 3's `daily_postprocess`
(ADR-0013) — independently fail-isolated, same posture as every other stage in
`_cli_scan`. It must run *after* verify: today's freshly emitted `signal_events` (from
today's confirmed changes) should be visible to today's score. It runs before Phase 3
postprocess for no strict dependency reason — keeping "stages that produce/consume
signals and scores" grouped ahead of "stages that measure the watch/verify pipeline's
own health" is the only rationale, and it's a weak one; either order would work.

**Rejected: a separate scheduled machine.** Same reasoning as ADR-0013 Decision 1 for
health/recall/retention: nothing about scoring needs sub-daily resolution, and it's
pure computation riding data the daily worker already produces.

## Decision 5 — The gate uses the MOST RECENTLY STORED score, never same-run

**The circularity, resolved.** `scripts/verify/wiring.py`'s gate needs an
`account_score` to prioritize which confirmed changes get extracted *before* today's
extraction happens — but today's `Score` (Decision 4) is computed *from* today's
`signal_events`, which don't exist until *after* verify runs. There is no way for
today's verify pass to use today's score; it was never possible to close that loop
same-run.

**Chosen:** `run_verify_stage` queries the most recent existing `Score.score` for the
account (whatever was last computed — yesterday's, in steady state) when building each
`ChangeRef`. An account with no `Score` row yet (cold start) falls back to the existing
`0.0` default — consistent with every other "first observation, no prior data" case
this project has handled (ADR-0006 Decision 5, ADR-0007 Decision 4, ADR-0010's
holdout-scan baseline).

**Rejected: block verify on scoring somehow running first.** Would need a stable score
before ANY signal has ever been observed for a new account — impossible by
construction, not merely inconvenient.

## What this does NOT decide

- **Calibrating the `signal_type` weight table against real outcomes** — Decision 1 is
  a starting point, not a tuned model; needs real signal volume and (eventually)
  outreach outcome data (Phase 5) to validate against.
- **A `Score` retention policy.** Not needed at today's volume; revisit if this table's
  growth rate ever approaches `probes`'s pre-Task-3.4 trajectory.
- **Task 4.2/4.3** (personas, audiences, dashboard) — those are the actual consumers of
  a `Score` history; this task only makes sure one gets produced.

## Consequences

- `scripts/verify/wiring.py` gains a read dependency on `Score` (querying the latest
  row per account) that didn't exist before — a one-directional dependency, not a
  cycle, but worth knowing when reasoning about wiring-module boundaries in this
  codebase going forward.
- The gate's account-prioritization now reflects real signal history starting from
  whatever day this ships, with a `0.0`-baseline warm-up period for existing accounts
  until their first `Score` row lands.
