# ADR-0005: Watch layer — concurrency, confirmation, and persistence

**Status:** Accepted
**Date:** 2026-08-04
**Scope:** Phase 1, Task 1.3 — `scripts/watch/fetcher.py`, `scripts/watch/runner.py`

---

## Context

The watch layer is the thing that actually runs every day. It fetches every registered source, hashes the result, and decides which ones changed. Everything downstream — the verify layer's cost, the signals emitted, Phase 3's recall and detection-lag numbers — is a function of what this produces.

Its correctness has an unusual shape: **the expensive failure is silent.** A watch pass that fetches nothing, or that flags everything as changed, or that dies halfway through, all look similar from outside. Nobody gets paged. The only evidence is data that never arrives.

## Decision 1 — asyncio with two semaphores

**Chosen:** `httpx.AsyncClient` with a global concurrency semaphore (default 100) and a per-host semaphore (default 2).

**Rejected: threads (`ThreadPoolExecutor` + `requests`).** The existing `scripts/api_client.py` is sync `requests` and works well, so threads would be consistent with it. Rejected because this workload is thousands of concurrent network waits with almost no CPU — the exact case where a thread per request wastes ~8MB of stack each and the GIL makes the parallelism illusory anyway. 100 concurrent sockets in one event loop is a few hundred KB.

**Rejected: multiprocessing.** Solves a CPU problem this workload does not have, and adds IPC and connection-pool duplication.

**Rejected: sequential fetching.** 2,000 sources at ~1.5s each is ~50 minutes. At 20,000 it is 8+ hours, which collides with the next daily run. Concurrency is not premature here; it is the difference between a daily job and one that cannot complete daily.

**Why two semaphores rather than one.** They protect different parties and would be wrong at the same number:

| Limit | Protects | Failure if too high |
|---|---|---|
| Global (100) | **us** — memory, file descriptors, local egress | resource exhaustion, our process dies |
| Per-host (2) | **them** — a single domain | rate-limit or ban |

A single global limit of 100 permits 100 simultaneous requests to *one* domain if that domain happens to own 100 sources. That reads as an attack, and the response is a ban. A ban then produces empty results that are indistinguishable from a genuinely quiet account — the exact silent failure Phase 3 exists to detect, invited at the fetch layer.

Sajwal described Rippling running ~100 requests/second across rotating DNS providers. That is a different posture, backed by a legal team and commercial relationships. This system fetches a few thousand public pages once a day and should be a good citizen.

## Decision 2 — Confirm-on-change ★

**Chosen:** when a source's hash differs from `last_hash`, re-fetch that source once immediately and require both fetches to agree before recording a change.

**This is a measured decision, not a precaution.** Fetching `boards.greenhouse.io/anthropic` six times on 2026-08-04 produced **two distinct content hashes** (5:1). The five-character delta was an unresolved i18n template key — Greenhouse intermittently renders `tags.new` instead of `New`. It is a rendering race in their application, pure noise, firing on roughly 17% of fetches.

Phase 1's exit criterion is a change rate of 3-20%. **A single upstream flake on one ATS would consume that entire budget.** Greenhouse is a primary target source, so this is not a corner case.

Confirmation reduces a 17% single-fetch false-positive rate to roughly 3% (0.17²), and costs one extra cheap GET on only the ~5-17% of sources that appeared to change.

**Rejected: require a change to persist across two consecutive daily runs.** Identical false-positive reduction, no extra fetches. Rejected because it adds ~24 hours to detection lag — the precise metric Phase 3 exists to minimise and report. Trading the headline number to save a handful of GETs is backwards.

**Rejected: strip `tags.*` placeholders.** Fixes this instance and nothing else. Every ATS will have its own flake, discovered one at a time, each requiring a new special case. Confirm-on-change is source-agnostic and needs no knowledge of what churned.

**Rejected: similarity threshold instead of exact hash equality.** Robust to small deltas, and it discards the property that makes hashing cheap — you would have to store and diff normalized text rather than 64 bytes. It also picks an arbitrary similarity constant that would silently swallow small real changes, like a single new job posting on a long page.

**On disagreement:** record the probe with `changed=False` and leave `last_hash` untouched, so the next run re-evaluates from the same baseline. A genuinely changed page will differ from `last_hash` again next run and will usually confirm then — so a real change survives, at worst one run late, even on a flaky source. Count these as `confirm_rejected` on the run: a rising rate is the early warning that a source has become unstable, and it is the number that says whether normalization needs to get more aggressive.

## Decision 3 — Sync SQLAlchemy, outside the async section

**Chosen:** three phases — (1) sync DB read of due sources, (2) async fetch of everything, (3) sync DB write of results. No async database driver.

**Rejected: `asyncpg` / SQLAlchemy async.** The natural-looking choice inside an async function. Rejected because the database is not the bottleneck — one bulk read and one batched write bracket several minutes of network waiting — and adopting async SQLAlchemy means a second engine configuration, a second session pattern, and async versions of every helper, for no measured gain. `scripts/storage/session.py` stays the single way this project talks to Postgres.

**Rejected: writing each probe as it completes.** Would keep memory flat and give partial progress on crash. Rejected because it puts a database round trip inside the fetch loop, coupling scan throughput to database latency, and produces one transaction per probe.

**Accepted cost — memory.** Phase 2 holds every `ProbeResult` in memory before writing. At 20,000 sources × a small frozen model that is a few MB. **This breaks somewhere north of ~500,000 sources**, at which point the fix is chunking the source list and running the three phases per chunk. Know the threshold; do not build for it now.

**Write in batches of 500 with a commit per batch.** One transaction over 20,000 inserts holds locks long enough to matter and loses everything on failure. Batching bounds both.

## Decision 4 — Re-check robots.txt every run

**Chosen:** fetch and honour `robots.txt` per domain per run, cached in memory for the duration of the run.

Resolution (ADR-0004 Decision 5) checked robots.txt once, at registry time. That is not sufficient forever: a site can add a `Disallow` at any point, and a registry entry resolved six months ago carries no authority today.

For a daily run this is one extra fetch per domain per day — identical to what a 24-hour TTL cache would produce, without the cache-invalidation logic.

**Also fixes a carried finding:** `_fetch_robots` in the resolver does not pass `follow_redirects=True`, unlike the other fetches. A `robots.txt` that 301s (common for bare-domain → www) would be read as absent and therefore permissive. That fails in the safe direction, so it did not block Task 1.1 — but the watch layer's implementation must pass `follow_redirects=True`, and the resolver should be corrected to match.

## Decision 5 — A run that dies must be visible

**Chosen:** `scan_runs` rows are written at start with `status="running"` and updated at completion. A run still marked `running` after 2 hours is **stale**, and stale runs are surfaced rather than silently ignored.

The failure this addresses: the worker machine is OOM-killed or the process dies mid-pass. Nothing errors anywhere a human sees. The `scan_runs` row sits at `running` forever, no probes land for that day, and the only evidence is a gap in data that nobody is looking at.

**Absence is the signal, and absence is what monitoring is worst at.** Phase 3's health page must surface "no completed run in the last 36 hours" as prominently as any metric it computes. A dashboard that shows only what happened cannot show what did not.

**Rejected: a heartbeat / liveness row updated during the run.** More precise, and more machinery than a single-worker system needs. The 2-hour staleness rule is a good approximation of "should have finished by now" for a pass that takes minutes.

## Decision 6 — A separate scheduled Fly machine

Restated from ADR-0003 Decision 2 because this is the task that implements it: the worker is its own scheduled machine that starts, runs, and exits. It is **not** a scheduler thread inside the web process.

`min_machines_running = 0` means the web machine suspends when idle. An in-process scheduler would stop firing the moment the dashboard went quiet, producing a system that looks healthy, costs nothing, and silently produces no data.

```
fly machine run . --schedule daily --command "python -m scripts.watch.runner"
```

## What this does NOT decide

- Per-source cadence tiering by account score — Fly's scheduler only does daily anyway
- Retry of individual failed fetches within a run — `consecutive_failures` handles it across runs
- The verify layer's budget or extraction (Phase 2)
- Partitioning or retention of `probes` (Task 3.4)

## Consequences

- Two fetches for every source that appears changed. Budget for it.
- A genuinely changed but flaky source may be recorded one run late. Acceptable against the alternative of recording noise as signal.
- Memory grows with source count; revisit past ~500k.
- The worker's failures are invisible in the web logs. `scan_runs` is the record, and a *missing* row is the alarm — which only works if Phase 3 actually surfaces it.
