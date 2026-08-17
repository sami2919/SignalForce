# SignalForce Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn SignalForce from a local script collection into a deployed, scheduled, measurable signal engine running live against AgentMail's ICP — with the operational numbers that prove it ran.

**Architecture:** A two-tier crawl (cheap content-hash watch layer over a persisted URL registry; expensive extraction only on hash change) writing diff-shaped `signal_events` to Postgres, scored with a replayable trace, measured by a holdout set that yields real recall and detection-lag numbers, surfaced in a server-rendered dashboard, with outbound sending and reply capture on AgentMail's API.

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy 2.x + Alembic · Postgres (Neon) · httpx (async watch layer) · Jinja2 + HTMX (dashboard) · Docker · Fly.io · pytest

---

## Global Constraints

- Python `>=3.11`. Ruff line-length 100, target `py311`.
- All Pydantic models `frozen=True`. Never mutate — return new objects.
- Type hints required on every function signature.
- pytest, 80% minimum coverage. Mock all HTTP in tests — never hit real APIs.
- All secrets via env vars loaded by `python-dotenv`. Never hardcode.
- Every script importable as a module AND runnable as CLI (`if __name__ == "__main__"`).
- Every table carries `tenant_id`. Multi-tenant schema, single tenant live.
- **Integrity rule:** anything not actually deployed and running is described as "designed," never "ran." This plan exists to shrink the set of things in the first category.

---

## The Problem This Solves

Two failures, one root cause.

**Rippling, John Kutay round:** couldn't say where the Circuit engine was deployed (a laptop), couldn't name the database, gave 8% and 48% for the same reply rate without flagging the conflict.

**Rippling, Sajwal round:** at 16:12 he asked *"if you don't know something changed at all, how would you know if you captured it fast enough?"* The answer given — holdout rescans plus source health metrics — was correct, but derived live over 90 seconds. It sounded like a guess because it was one.

Both are the same gap: **architecture-level fluency without operator-level evidence.** The fix is not more architecture documents. `docs/system-design/` already has 2,156 lines of those, including an explicit self-instruction (`10-circuit-outbound-engine.md:27`) that every production claim must be framed as "designed, never ran." That guardrail is honest, and it is the trap — it guarantees the next interviewer's follow-up lands in the same hole.

This plan moves specific claims from the "designed" column to the "ran" column. Nothing more.

### The four numbers this produces

By end of Phase 3, these are answerable from a database query, not from memory:

| Question | Source of truth |
|---|---|
| "How fast do you detect a change?" | `detection_lag_hours` p50/p95 over the holdout set |
| "What's your recall?" | `changes_caught_by_watch / changes_found_by_deep_scan` |
| "How do you know a scanner isn't silently broken?" | `source_health` zero-result-rate trend + alert threshold |
| "What does it cost to run?" | `scan_runs.cost_usd` summed per month |

---

## What Already Exists

Verified by reading, not assumed.

| Asset | State | Plan's use |
|---|---|---|
| `scripts/api_client.py` (197 lines) | **Genuinely good.** 429/403-quota/5xx backoff, timeout doubling, typed error hierarchy. The 429-doesn't-count-against-backoff-budget distinction at `:150` is correct and non-obvious. | **Reused unchanged.** Becomes the verify-layer transport. |
| 15 scanners in `scripts/scanners/` | Working, sync, `requests`-based, return `ScanResult` | **Reused as verify layer.** Not rewritten. Two new AgentMail-specific scanners added. |
| `scripts/models.py` (321 lines) | Frozen Pydantic models, good discipline | Extended, not replaced |
| `scripts/config_loader.py` | YAML ICP config loading | Becomes per-tenant config |
| `scripts/db.py` (246 lines) | SQLite, file-on-disk | **Replaced** by Postgres + Alembic. SQLite cannot support concurrent workers or JSONB traces. |
| `scripts/scanner_runner.py` (65 lines) | Sequential `for` loop, `try/except`, no concurrency/budget/timeout/persistence | **Replaced** by the orchestrator in Phase 1 |
| `docs/system-design/` | 2,156 lines of narrative | Reference only. Not extended by this plan. |
| `tests/` (~40 files) | Real coverage on existing modules | Kept. New work is TDD. |

**Correction to record:** saved memory obs 1378 states SignalForce "contains a production-grade orchestrator with budget, concurrency, and fault tolerance." It does not — `scanner_runner.py` is a 65-line try/except loop. Delete or correct that memory before it gets repeated in a room where someone can open the file.

---

## Architecture

### Data flow

```
┌────────────────────────────────────────────────────────────────────┐
│ DISCOVERY (once per account, amortized)                            │
│   domain → resolve careers/docs/changelog/pricing URLs             │
│   → account_sources rows                                           │
│   Sajwal 25:37 — "go to THIS careers page, this is the URL"        │
│   vs "go find the careers page" — a different, much worse story    │
└───────────────────────────┬────────────────────────────────────────┘
                            │ (never repeated unless resolution fails)
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│ WATCH LAYER — async, all accounts, every run                       │
│   httpx.AsyncClient, semaphore(100)                                │
│   GET url → normalize_html() → sha256                              │
│   write probes row (hash, status, latency_ms, bytes)               │
│   changed = hash != account_sources.last_hash                      │
│   COST: bandwidth only. No LLM. No paid API.                       │
└───────────────────────────┬────────────────────────────────────────┘
                            │
                ┌───────────┴────────────┐
            unchanged                 changed  (~5-15% of rows)
                │                         │
                ▼                         ▼
   ┌────────────────────┐   ┌──────────────────────────────────┐
   │ probe row only     │   │ VERIFY LAYER                     │
   │ (proves the source │   │  existing scanners + LLM extract │
   │  is ALIVE, which   │   │  → normalize vendor names        │
   │  is what tells you │   │  → diff vs last extraction       │
   │  quiet ≠ broken)   │   │  → emit signal_event (the DIFF)  │
   └────────────────────┘   └──────────────┬───────────────────┘
                                           ▼
                            ┌──────────────────────────────────┐
                            │ SCORING                          │
                            │  ICP×0.4 + Intent×0.6            │
                            │  recency decay · breadth mult.   │
                            │  → scores.trace (JSONB, replayable)
                            └──────────────┬───────────────────┘
                                           ▼
                            ┌──────────────────────────────────┐
                            │ AUDIENCES (composable predicates)│
                            │  hiring(persona=X) AND raised(<30d)
                            └──────────────┬───────────────────┘
                                           ▼
                        ┌──────────────────┴───────────────────┐
                        ▼                                      ▼
              ┌──────────────────┐              ┌──────────────────────┐
              │ DASHBOARD        │              │ AGENTMAIL SEND       │
              │ Jinja2 + HTMX    │              │ inbox → thread → send│
              │ read-only        │              │ webhook ← reply      │
              └──────────────────┘              └──────────┬───────────┘
                                                            ▼
                                                 ┌──────────────────────┐
                                                 │ OUTCOME LOOP         │
                                                 │ reply → cohort compare
                                                 │ → which signals lift │
                                                 └──────────────────────┘

╔════════════════════════════════════════════════════════════════════╗
║ MEASUREMENT PLANE — runs beside everything above                   ║
║                                                                    ║
║  HOLDOUT SET: N accounts deep-scanned on fixed cadence,            ║
║  ignoring the watch layer entirely.                                ║
║    recall        = |watch ∩ deep| / |deep|                         ║
║    detection_lag = deep_found_at − watch_found_at                  ║
║                                                                    ║
║  SOURCE HEALTH, per source_type per day:                           ║
║    fetch_success_rate · parse_success_rate · zero_result_rate      ║
║    → alert when zero_result_rate jumps >3σ from trailing 14d mean  ║
║                                                                    ║
║  THIS IS THE ANSWER TO SAJWAL 16:12.                               ║
╚════════════════════════════════════════════════════════════════════╝
```

### Why two tiers (the justification, not the name)

Discovery is a search problem: expensive, flaky, per-run. Retrieval is a bandwidth problem: cheap, parallel, cacheable. Persisting the URL registry converts `O(accounts × runs)` searches into `O(accounts)` one-time resolution plus `O(accounts × runs)` cheap GETs.

Content hashing then makes extraction a cache-invalidation problem — the same cache-aside pattern in `docs/system-design/03-caching.md`, applied to crawl scheduling instead of reads. The LLM only runs on the ~5-15% of pages that moved.

Concretely, at 5,000 accounts × 4 sources × daily:
- Naive: 20,000 LLM extractions/day. At ~$0.002 each ≈ **$40/day**.
- Two-tier: 20,000 cheap GETs + ~1,500 extractions ≈ **$3/day** plus bandwidth.

The number to quote in an interview is the ratio, and it should come from `scan_runs.cost_usd`, not from this document.

### Deployment

```
   Fly.io                                    Neon
  ┌──────────────────────────┐        ┌──────────────────┐
  │ app: signalforce         │        │ Postgres         │
  │                          │───────▶│ (managed, PITR)  │
  │ [web]  FastAPI           │        └──────────────────┘
  │   /healthz               │
  │   /dashboard  (Jinja2)   │        Secrets: fly secrets set
  │   /api/v1/*              │          GITHUB_TOKEN
  │   /webhooks/agentmail    │          AGENTMAIL_API_KEY
  │                          │          ANTHROPIC_API_KEY
  │ [worker] scheduled       │          DATABASE_URL
  │   fly machine --schedule │
  │   daily 09:00 UTC        │
  └──────────────────────────┘
```

Fly.io over Railway/Render because Docker + explicit health checks + secrets management + scheduled machines are the concepts interviews actually probe, and the friction is a one-time cost. Neon over Fly Postgres because managed beats self-run for a solo operator at 10h/week, and connection pooling comes free.

**Innovation token accounting** (McKinley): Postgres, FastAPI, Docker, Jinja2 are all boring on purpose. The one novel thing is AgentMail's API, which is novel by design — being their customer is the point.

---

## Signals for AgentMail's ICP

AgentMail sells programmatic email inboxes to developers building AI agents. The buying moment is: **a team just shipped an agent that touches email.**

| # | Signal | Source | Why it's high intent |
|---|---|---|---|
| 1 | **Agent framework + email library in the same repo, first seen <30d** | GitHub code search | The bullseye. They are building the exact thing AgentMail replaces, right now. No incumbent runs this. |
| 2 | Repo newly imports an agent framework | GitHub | Earlier, weaker — they're building agents, email may come |
| 3 | Job post: "AI agent engineer", "forward deployed engineer", framework named in JD | Greenhouse/Lever/Ashby via URL registry | Budget committed to agents |
| 4 | Docs/changelog announces an agent or email feature | URL registry + watch layer | Public commitment, and it exercises the watch layer end-to-end |
| 5 | Funding round, AI-agent classified | existing `funding_scanner.py` | Budget + urgency |

Phase 2 builds **1, 2, 3**. Signal 4 arrives free once the watch layer exists. Signal 5 is existing code, retuned.

Signal 1 is the demo. A live, traced list of companies that shipped an email-touching agent in the last 30 days is something AgentMail's founder does not currently have.

---

## File Structure

```
scripts/
  registry/
    __init__.py
    resolver.py        # domain → candidate source URLs
    models.py          # SourceType enum, ResolvedSource
  watch/
    __init__.py
    fetcher.py         # async httpx fetch w/ semaphore + per-host politeness
    normalize.py       # HTML → stable text for hashing
    runner.py          # orchestrates a watch pass, writes probes
  verify/
    __init__.py
    gate.py            # decides which changed sources get extracted
    extractor.py       # LLM extraction → structured facts
    differ.py          # previous facts vs current → signal_events
  measure/
    __init__.py
    holdout.py         # holdout selection + deep scan
    lag.py             # recall + detection lag computation
    health.py          # source health metrics + anomaly alert
  scoring/
    __init__.py
    engine.py          # score + trace  ◀── YOUR CONTRIBUTION
    personas.py        # job title → persona subcategory
    audiences.py       # composable predicate evaluator
  outreach/
    __init__.py
    agentmail.py       # AgentMail API client
    sequencer.py       # audience → send decisions
  web/
    __init__.py
    app.py             # FastAPI app factory
    routes_dashboard.py
    routes_api.py
    routes_webhooks.py
    templates/         # Jinja2
  storage/
    __init__.py
    models.py          # SQLAlchemy ORM (replaces db.py)
    session.py         # engine + session factory
migrations/            # Alembic
Dockerfile
fly.toml
.github/workflows/ci.yml
```

Existing `scripts/scanners/*` unchanged. `scripts/db.py` deleted in Phase 0 (its consumers migrate to `storage/`).

---

## Schema

```sql
-- Multi-tenant root
tenants(id, slug UNIQUE, name, config_yaml TEXT, created_at)

-- Accounts under scan
accounts(id, tenant_id FK, domain, name, first_seen_at, metadata JSONB,
         UNIQUE(tenant_id, domain))

-- THE URL REGISTRY. Sajwal 25:37.
account_sources(id, tenant_id FK, account_id FK,
                source_type,            -- careers|docs|changelog|pricing|blog
                url,
                resolved_at,
                resolution_method,      -- wellknown|sitemap|heuristic|manual
                last_hash,              -- sha256 of normalized body
                last_fetched_at,
                last_changed_at,
                consecutive_failures INT DEFAULT 0,
                active BOOL DEFAULT true,
                UNIQUE(account_id, source_type))

-- Cheap watch layer log. One row per fetch. High volume.
probes(id, tenant_id FK, account_source_id FK, scan_run_id FK,
       fetched_at, content_hash, changed BOOL,
       status_code, latency_ms, bytes,
       error TEXT NULL)

-- Signals are DIFFS, not snapshots. Sami 13:42: "difference first, not snapshot first"
signal_events(id, tenant_id FK, account_id FK,
              account_source_id FK NULL,
              signal_type,              -- agent_email_repo|hiring|funding|stack_change
              payload JSONB,            -- {before, after, extracted}
              detected_at,              -- when WE saw it
              occurred_at NULL,         -- when it actually happened, if knowable
              confidence FLOAT,
              scan_run_id FK)

-- Traceable scoring. Replayable. Zero-out-able.
scores(id, tenant_id FK, account_id FK, score FLOAT, computed_at,
       trace JSONB,                     -- per-component contributions
       config_version)

-- Sajwal 28:49: job title → persona subcategory
personas(id, tenant_id FK, name, title_patterns JSONB, seniority_min)

-- Sajwal 29:26: "every signal can be stacked to build an audience"
audiences(id, tenant_id FK, name, predicate JSONB, created_at)

-- MEASUREMENT PLANE
holdout_accounts(id, tenant_id FK, account_id FK, added_at, cadence_days)
holdout_scans(id, holdout_account_id FK, scanned_at,
              changes_found JSONB,      -- ground truth
              watch_detected_at NULL,   -- when watch layer saw it, or NULL = MISS
              detection_lag_hours FLOAT NULL)
source_health(id, tenant_id FK, source_type, run_date,
              fetch_success_rate, parse_success_rate, zero_result_rate,
              sample_size,
              UNIQUE(tenant_id, source_type, run_date))

-- Run-level operational metrics. THIS is where cost/latency numbers come from.
scan_runs(id, tenant_id FK, started_at, finished_at, status,
          accounts_probed, sources_probed, changes_detected,
          verify_calls, signals_emitted,
          cost_usd, p50_latency_ms, p95_latency_ms,
          error TEXT NULL)

-- Outcome loop
contacts(id, tenant_id FK, account_id FK, email, name, title, persona_id FK NULL)
outreach(id, tenant_id FK, contact_id FK, audience_id FK,
         agentmail_inbox_id, agentmail_thread_id,
         sent_at, replied_at NULL, reply_classification NULL,
         triggering_signal_ids JSONB)
```

Indexes that matter:
```sql
CREATE INDEX ix_probes_source_time ON probes(account_source_id, fetched_at DESC);
CREATE INDEX ix_signal_events_account ON signal_events(tenant_id, account_id, detected_at DESC);
CREATE INDEX ix_signal_events_type_time ON signal_events(tenant_id, signal_type, detected_at DESC);
CREATE INDEX ix_sources_due ON account_sources(tenant_id, active, last_fetched_at);
```

`probes` is the high-volume table (accounts × sources × runs) and the only unbounded one. **Task 3.4 caps it** with rollup-then-prune: unchanged probes live 30 days, changed probes 180, and the aggregate survives in `source_health`. Steady state at 5,000 accounts is ~144 MB — flat, not growing.

Partitioning is therefore deferred indefinitely rather than "until ~10M rows": retention keeps the table below that ceiling permanently. If retention were removed, the threshold argument returns. The interview answer is *"bounded by retention, not by partitioning — here's the arithmetic and here's the safety guard that stops the prune from outrunning the rollup."*

---

# PHASE 0 — Deployed Skeleton (Week 1, ~10h)

**Goal:** By end of week one, "it's deployed" is a true statement. Everything else builds on a live system.

### Task 0.1: Postgres storage layer

**Files:**
- Create: `scripts/storage/models.py`, `scripts/storage/session.py`, `scripts/storage/__init__.py`
- Create: `migrations/` (alembic init)
- Modify: `scripts/db.py` (deprecation notice only — see D8 below)
- Test: `tests/storage/test_models.py`

> **D8 amendment (2026-08-04).** This task originally said "Delete `scripts/db.py`."
> That was a plan defect: `scripts/outcome_tracker.py` (313 lines, with tests) depends
> on its four tables (`campaigns`, `tracked_signals`, `outreach_events`,
> `outcome_events`), and their replacement (`contacts` / `outreach`) is not built until
> Phase 5. Deleting now means either breaking working code or building four tables
> Phase 5 will redesign. **Resolution: keep `db.py`, add a deprecation docstring, migrate
> `outcome_tracker` in Phase 5 Task 5.4.** The two storage layers coexist for ~5 weeks;
> that is the cheaper of the two costs.

**Interfaces:**
- Produces: `get_session() -> Iterator[Session]`, `Base`, ORM classes `Tenant, Account, AccountSource, Probe, SignalEvent, Score, ScanRun`

- [ ] **Step 1: Add dependencies**

```bash
# pyproject.toml [project.dependencies] — add:
#   "psycopg[binary]>=3.2", "alembic>=1.13", "fastapi>=0.115",
#   "uvicorn[standard]>=0.32", "httpx>=0.27", "selectolax>=0.3"
pip install -e ".[dev]"
```

- [ ] **Step 2: Write the failing test**

```python
# tests/storage/test_models.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from scripts.storage.models import Base, Tenant, Account, AccountSource

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)()

def test_account_source_unique_per_type(session):
    t = Tenant(slug="agentmail", name="AgentMail")
    a = Account(tenant=t, domain="acme.com", name="Acme")
    session.add_all([t, a, AccountSource(tenant=t, account=a,
                                         source_type="careers",
                                         url="https://acme.com/careers")])
    session.commit()
    assert session.query(AccountSource).one().url == "https://acme.com/careers"

def test_tenant_slug_is_unique(session):
    session.add(Tenant(slug="dup", name="A"))
    session.commit()
    session.add(Tenant(slug="dup", name="B"))
    with pytest.raises(Exception):
        session.commit()
```

- [ ] **Step 3: Run it, confirm it fails**

Run: `pytest tests/storage/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.storage`

- [ ] **Step 4: Implement the ORM**

```python
# scripts/storage/models.py
"""SQLAlchemy ORM for SignalForce. Every table carries tenant_id."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

# JSONB on Postgres, JSON on SQLite (tests)
JSONType = JSONB().with_variant(JSON(), "sqlite")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_yaml: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "domain"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    account_metadata: Mapped[dict] = mapped_column(JSONType, default=dict)

    tenant: Mapped[Tenant] = relationship()
    sources: Mapped[list["AccountSource"]] = relationship(back_populates="account")


class AccountSource(Base):
    """The URL registry. Resolved once, reused forever."""
    __tablename__ = "account_sources"
    __table_args__ = (
        UniqueConstraint("account_id", "source_type"),
        Index("ix_sources_due", "tenant_id", "active", "last_fetched_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolution_method: Mapped[str] = mapped_column(String(32), default="heuristic")
    last_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    tenant: Mapped[Tenant] = relationship()
    account: Mapped[Account] = relationship(back_populates="sources")
```

Continue with `Probe`, `SignalEvent`, `Score`, `ScanRun` following the schema section above. Same pattern: `tenant_id` FK first, timezone-aware datetimes, `JSONType` for payloads.

```python
# scripts/storage/session.py
"""Engine and session factory. DATABASE_URL from env."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_SessionLocal = None


def _init() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        return
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # Neon pooler works fine with modest pool sizes; fail fast on exhaustion.
    _engine = create_engine(url, pool_size=5, max_overflow=5, pool_pre_ping=True)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


@contextmanager
def get_session() -> Iterator[Session]:
    _init()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 5: Run tests, confirm pass**

Run: `pytest tests/storage/ -v`
Expected: PASS

- [ ] **Step 6: Initialize Alembic and generate the first migration**

```bash
alembic init migrations
# In migrations/env.py: set target_metadata = Base.metadata,
# and read sqlalchemy.url from os.environ["DATABASE_URL"]
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

- [ ] **Step 7: Commit**

```bash
git add scripts/storage/ migrations/ alembic.ini tests/storage/ pyproject.toml \
        docs/decisions/ scripts/db.py
git commit -m "feat: postgres storage layer with multi-tenant schema"
```

### Task 0.2: FastAPI app with health check

**Files:**
- Create: `scripts/web/app.py`, `scripts/web/routes_api.py`
- Test: `tests/web/test_health.py`

**Interfaces:**
- Produces: `create_app() -> FastAPI`; `GET /healthz` (liveness, no DB); `GET /readyz` (readiness, checks DB, 503 on failure)

> **ADR-0002 amendment (2026-08-04).** This task originally specified a single
> `/healthz` returning `{"status": "ok", "db": bool}` with a 200 regardless of DB
> state. That conflates liveness with readiness. Fly restarts machines whose health
> check fails — so a DB-checking `/healthz` converts a Neon outage into a Neon outage
> *plus* a crash-looping web tier, since restarting cannot fix a remote dependency.
> **Split into two endpoints:** `/healthz` never touches the DB (Fly's check points
> here); `/readyz` checks it and returns 503. See
> `docs/decisions/0002-web-layer-and-health-checks.md`, Decision 3.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_health.py
from fastapi.testclient import TestClient
from scripts.web.app import create_app

def test_healthz_reports_ok():
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

- [ ] **Step 2: Run it, confirm it fails**

Run: `pytest tests/web/test_health.py -v` → FAIL, no module `scripts.web.app`

- [ ] **Step 3: Implement**

```python
# scripts/web/app.py
"""FastAPI application factory."""
from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import text

from scripts.storage.session import get_session


def create_app() -> FastAPI:
    app = FastAPI(title="SignalForce", version="0.2.0")

    @app.get("/healthz")
    def healthz() -> dict:
        """Liveness + DB reachability. Fly.io health checks hit this."""
        db_ok = False
        try:
            with get_session() as s:
                s.execute(text("SELECT 1"))
            db_ok = True
        except Exception:  # noqa: BLE001 — health check must never raise
            db_ok = False
        return {"status": "ok", "db": db_ok}

    return app


app = create_app()
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `pytest tests/web/ -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/web/ tests/web/
git commit -m "feat: fastapi app with health endpoint"
```

### Task 0.3: Docker + Fly deploy + CI

**Files:**
- Create: `Dockerfile`, `fly.toml`, `.dockerignore`, `.github/workflows/ci.yml`

- [ ] **Step 1: Dockerfile**

```dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY scripts/ ./scripts/
RUN pip install --no-cache-dir -e .

COPY migrations/ ./migrations/
COPY alembic.ini ./

EXPOSE 8080
CMD ["uvicorn", "scripts.web.app:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: fly.toml**

```toml
app = "signalforce"
primary_region = "sjc"

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = "suspend"
  auto_start_machines = true
  min_machines_running = 1

[[http_service.checks]]
  interval = "30s"
  timeout = "5s"
  grace_period = "10s"
  method = "GET"
  path = "/healthz"

[deploy]
  release_command = "alembic upgrade head"
```

`release_command` runs migrations before the new version takes traffic — this is the piece people forget, and it's the difference between a deploy and an outage.

- [ ] **Step 3: Deploy**

```bash
fly launch --no-deploy
fly secrets set DATABASE_URL="postgresql+psycopg://..." \
                GITHUB_TOKEN="..." ANTHROPIC_API_KEY="..."
fly deploy
curl https://signalforce.fly.dev/healthz   # {"status":"ok","db":true}
```

- [ ] **Step 4: CI**

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: ruff format --check .
      - run: pytest --cov=scripts --cov-report=term-missing --cov-fail-under=80
```

- [ ] **Step 5: Commit**

```bash
git add Dockerfile fly.toml .dockerignore .github/
git commit -m "chore: docker, fly deploy, and CI"
```

**Phase 0 exit criteria:** `curl https://signalforce.fly.dev/healthz` returns `{"status":"ok","db":true}` from a machine that is not your laptop. Write down the date. That date is the answer to "when did it go live."

---

# PHASE 1 — URL Registry + Watch Layer (Week 2, ~10h)

### Task 1.1: Source resolution

**Files:**
- Create: `scripts/registry/resolver.py`, `scripts/registry/models.py`
- Test: `tests/registry/test_resolver.py`

**Interfaces:**
- Produces: `resolve_sources(domain: str, client: httpx.AsyncClient) -> list[ResolvedSource]`
- `ResolvedSource` = frozen Pydantic: `source_type: SourceType, url: str, method: str, confidence: float`

- [ ] **Step 1: Write the failing test**

```python
# tests/registry/test_resolver.py
import pytest, httpx
from scripts.registry.resolver import resolve_sources, CAREERS_PATHS

@pytest.mark.asyncio
async def test_resolves_careers_from_common_path():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/careers":
            return httpx.Response(200, text="<html>Open roles</html>")
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        results = await resolve_sources("acme.com", c)

    careers = [r for r in results if r.source_type == "careers"]
    assert careers and careers[0].url == "https://acme.com/careers"

@pytest.mark.asyncio
async def test_returns_empty_when_nothing_resolves():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(404))
    ) as c:
        assert await resolve_sources("nothing.example", c) == []
```

- [ ] **Step 2: Run it, confirm it fails**

Run: `pytest tests/registry/ -v` → FAIL, no module

- [ ] **Step 3: Implement**

```python
# scripts/registry/resolver.py
"""Resolve a domain to its signal-bearing URLs.

Runs ONCE per account. The whole cost model depends on never repeating this.
Sajwal (Rippling, 25:37): "we never do a Google search for the website. We go
to the website... knowing exactly where to go find the signal."
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from scripts.registry.models import ResolvedSource

logger = logging.getLogger(__name__)

CAREERS_PATHS = ("/careers", "/jobs", "/careers/", "/company/careers", "/about/careers")
DOCS_PATHS = ("/docs", "/documentation", "/developers")
CHANGELOG_PATHS = ("/changelog", "/releases", "/whats-new", "/blog/changelog")
PRICING_PATHS = ("/pricing", "/plans")

_PATHS_BY_TYPE = {
    "careers": CAREERS_PATHS,
    "docs": DOCS_PATHS,
    "changelog": CHANGELOG_PATHS,
    "pricing": PRICING_PATHS,
}

_TIMEOUT = httpx.Timeout(10.0)


async def _probe_path(client: httpx.AsyncClient, domain: str, path: str) -> str | None:
    """Return the URL if it responds 200, else None."""
    url = f"https://{domain.rstrip('/')}{path}"
    try:
        resp = await client.get(url, timeout=_TIMEOUT, follow_redirects=True)
    except (httpx.HTTPError, httpx.InvalidURL):
        return None
    return url if resp.status_code == 200 else None


async def resolve_sources(domain: str, client: httpx.AsyncClient) -> list[ResolvedSource]:
    """Find signal-bearing URLs for a domain. First hit per type wins."""
    resolved: list[ResolvedSource] = []

    for source_type, paths in _PATHS_BY_TYPE.items():
        found = await asyncio.gather(*(_probe_path(client, domain, p) for p in paths))
        hit = next((u for u in found if u), None)
        if hit:
            resolved.append(
                ResolvedSource(
                    source_type=source_type, url=hit, method="heuristic", confidence=0.8
                )
            )
        else:
            logger.info("No %s source resolved for %s", source_type, domain)

    return resolved
```

```python
# scripts/registry/models.py
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict

SourceType = Literal["careers", "docs", "changelog", "pricing", "blog"]


class ResolvedSource(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_type: SourceType
    url: str
    method: str
    confidence: float
```

- [ ] **Step 4: Run tests, confirm pass** → `pytest tests/registry/ -v`

- [ ] **Step 5: Commit**

```bash
git add scripts/registry/ tests/registry/
git commit -m "feat: URL registry source resolution"
```

### Task 1.2: HTML normalization for stable hashing

**Files:**
- Create: `scripts/watch/normalize.py`
- Test: `tests/watch/test_normalize.py`

**Interfaces:**
- Produces: `normalize_html(raw: str) -> str`, `content_hash(raw: str) -> str`

This is the task that decides whether the watch layer works at all. Raw HTML changes on every request — CSRF tokens, session IDs, build hashes, timestamps, ad slots. Hash raw HTML and everything looks changed every run, which collapses the two-tier design back into a one-tier design and blows the cost model.

- [ ] **Step 1: Write the failing test**

```python
# tests/watch/test_normalize.py
from scripts.watch.normalize import normalize_html, content_hash

def test_ignores_scripts_and_styles():
    a = "<html><body><h1>Jobs</h1><script>var t=1</script></body></html>"
    b = "<html><body><h1>Jobs</h1><script>var t=2</script></body></html>"
    assert content_hash(a) == content_hash(b)

def test_ignores_whitespace_differences():
    a = "<div>  Senior   Engineer </div>"
    b = "<div>Senior Engineer</div>"
    assert content_hash(a) == content_hash(b)

def test_ignores_csrf_and_nonce_attributes():
    a = '<form csrf-token="abc123"><input name="q"></form>'
    b = '<form csrf-token="xyz789"><input name="q"></form>'
    assert content_hash(a) == content_hash(b)

def test_detects_real_content_change():
    a = "<div><h2>Senior Engineer</h2></div>"
    b = "<div><h2>Senior Engineer</h2><h2>Staff Engineer</h2></div>"
    assert content_hash(a) != content_hash(b)
```

- [ ] **Step 2: Run it, confirm it fails** → FAIL, no module

- [ ] **Step 3: Implement**

```python
# scripts/watch/normalize.py
"""Normalize HTML to a stable text representation before hashing.

Without this, every fetch looks changed (CSRF tokens, build hashes, timestamps)
and the verify layer runs on 100% of sources instead of ~5-15%, which destroys
the entire cost argument for the two-tier design.
"""
from __future__ import annotations

import hashlib
import re

from selectolax.parser import HTMLParser

_DROP_TAGS = ("script", "style", "noscript", "svg", "iframe")
_WHITESPACE = re.compile(r"\s+")


def normalize_html(raw: str) -> str:
    """Strip volatile markup, return collapsed visible text."""
    tree = HTMLParser(raw)
    for tag in _DROP_TAGS:
        for node in tree.css(tag):
            node.decompose()
    text = tree.body.text(separator=" ") if tree.body else tree.text(separator=" ")
    return _WHITESPACE.sub(" ", text).strip()


def content_hash(raw: str) -> str:
    """sha256 of the normalized text. Stable across cosmetic churn."""
    return hashlib.sha256(normalize_html(raw).encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run tests, confirm pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/watch/normalize.py tests/watch/test_normalize.py
git commit -m "feat: stable HTML normalization for content hashing"
```

### Task 1.3: Async watch layer

**Files:**
- Create: `scripts/watch/fetcher.py`, `scripts/watch/runner.py`
- Test: `tests/watch/test_fetcher.py`, `tests/watch/test_runner.py`

**Interfaces:**
- Consumes: `content_hash` (1.2), `AccountSource`/`Probe`/`ScanRun` ORM (0.1)
- Produces: `async fetch_all(sources: list[SourceRef], concurrency: int = 100) -> list[ProbeResult]`
- `ProbeResult` frozen Pydantic: `source_id: int, content_hash: str|None, status_code: int|None, latency_ms: int, bytes: int, error: str|None`

Sajwal 25:00 described Rippling's throughput: "maintain very good concurrency limits... push it across different DNS providers so you don't get throttled... a solid hundred per second." Global concurrency of 100 with per-host politeness of 2 is the honest small-scale version of that. Per-host limiting is what keeps you from hammering one domain 100-wide and getting banned.

- [ ] **Step 1: Write the failing test**

```python
# tests/watch/test_fetcher.py
import pytest, httpx
from scripts.watch.fetcher import fetch_all, SourceRef

@pytest.mark.asyncio
async def test_fetches_and_hashes_all_sources():
    def handler(request):
        return httpx.Response(200, text=f"<div>{request.url.path}</div>")

    refs = [SourceRef(source_id=i, url=f"https://a{i}.com/careers") for i in range(5)]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        results = await fetch_all(refs, client=c, concurrency=3)

    assert len(results) == 5
    assert all(r.content_hash and r.status_code == 200 for r in results)

@pytest.mark.asyncio
async def test_records_error_without_failing_the_batch():
    def handler(request):
        if "bad" in str(request.url):
            raise httpx.ConnectError("boom")
        return httpx.Response(200, text="<div>ok</div>")

    refs = [SourceRef(source_id=1, url="https://ok.com/c"),
            SourceRef(source_id=2, url="https://bad.com/c")]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        results = await fetch_all(refs, client=c, concurrency=2)

    by_id = {r.source_id: r for r in results}
    assert by_id[1].content_hash is not None
    assert by_id[2].error is not None and by_id[2].content_hash is None

@pytest.mark.asyncio
async def test_respects_per_host_concurrency():
    """20 sources on ONE host must not run 20-wide."""
    import asyncio
    inflight = 0
    peak = 0

    async def handler(request):
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        await asyncio.sleep(0.01)
        inflight -= 1
        return httpx.Response(200, text="<div>x</div>")

    refs = [SourceRef(source_id=i, url=f"https://same.com/p{i}") for i in range(20)]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        await fetch_all(refs, client=c, concurrency=20, per_host=2)

    assert peak <= 2
```

- [ ] **Step 2: Run it, confirm it fails** → FAIL, no module

- [ ] **Step 3: Implement**

```python
# scripts/watch/fetcher.py
"""Async watch layer. Cheap GET + content hash across all sources.

Two limits, for two different reasons:
  concurrency — protects US (memory, file descriptors, egress)
  per_host    — protects THEM (politeness; avoids bans that look like "quiet")
The second one matters more: a banned host produces empty results that are
indistinguishable from a genuinely quiet account unless source health catches it.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict

from scripts.watch.normalize import content_hash

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_MAX_BYTES = 2_000_000  # skip hashing pathological pages


class SourceRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_id: int
    url: str


class ProbeResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_id: int
    content_hash: str | None = None
    status_code: int | None = None
    latency_ms: int = 0
    bytes: int = 0
    error: str | None = None


async def _fetch_one(
    client: httpx.AsyncClient,
    ref: SourceRef,
    gate: asyncio.Semaphore,
    host_gates: dict[str, asyncio.Semaphore],
) -> ProbeResult:
    host = urlparse(ref.url).netloc
    started = time.perf_counter()
    async with gate, host_gates[host]:
        try:
            resp = await client.get(ref.url, timeout=_TIMEOUT, follow_redirects=True)
        except httpx.HTTPError as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            logger.warning("Fetch failed %s: %s", ref.url, exc)
            return ProbeResult(source_id=ref.source_id, latency_ms=elapsed, error=str(exc))

    elapsed = int((time.perf_counter() - started) * 1000)
    body = resp.text
    size = len(body.encode("utf-8", errors="ignore"))

    if resp.status_code != 200:
        return ProbeResult(source_id=ref.source_id, status_code=resp.status_code,
                           latency_ms=elapsed, bytes=size,
                           error=f"HTTP {resp.status_code}")
    if size > _MAX_BYTES:
        return ProbeResult(source_id=ref.source_id, status_code=200, latency_ms=elapsed,
                           bytes=size, error="body too large")

    return ProbeResult(source_id=ref.source_id, content_hash=content_hash(body),
                       status_code=200, latency_ms=elapsed, bytes=size)


async def fetch_all(
    sources: list[SourceRef],
    client: httpx.AsyncClient,
    concurrency: int = 100,
    per_host: int = 2,
) -> list[ProbeResult]:
    """Fetch every source. Never raises — failures come back as ProbeResult.error."""
    gate = asyncio.Semaphore(concurrency)
    host_gates: dict[str, asyncio.Semaphore] = defaultdict(
        lambda: asyncio.Semaphore(per_host)
    )
    return list(
        await asyncio.gather(*(_fetch_one(client, s, gate, host_gates) for s in sources))
    )
```

- [ ] **Step 4: Run tests, confirm pass** → `pytest tests/watch/ -v`

- [ ] **Step 5: Implement the runner that persists probes**

```python
# scripts/watch/runner.py
"""One watch pass: load due sources → fetch → persist probes → return changes."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from scripts.storage.models import AccountSource, Probe, ScanRun
from scripts.storage.session import get_session
from scripts.watch.fetcher import SourceRef, fetch_all

logger = logging.getLogger(__name__)
_MAX_CONSECUTIVE_FAILURES = 5


async def run_watch_pass(tenant_id: int, concurrency: int = 100) -> int:
    """Probe all active sources. Returns the scan_run id."""
    with get_session() as session:
        run = ScanRun(tenant_id=tenant_id, started_at=datetime.now(timezone.utc),
                      status="running")
        session.add(run)
        session.flush()
        run_id = run.id

        sources = session.scalars(
            select(AccountSource).where(
                AccountSource.tenant_id == tenant_id, AccountSource.active.is_(True)
            )
        ).all()
        refs = [SourceRef(source_id=s.id, url=s.url) for s in sources]
        by_id = {s.id: s for s in sources}

    async with httpx.AsyncClient(
        headers={"User-Agent": "SignalForce/0.2 (+https://signalforce.fly.dev)"}
    ) as client:
        results = await fetch_all(refs, client=client, concurrency=concurrency)

    changed = 0
    now = datetime.now(timezone.utc)
    with get_session() as session:
        for r in results:
            src = session.get(AccountSource, r.source_id)
            is_change = bool(r.content_hash and r.content_hash != src.last_hash)

            session.add(Probe(tenant_id=tenant_id, account_source_id=r.source_id,
                              scan_run_id=run_id, fetched_at=now,
                              content_hash=r.content_hash, changed=is_change,
                              status_code=r.status_code, latency_ms=r.latency_ms,
                              bytes=r.bytes, error=r.error))

            src.last_fetched_at = now
            if r.error:
                src.consecutive_failures += 1
                if src.consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    # Deactivate, but source_health will still show the drop —
                    # a silently deactivated source is exactly the failure we
                    # are trying to make visible, so log loudly.
                    src.active = False
                    logger.error("Deactivating source %s after %d failures: %s",
                                 src.url, src.consecutive_failures, r.error)
            else:
                src.consecutive_failures = 0
                if is_change:
                    src.last_hash = r.content_hash
                    src.last_changed_at = now
                    changed += 1

        latencies = sorted(r.latency_ms for r in results) or [0]
        run = session.get(ScanRun, run_id)
        run.finished_at = datetime.now(timezone.utc)
        run.status = "completed"
        run.sources_probed = len(results)
        run.changes_detected = changed
        run.p50_latency_ms = latencies[len(latencies) // 2]
        run.p95_latency_ms = latencies[int(len(latencies) * 0.95)]

    logger.info("Watch pass %d: %d sources, %d changed", run_id, len(results), changed)
    return run_id
```

- [ ] **Step 6: Test the runner against an in-memory DB, confirm pass**

- [ ] **Step 7: Commit**

```bash
git add scripts/watch/ tests/watch/
git commit -m "feat: async watch layer with per-host politeness and probe persistence"
```

**Phase 1 exit criteria:** a scheduled watch pass runs on Fly, writes `probes` rows, and `changes_detected / sources_probed` sits somewhere in the 3-20% band. If it's near 100%, normalization is broken — fix that before proceeding, because the entire cost model depends on this ratio.

---

# PHASE 2 — Signals (Week 3, ~10h)

### Task 2.1: Verify gate

**Files:**
- Create: `scripts/verify/gate.py`
- Test: `tests/verify/test_gate.py`

**Interfaces:**
- Produces: `select_for_verification(changes: list[ChangeRef], budget: VerifyBudget) -> list[ChangeRef]`

Not every change deserves an LLM call. A careers page that changed at 2am with 40 bytes of diff is probably a rotating testimonial. Budget is enforced here, not hoped for.

- [ ] **Step 1: Write the failing test**

```python
# tests/verify/test_gate.py
from scripts.verify.gate import select_for_verification, ChangeRef, VerifyBudget

def test_respects_max_calls_budget():
    changes = [ChangeRef(source_id=i, source_type="careers", account_score=50.0)
               for i in range(100)]
    selected = select_for_verification(changes, VerifyBudget(max_calls=10))
    assert len(selected) == 10

def test_prioritizes_higher_scoring_accounts():
    changes = [ChangeRef(source_id=1, source_type="careers", account_score=10.0),
               ChangeRef(source_id=2, source_type="careers", account_score=90.0)]
    selected = select_for_verification(changes, VerifyBudget(max_calls=1))
    assert selected[0].source_id == 2

def test_empty_budget_selects_nothing():
    changes = [ChangeRef(source_id=1, source_type="careers", account_score=99.0)]
    assert select_for_verification(changes, VerifyBudget(max_calls=0)) == []
```

- [ ] **Step 2: Run it, confirm it fails**

- [ ] **Step 3: Implement**

```python
# scripts/verify/gate.py
"""Decide which detected changes earn an expensive extraction.

Budget is a hard cap, not a target. Sorting by account score means when the
budget binds, it binds on accounts you care least about.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# Sources ranked by how often a change is a real signal vs. cosmetic churn.
_SOURCE_PRIORITY = {"careers": 1.0, "changelog": 0.9, "pricing": 0.7, "docs": 0.5,
                    "blog": 0.3}


class ChangeRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_id: int
    source_type: str
    account_score: float = 0.0


class VerifyBudget(BaseModel):
    model_config = ConfigDict(frozen=True)
    max_calls: int
    max_cost_usd: float = 5.0


def select_for_verification(
    changes: list[ChangeRef], budget: VerifyBudget
) -> list[ChangeRef]:
    """Rank by (source priority × account score), take up to budget."""
    ranked = sorted(
        changes,
        key=lambda c: _SOURCE_PRIORITY.get(c.source_type, 0.1) * c.account_score,
        reverse=True,
    )
    return ranked[: budget.max_calls]
```

- [ ] **Step 4: Run tests, confirm pass**

- [ ] **Step 5: Commit** — `git commit -m "feat: verify layer budget gate"`

### Task 2.2: The agent+email repo scanner (the AgentMail bullseye)

**Files:**
- Create: `scripts/scanners/agent_email_scanner.py`
- Test: `tests/scanners/test_agent_email_scanner.py`

**Interfaces:**
- Consumes: `BaseAPIClient` from `scripts/api_client.py` (unchanged)
- Produces: `scan(config: ScannerConfig) -> ScanResult`

Detects repos importing an agent framework **and** an email library — teams building exactly what AgentMail replaces.

- [ ] **Step 1: Write the failing test**

```python
# tests/scanners/test_agent_email_scanner.py
from unittest.mock import patch
from scripts.scanners.agent_email_scanner import scan, AGENT_FRAMEWORKS, EMAIL_LIBS

def _repo(name, org="acme"):
    return {"full_name": f"{org}/{name}", "html_url": f"https://github.com/{org}/{name}",
            "owner": {"login": org, "type": "Organization"},
            "pushed_at": "2026-08-01T00:00:00Z", "stargazers_count": 12}

@patch("scripts.scanners.agent_email_scanner._search_code")
def test_emits_signal_when_repo_has_both(mock_search, scanner_config):
    mock_search.side_effect = lambda q, _: (
        [_repo("bot")] if any(f in q for f in AGENT_FRAMEWORKS) else [_repo("bot")]
    )
    result = scan(scanner_config)
    assert any(s.signal_type == "agent_email_repo" for s in result.signals_found)

@patch("scripts.scanners.agent_email_scanner._search_code")
def test_no_signal_when_only_agent_framework(mock_search, scanner_config):
    mock_search.side_effect = lambda q, _: (
        [_repo("bot")] if any(f in q for f in AGENT_FRAMEWORKS) else []
    )
    result = scan(scanner_config)
    assert result.signals_found == []

@patch("scripts.scanners.agent_email_scanner._search_code")
def test_skips_personal_accounts(mock_search, scanner_config):
    personal = _repo("bot"); personal["owner"]["type"] = "User"
    mock_search.return_value = [personal]
    result = scan(scanner_config)
    assert result.signals_found == []
```

- [ ] **Step 2: Run it, confirm it fails**

- [ ] **Step 3: Implement**

```python
# scripts/scanners/agent_email_scanner.py
"""Detect repos that import BOTH an agent framework AND an email library.

This is the highest-intent signal for AgentMail's ICP: a team shipping an agent
that sends or receives email is, by definition, solving the problem AgentMail
sells a solution to — and they are solving it right now.

Intersection, not union: an agent framework alone means "building agents"
(weak). An email library alone means "sends email" (meaningless). Both in one
repo, first seen recently, means "building an agent that emails" (strong).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from scripts.api_client import APIError, BaseAPIClient
from scripts.config import get_github_token
from scripts.config_loader import ScannerConfig
from scripts.models import ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)

AGENT_FRAMEWORKS = ("openai-agents", "langgraph", "crewai", "mastra", "agno",
                    "autogen", "llama_index.agent", "pydantic_ai")
EMAIL_LIBS = ("resend", "sendgrid", "nodemailer", "smtplib", "postmark",
              "mailgun", "ses.send_email")

_MAX_PER_QUERY = 100


def _client() -> BaseAPIClient:
    return BaseAPIClient(
        base_url="https://api.github.com",
        auth_headers={"Authorization": f"Bearer {get_github_token()}",
                      "Accept": "application/vnd.github+json"},
    )


def _search_code(query: str, client: BaseAPIClient) -> list[dict]:
    """GitHub code search → deduped repo dicts."""
    try:
        data = client.get("/search/code", params={"q": query, "per_page": _MAX_PER_QUERY})
    except APIError:
        logger.exception("Code search failed for %r", query)
        return []
    seen: dict[str, dict] = {}
    for item in data.get("items", []):
        repo = item.get("repository", {})
        if repo.get("full_name"):
            seen[repo["full_name"]] = repo
    return list(seen.values())


def scan(config: ScannerConfig) -> ScanResult:
    """Find org-owned repos importing an agent framework AND an email library."""
    client = _client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.lookback_days or 30)

    agent_repos: dict[str, dict] = {}
    for fw in AGENT_FRAMEWORKS:
        for repo in _search_code(f'"{fw}" language:python language:typescript', client):
            agent_repos[repo["full_name"]] = repo

    email_repos: set[str] = set()
    for lib in EMAIL_LIBS:
        email_repos.update(r["full_name"] for r in _search_code(f'"{lib}"', client))

    signals: list[Signal] = []
    for full_name in set(agent_repos) & email_repos:
        repo = agent_repos[full_name]

        if repo.get("owner", {}).get("type") != "Organization":
            continue  # personal side projects are not buyers

        pushed = repo.get("pushed_at")
        if pushed:
            pushed_dt = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
            if pushed_dt < cutoff:
                continue

        signals.append(
            Signal(
                signal_type="agent_email_repo",
                company_name=repo["owner"]["login"],
                strength=SignalStrength.STRONG,
                source_url=repo["html_url"],
                detected_at=datetime.now(timezone.utc),
                details={
                    "repo": full_name,
                    "stars": repo.get("stargazers_count", 0),
                    "pushed_at": pushed,
                    "rationale": "imports an agent framework and an email library",
                },
            )
        )

    logger.info("agent_email_scanner: %d signals from %d agent repos",
                len(signals), len(agent_repos))
    return ScanResult(scanner_name="agent_email_scanner", signals_found=signals)


if __name__ == "__main__":
    import json
    from scripts.config_loader import load_config

    logging.basicConfig(level=logging.INFO)
    cfg = load_config().scanners["agent_email"]
    print(json.dumps(scan(cfg).model_dump(mode="json"), indent=2))
```

- [ ] **Step 4: Run tests, confirm pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/scanners/agent_email_scanner.py tests/scanners/
git commit -m "feat: agent+email repo scanner for AgentMail ICP"
```

### Task 2.3: Diff-based signal events

**Files:**
- Create: `scripts/verify/differ.py`
- Test: `tests/verify/test_differ.py`

**Interfaces:**
- Produces: `diff_facts(previous: dict, current: dict) -> list[FactChange]`

Sami (Rippling, 13:42): *"design for updates and not rebuilds... the difference first and not snapshot first."* A `signal_event` row is a change, not a state.

- [ ] **Step 1: Write the failing test**

```python
# tests/verify/test_differ.py
from scripts.verify.differ import diff_facts

def test_detects_added_job():
    prev = {"jobs": [{"title": "Engineer"}]}
    curr = {"jobs": [{"title": "Engineer"}, {"title": "AI Agent Engineer"}]}
    changes = diff_facts(prev, curr)
    assert any(c.kind == "added" and c.value["title"] == "AI Agent Engineer"
               for c in changes)

def test_detects_removed_job():
    prev = {"jobs": [{"title": "Engineer"}, {"title": "Designer"}]}
    curr = {"jobs": [{"title": "Engineer"}]}
    assert any(c.kind == "removed" for c in diff_facts(prev, curr))

def test_no_changes_when_identical():
    facts = {"jobs": [{"title": "Engineer"}]}
    assert diff_facts(facts, facts) == []

def test_treats_empty_previous_as_all_added():
    curr = {"jobs": [{"title": "Engineer"}]}
    changes = diff_facts({}, curr)
    assert len(changes) == 1 and changes[0].kind == "added"
```

- [ ] **Step 2: Run it, confirm it fails**

- [ ] **Step 3: Implement**

```python
# scripts/verify/differ.py
"""Turn two extraction snapshots into a list of changes.

The DIFF is the signal. Storing snapshots and re-deriving diffs at query time
means every consumer reimplements the comparison and they drift apart.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict


class FactChange(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["added", "removed"]
    field: str
    value: dict


def _key(item: dict) -> str:
    """Stable identity for a fact, independent of key ordering."""
    return json.dumps(item, sort_keys=True)


def diff_facts(previous: dict, current: dict) -> list[FactChange]:
    """Compare list-valued fields. Missing previous means everything is new."""
    changes: list[FactChange] = []

    for field, curr_items in current.items():
        if not isinstance(curr_items, list):
            continue
        prev_items = previous.get(field, [])
        if not isinstance(prev_items, list):
            prev_items = []

        prev_keys = {_key(i) for i in prev_items}
        curr_keys = {_key(i) for i in curr_items}

        for item in curr_items:
            if _key(item) not in prev_keys:
                changes.append(FactChange(kind="added", field=field, value=item))
        for item in prev_items:
            if _key(item) not in curr_keys:
                changes.append(FactChange(kind="removed", field=field, value=item))

    return changes
```

- [ ] **Step 4: Run tests, confirm pass**

- [ ] **Step 5: Commit** — `git commit -m "feat: diff-based signal event generation"`

---

# PHASE 3 — Measurement (Week 4, ~10h) ★ THE CRITICAL PHASE

**This phase is the entire reason the plan exists.** Everything before it is table stakes; this is what makes "how do you know you caught it fast enough?" a query instead of a fumble. If the schedule slips, cut Phase 5, not this.

### Task 3.1: Holdout set and deep scan

**Files:**
- Create: `scripts/measure/holdout.py`
- Test: `tests/measure/test_holdout.py`

**Interfaces:**
- Produces: `select_holdout(accounts, size, seed) -> list[int]`, `async run_deep_scan(tenant_id) -> list[HoldoutResult]`

- [ ] **Step 1: Write the failing test**

```python
# tests/measure/test_holdout.py
from scripts.measure.holdout import select_holdout

def test_holdout_is_deterministic_for_a_seed():
    accounts = list(range(1, 201))
    assert select_holdout(accounts, size=20, seed=42) == \
           select_holdout(accounts, size=20, seed=42)

def test_holdout_size_is_respected():
    assert len(select_holdout(list(range(1, 201)), size=20, seed=1)) == 20

def test_holdout_caps_at_population_size():
    assert len(select_holdout([1, 2, 3], size=20, seed=1)) == 3
```

- [ ] **Step 2: Run it, confirm it fails**

- [ ] **Step 3: Implement**

```python
# scripts/measure/holdout.py
"""Holdout set: accounts deep-scanned on a fixed cadence, ignoring the watch layer.

This is the ONLY source of ground truth about what the watch layer misses.
Without it, a dead scanner and a quiet market look identical.

Deterministic seeding matters: the holdout must be stable across runs, or you
are measuring a different population every month and the trend is meaningless.
"""
from __future__ import annotations

import logging
import random

logger = logging.getLogger(__name__)


def select_holdout(account_ids: list[int], size: int, seed: int) -> list[int]:
    """Stable pseudo-random sample. Same inputs → same holdout, forever."""
    rng = random.Random(seed)
    return sorted(rng.sample(account_ids, min(size, len(account_ids))))
```

Then `run_deep_scan(tenant_id)`: for each holdout account, bypass the hash check entirely and run full extraction on every source. Write `holdout_scans` rows with `changes_found`.

- [ ] **Step 4: Run tests, confirm pass**

- [ ] **Step 5: Commit** — `git commit -m "feat: deterministic holdout selection"`

### Task 3.2: Recall and detection lag ★

**Files:**
- Create: `scripts/measure/lag.py`
- Test: `tests/measure/test_lag.py`

**Interfaces:**
- Produces: `compute_recall(deep_changes, watch_changes) -> RecallReport`

**This function produces the number that answers Sajwal's question.**

- [ ] **Step 1: Write the failing test**

```python
# tests/measure/test_lag.py
from datetime import datetime, timedelta, timezone
from scripts.measure.lag import compute_recall, DetectedChange

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)

def test_perfect_recall_when_watch_caught_everything():
    deep = [DetectedChange(account_id=1, source_type="careers", detected_at=NOW)]
    watch = [DetectedChange(account_id=1, source_type="careers",
                            detected_at=NOW - timedelta(hours=6))]
    report = compute_recall(deep, watch)
    assert report.recall == 1.0
    assert report.missed_count == 0

def test_missed_change_lowers_recall():
    deep = [DetectedChange(account_id=1, source_type="careers", detected_at=NOW),
            DetectedChange(account_id=2, source_type="careers", detected_at=NOW)]
    watch = [DetectedChange(account_id=1, source_type="careers", detected_at=NOW)]
    report = compute_recall(deep, watch)
    assert report.recall == 0.5
    assert report.missed_count == 1

def test_lag_is_positive_when_watch_was_faster():
    deep = [DetectedChange(account_id=1, source_type="careers", detected_at=NOW)]
    watch = [DetectedChange(account_id=1, source_type="careers",
                            detected_at=NOW - timedelta(hours=12))]
    assert compute_recall(deep, watch).p50_lag_hours == 12.0

def test_no_deep_changes_yields_undefined_recall_not_crash():
    report = compute_recall([], [])
    assert report.recall is None
    assert report.deep_count == 0
```

- [ ] **Step 2: Run it, confirm it fails**

- [ ] **Step 3: Implement**

```python
# scripts/measure/lag.py
"""Recall and detection lag for the watch layer, measured against the holdout.

    recall        = |watch ∩ deep| / |deep|
    detection_lag = deep_detected_at − watch_detected_at   (positive = watch won)

Deep scan is ground truth by construction: it ignores hashes and re-extracts
everything, so anything it finds is real. Anything it finds that the watch layer
did not is a MISS, and misses are the number that actually matters.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DetectedChange(BaseModel):
    model_config = ConfigDict(frozen=True)
    account_id: int
    source_type: str
    detected_at: datetime

    @property
    def key(self) -> tuple[int, str]:
        return (self.account_id, self.source_type)


class RecallReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    recall: float | None
    deep_count: int
    caught_count: int
    missed_count: int
    p50_lag_hours: float | None
    p95_lag_hours: float | None
    missed_keys: list[tuple[int, str]]


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(int(len(ordered) * pct), len(ordered) - 1)
    return ordered[idx]


def compute_recall(
    deep_changes: list[DetectedChange], watch_changes: list[DetectedChange]
) -> RecallReport:
    """Compare ground truth against what the watch layer caught."""
    watch_by_key: dict[tuple[int, str], datetime] = {}
    for c in watch_changes:
        # Earliest watch detection wins — that's when we actually knew.
        prev = watch_by_key.get(c.key)
        if prev is None or c.detected_at < prev:
            watch_by_key[c.key] = c.detected_at

    caught: list[float] = []
    missed: list[tuple[int, str]] = []

    for change in deep_changes:
        seen_at = watch_by_key.get(change.key)
        if seen_at is None:
            missed.append(change.key)
        else:
            caught.append((change.detected_at - seen_at).total_seconds() / 3600.0)

    deep_count = len(deep_changes)
    return RecallReport(
        recall=(len(caught) / deep_count) if deep_count else None,
        deep_count=deep_count,
        caught_count=len(caught),
        missed_count=len(missed),
        p50_lag_hours=_percentile(caught, 0.50),
        p95_lag_hours=_percentile(caught, 0.95),
        missed_keys=missed,
    )
```

- [ ] **Step 4: Run tests, confirm pass**

- [ ] **Step 5: Commit** — `git commit -m "feat: watch layer recall and detection lag measurement"`

### Task 3.3: Source health and silent-breakage alerting

**Files:**
- Create: `scripts/measure/health.py`
- Test: `tests/measure/test_health.py`

**Interfaces:**
- Produces: `compute_health(probes, source_type, run_date) -> SourceHealth`, `detect_anomaly(current, trailing) -> Anomaly | None`

Sami (Rippling, 17:07): *"you can't really tell real quiet from a broken scanner."* Correct — unless you measure it. Zero-result rate jumping >3σ above the trailing 14-day mean is a broken parser, not a quiet market.

- [ ] **Step 1: Write the failing test**

```python
# tests/measure/test_health.py
from scripts.measure.health import detect_anomaly, SourceHealth
from datetime import date

def _h(rate, day=1):
    return SourceHealth(source_type="careers", run_date=date(2026, 8, day),
                        fetch_success_rate=1.0, parse_success_rate=1.0,
                        zero_result_rate=rate, sample_size=100)

def test_flags_zero_result_spike():
    trailing = [_h(0.12, d) for d in range(1, 15)]
    assert detect_anomaly(_h(1.0, 15), trailing) is not None

def test_no_alert_for_normal_variation():
    trailing = [_h(0.10 + (i % 3) * 0.01, i + 1) for i in range(14)]
    assert detect_anomaly(_h(0.12, 15), trailing) is None

def test_no_alert_without_enough_history():
    assert detect_anomaly(_h(1.0, 5), [_h(0.1, 1), _h(0.1, 2)]) is None
```

- [ ] **Step 2: Run it, confirm it fails**

- [ ] **Step 3: Implement**

```python
# scripts/measure/health.py
"""Per-source health metrics and silent-breakage detection.

Three rates, because there are three distinct failure modes:
  fetch_success_rate — network/ban failures     (we can't reach it)
  parse_success_rate — extraction failures      (we reached it, couldn't read it)
  zero_result_rate   — structural drift         (we read it, found nothing)

The third is the dangerous one. A site redesign silently zeroes your results and
nothing errors. Only the trend catches it.
"""
from __future__ import annotations

import statistics
from datetime import date

from pydantic import BaseModel, ConfigDict

_MIN_HISTORY = 7
_SIGMA_THRESHOLD = 3.0


class SourceHealth(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_type: str
    run_date: date
    fetch_success_rate: float
    parse_success_rate: float
    zero_result_rate: float
    sample_size: int


class Anomaly(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_type: str
    metric: str
    current: float
    baseline_mean: float
    sigma: float
    message: str


def detect_anomaly(
    current: SourceHealth, trailing: list[SourceHealth]
) -> Anomaly | None:
    """Flag a zero-result-rate spike beyond 3σ of the trailing baseline."""
    if len(trailing) < _MIN_HISTORY:
        return None

    rates = [h.zero_result_rate for h in trailing]
    mean = statistics.mean(rates)
    stdev = statistics.stdev(rates) if len(rates) > 1 else 0.0

    # A flat baseline that suddenly moves is still an anomaly; guard div-by-zero.
    if stdev == 0.0:
        if current.zero_result_rate > mean + 0.25:
            return Anomaly(source_type=current.source_type, metric="zero_result_rate",
                           current=current.zero_result_rate, baseline_mean=mean,
                           sigma=float("inf"),
                           message=f"{current.source_type}: zero-result rate "
                                   f"{current.zero_result_rate:.0%} vs flat baseline "
                                   f"{mean:.0%} — likely parser breakage")
        return None

    sigma = (current.zero_result_rate - mean) / stdev
    if sigma < _SIGMA_THRESHOLD:
        return None

    return Anomaly(
        source_type=current.source_type, metric="zero_result_rate",
        current=current.zero_result_rate, baseline_mean=mean, sigma=sigma,
        message=(f"{current.source_type}: zero-result rate "
                 f"{current.zero_result_rate:.0%} is {sigma:.1f}σ above "
                 f"{mean:.0%} baseline — likely parser breakage, not quiet market"),
    )
```

- [ ] **Step 4: Run tests, confirm pass**

- [ ] **Step 5: Commit** — `git commit -m "feat: source health metrics and silent-breakage alerts"`

### Task 3.4: Probe retention and rollup

**Files:**
- Create: `scripts/measure/retention.py`
- Test: `tests/measure/test_retention.py`

**Interfaces:**
- Consumes: `compute_health` (3.3), `Probe` / `SourceHealth` ORM
- Produces: `rollup_and_prune(tenant_id, session, now) -> RetentionReport`

**Why this exists.** `probes` is the only unbounded table in the schema — one row per source per run, forever. The arithmetic:

```
rows/day = accounts × sources                    row ≈ 150 bytes with index overhead

   500 accounts × 4  =  2,000/day  →  110 MB/year   fits Neon's 0.5 GB free tier for years
 5,000 accounts × 4  = 20,000/day  →  1.1 GB/year   blows it in ~5 months
```

Individual probe rows have a short useful life. What you actually query long-term is the *aggregate* — `source_health` — which is already computed daily by Task 3.3. So roll up, then prune. Storage goes from linear-in-time to flat.

**Two-tier retention.** Unchanged probes are the bulk (85-95%) and the least interesting: they only ever proved a source was alive, and `source_health` already records that. Changed probes are the forensic record — when detection lag or a missed signal needs explaining, these are what you read. So:

| Probe | Retained | Rationale |
|---|---|---|
| `changed = False` | 30 days | Aggregate survives in `source_health`; the row itself adds nothing |
| `changed = True` | 180 days | ~10% of volume, and the only per-event evidence for lag debugging |

Steady state at 5,000 accounts: ~600K unchanged + ~360K changed ≈ 144 MB. Flat, not growing.

**The safety property that matters.** Never delete a probe whose `source_health` rollup does not exist — that silently destroys data with no aggregate to replace it. The prune must verify the rollup landed first. A retention job that runs before its rollup is a data-loss bug that reports success.

- [ ] **Step 1: Write the failing test**

```python
# tests/measure/test_retention.py
from datetime import datetime, timedelta, timezone
from scripts.measure.retention import rollup_and_prune

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_prunes_unchanged_probes_older_than_30_days(session, tenant, seeded_health):
    _probe(session, tenant, fetched_at=NOW - timedelta(days=45), changed=False)
    report = rollup_and_prune(tenant.id, session, now=NOW)
    assert report.unchanged_pruned == 1


def test_keeps_unchanged_probes_inside_the_window(session, tenant, seeded_health):
    _probe(session, tenant, fetched_at=NOW - timedelta(days=10), changed=False)
    assert rollup_and_prune(tenant.id, session, now=NOW).unchanged_pruned == 0


def test_keeps_changed_probes_for_180_days(session, tenant, seeded_health):
    _probe(session, tenant, fetched_at=NOW - timedelta(days=45), changed=True)
    assert rollup_and_prune(tenant.id, session, now=NOW).changed_pruned == 0


def test_prunes_changed_probes_past_180_days(session, tenant, seeded_health):
    _probe(session, tenant, fetched_at=NOW - timedelta(days=200), changed=True)
    assert rollup_and_prune(tenant.id, session, now=NOW).changed_pruned == 1


def test_never_prunes_a_day_with_no_source_health_rollup(session, tenant):
    """THE safety property. No aggregate means the row is the only record."""
    _probe(session, tenant, fetched_at=NOW - timedelta(days=45), changed=False)
    report = rollup_and_prune(tenant.id, session, now=NOW)   # no seeded_health fixture
    assert report.unchanged_pruned == 0
    assert report.skipped_days_missing_rollup == 1


def test_rollup_is_idempotent(session, tenant):
    """Re-running must not double-count into source_health."""
    _probe(session, tenant, fetched_at=NOW - timedelta(days=45), changed=False)
    first = rollup_and_prune(tenant.id, session, now=NOW)
    second = rollup_and_prune(tenant.id, session, now=NOW)
    assert second.rows_rolled_up == 0
    assert first.rows_rolled_up >= 1


def test_prune_is_batched(session, tenant, seeded_health):
    """A single unbounded DELETE can hold a lock long enough to stall the scan run."""
    for _ in range(2500):
        _probe(session, tenant, fetched_at=NOW - timedelta(days=45), changed=False)
    report = rollup_and_prune(tenant.id, session, now=NOW, batch_size=1000)
    assert report.unchanged_pruned == 2500
    assert report.batches >= 3
```

- [ ] **Step 2: Run tests, confirm they fail** — `pytest tests/measure/test_retention.py -v`

- [ ] **Step 3: Implement**

Order of operations is the whole design — do not reorder:

```
  1. Find distinct probe days older than the shorter cutoff
  2. For each day: ensure a source_health row exists (compute it if missing)
  3. ONLY for days with a confirmed rollup, delete in batches
  4. Report what was rolled up, what was pruned, what was skipped and why
```

Use `ON CONFLICT (tenant_id, source_type, run_date) DO NOTHING` for the upsert so re-runs are idempotent. Batch deletes as `DELETE FROM probes WHERE id IN (SELECT id FROM probes WHERE ... LIMIT :batch_size)` — an unbounded `DELETE` over hundreds of thousands of rows holds locks long enough to stall a concurrent scan run.

`RetentionReport` is a frozen Pydantic model: `rows_rolled_up`, `unchanged_pruned`, `changed_pruned`, `skipped_days_missing_rollup`, `batches`.

- [ ] **Step 4: Run tests, confirm pass**

- [ ] **Step 5: Wire into the scheduled worker** — runs *after* the watch pass and *after* Task 3.3's health computation, never before. Record counts on the `scan_runs` row.

- [ ] **Step 6: Commit**

```bash
git add scripts/measure/retention.py tests/measure/test_retention.py
git commit -m "feat: probe retention with rollup-before-prune safety guard"
```

---

**Phase 3 exit criteria:** `/dashboard/health` shows recall, p50/p95 detection lag, and per-source zero-result trend, computed from at least two weeks of real runs. Screenshot it. That screenshot is the answer to the question that beat you.

---

# PHASE 4 — Scoring, Audiences, Dashboard (Week 5, ~10h)

### Task 4.1: Scoring engine with replayable trace ★ YOUR CONTRIBUTION

**Files:**
- Create: `scripts/scoring/engine.py`
- Test: `tests/scoring/test_engine.py`

I'll scaffold the types, the trace structure, and the zero-out machinery. **The weighting function itself is yours to write** — see "Your Contribution" at the end of this document. It's ~10 lines and it encodes opinions you already hold and I don't.

- [ ] **Step 1: Write the failing test**

```python
# tests/scoring/test_engine.py
from datetime import datetime, timedelta, timezone
from scripts.scoring.engine import score_account, SignalInput, zero_out

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)

def _sig(kind, days_ago, weight=1.0):
    return SignalInput(signal_type=kind, detected_at=NOW - timedelta(days=days_ago),
                       base_weight=weight, is_icp=False)

def test_recent_signal_outscores_old_signal():
    recent = score_account([_sig("hiring", 1)], now=NOW)
    old = score_account([_sig("hiring", 60)], now=NOW)
    assert recent.score > old.score

def test_breadth_beats_a_single_strong_signal():
    """Sami's stated philosophy: three weak converging > one flashy."""
    three_weak = score_account(
        [_sig("hiring", 3, 0.4), _sig("funding", 5, 0.4), _sig("stack", 4, 0.4)],
        now=NOW)
    one_strong = score_account([_sig("hiring", 3, 1.0)], now=NOW)
    assert three_weak.score > one_strong.score

def test_trace_records_every_contribution():
    result = score_account([_sig("hiring", 1), _sig("funding", 2)], now=NOW)
    assert len(result.trace["components"]) == 2
    assert all("decayed_weight" in c for c in result.trace["components"])

def test_zero_out_isolates_a_signals_contribution():
    signals = [_sig("hiring", 1), _sig("funding", 2)]
    full = score_account(signals, now=NOW)
    without = zero_out(signals, "hiring", now=NOW)
    assert without.score < full.score

def test_empty_signals_score_zero():
    assert score_account([], now=NOW).score == 0.0
```

- [ ] **Step 2: Run it, confirm it fails**

- [ ] **Step 3: Implement the scaffold** (see "Your Contribution" for `_combine`)

```python
# scripts/scoring/engine.py
"""Deterministic, traceable account scoring.

Every score carries a trace so it can be replayed and so individual signals can
be zeroed out to isolate their contribution. Sami (Rippling, 20:24): "zero out
which signal one by one and see which one was actually doing the work."

Deterministic, not learned, on purpose: when a rep says "this account was
terrible," you need to explain WHY it scored 87, not shrug at a model.
"""
from __future__ import annotations

import math
from datetime import datetime

from pydantic import BaseModel, ConfigDict

HALF_LIFE_DAYS = 14.0
ICP_WEIGHT = 0.4
INTENT_WEIGHT = 0.6


class SignalInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    signal_type: str
    detected_at: datetime
    base_weight: float
    is_icp: bool = False


class ScoreResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    score: float
    trace: dict


def recency_decay(detected_at: datetime, now: datetime,
                  half_life_days: float = HALF_LIFE_DAYS) -> float:
    """Exponential decay. A 48h-old signal is worth far more than a 6-week-old one."""
    age_days = max((now - detected_at).total_seconds() / 86400.0, 0.0)
    return math.pow(0.5, age_days / half_life_days)


def score_account(signals: list[SignalInput], now: datetime) -> ScoreResult:
    """Score an account, recording every contribution in the trace."""
    components: list[dict] = []
    for sig in signals:
        decay = recency_decay(sig.detected_at, now)
        components.append({
            "signal_type": sig.signal_type,
            "base_weight": sig.base_weight,
            "age_days": round((now - sig.detected_at).total_seconds() / 86400.0, 2),
            "decay": round(decay, 4),
            "decayed_weight": round(sig.base_weight * decay, 4),
            "is_icp": sig.is_icp,
        })

    score = _combine(components)   # ◀── YOUR CONTRIBUTION
    return ScoreResult(
        score=round(score, 2),
        trace={"components": components, "half_life_days": HALF_LIFE_DAYS,
               "icp_weight": ICP_WEIGHT, "intent_weight": INTENT_WEIGHT,
               "computed_at": now.isoformat()},
    )


def zero_out(signals: list[SignalInput], signal_type: str,
             now: datetime) -> ScoreResult:
    """Rescore with one signal type removed. Isolates its real contribution."""
    return score_account([s for s in signals if s.signal_type != signal_type], now=now)
```

- [ ] **Step 4: Run tests, confirm pass**

- [ ] **Step 5: Commit** — `git commit -m "feat: traceable scoring engine with zero-out analysis"`

### Task 4.2: Personas and composable audiences

**Files:**
- Create: `scripts/scoring/personas.py`, `scripts/scoring/audiences.py`
- Test: `tests/scoring/test_personas.py`, `tests/scoring/test_audiences.py`

Sajwal 28:49 and 29:26 — job titles map to persona subcategories, and any signals compose into an audience.

- [ ] **Step 1: Write the failing tests**

```python
# tests/scoring/test_audiences.py
from datetime import datetime, timedelta, timezone
from scripts.scoring.audiences import evaluate, AccountFacts

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)

def _facts(**kw):
    return AccountFacts(account_id=1, signals=kw.get("signals", []),
                        score=kw.get("score", 0.0))

def test_and_requires_both_predicates():
    pred = {"and": [{"has_signal": "hiring"}, {"has_signal": "funding"}]}
    assert evaluate(pred, _facts(signals=["hiring", "funding"])) is True
    assert evaluate(pred, _facts(signals=["hiring"])) is False

def test_or_requires_either():
    pred = {"or": [{"has_signal": "hiring"}, {"has_signal": "funding"}]}
    assert evaluate(pred, _facts(signals=["funding"])) is True

def test_not_inverts():
    assert evaluate({"not": {"has_signal": "hiring"}}, _facts(signals=[])) is True

def test_min_score_gate():
    assert evaluate({"min_score": 70}, _facts(score=85.0)) is True
    assert evaluate({"min_score": 70}, _facts(score=50.0)) is False

def test_nested_composition():
    pred = {"and": [{"or": [{"has_signal": "hiring"},
                            {"has_signal": "agent_email_repo"}]},
                    {"min_score": 60}]}
    assert evaluate(pred, _facts(signals=["agent_email_repo"], score=75.0)) is True
```

- [ ] **Step 2: Run them, confirm they fail**

- [ ] **Step 3: Implement**

```python
# scripts/scoring/audiences.py
"""Composable signal predicates.

Sajwal (Rippling, 29:26): "every single signal can be stacked to build an
audience... whatever is your money-making combo."

A recursive JSON predicate rather than a fixed score threshold, because the
useful query is "hiring field marketers AND raised in 30d" — a shape no single
scalar can express.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AccountFacts(BaseModel):
    model_config = ConfigDict(frozen=True)
    account_id: int
    signals: list[str]
    score: float


def evaluate(predicate: dict, facts: AccountFacts) -> bool:
    """Recursively evaluate a predicate against an account's facts."""
    if "and" in predicate:
        return all(evaluate(p, facts) for p in predicate["and"])
    if "or" in predicate:
        return any(evaluate(p, facts) for p in predicate["or"])
    if "not" in predicate:
        return not evaluate(predicate["not"], facts)
    if "has_signal" in predicate:
        return predicate["has_signal"] in facts.signals
    if "min_score" in predicate:
        return facts.score >= predicate["min_score"]
    raise ValueError(f"Unknown predicate: {predicate!r}")
```

- [ ] **Step 4: Run tests, confirm pass**

- [ ] **Step 5: Commit** — `git commit -m "feat: persona model and composable audience predicates"`

### Task 4.3: Read-only dashboard

**Files:**
- Create: `scripts/web/routes_dashboard.py`, `scripts/web/templates/{base,accounts,account_detail,health}.html`
- Test: `tests/web/test_dashboard.py`

Four pages, Jinja2 + HTMX, no build step:

| Route | Shows |
|---|---|
| `/dashboard` | Top-scored accounts, signal chips, last-changed |
| `/dashboard/account/{id}` | Full score trace, signal timeline, source registry, zero-out table |
| `/dashboard/health` | **Recall, p50/p95 detection lag, per-source zero-result trend** |
| `/dashboard/runs` | Scan run history: duration, sources probed, change rate, cost |

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_dashboard.py
from fastapi.testclient import TestClient
from scripts.web.app import create_app

def test_dashboard_renders(seeded_db):
    resp = TestClient(create_app()).get("/dashboard")
    assert resp.status_code == 200
    assert "Accounts" in resp.text

def test_health_page_shows_recall(seeded_db):
    resp = TestClient(create_app()).get("/dashboard/health")
    assert resp.status_code == 200
    assert "Recall" in resp.text and "Detection lag" in resp.text
```

- [ ] **Step 2: Run it, confirm it fails**
- [ ] **Step 3: Implement routes and templates**
- [ ] **Step 4: Run tests, confirm pass**
- [ ] **Step 5: Deploy and screenshot**

```bash
fly deploy && open https://signalforce.fly.dev/dashboard/health
```

- [ ] **Step 6: Commit** — `git commit -m "feat: read-only dashboard with health metrics"`

---

# PHASE 5 — AgentMail Outbound (Week 6, ~10h)

**Cut this first if the schedule slips.** Phases 0-4 fix the interview gaps on their own. This phase adds the outcome loop and the customer-of-AgentMail angle.

### Task 5.1: AgentMail client

**Files:**
- Create: `scripts/outreach/agentmail.py`
- Test: `tests/outreach/test_agentmail.py`

**Interfaces:**
- Produces: `AgentMailClient.create_inbox(...)`, `.send(...)`, `.get_thread(...)`

Built on the existing `BaseAPIClient` — its retry and rate-limit handling is already correct, so this is a thin subclass, not a new transport.

- [ ] **Step 1: Write the failing test**

```python
# tests/outreach/test_agentmail.py
import pytest
from unittest.mock import patch
from scripts.outreach.agentmail import AgentMailClient
from scripts.api_client import APIError

@patch.object(AgentMailClient, "post")
def test_create_inbox_returns_id(mock_post):
    mock_post.return_value = {"inbox_id": "ib_123", "address": "a@x.agentmail.to"}
    assert AgentMailClient(api_key="k").create_inbox("outbound").inbox_id == "ib_123"

@patch.object(AgentMailClient, "post")
def test_send_returns_thread_id(mock_post):
    mock_post.return_value = {"thread_id": "th_9", "message_id": "msg_1"}
    sent = AgentMailClient(api_key="k").send(
        inbox_id="ib_123", to="p@acme.com", subject="s", text="b")
    assert sent.thread_id == "th_9"

@patch.object(AgentMailClient, "post")
def test_api_errors_propagate(mock_post):
    mock_post.side_effect = APIError(status_code=401, message="bad key", url="/inboxes")
    with pytest.raises(APIError):
        AgentMailClient(api_key="bad").create_inbox("x")
```

- [ ] **Step 2: Run it, confirm it fails**

- [ ] **Step 3: Implement**

```python
# scripts/outreach/agentmail.py
"""AgentMail API client — programmatic inboxes for agent-driven outbound.

Subclasses BaseAPIClient so 429/5xx backoff behaviour is shared with every other
integration rather than reimplemented per-vendor.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict

from scripts.api_client import BaseAPIClient

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.agentmail.to/v0"


class Inbox(BaseModel):
    model_config = ConfigDict(frozen=True)
    inbox_id: str
    address: str


class SentMessage(BaseModel):
    model_config = ConfigDict(frozen=True)
    thread_id: str
    message_id: str


class AgentMailClient(BaseAPIClient):
    """Thin typed wrapper over AgentMail's REST API."""

    def __init__(self, api_key: str, timeout: int = 30) -> None:
        super().__init__(
            base_url=_BASE_URL,
            auth_headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def create_inbox(self, username: str, domain: str | None = None) -> Inbox:
        payload = {"username": username}
        if domain:
            payload["domain"] = domain
        data = self.post("/inboxes", json_data=payload)
        logger.info("Created AgentMail inbox %s", data.get("inbox_id"))
        return Inbox(inbox_id=data["inbox_id"], address=data["address"])

    def send(self, inbox_id: str, to: str, subject: str, text: str) -> SentMessage:
        data = self.post(f"/inboxes/{inbox_id}/messages/send",
                         json_data={"to": [to], "subject": subject, "text": text})
        return SentMessage(thread_id=data["thread_id"], message_id=data["message_id"])

    def get_thread(self, inbox_id: str, thread_id: str) -> dict:
        return self.get(f"/inboxes/{inbox_id}/threads/{thread_id}")
```

- [ ] **Step 4: Run tests, confirm pass**

- [ ] **Step 5: Commit** — `git commit -m "feat: AgentMail API client for outbound"`

### Task 5.2: Reply webhook and outcome loop

**Files:**
- Create: `scripts/web/routes_webhooks.py`
- Test: `tests/web/test_webhooks.py`

Reply data closes the loop Sajwal pushed on: *"how would you know the signal worked?"* With replies stored against `triggering_signal_ids`, cohort comparison becomes a SQL query.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_webhooks.py
from fastapi.testclient import TestClient
from scripts.web.app import create_app

def test_reply_webhook_records_reply(seeded_outreach):
    client = TestClient(create_app())
    resp = client.post("/webhooks/agentmail",
                       json={"event": "message.received",
                             "thread_id": seeded_outreach.agentmail_thread_id,
                             "text": "sure, let's talk"})
    assert resp.status_code == 200

def test_unknown_thread_is_ignored_not_errored():
    client = TestClient(create_app())
    resp = client.post("/webhooks/agentmail",
                       json={"event": "message.received", "thread_id": "th_nope",
                             "text": "hi"})
    assert resp.status_code == 200  # webhooks must never 500 — senders retry forever
```

- [ ] **Step 2: Run it, confirm it fails**
- [ ] **Step 3: Implement the webhook handler with signature verification**
- [ ] **Step 4: Run tests, confirm pass**
- [ ] **Step 5: Commit** — `git commit -m "feat: AgentMail reply webhook and outcome tracking"`

### Task 5.3: Cohort lift analysis

**Files:**
- Create: `scripts/measure/cohort.py`
- Test: `tests/measure/test_cohort.py`

**Interfaces:**
- Produces: `compute_lift(cohort_a, cohort_b) -> LiftReport` with reply rate, sample size, and a two-proportion z-test

The answer to "how do you know the signal works?" becomes: *"Accounts with agent_email_repo replied at 11.2% vs 3.1% baseline, n=180 and n=1,400, p=0.003."*

- [ ] Standard TDD cycle. Guard against reporting lift on tiny samples — require n≥30 per arm or return `insufficient_data`.
- [ ] **Commit** — `git commit -m "feat: cohort lift analysis for signal validation"`

### Task 5.4: Retire `scripts/db.py` (deferred from Task 0.1 by D8)

**Files:**
- Modify: `scripts/outcome_tracker.py` → use `scripts/storage/`
- Delete: `scripts/db.py`, `tests/unit/test_db.py`
- Modify: `tests/unit/test_outcome_tracker.py`

By this point `contacts` and `outreach` exist and carry `triggering_signal_ids`, which is
strictly better than the old `tracked_signals` / `outreach_events` pair — outcomes tie
directly to the signal rows that caused them, so cohort lift is a join rather than a
reconstruction.

- [ ] Map the four legacy tables onto the new schema. `campaigns` → `audiences`;
      `tracked_signals` → `signal_events`; `outreach_events` + `outcome_events` →
      `outreach` (sent/replied columns).
- [ ] Write a one-shot backfill script if `data/signalforce.db` holds real rows worth
      keeping. If it holds only test data, say so and skip the backfill.
- [ ] Port `outcome_tracker.py`, keeping its public function signatures so callers
      don't change.
- [ ] Run the full suite, delete `scripts/db.py` and `tests/unit/test_db.py`.
- [ ] **Commit** — `git commit -m "refactor: retire SQLite db.py, outcome tracking on storage layer"`

---

## Failure Modes

| # | Codepath | Failure | Test? | Handled? | User sees? |
|---|---|---|---|---|---|
| 1 | `watch/fetcher` | Host bans us; all fetches 403 | ✅ error test | ✅ `consecutive_failures` → deactivate | ⚠️ **Only via source health.** Without Phase 3 this is silent. |
| 2 | `watch/normalize` | Site redesign → hash churns every run | ✅ normalize tests | ⚠️ Partial | ⚠️ Verify budget absorbs it, cost spikes. Add change-rate alert. |
| 3 | `verify/extractor` | LLM returns malformed JSON | ✅ parse test | ✅ parse_success_rate | ✅ Health page |
| 4 | `registry/resolver` | Careers page moves | ⚠️ **GAP** | ⚠️ **GAP** | ❌ **SILENT** — see critical gap below |
| 5 | `scoring/engine` | All signals decay to ~0 | ✅ decay test | ✅ Score → 0 | ✅ Account drops off dashboard |
| 6 | `outreach/agentmail` | API down mid-send | ✅ error test | ✅ APIError propagates | ✅ Outreach marked failed |
| 7 | `measure/lag` | Holdout too small → noisy recall | ✅ empty test | ⚠️ Partial | ⚠️ Show n on health page |
| 8 | `web/routes_webhooks` | Duplicate webhook delivery | ⚠️ **GAP** | ⚠️ **GAP** | ❌ Double-counted replies |

**CRITICAL GAP — #4.** A resolved URL 404s after a site restructure. `consecutive_failures` deactivates the source after 5 runs, and then that account produces zero signals forever with no error and no alert. Silent, permanent, and it looks exactly like a quiet account. **Fix, added to Phase 1:** on deactivation, enqueue re-resolution rather than giving up; surface `deactivated_sources` count on the health page.

**CRITICAL GAP — #8.** Webhook senders retry. Without an idempotency key on `(thread_id, message_id)`, one reply counts two or three times and corrupts the cohort lift numbers — the exact numbers meant to be defensible. **Fix, added to Phase 5:** `UNIQUE(agentmail_message_id)` on the reply table, `ON CONFLICT DO NOTHING`.

---

## NOT in Scope

| Deferred | Why |
|---|---|
| Auth, signup, billing | D4: engine + dashboard. Least persuasive work to a 10-person team, most hours. |
| Real tenant isolation (RLS, per-tenant creds) | Schema carries `tenant_id`; enforcement is a Phase 6 concern when a second tenant exists. Say "designed, one tenant running." |
| Queues (SQS/Celery) | Daily batch over ~5K accounts fits comfortably in one process. Adding a broker now is an innovation token spent on a problem you don't have. |
| Sharding | `docs/system-design/02-sharding.md` puts the threshold near 500M rows. Current scale is ~7 orders of magnitude below it. Do the math out loud if asked; don't build it. |
| Redis caching | No measured read bottleneck. Caching without a quantified bottleneck is the exact name-dropping failure `docs/system-design/03-caching.md` warns about. |
| React/Next frontend | Jinja2 + HTMX is read-only-appropriate and has no build step. |
| Contact enrichment (Apollo/Hunter) | Existing code covers it; not on the critical path to the four numbers. |
| n8n workflows | Superseded by the scheduled worker. |
| Second tenant config | D6: AgentMail specifically. Config-driven architecture makes this a YAML edit later. |
| Partitioning `probes` | Superseded by Task 3.4 retention — rollup-then-prune holds the table flat at ~144 MB, so it never reaches the ~10M-row threshold where partitioning pays. Revisit only if retention is removed. |
| Neon paid tier | Free tier (0.5 GB storage, 100 CU-hours/mo) is sufficient once Task 3.4 caps `probes`. Compute is comfortable because the workload is a daily batch that lets the database autosuspend ~23h/day. |

---

## Parallelization

| Lane | Tasks | Modules | Depends on |
|---|---|---|---|
| **A** | 0.1 → 0.2 → 0.3 | `storage/`, `web/`, infra | — |
| **B** | 1.1 → 1.2 → 1.3 | `registry/`, `watch/` | A (storage) |
| **C** | 2.2 | `scanners/` | A (models only) |
| **D** | 4.1 → 4.2 | `scoring/` | A (models only) |
| **E** | 3.1 → 3.2 → 3.3 | `measure/` | B (probe data) |
| **F** | 5.1 → 5.2 → 5.3 | `outreach/` | A, D |

**Order:** A must finish first. Then **B, C, D run in parallel** — disjoint modules, no shared files. E waits on B. F waits on D.

**Conflict flag:** C and D both touch `scripts/models.py` for new Signal types. Land the model additions in a single commit at the end of A to avoid a merge conflict.

Solo at 10h/week you'll work sequentially anyway — but this is the map if you dispatch parallel subagents.

---

## Interview Answers This Unlocks

Bank these only once the number exists in the database. Every one is "ran," not "designed."

| Question | Answer after this plan |
|---|---|
| "Where does it run?" | Fly.io, sjc region, Docker, Neon Postgres, migrations on release. Live since [Phase 0 date]. |
| "What database?" | Postgres 16 on Neon. 12 tables. `probes` is highest-volume — partition at ~10M rows, currently ~N. |
| "How do you know you caught a change fast enough?" | 40-account holdout deep-scanned weekly. Recall N%, p50 lag N hours, p95 N hours. |
| "How do you know a scanner isn't broken?" | Zero-result rate per source vs trailing-14d mean. Alert at 3σ. It caught [real incident]. |
| "What does it cost?" | $N/month. Two-tier design; verify runs on N% of probes. |
| "How do you know the signal works?" | Cohort: signal-present replied at N% vs N% baseline, n=N, p=N. |
| "Would this scale to 2M accounts?" | Watch layer is the bottleneck — 2M×4 sources at 100 concurrent is N hours. Fixes in order: raise concurrency, shard by `hash(account_id)`, tier cadence by score. Sharding math says not until ~500M. |
| "What broke?" | [Whatever actually broke.] Keep an incident log from day one. |

---

## Your Contribution — the weighting function

**File:** `scripts/scoring/engine.py`, function `_combine(components: list[dict]) -> float`

Everything around it is scaffolded: decay is computed, the trace is populated, `zero_out()` works. What's missing is how contributions combine into one number — and that encodes opinions you hold and I don't.

From the Rippling transcript and your SignalForce retrospective, you've said:
- ICP × 0.4 + Intent × 0.6 — intent weighted over fit
- Recency weighted hard
- **"three weak signals converging beats one flashy signal"** (Sajwal, 6:10)
- Breadth multiplier for signal diversity
- "Rather skip a prospect than send garbage"

The tension to resolve: a plain sum lets one huge signal dominate, which contradicts your convergence belief. A plain average punishes accounts for having *more* evidence. Something has to give.

```python
def _combine(components: list[dict]) -> float:
    """Combine decayed signal contributions into a 0-100 account score.

    Each component dict has:
        signal_type: str
        base_weight: float      (0-1, per-signal-type importance)
        age_days: float
        decay: float            (0-1, exponential, 14-day half-life)
        decayed_weight: float   (base_weight * decay)
        is_icp: bool            (True = fit signal, False = intent signal)

    Must satisfy the tests in tests/scoring/test_engine.py:
      - recent > old for identical signals
      - three weak converging signals > one strong signal
      - empty list returns 0.0
      - output bounded 0-100

    Consider: how do you express breadth? A multiplier on distinct signal_type
    count? Diminishing returns via sqrt or log on the sum? A convergence bonus
    that only fires at 3+ distinct types? Each choice says something different
    about what you believe a "buying window" is.
    """
    # TODO(sami): ~10 lines. This is the opinion at the center of the product.
    raise NotImplementedError
```

Write that one and I'll wire the rest around it.

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| 60h estimate is optimistic for 6 phases | **HIGH** | Phase 5 is explicitly cuttable. Phases 0-4 stand alone. |
| GitHub code search rate limits throttle Signal 1 | **MED** | 10 req/min authenticated. Cache aggressively, run nightly, narrow queries. `api_client.py` already handles 403-quota. |
| AgentMail fills the GTM role before you ship | **MED** | Phase 0-1 alone (deployed + running) is worth reaching out on. Don't wait for Phase 5 to make contact. |
| Momentum loss at 10h/week | **HIGH** | Phase 0 makes it live in week one, so there's always something running to come back to. |
| Holdout too small for meaningful recall | **MED** | Start at 40 accounts. Report n alongside every rate. Never quote a rate without its sample size — that's the 8%-vs-48% failure repeating. |
| Two-tier ratio near 100% (normalization broken) | **HIGH** | Phase 1 exit criteria checks this explicitly before Phase 2 starts. |

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | ISSUES_OPEN | 2 critical gaps (silent source death, webhook dedup), both folded into plan |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**UNRESOLVED:** 0 — all scope decisions locked via D4 (surface), D6 (target), D7 (sending).
**VERDICT:** ENG CLEARED — ready to implement. Start at Phase 0, Task 0.1.
