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

**Cost of being wrong:** low and reversible. SQLAlchemy abstracts the dialect; the escape hatch is a connection string change plus a migration replay.

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

## Consequences

- `scripts/db.py` is deleted. Any consumer importing it breaks and must migrate to `scripts/storage/`.
- Local development now needs a `DATABASE_URL`. Neon's free tier or a local Docker Postgres both work.
- Test fixtures move from file-backed SQLite to in-memory, so they get faster and stop leaking state between runs.
