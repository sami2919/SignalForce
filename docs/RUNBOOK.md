# SignalForce — Operator's Runbook

This describes the system as it actually runs in production today: a Postgres-backed
watch/verify/score/outreach pipeline for one tenant (AgentMail), deployed on Fly.io,
built across Phases 0–5 (`docs/superpowers/plans/2026-08-04-signalforce-production.md`).
Every claim below was verified against the real running system, not written from
memory of the plan.

**This repo also contains two older, unrelated projects** you may run into while
browsing — `README.md` and `docs/setup-guide.md` describe a Fireworks-AI demo and an
earlier n8n/Apollo/HubSpot/Instantly GTM engine, respectively. Neither is wired to
anything below; ignore them if you're operating the deployed system.

---

## 1. What's actually running

| Component | What it is | Where |
|---|---|---|
| **Web app** | FastAPI dashboard + AgentMail reply webhook, read-only except for webhook writes | Fly app `signalforce`, machine group `app`, `min_machines_running=0` (suspends when idle, ~1-3s cold start) |
| **Daily worker** | Watch pass (probe all sources for changes) → verify/score → health rollup, recall report, retention prune | Standalone Fly machine `signalforce-worker`, `--schedule daily` |
| **Hourly holdout** | Independent ground-truth deep scan of a 5-account holdout, used to measure the daily worker's recall | Standalone Fly machine `signalforce-holdout`, `--schedule hourly` |
| **Database** | Postgres 18, one tenant (`agentmail`, id=1), ~7 tables of pipeline state + Phase 5's outreach tables | Neon, `us-west-2`, autosuspends when idle |
| **Outbound email** | Send + inbound reply capture | AgentMail API (`sami-r@agentmail.to` inbox) |

Live URLs: `https://signalforce.fly.dev/healthz`, `/readyz`, `/dashboard`,
`/dashboard/health`, `/dashboard/runs`, `/dashboard/account/{id}`,
`/webhooks/agentmail` (AgentMail calls this; you don't).

---

## 2. Local setup

```bash
cd /Users/sami/SignalForce-production   # NOT /Users/sami/SignalForce — that's a
                                          # different worktree; this branch is
                                          # signalforce-production
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Create `.env` (gitignored, never commit) with:

```
DATABASE_URL=<Neon pooled connection string>
DATABASE_URL_DIRECT=<Neon direct connection string — migrations only>
ANTHROPIC_API_KEY=<for the verify layer's LLM extraction>
GITHUB_TOKEN=<for the Task 2.2 repo scanner>
AGENTMAIL_API_KEY=<for outbound send>
AGENTMAIL_WEBHOOK_SECRET=<whsec_..., from the AgentMail console after
                           registering a webhook — see §6>
TENANT_SLUG=agentmail
```

**Never write to production Neon manually.** `DATABASE_URL_DIRECT` is read-only-safe
for `SELECT`s while you're debugging; writes go through the app or a migration, not
an ad hoc script — that's a standing rule for this project, not a suggestion.

Verify the install:

```bash
python -B -m pytest --no-cov -q         # 1047+ passed, 2 pre-existing unrelated
                                          # failures (tests/test_fireworks_icp_config.py
                                          # — the old Fireworks demo, not this system)
ruff check . && ruff format --check .
```

---

## 3. Running pieces locally

**The dashboard:**

```bash
uvicorn scripts.web.app:app --reload --port 8080
# http://localhost:8080/dashboard
```

**A watch pass** (probes every active `AccountSource`, records `probes` rows, emits
`signal_events` on confirmed changes, scores accounts):

```bash
python -m scripts.watch.runner scan
```

**Seed new accounts** (resolves careers/docs/pricing/blog/changelog URLs for a
domain, no watch pass yet):

```bash
python -m scripts.watch.runner resolve --domains acme.com,other.com
```

**The hourly holdout deep-scan** (ground truth for recall measurement):

```bash
python -m scripts.measure.holdout --holdout-size 5 --seed 42
```

**Daily postprocess** (health rollup + anomaly check + recall report + retention
prune — runs automatically as part of `signalforce-worker`'s scheduled command, not
its own CLI entrypoint):

```bash
python -m scripts.watch.runner scan   # this IS the daily job; postprocess runs
                                        # inside it, see scripts/measure/daily_postprocess.py
```

All of the above require `TENANT_SLUG` set and will auto-create that `Tenant` row on
first use if it doesn't exist (`ensure_tenant`).

**Migrations** (never against `DATABASE_URL` — always `DATABASE_URL_DIRECT`, since
pooled connections can silently half-apply DDL):

```bash
DATABASE_URL_DIRECT=... alembic upgrade head
alembic current                          # check what's applied
```

---

## 4. Deploying

```bash
fly deploy -a signalforce               # builds, pushes, runs release_command
                                          # (alembic upgrade head) BEFORE traffic
                                          # shifts, then rolling-restarts the app
                                          # machine
```

`fly deploy` only touches the `app` machine group. It does **not** update
`signalforce-worker` or `signalforce-holdout` — those are standalone scheduled
machines, not part of the deploy's process group. After any deploy that changes
code those two machines execute, re-point them explicitly:

```bash
fly machine update <worker-id>  --image registry.fly.io/signalforce:<new-tag> --yes
fly machine update <holdout-id> --image registry.fly.io/signalforce:<new-tag> --yes
```

Get current machine IDs and images with `fly machine list -a signalforce`.

**After changing secrets** (`fly secrets set ...`): this auto-restarts the `app`
machine group to pick up new values, but does **not** touch the standalone scheduled
machines — they resume from their last-updated config snapshot on their next
scheduled fire, which won't include the new secret. Run the same
`fly machine update <id> --image <current-image> --yes` on each scheduled machine
after any secrets change, even with an unchanged image — this was a real,
twice-reproduced bug during Phase 2 (ANTHROPIC_API_KEY missing at runtime after a
secrets-only change).

Verify a deploy:

```bash
curl https://signalforce.fly.dev/healthz    # {"status":"ok"}
curl https://signalforce.fly.dev/readyz     # {"status":"ready","db":true}
fly status -a signalforce                   # machine state + health checks
```

---

## 5. Checking on it (day to day)

**Is it alive:** `/healthz` (liveness only — never gate on `/readyz`, which checks
the DB and is allowed to fail transiently per ADR-0002).

**Dashboard:** `/dashboard` (top-scored accounts), `/dashboard/health` (recall,
detection lag, per-source fetch success, deactivated-sources count),
`/dashboard/runs` (scan run history, cost, change rate), `/dashboard/account/{id}`
(full signal timeline + replayable scoring trace + zero-out table).

**Worker logs:**

```bash
fly logs -a signalforce -i <worker-machine-id> --no-tail
```

The log buffer only retains recent lines — for anything older than the last run or
two, read from the database directly (read-only) instead of hunting through logs.

**Read-only DB checks that don't need `fly logs`:**

```sql
-- scan run history, cost, change detection rate
SELECT id, started_at, sources_probed, changes_detected, cost_usd, status
FROM scan_runs ORDER BY id DESC LIMIT 10;

-- per-source-type fetch health, most recent days
SELECT source_type, run_date, fetch_success_rate, sample_size
FROM source_health ORDER BY run_date DESC LIMIT 20;

-- deactivated sources (should be near 0; each one means a source stopped
-- being probed at all until re-resolution recovers it)
SELECT count(*) FROM account_sources WHERE active = false;

-- outreach + reply state
SELECT id, agentmail_thread_id, sent_at, replied_at FROM outreach ORDER BY id DESC;
```

**Cost:** every `scan_runs` row carries `cost_usd` (verify-layer LLM spend for that
run). Sum over a period to get real spend, don't estimate.

---

## 6. Sending real outbound (AgentMail)

```python
from scripts.outreach.agentmail import AgentMailClient
from scripts.outreach.recorder import record_outreach
from scripts.storage.session import get_session

client = AgentMailClient(api_key=os.environ["AGENTMAIL_API_KEY"])
result = client.send(inbox_id="sami-r@agentmail.to", to="...", subject="...", text="...")

with get_session() as session:
    record_outreach(
        session,
        tenant_id=1,                    # the agentmail tenant
        account_id=<a real Account.id>, # required — never derive from email domain,
                                          # see ADR-0023
        contact_email="...",
        agentmail_inbox_id="sami-r@agentmail.to",
        agentmail_thread_id=result.thread_id,
        sent_at=<real send timestamp>,
    )
```

`record_outreach` is what lets a reply actually get matched and recorded — sending
without it means the webhook has nothing to attach a reply to (this was a real gap,
closed by ADR-0023; see the ledger).

**Webhook setup** (one-time per environment): register a webhook in the AgentMail
console pointed at `https://signalforce.fly.dev/webhooks/agentmail` with
`event_types=["message.received"]`, grab its `whsec_...` secret, set it as
`AGENTMAIL_WEBHOOK_SECRET` both locally and via `fly secrets set` — plus the
machine-update step in §4, since that's a secrets change.

---

## 7. Statistical outputs — read the guard, not just the number

- **Recall** (`/dashboard/health`, `compute_recall_for_tenant`): `caught/deep`
  against the hourly holdout. A low number isn't automatically "the watch layer is
  broken" — a source that gets edited several times in one day will show multiple
  "deep changes" that a once-daily watch pass structurally can't all individually
  match, even when it correctly catches the net change. Check the actual `missed`
  entries' timestamps before concluding anything.
- **Cohort lift** (`scripts.measure.cohort.compute_lift`): only emits a z-score/
  p-value when BOTH cohorts clear `n≥30` AND the success-failure condition
  (`n·p̂≥5`, `n·(1-p̂)≥5` per arm) — below that, `insufficient_data=True` and the
  statistical fields are `None` on purpose. Don't quote a rate without checking
  `insufficient_data` first.

---

## 8. Where to look next

- `docs/decisions/000N-*.md` — every non-obvious design decision, in order, with
  what was rejected and why.
- `.superpowers/sdd/2026-08-04-signalforce-production/progress.md` (in the sibling
  `/Users/sami/SignalForce` worktree) — the full build ledger: every bug found, every
  measurement taken against real infrastructure, every deploy.
- `docs/superpowers/plans/2026-08-04-signalforce-production.md` — the original plan,
  including the "Interview Answers This Unlocks" table (kept up to date with real
  numbers, not placeholders) and the Failure Modes table.

---

## 9. Web access (ADR-0025)

### Before the first deploy

The image installs `signal-audit` from the tarball of tag `v0.2.0` of github.com/sami2919/signal-audit (see `pyproject.toml`). That tag must exist and must contain `signal_audit/service.py`, which the web app imports. Today that file lives on the signal-audit branch `feat/audit-uploads` (commit `590e93f`), not on its `main`. Do these in order, by hand:

1. In the signal-audit repo, merge `feat/audit-uploads` into `main` (or tag commit `590e93f` directly).
2. Tag that commit `v0.2.0` and push the tag: `git tag v0.2.0 <commit> && git push origin v0.2.0`.
3. Check the tarball resolves: `curl -sIL https://github.com/sami2919/signal-audit/archive/refs/tags/v0.2.0.tar.gz | grep -m1 '^HTTP'` should print a 200 line.
4. Set the session secret: `fly secrets set SESSION_SECRET=$(openssl rand -hex 32) -a signalforce`.
5. Deploy.

If you skip steps 1-3, the deploy fails in a confusing way: if the tag is missing, the image build fails when pip cannot download the tarball. If the tag exists without `service.py`, the image builds, but the app fails on import at boot (`ModuleNotFoundError: signal_audit.service`), so the health check fails and the release does not go live.

Secrets: `fly secrets set SESSION_SECRET=$(openssl rand -hex 32) -a signalforce`. The app refuses to start in production without it.

Manage invites on the running machine (codes are shown once; only the hash is stored):

```bash
fly ssh console -a signalforce -C "python -m scripts.web.invites create --label owner --tenant-slug agentmail --owner"
fly ssh console -a signalforce -C "python -m scripts.web.invites create --label maya --tenant-slug maya"
fly ssh console -a signalforce -C "python -m scripts.web.invites list"
fly ssh console -a signalforce -C "python -m scripts.web.invites revoke --label maya"
```

Smoke test after a deploy (replace `$CODE`):

```bash
J=$(mktemp)
curl -s -o /dev/null -w "%{http_code}\n" https://signalforce.fly.dev/healthz               # 200
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" https://signalforce.fly.dev/dashboard   # 303 .../login
curl -s -c $J -o /dev/null -w "%{http_code}\n" -d "code=$CODE" https://signalforce.fly.dev/login   # 303
curl -s -b $J -o /tmp/sample.zip https://signalforce.fly.dev/audit/sample.zip && unzip -o -q /tmp/sample.zip -d /tmp/sample
curl -s -b $J -o /tmp/report.html -w "%{http_code}\n" -F accounts=@/tmp/sample/accounts.csv \
  -F signals=@/tmp/sample/signals.csv -F outcomes=@/tmp/sample/outcomes.csv \
  -F engagements=@/tmp/sample/engagements.csv -F config=@/tmp/sample/audit.json \
  https://signalforce.fly.dev/audit/run                                                      # 200
head -c 15 /tmp/report.html                                                                  # <!DOCTYPE html>
```

## Multi-tenant scanning (ADR-0026)

The daily worker scans every tenant with an active source when `SCAN_TENANTS=all` is set on the machine. `TENANT_SLUG` still works for a single tenant. The `[env]` block in `fly.toml` does not reach `fly machine run` machines, so set it on the machine itself:

```bash
fly machine update <worker-machine-id> --env SCAN_TENANTS=all -a signalforce
```

After any deploy that changes worker code, re-point the worker (and the holdout machine) at the new image as described in the notes in `fly.toml`.

A new tenant's first scan happens at the next daily run; the watchlist page shows "resolving…" until the background source resolution finishes.

A tenant whose scan crashes is logged (`tenant scan crashed`) and the other tenants still run; the run then exits 1. The hourly holdout machine still measures the owner tenant only.

Outbound fetches refuse non-public addresses (ADR-0026). A watchlist domain that resolves to an internal address is refused with a 422 at intake, and a refused fetch during a scan is recorded as a failed fetch. A watchlist holds at most 25 domains, and there is no UI to remove one; removing an account is an operator task in the database.
