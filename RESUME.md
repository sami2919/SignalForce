# SignalForce — session resume prompt

Copy everything in the fenced block below into a fresh Claude Code session.

---

```
I'm continuing work on SignalForce. Phase 0 is complete and deployed. Read these
files first, in this order, before doing anything:

1. /Users/sami/SignalForce/.superpowers/sdd/2026-08-04-signalforce-production/progress.md
   — the SDD ledger. This is the authoritative record of what is done. Trust it
   and `git log` over anything else, including your own reasoning.

2. /Users/sami/SignalForce-production/docs/superpowers/plans/2026-08-04-signalforce-production.md
   — the implementation plan. Phases 0-5. Note the D8 and ADR-0002 amendments
   inline, and Task 3.4 (probe retention) and Task 5.4 (retire db.py) which were
   added after the plan was first written.

3. /Users/sami/SignalForce-production/docs/decisions/000{1,2,3}-*.md
   — ADRs for the storage layer, web layer/health checks, and deployment.
   These record what was rejected and why. Do not re-litigate them.

## Where the work happens

Git worktree at /Users/sami/SignalForce-production, branch `signalforce-production`.
NOT /Users/sami/SignalForce — that is a different working tree with ~60 unrelated
uncommitted files. Never work there.

Python: /Users/sami/SignalForce/.venv/bin/python (the venv lives in the other
checkout; this is expected). Run tests as
`/Users/sami/SignalForce/.venv/bin/python -m pytest`.

The full suite takes ~95 seconds. Use a timeout of at least 300000ms.

## What is live right now

- https://signalforce.fly.dev/healthz -> 200 {"status":"ok"}
- https://signalforce.fly.dev/readyz  -> 200 {"status":"ready","db":true}
- Fly app `signalforce`, org `personal`, region sjc, ONE shared-cpu-1x machine,
  auto_stop = suspend.
- Neon Postgres 18.4, AWS us-west-2, database `neondb`, 7 tables at Alembic
  revision 36d4e4799449.
- Suite: 601 passed, 2 failed (pre-existing, deselected in CI), 86% coverage.

## How I want you to work — this matters most

1. ONE STEP AT A TIME. Do not run through multiple tasks without stopping. After
   each task completes and passes review, stop and report. Wait for me to say
   continue. This overrides the subagent-driven-development skill's default of
   continuous execution.

2. BEFORE writing any code for a step, write an ADR to
   docs/decisions/000N-<slug>.md covering: what was chosen, what alternatives
   were rejected AND WHY, what the accepted costs are, and what this decision
   does NOT decide. Name the reasons that do NOT apply as well as the ones that
   do — e.g. ADR-0002 chose FastAPI and explicitly says the usual "it's async
   and fast" reason does not apply to this workload. Then show it to me.

3. Use superpowers:subagent-driven-development. Write a task brief to the SDD
   workspace, dispatch an implementer subagent, then dispatch a code-reviewer
   subagent with the diff as a review package file. Never skip the review.

4. Verify claims yourself rather than trusting subagent reports. A reviewer once
   asserted DATABASE_URL_DIRECT was empty when it was set correctly; acting on
   that would have broken a working config. Run the commands and read the output.

5. Append every decision, ruling, and deferred finding to the ledger as you go.
   The ledger is what survives context compaction.

## Open items

- Neon password appeared in an earlier transcript. Rotate it (Neon dashboard ->
  Branch -> Roles -> Reset password), update line 16 of
  /Users/sami/SignalForce-production/.env, then re-run:
  `cd /Users/sami/SignalForce-production && set -a && . ./.env && set +a && \
   fly secrets set --app signalforce DATABASE_URL="$DATABASE_URL" \
   DATABASE_URL_DIRECT="$DATABASE_URL_DIRECT"`
- GITHUB_TOKEN and ANTHROPIC_API_KEY are blank in .env. Phase 1 does not need
  them; Phase 2's scanners do.

## Deferred findings to carry forward

- Task 0.1: JSON columns are not MutableDict-wrapped, so in-place mutation of a
  fetched dict does NOT persist and does NOT error. Assign a whole new dict.
  Carry this pointer into any task touching SignalEvent.payload (Phase 2) or
  Score.trace (Phase 4).
- Task 0.2: /readyz issues `SET LOCAL statement_timeout`, which is Postgres-only.
  A SQLite DATABASE_URL makes /readyz report 503 even when fine. Dev-only.
- Task 0.3b: configure_logging() strips all root handlers at import time via
  `app = create_app()`. Safe today, latent footgun for future caplog tests.
- Task 0.3b: uvicorn keeps its own log handlers, so its access/startup lines are
  prose while application lines are JSON. Assessed as genuinely minor. Deferred.
- scripts/scanners/g2_seed_scanner.py is at 0% coverage and deliberately left
  measured (not omitted) so the gap stays visible.

## Next task: Phase 1, Task 1.1 — source resolution

Start by writing ADR-0004 covering the URL registry design, then the task brief,
then dispatch. The plan has full code for Tasks 1.1, 1.2, and 1.3.

Phase 1's exit criterion is the number that validates the whole architecture:
`changes_detected / sources_probed` must land in the 3-20% band. If it is near
100%, HTML normalization is broken and the two-tier cost model collapses — fix
that before Phase 2.

Also in Phase 1: create the scheduled worker machine. It must be a SEPARATE Fly
machine, never an in-process scheduler, because min_machines_running = 0 means
the web machine suspends and an in-process scheduler would silently stop firing.
See ADR-0003 Decision 2. The command is commented at the bottom of fly.toml.

## Context for why this project exists

I was rejected after onsite rounds at Rippling. The feedback cited insufficient
depth on technical and product explanations. The real cause: I could describe
architecture but not operational specifics — I could not say where my Circuit
project was deployed (a laptop), could not name its database, and gave
conflicting reply-rate numbers. A separate round (Sajwal, signals) asked "if you
don't know something changed at all, how would you know if you captured it fast
enough?" and I derived the answer live instead of describing something I had
operated.

This project moves claims from "designed" to "ran." The load-bearing phase is
Phase 3 (holdout set, recall, detection lag, source health) because it produces
the numbers that answer that question from a database query. If time runs short,
cut Phase 5 (outbound), never Phase 3.

Target: AgentMail (YC S25, $6M seed led by General Catalyst, ~10 people, SF).
They have an open on-site GTM Engineer role. The ICP is companies shipping AI
agents that touch email. The bullseye signal is a GitHub repo importing both an
agent framework and an email library, first seen in the last 30 days.
```
