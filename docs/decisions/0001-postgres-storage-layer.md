# ADR-0001: Postgres + SQLAlchemy + Alembic storage layer

**Status:** Accepted
**Date:** 2026-08-04
**Scope:** Phase 0, Task 0.1 — replaces `scripts/db.py`

---

## Context

SignalForce currently persists to SQLite at `data/signalforce.db` (`scripts/db.py`, 246 lines, WAL mode). That worked when the only writer was one person running a script on a laptop. The plan requires a scheduled worker and a web process writing concurrently from a deployed host, JSONB score traces that get queried by key, and per-tenant scoping on every table.

## Decision 1 — Postgres, not SQLite

**Chosen:** Postgres 16, managed by Neon.

**Rejected: keep SQLite.** Three concrete blockers, in order of severity:

1. **Concurrent writers.** WAL mode gives concurrent *readers* with one writer. The architecture has a scheduled worker writing `probes` in bulk while the web process writes `outreach` rows on webhook delivery. That is two writers. SQLite serializes them with a lock and returns `SQLITE_BUSY` under contention.
2. **No real JSONB.** `scores.trace` and `signal_events.payload` need querying by key (`trace->'components'`). SQLite stores JSON as text and re-parses per row on every query — fine at 1K rows, not at 1M.
3. **Filesystem coupling.** A file-backed DB on Fly.io means a volume, which means the machine can't be freely replaced, which means no `auto_stop_machines`. The deployment story gets worse to keep the database simpler.

**Rejected: Postgres self-hosted on Fly.** Fly's unmanaged Postgres makes backups, failover, and connection pooling your problem. At 10h/week that is the wrong place to spend hours. Neon gives PITR and a pooler with zero operational work, and has a usable free tier.

### Decision 1a — Neon over the other managed providers (added 2026-08-04)

The original text justified managed-over-self-hosted but never compared managed providers. Closing that gap.

| | Neon | Supabase | Databricks Lakebase |
|---|---|---|---|
| Free storage | 0.5 GB | 500 MB (identical) | no meaningful free tier |
| Free compute | 100 CU-hrs, autoscale to 2 CU | shared CPU, no allocation | DBU-based |
| Idle behavior | scale-to-zero at 5 min, **auto-resumes on connect** | **pauses after 1 week, manual unpause** | workspace-dependent |
| Bundles | nothing — plain Postgres | auth, storage, realtime, PostgREST | lakehouse / Delta sync |
| Next tier | usage-based, no minimum | $25/mo flat | enterprise |

**Rejected: Supabase — because of the pause, not the specs.** On storage the two free tiers are identical. The difference that decides it is idle behaviour. Supabase pauses free projects after a week of inactivity and requires a manual dashboard action to restore them.

This project is built at ~10h/week alongside a job search, so multi-week gaps are likely rather than hypothetical. Phase 3's deliverable is a **continuous measurement record** — detection lag, recall, and a 14-day trailing baseline for source-health anomaly detection. A paused database does not merely stop the cron; it punches a hole in the trend data the project exists to produce, and it does so silently. Neon's scale-to-zero achieves the same $0 idle cost through a mechanism that self-heals on the next connection.

**Supabase's bundle is an anti-feature here.** Its differentiation is auth, storage, realtime, and PostgREST. D4 deferred auth and billing entirely, so none of it would be used, while its opinions (the `auth` schema, RLS conventions, PostgREST exposure) would be inherited by a plain SQLAlchemy app. This is the same reasoning that rejected Django in Decision 2: do not adopt a platform whose value is integration when the components have already been chosen independently.

**Rejected: Databricks Lakebase — it is Neon.** Databricks acquired Neon for ~$1B in May 2025; Lakebase is Neon's separated compute/storage engine inside the Databricks platform. Choosing it means the same engine behind a workspace, DBU pricing, and enterprise onboarding, for a lakehouse-integration value proposition irrelevant to a daily batch job.

**Rejected: Railway / Render Postgres.** Both are fine and simpler to reason about than Fly. Neither offers scale-to-zero on a free tier, so idle cost is not $0 — the specific property being optimised for.

**Known risks, stated:**
- Post-acquisition free tiers usually get squeezed. Neon's went the other way (compute allowance doubled, storage price cut ~80%), but a $1B acquirer tuning an enterprise funnel is a real medium-term risk.
- **Revisit trigger:** if the product pivots to D4-option-B (true multi-tenant SaaS with signup and auth), Supabase Auth is worth weeks of work and this decision should be re-opened.

**Cost of being wrong:** near zero, which is why this decision does not deserve more deliberation than the above. Plain Postgres behind SQLAlchemy and Alembic means switching providers is a `DATABASE_URL` change plus `alembic upgrade head` — no ORM rewrite, no query changes, no data-model coupling. Reversible decisions get made fast.

## Decision 2 — SQLAlchemy ORM, not raw SQL or an alternative ORM

**Chosen:** SQLAlchemy 2.x with `DeclarativeBase` and `Mapped[]` typing.

**Rejected: raw SQL via psycopg.** Faster and more explicit for a fixed query set. But 12 tables with FK relationships, and a codebase whose convention is typed Pydantic models everywhere, means hand-rolling row-to-object mapping for every table. That is the exact boilerplate an ORM exists to remove, and it drifts from the schema silently.

**Rejected: SQLModel / Tortoise / Piccolo.** SQLModel is appealing (Pydantic + SQLAlchemy in one) but adds a dependency whose release cadence lags SQLAlchemy's, for the benefit of not writing two model layers. SQLAlchemy is already a declared dependency in `pyproject.toml` and already used by `scripts/db.py`. **Choosing the thing already in the project is the boring, correct move.** No innovation token spent here.

**Note on the two model layers.** ORM classes (`scripts/storage/models.py`) and Pydantic models (`scripts/models.py`) coexist deliberately. ORM = persistence shape, mutable, session-bound. Pydantic = transport shape, `frozen=True`, session-free. Collapsing them means either mutable domain objects (violates the project's immutability rule) or frozen ORM objects (fights SQLAlchemy's unit of work). The duplication is real and it is the cheaper of the two costs.

## Decision 3 — Alembic migrations, not `create_all()`

**Chosen:** Alembic, run via Fly's `release_command` before new machines take traffic.

**Rejected: `Base.metadata.create_all()` at startup.** It creates missing tables but never alters existing ones. The first column addition after data exists requires a manual `ALTER`, done by hand, on prod, from memory. That is how schemas drift from code.

**Rejected: hand-written SQL migration files.** Alembic's autogenerate produces a reviewable diff from the model change, which is strictly better than remembering to write the DDL. Autogenerate output is reviewed, never trusted blindly — it misses constraint renames and server defaults.

## Decision 4 — `tenant_id` on every table now, real isolation later

**Chosen:** every table carries `tenant_id`. Enforcement stays at the application layer.

**Rejected: no multi-tenancy until needed.** Retrofitting a tenant column onto a populated schema means a backfill and touching every query. The column costs 4 bytes and one FK now.

**Rejected: Postgres Row-Level Security now.** RLS is the correct eventual answer and is explicitly deferred. It requires per-tenant DB roles, `SET LOCAL` on every session, and a policy per table — real work, testable only with more than one tenant, and there is exactly one. Building it now would be enforcing an isolation boundary that no adversary is on the other side of.

**Integrity note for interviews:** the honest statement is *"schema is multi-tenant, one tenant is running, isolation is application-layer — RLS is the next step and here's why it isn't built."* Not *"it's multi-tenant."*

## Decision 5 — SQLite in tests, Postgres in production

**Chosen:** `JSONB().with_variant(JSON(), "sqlite")`, tests run against `sqlite:///:memory:`.

**The trade is explicit and it is a real risk.** In-memory SQLite makes the unit suite fast and dependency-free, which matters at 10h/week and keeps CI from needing a service container. The cost is that dialect-specific behaviour goes untested: JSONB operators, `ON CONFLICT` semantics, and constraint-violation error types all differ.

**Mitigation:** anything relying on Postgres-specific behaviour — the webhook `ON CONFLICT DO NOTHING` dedup in Phase 5, JSONB key queries — gets an integration test against a real Postgres in CI. Unit tests stay on SQLite. If that boundary starts blurring, move the whole suite to a Postgres service container.

## Decision 6 — `probes` stays unpartitioned

**Chosen:** a plain table with `(account_source_id, fetched_at DESC)` indexed.

**Rejected: partition by month now.** `probes` is the high-volume table: accounts × sources × runs. At 5K accounts × 4 sources × daily that is 20K rows/day, ~7.3M/year. Postgres handles that on one table without complaint. Partitioning matters near ~10M rows and costs migration complexity plus a partition-maintenance job.

**Know the threshold, don't build to it.** The interview answer is *"unpartitioned, ~7M rows/year projected, partition by month at ~10M — here's the arithmetic,"* not a partitioned table with 200 rows in it.

## What this does NOT decide

- Connection pooling strategy beyond `pool_size=5` (revisit when the worker and web contend)
- Read replicas (no measured read bottleneck; adding one now would be caching-without-a-bottleneck, the failure mode `docs/system-design/03-caching.md` warns about)
- Backup policy beyond Neon's default PITR

## Decision 7 — `scripts/db.py` survives until Phase 5 (amended 2026-08-04)

**Original intent:** delete `scripts/db.py` in this task.

**Reality found during implementation:** `scripts/outcome_tracker.py` (313 lines, with a full test suite) depends on its four tables — `campaigns`, `tracked_signals`, `outreach_events`, `outcome_events`. Their conceptual replacement is the Phase 5 `contacts` / `outreach` pair, which does not exist yet.

**Chosen:** keep `db.py`, add a deprecation docstring naming Phase 5 Task 5.4 as the removal point.

**Rejected: port the four tables into the new schema now.** Phase 5 designs `outreach` against `signal_events` with `triggering_signal_ids`, so outcomes join directly to the signals that caused them. Porting the legacy shape now means building tables that get redesigned in five weeks — guaranteed rework, and roughly double this task's size.

**Rejected: delete `outcome_tracker.py` outright.** It is the only outcome measurement currently in the codebase, and measurement is the entire thesis of this project. Removing it for a replacement that is five weeks out and explicitly marked cuttable is trading a bird in hand for one in the bush.

**Accepted cost:** two storage layers coexist for ~5 weeks. Mitigated by the deprecation docstring; the risk is someone writing *new* code against the old layer, which the docstring exists to prevent.

## Consequences

- `scripts/db.py` remains, deprecated, until Phase 5 Task 5.4. Write no new code against it.
- Local development now needs a `DATABASE_URL`. Neon's free tier or a local Docker Postgres both work.
- Test fixtures move from file-backed SQLite to in-memory, so they get faster and stop leaking state between runs.
