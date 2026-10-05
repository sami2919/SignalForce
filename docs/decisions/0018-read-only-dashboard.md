# ADR-0018: Read-only dashboard

**Status:** Accepted
**Date:** 2026-08-07
**Scope:** Task 4.3 — `scripts/web/routes_dashboard.py`, `scripts/web/templates/*.html`

---

## Context

ADR-0002 already decided the framework question (FastAPI + Jinja2 + HTMX, no build
step, no SPA — Decision 2) and the liveness/readiness split. This ADR covers what's
left: what each of the four pages actually queries, and two real gaps in the plan's
own spec for this task.

**Gap 1 — the route table and the file list disagree.** The plan's route table lists
four pages including `/dashboard/runs`; its "Files" list names only three content
templates (`accounts`, `account_detail`, `health`) plus `base` — `runs.html` is
missing. Fixed here by adding it; same shape as Task 4.2's `personas.py` gap (a route
promised, but the file it needs was never listed).

**Gap 2 — the plan's test fixture doesn't exist.** `test_dashboard_renders(seeded_db)`
references a `seeded_db` fixture never defined anywhere in the plan or this codebase.
Built from scratch here, matching this project's established DB-test pattern
(in-memory SQLite + `sessionmaker`, `get_session` monkeypatched at the route module,
same shape `tests/web/test_health.py` already uses for `scripts.web.routes_health`).

## Decision 1 — Recall/detection-lag on the health page are computed LIVE, not read
from a persisted trend

**Chosen:** `/dashboard/health` calls `compute_recall_for_tenant` (ADR-0013) directly,
on every request. ADR-0013 Decision 4 explicitly deferred persisting recall reports:
*"If a future task wants a trend view across days, that's a new, explicit decision
with its own read pattern in hand."* This task is that future task arriving — and the
plan's own spec only asks for **current** recall/p50/p95, not a historical trend
chart. A live computation over the same bounded 7-day window ADR-0013 already
established satisfies that exactly, at effectively zero cost (a pure function over two
bounded queries), without building a new persistence layer for a chart nobody asked
for yet.

**Rejected: add a `recall_reports` table now.** Would be exactly the speculative
storage ADR-0011/0013 already declined twice this project — building for a trend view
this task's own spec doesn't request.

`zero_result_rate` (the third of `SourceHealthRecord`'s three columns) stays visibly
`None`/"not yet available" on the health page — ADR-0011's scope was never expanded,
and the dashboard must not paper over that gap by omitting the field or faking a
number.

## Decision 2 — Single-tenant scoping via `TENANT_SLUG`, matching every other
entrypoint

**Chosen:** every route resolves the tenant from `os.environ["TENANT_SLUG"]`, the same
env var every CLI entrypoint in this codebase already reads. If the env var is unset,
or the tenant has no data yet, pages render a friendly empty state (never a 500) —
matches ADR-0002's health-endpoint posture ("never raise") extended to the dashboard.

**Rejected: a tenant selector / multi-tenant UI.** ADR-0001 Decision 4 explicitly
deferred auth entirely; a tenant switcher with no auth in front of it would let anyone
who can reach the dashboard read any tenant's data by URL-guessing an id — building
multi-tenant UI ahead of the auth story that has to gate it is a real security gap
this task has no business introducing.

## Decision 3 — The account-detail page's zero-out table reuses
`scoring/wiring.py`'s existing signal loader, not a second implementation

**Chosen:** `_load_signal_inputs` (private in `scripts/scoring/wiring.py`, used by
`run_scoring_stage` to turn `signal_events` into `SignalInput` objects) is promoted to
public and reused directly by the dashboard to build the same list, then calls
`zero_out` (Task 4.1) once per distinct `signal_type` present to show "score without
this signal type" next to the real score — the literal feature ADR-0015's own framing
names ("zero out which signal one by one and see which one was actually doing the
work"). Reusing the loader means the dashboard's zero-out table can never silently
drift from what `run_scoring_stage` actually scored — same "second caller promotes a
helper to public" pattern already used for `load_active_account_ids`,
`ensure_rollup`/`find_rollup`, and `load_outcomes_for_day`.

**Rejected: a second signal-loading query written for the dashboard.** Two
implementations of "turn `signal_events` into `SignalInput`s" is exactly the kind of
duplication that drifts — a future change to weight/window logic (ADR-0016) would need
to be applied twice and could silently diverge.

## Decision 4 — The accounts list shows every account, including ones never scored,
not just scored ones

**Chosen:** `/dashboard` loads every `Account` for the tenant, then separately loads
latest scores/signal types/last-changed timestamps as lookups keyed by `account_id` —
an account with no `Score` row yet still appears, with `—` for score, sorted after
every scored account. Same reasoning as Decision 4's counterpart in ADR-0016/ADR-0011:
an unscored account isn't an error state, and hiding it would make the dashboard
under-report how many accounts the system is actually tracking.

**Rejected: an inner join on latest Score**, which would silently drop any account
that hasn't been scored yet (every account, on day one of a fresh tenant) — the
dashboard's very first real use would show zero rows and look broken.

## What this does NOT decide

- **Auth of any kind** — still ADR-0001 Decision 4's deferred scope; this dashboard is
  reachable by anyone who can reach the deployed URL, same as every other route today.
- **A persisted recall/health trend chart** — Decision 1 computes current numbers live;
  a historical chart is a distinct, larger feature with its own storage decision.
- **HTMX-driven partial updates.** ADR-0002 named HTMX as available for "small
  interactive pieces"; this task's four pages are full-page GETs with no interactive
  state, so nothing here uses it yet — a fine and correct starting point for a
  read-only dashboard, not a gap.

## Consequences

- `scripts/scoring/wiring._load_signal_inputs` becomes a second-caller public function,
  same as the promotions in Tasks 3.1/3.4/4.1.
- The health page's recall number recomputes on every page load — cheap today (a
  handful of accounts), worth revisiting if either the account count or the recall
  window grows enough to make that recomputation non-trivial.
