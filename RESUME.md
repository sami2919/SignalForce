# SignalForce — session resume prompt

Copy everything in the fenced block below into a fresh Claude Code session.

---

```
I'm continuing work on SignalForce. Phases 0 and 1 are implemented and deployed,
with a scheduled worker running daily. Read these
files first, in this order, before doing anything:

1. /Users/sami/SignalForce/.superpowers/sdd/2026-08-04-signalforce-production/progress.md
   — the SDD ledger. This is the authoritative record of what is done. Trust it
   and `git log` over anything else, including your own reasoning.

2. /Users/sami/SignalForce-production/docs/superpowers/plans/2026-08-04-signalforce-production.md
   — the implementation plan. Phases 0-5. Note the D8 and ADR-0002 amendments
   inline, and Task 3.4 (probe retention) and Task 5.4 (retire db.py) which were
   added after the plan was first written.

3. /Users/sami/SignalForce-production/docs/decisions/*.md — FIVE ADRs:
     0001 storage layer (Postgres/SQLAlchemy/Alembic, + Neon vs Supabase vs Lakebase)
     0002 web layer + the liveness/readiness split
     0003 deployment, scheduling, migrations-as-release-command
     0004 URL registry, soft-404 detection, robots.txt
     0005 watch layer concurrency, confirm-on-change, persistence
   These record what was REJECTED and why. Do not re-litigate them.

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
- Fly app `signalforce`, org `personal`, region sjc. TWO machines:
    web    d8dd9e2f74e108  shared-cpu-1x, auto_stop=suspend, min_machines_running=0
    worker 0800349a077308  1GB, --schedule daily, --restart no, -e TENANT_SLUG=agentmail
- Neon Postgres 18.4, AWS us-west-2, db `neondb`, Alembic head 10a15fbb92b1.
- LIVE DATA: 20 accounts, 90 account_sources, 270+ probes, 3+ scan_runs.
  The worker appends a run every 24h. DO NOT run the CLI against .env casually —
  it pollutes the measurement. Verify with in-memory SQLite instead.
- Suite: 680 passed, 2 failed (pre-existing `scripts.fireworks_client`, deselected
  in CI). Coverage gate 80%, with two demo scripts omitted.

## PHASE 1 IS IMPLEMENTED. Its exit criterion is NOT yet measured.

Phase 1 exits when `changes_detected / sources_probed` sits in 3-20% AT DAILY
CADENCE. The only measurement so far used a 6.5-MINUTE interval and produced
1.11%, which answers nothing — websites do not change every six minutes.
Reading that against a daily target is a category error.

FIRST THING TO DO ON RESUME: compute the real rate from accumulated runs.

    cd /Users/sami/SignalForce-production
    set -a && . ./.env && set +a
    /Users/sami/SignalForce/.venv/bin/python -m scripts.watch.runner --help

Then query scan_runs where id > 3 (runs 1-3 carry a wrong accounts_probed from a
since-fixed bug; filter them out) and compute changes_detected / sources_probed
per run.

  - 3-20%  -> the two-tier design works. Record it, move to Phase 2.
  - ~0%    -> plausible. First check the worker is actually firing daily:
              `fly machine status 0800349a077308 --app signalforce`
  - ~100%  -> normalization is insufficient. Report WHICH sources churn and STOP.
              Do not start adding strippers — that is a design decision, not a fix.

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

## Next: Phase 2 — the verify layer and the AgentMail scanners

Only after the Phase 1 exit number is measured (see above). Then:

- Task 2.1 verify budget gate — decides which detected changes earn an LLM call
- Task 2.2 agent_email_scanner — THE bullseye signal for AgentMail's ICP: a GitHub
  repo importing BOTH an agent framework (openai-agents, langgraph, crewai, mastra,
  agno) AND an email library (resend, sendgrid, nodemailer, smtplib), first seen in
  the last 30 days. Intersection, not union. Nobody else runs this signal.
- Task 2.3 diff-based signal events — a signal is a DIFF, not a snapshot

Phase 2 needs GITHUB_TOKEN and ANTHROPIC_API_KEY, which are currently blank in .env.

Carry into Phase 2: the Task 0.1 MutableDict finding (SignalEvent.payload).

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
