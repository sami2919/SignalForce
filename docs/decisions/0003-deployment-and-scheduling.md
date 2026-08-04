# ADR-0003: Deployment, scheduling, and migration strategy

**Status:** Accepted
**Date:** 2026-08-04
**Scope:** Phase 0, Task 0.3 — `Dockerfile`, `fly.toml`, CI, structured logging

---

## Context

Two workloads with opposite shapes share one codebase:

| | Web | Worker |
|---|---|---|
| Lifetime | long-running, mostly idle | short burst, ~15 min/day |
| Triggered by | HTTP request | clock |
| Failure means | dashboard is down (annoying) | **no data for that day** (a hole in the measurement record) |

The worker's failure mode is the serious one. Phase 3's deliverable is a *continuous* record — recall, detection lag, and a 14-day trailing baseline for anomaly detection. A silently skipped run is a gap in the exact data the project exists to produce.

## Decision 1 — Fly.io

**Chosen:** Fly.io, Docker-based, two process types.

**Rejected: Railway.** Genuinely the lowest-friction option — connect a repo, get a URL, cron built in. Rejected because the whole point of Phase 0 is being able to answer *"where does it run and how"* with specifics. Railway's value is hiding those specifics. Fly forces explicit contact with Docker, health checks, secrets, regions, and machine lifecycle — the vocabulary the Rippling rounds probed. Paying a one-time friction cost to own that vocabulary is the point, not a side effect.

**Rejected: Render.** Cron jobs are a paid feature; free web services spin down with ~50s cold starts. Fly suspends and restores in ~1-3s because it restores memory rather than cold-booting.

**Rejected: AWS (ECS/Lambda/App Runner).** `docs/system-design/10-circuit-outbound-engine.md` describes an ALB + ECS Fargate + RDS architecture as the *designed* production target. Building that here would mean VPCs, subnets, security groups, task definitions, and IAM — days of work at 10h/week, for a workload that is one small web process and one daily batch. The honest interview line stays *"designed for ECS, running on Fly, and here's the specific scale at which I'd move"* rather than a half-finished AWS setup.

**Rejected: Google Cloud Run + Cloud Scheduler.** Technically an excellent fit — scale-to-zero and a real cron service. Rejected on ecosystem consistency: Neon is already the database, Fly's `release_command` gives clean migration semantics, and adding a second cloud vendor for the scheduler adds an IAM surface for no capability gain.

## Decision 2 — Two machines, not one process with an internal scheduler ★

**This decision is forced by Decision 4, and getting it wrong produces a system that silently never runs.**

**Chosen:** a `web` machine serving HTTP, and a separate scheduled `worker` machine that starts, runs the scan, and exits.

**Rejected: APScheduler (or similar) inside the web process.** Simplest thing that could work, one machine, no extra config. It is also **incompatible with `min_machines_running = 0`** (Decision 4). A suspended machine runs no threads, so an in-process scheduler stops firing the moment the dashboard goes idle. You would have a deployed system that appears healthy, costs nothing, and quietly produces no data. The failure is invisible — precisely the class of silent breakage Phase 3 exists to detect, reintroduced at the infrastructure layer.

Keeping the scheduler in-process would force `min_machines_running = 1` and an always-on machine, i.e. paying continuously so a once-a-day job can fire.

**Rejected: cron/supercronic inside a long-running container.** Same always-on cost, plus cron's traditional weakness — a failed job is a line in a log nobody reads. A scheduled Fly Machine surfaces its exit status as machine state.

**Rejected: GitHub Actions on a schedule.** Free, real cron syntax, good logs. Rejected because it puts production database credentials in GitHub secrets and makes the daily pipeline depend on CI availability. It also splits "where the system runs" across two providers, which is a worse answer to the question this phase exists to answer. Kept as the documented fallback if Fly's scheduling proves unreliable.

**Accepted limitation:** Fly's scheduled machines take coarse intervals (`hourly` / `daily` / `weekly`), not cron expressions. Daily is what the plan calls for, so this costs nothing today. If per-hour source tiering arrives in a later phase, revisit.

## Decision 3 — Migrations as `release_command`

**Chosen:** `release_command = "alembic upgrade head"` in `fly.toml`, run against the **direct** (non-pooled) endpoint.

Fly runs `release_command` in a temporary machine after the image is built and **before** any new machine takes traffic. If it exits non-zero, the deploy aborts and the previous version keeps serving. That is exactly the desired semantics: a broken migration blocks the rollout instead of half-landing.

**Rejected: migrate on application startup.** Every machine would run migrations on boot. With more than one machine that is a race on the same schema, and Alembic's version-table lock turns it into either a deadlock or a crash loop. A migration failure would also become a boot failure, which Fly answers by restarting — the same crash-loop pathology ADR-0002 avoided in the health check.

**Rejected: manual `alembic upgrade head` before each deploy.** Safest for destructive migrations and correct for a large team with a DBA. For one person at 10h/week it is a step that will eventually be forgotten, producing code that expects a column the database does not have.

**Required implementation detail, found during setup:** `migrations/env.py` currently reads `os.environ["DATABASE_URL"]` only. Left alone, `release_command` would send DDL through PgBouncer. Transaction-mode pooling can route consecutive statements to different backends, so a migration can partially apply **and still exit zero**. `env.py` must prefer `DATABASE_URL_DIRECT`, falling back to `DATABASE_URL`.

## Decision 4 — `min_machines_running = 0`

**Chosen:** the web machine suspends when idle and restores on the next request.

Fly's `suspend` snapshots memory rather than cold-booting, so restore is ~1-3s rather than the ~50s typical of a cold container. The dashboard is read-only and consulted occasionally by one person. Trading a couple of seconds on first load for most of the compute bill is obviously correct at this scale.

**Rejected: `min_machines_running = 1`.** ~$2-3/month for a machine that is idle ~99% of the time. Justified only if an in-process scheduler needed it — and Decision 2 removed that requirement precisely so this one could be made freely.

**Open question, to verify after the first deploy:** whether Fly's proxy-level `[[http_service.checks]]` polling `/healthz` every 30s constitutes traffic that prevents suspension. If the machine never suspends, the fix is a longer check interval or a machine-level check rather than abandoning suspend. **This is a verification step, not an assumption** — measure it rather than trusting either answer.

**Second-order benefit:** because ADR-0002's `/healthz` deliberately never touches the database, health-check traffic does not wake Neon's compute either. Neon stays scaled to zero. The endpoint split was chosen for outage behaviour; the billing effect on both providers is a bonus.

## Decision 5 — Secrets vs. config, and structured logging

**Secrets** (`fly secrets set`, encrypted, not in the repo): `DATABASE_URL`, `DATABASE_URL_DIRECT`, `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `AGENTMAIL_API_KEY`.

**Config** (`fly.toml [env]`, plaintext, committed): `LOG_LEVEL`, `TENANT_SLUG`, `PYTHONUNBUFFERED`.

The test is not "is it sensitive" but **"would this be bad in a screenshot?"** Connection strings contain passwords, so both `DATABASE_URL` values are secrets despite looking like configuration.

**Structured JSON logging is added to this task** despite not appearing in the original plan. Deployed logs are the only debugging surface once the code leaves the laptop, and prose logs are not queryable. Roughly 30 lines for a JSON formatter on stdout, which Fly captures automatically. The alternative — discovering during the first incident that logs cannot be filtered by scanner or run id — costs more than writing it now. Scope creep is normally worth resisting; observability added at deploy time is not creep, it is part of deploying.

**Rejected: an external log aggregator** (Datadog, Better Stack). No volume justifies it. `fly logs` suffices until it does not.

## Decision 6 — CI tests, deploy stays manual

**Chosen:** GitHub Actions runs `ruff check`, `ruff format --check`, and `pytest --cov-fail-under=80`. It does **not** deploy.

**Rejected: continuous deployment on push.** Standard good practice, and wrong here for now. `signalforce-production` is an active development branch receiving work-in-progress commits. Auto-deploying every push means deploying half-finished work to the only running instance. Manual `fly deploy` is a deliberate gate while the branch is unstable.

**Revisit trigger:** once this merges to `main` and `main` is protected, auto-deploy from `main` becomes correct.

**CI runs against SQLite only**, consistent with ADR-0001 Decision 5. No integration tests requiring real Postgres exist yet. When the Phase 5 webhook dedup lands — which depends on `ON CONFLICT` semantics SQLite does not share — CI gains a Postgres service container.

## Consequences

- Two machine types to reason about; `fly status` shows both.
- A failed scheduled run leaves no trace in the web logs. `scan_runs` rows are the record — a run that never started leaves no row, so **absence is the signal**. Phase 3's health page must surface "no run in the last 36 hours" or the silent failure this ADR worries about goes undetected anyway.
- Deploy is a manual step and will occasionally be forgotten.
- Suspension means the first dashboard load after idle takes ~1-3s.
