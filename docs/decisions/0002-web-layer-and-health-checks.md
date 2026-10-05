# ADR-0002: FastAPI web layer, server-rendered templates, and liveness/readiness split

**Status:** Accepted
**Date:** 2026-08-04
**Scope:** Phase 0, Task 0.2 — `scripts/web/`

---

## Context

The deployed system needs three HTTP surfaces, and they have almost nothing in common:

1. **Health endpoints** — consumed by Fly.io's checker, machine-to-machine, must be trivial
2. **A read-only dashboard** — HTML, human-consumed, showing accounts / traces / health metrics
3. **A webhook receiver + small JSON API** — AgentMail reply delivery (Phase 5), plus `/api/v1/*`

Task 0.2 builds only the health endpoints and the app skeleton. The other two land in Phases 4 and 5. But the framework choice is made now and binds all three, so it gets reasoned about now.

## Decision 1 — FastAPI, and the honest reason why

**Chosen:** FastAPI with an app-factory (`create_app()`) plus a module-level `app` for uvicorn.

**The reason that is usually given and does not apply here:** "FastAPI is async, and async is fast." The web process in this architecture does very little concurrent I/O. The genuinely async work — 100-way concurrent fetching — lives in the **worker** process (`scripts/watch/fetcher.py`), which is plain asyncio and needs no web framework at all. Choosing FastAPI for its async support would be selecting on a property this workload does not exercise. Saying so out loud is the difference between a reason and a name-drop.

**The two reasons that do apply:**

1. **Pydantic is already the project's data language.** `scripts/models.py` is entirely Pydantic with `frozen=True`. AgentMail's webhook payload arrives as untrusted JSON from the network and needs validation at the boundary — a hard project rule. In FastAPI that validation is the type annotation. In Flask it is marshmallow, or hand-written `if "thread_id" not in payload` checks that drift from the model.
2. **`/api/v1/*` gets OpenAPI docs for free.** If someone at AgentMail is handed this system, a live `/docs` page is worth more than a README section, and it cannot go stale because it is generated from the code.

**Rejected: Flask.** Genuinely simpler, mature, Jinja2 is native rather than bolted on, and it would work. The deciding factor is validation: every webhook and API boundary needs schema enforcement, and Flask makes that a separate library and a separate set of classes that duplicate the Pydantic models already in the repo. That is a DRY violation across a boundary the project crosses often.

**Rejected: Django.** Django's value is its ORM, admin, auth, and migrations working as one system. ADR-0001 chose SQLAlchemy + Alembic, and ADR-0001's D4 defers auth entirely. Adopting Django means either abandoning those decisions or fighting the framework at every layer. Wrong tool for a system whose persistence story is already settled.

**Rejected: a bare ASGI app / Starlette.** FastAPI *is* Starlette plus the validation and docs layer. Dropping to Starlette means giving up the only two reasons FastAPI was chosen.

## Decision 2 — Jinja2 + HTMX, not React/Next

**Chosen:** server-rendered Jinja2 templates, HTMX for the small interactive pieces.

**Rejected: React/Next SPA.** The dashboard is **read-only** (locked in D4). There is no client-side state to manage, no forms, no optimistic updates — the three problems SPAs exist to solve. The cost of an SPA is a Node toolchain in the Docker image, a build step in CI, a second deploy target or a static-asset pipeline, and a JSON API that must exist before any page can render. All of that to display tables.

**Rejected: HTML strings in Python.** Jinja2 is already a declared dependency (used by `scripts/marops/renderer`). Template inheritance and autoescaping are not worth re-inventing, and autoescaping specifically matters: the dashboard renders `source_url` and company names that came from scraped third-party pages. That is untrusted content going into HTML, and Jinja2's autoescape is the XSS defense.

**The cost, stated plainly:** if the dashboard later needs genuine interactivity — drag-to-reorder, live-updating charts, complex filter state — HTMX will strain and a rewrite becomes likely. That is accepted. At 10h/week, building an SPA for a read-only page is spending the budget in the wrong place, and a rewrite that may never be needed is cheaper than a build pipeline that is definitely needed today.

## Decision 3 — Liveness and readiness are different endpoints ★

**This is the decision that matters in this ADR.** The plan originally specified a single `/healthz` returning `{"status": "ok", "db": bool}` with a 200 regardless of database state. That conflates two questions with opposite correct responses.

**Chosen:**

| Endpoint | Question | DB checked? | On failure | Fly config |
|---|---|---|---|---|
| `/healthz` | Is this process alive? | **No** | 200 always, if it responds at all | **This is what Fly's check hits** |
| `/readyz` | Can it serve real traffic? | **Yes** | **503** | Not wired to Fly; for humans and future LB use |

**Why `/healthz` must not check the database.** Fly restarts machines whose health check fails. If Neon has an outage and `/healthz` reports the DB down, Fly kills the web machine, the new machine also can't reach the DB, and it gets killed too. You have converted a **database outage** into a **database outage plus a crash-looping web tier**, destroying your ability to serve anything — including a page that says "we're having database trouble." The restart was never going to fix a remote dependency, so triggering one is pure harm.

This is the standard Kubernetes liveness/readiness distinction. Liveness failure means *this process is broken, replace it*. Readiness failure means *this process is fine but can't serve right now, stop sending it traffic*. Restarting is the correct response to the first and actively harmful for the second.

**Rejected: one endpoint returning 503 when the DB is down.** Correct-looking, and it produces the crash loop above.

**Rejected: one endpoint always returning 200 with a `db` field** (the plan's original). Never crash-loops, but nothing is watching the field, so a database outage is invisible to every automated consumer. It reports a problem to no one.

**Health checks must never raise.** Both endpoints catch broadly (`except Exception`) around the DB probe. A health endpoint that 500s on an unexpected error is indistinguishable from a dead process and triggers the same bad restart. The exception is logged, then swallowed — this is the one place where swallowing is correct, and it gets a comment saying so, because the project rule is "never silently swallow errors."

**`/readyz` uses a short timeout.** A `SELECT 1` against a hung connection can block until the pool timeout. A readiness probe that hangs is worse than one that fails, because the checker's own timeout fires and the result is ambiguous. Bounded at 2 seconds.

## Decision 4 — App factory plus module-level instance

**Chosen:** both `create_app()` and `app = create_app()`.

The factory exists for tests: each test gets a fresh instance with no shared state, and configuration can be injected. The module-level instance exists because `uvicorn scripts.web.app:app` needs an importable object.

**Rejected: module-level only.** Test isolation suffers — state leaks between tests through the shared app object, producing order-dependent failures that are miserable to debug.

**Rejected: factory only.** Requires a separate entrypoint module or `uvicorn --factory`, which is a Docker CMD footgun for no benefit.

## What this does NOT decide

- Authentication (deferred by D4; there is no auth in this system)
- Rate limiting on `/api/v1/*` (nothing public-facing yet; revisit before the API is shared)
- Webhook signature verification (Phase 5, when there is a webhook)
- CORS (no browser client on another origin)
- Structured JSON logging (Task 0.3, alongside deployment)

## Consequences

- `/healthz` intentionally reports healthy during a total database outage. That is correct and will look wrong to anyone who has not read this ADR — hence the comment in the code pointing here.
- Anything wanting real service status must poll `/readyz`, not `/healthz`.
- `fly.toml` (Task 0.3) points its check at `/healthz`. Pointing it at `/readyz` reintroduces the crash loop this ADR exists to prevent.
- Adding genuine dashboard interactivity later means either accepting HTMX's limits or a frontend rewrite.
