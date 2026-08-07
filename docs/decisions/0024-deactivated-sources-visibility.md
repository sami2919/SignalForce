# ADR-0024: Surface `deactivated_sources` count on the health page

**Status:** Accepted
**Date:** 2026-08-07
**Scope:** Closes the second half of the plan's CRITICAL GAP #4 (Failure Modes
table): "on deactivation, enqueue re-resolution rather than giving up; surface
`deactivated_sources` count on the health page." The re-resolution recovery path
was already built (`ADR-0004` Decision 6, `scripts/registry/store.py`) — the
visibility half was never added. Confirmed by grep: zero references to
`deactivated` anywhere in `scripts/web/`.

---

## Context

`AccountSource.active` (ADR-0001) flips to `False` after `consecutive_failures`
crosses the deactivation threshold (Task 1.3b). Once that happens, the source
stops being probed at all — no error, no signal, indistinguishable from a
genuinely quiet account unless someone thinks to query `active = False` directly.
That's the exact silent-permanent failure mode CRITICAL GAP #4 named. Re-resolution
gives deactivated sources a path back to life; this task makes their existence
visible in the first place, without which the recovery path itself is unmonitored.

## Decision 1 — one total count, not a per-source-type breakdown

**Chosen:** a single `deactivated_sources: int` metric (count of
`AccountSource` rows with `active = False`, scoped to the tenant), displayed
alongside the existing recall/lag metric cards at the top of `/dashboard/health`.

**Reasoning.** The plan's own wording ("surface `deactivated_sources` count") asks
for a count, not a breakdown. A single number answers the operational question this
gap exists for — "is anything silently going dark right now" — at a glance. A
per-source-type table would be genuinely useful too, but nothing today reads that
level of detail and no caller has asked for it; adding it now would be exactly the
speculative-scope-creep this project's conventions rule out. If the plain count
ever needs a next click ("which ones, and why"), that's a real follow-up task
informed by an actual need, same "build it when there's a real caller" pattern used
for `fact_snapshots` (ADR-0014) and `compute_lift`'s deferred wiring (ADR-0021).

## Decision 2 — reuse the health route's existing no-tenant-configured guard,
don't add a second one

**Chosen:** `deactivated_sources` is computed inside the same `if tenant_id is
None` branch the route already has for `recall_report`/`health_rows` — `None`
when no tenant is configured (renders as `—`), a real `int` (including `0`)
otherwise. No new error-handling path.

## What this does NOT decide

- Any UI for triggering re-resolution manually from the dashboard (the recovery
  path already runs automatically per ADR-0004 Decision 6; this task is
  visibility-only, matching the dashboard's read-only design, ADR-0018).
- A per-source-type or per-account deactivation breakdown (Decision 1).
