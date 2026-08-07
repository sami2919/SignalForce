# ADR-0022: Retire `scripts/db.py` and `scripts/outcome_tracker.py`

**Status:** Accepted
**Date:** 2026-08-06
**Scope:** Task 5.4 — retire the legacy SQLite feedback-loop layer (deferred from
Task 0.1 by D8)

---

## Context

Task 0.1's D8 ruling kept `scripts/db.py` alive because `scripts/outcome_tracker.py`
depended on its four tables (`campaigns`, `tracked_signals`, `outreach_events`,
`outcome_events`) and Task 5.0's replacement (`Contact`/`Outreach`, tied to
`signal_events` via `triggering_signal_ids`) didn't exist yet. It landed in Task 5.0
(committed `cf3aef5`). This task closes the deferral.

The plan's stated task ("port `outcome_tracker.py`, keeping its public function
signatures so callers don't change") assumes there are callers whose signatures
matter. Verified before writing anything, per this session's standing rule of
checking plan claims against reality rather than porting code on the strength of the
plan's word alone:

**Finding 1 — zero production callers.** `grep -rn "outcome_tracker\|scripts\.db\b"`
across `scripts/`, `skills/`, `n8n-workflows/` (excluding the module's own files and
its own tests) returns nothing. No scanner, no scoring code, no dashboard route, no
skill ever calls `log_signal`, `log_outreach`, `log_outcome`, `create_campaign`,
`get_conversion_rates`, or `get_best_performing_signals`. The only callers are its
own test file.

**Finding 2 — zero real data to backfill.** The plan's own checklist item ("write a
one-shot backfill script if `data/signalforce.db` holds real rows worth keeping")
is moot: `data/` does not exist in this worktree at all. There is nothing to
migrate.

**Finding 3 — the new schema doesn't have a like-for-like target for the old API
shape.** The legacy tables key everything off `campaign_id` (`Campaign` = "a
specific ICP / client engagement") and a five-value `outcome_type` enum (`reply`,
`positive_reply`, `meeting_scheduled`, `meeting_completed`, `deal_closed`). The new
schema's closest analog to `Campaign` is `Tenant` (a *customer instance* of
SignalForce, not an outbound segment/campaign within one tenant — `Audience` is
closer in spirit but predicate-based, not a manually created row) and `Outreach` has
only `replied_at` (a timestamp) plus one free-text `reply_classification` column —
there's no structural equivalent of the old five-stage funnel. Porting
`get_conversion_rates`'s signature exactly would mean inventing a `campaign_id`
concept the new schema doesn't have, or silently reinterpreting it as `tenant_id`
(wrong: a single tenant's data would report as "one campaign" always, and the
grouped `signal_type` breakdown loses per-campaign framing that never had a real
equivalent target once campaigns themselves stopped existing).

## Decision 1 — delete outright rather than port ★

**Chosen:** delete `scripts/db.py`, `scripts/outcome_tracker.py`,
`tests/unit/test_db.py`, and `tests/unit/test_outcome_tracker.py`. Do not write a
schema-adapted `outcome_tracker.py` against the new tables.

**Reasoning.** Porting a zero-caller, zero-data module "because the plan said to
keep its signatures" would resurrect an unused analytics API against a schema it was
never designed for, and Task 5.3's `compute_lift` already is the schema-native,
statistically rigorous replacement for the exact question `get_conversion_rates` and
`get_best_performing_signals` were trying to answer ("did the outreach work") — a
two-proportion z-test against `Outreach.replied_at` is a strictly better answer than
funnel percentages with no significance test, computed from real `Contact`/
`Outreach`/`SignalEvent` rows instead of a parallel manually-populated table nobody
calls. Writing a second, unused analytics module alongside it would be exactly the
kind of speculative code this project's own conventions rule out ("Simplicity
First... Don't add features... beyond what the task requires").

**Rejected: port with adapted signatures.** Would produce code with the same
property that made the original dead — no caller — on a schema mapping that has to
guess at what `campaign_id` should become, adding surface area and test burden for
zero verified benefit. If a future task (most likely a dashboard funnel widget)
needs conversion-rate reporting, it should be written directly against
`Contact`/`Outreach`/`SignalEvent` at that point, informed by what the caller
actually needs to display — the same "build the callable when there's a real
consumer" pattern used for `fact_snapshots` (ADR-0014) and `compute_lift`'s deferred
wiring (ADR-0021).

**Rejected: keep `scripts/db.py` alive indefinitely as documented-dead code.** The
whole point of Task 0.1's D8 deferral was that it was temporary, gated on
`outcome_tracker.py`'s dependency existing. That dependency is now provably absent
(Finding 1); keeping a SQLite engine, four ORM tables, and their tests around with no
caller and no data is unexplained surface area for a future reader, not a safety
margin.

## What this does NOT decide

- **A new conversion-rate / funnel report against the Postgres schema.** Out of
  scope until a real caller (dashboard widget, most likely) needs one. `compute_lift`
  (Task 5.3) already covers the "did the signal work" question at the account-cohort
  level; a full outreach funnel view is a separate, not-yet-requested feature.
- **`reply_classification`'s taxonomy.** `Outreach.reply_classification` is a free
  `str | None` column (ADR-0019) with no enum enforced at the DB or app layer today.
  Deciding its allowed values is deferred to whichever task first writes to it.
