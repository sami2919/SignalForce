# ADR-0010: Holdout deep scan, recall, and detection lag

**Status:** Accepted
**Date:** 2026-08-06
**Scope:** Phase 3, Tasks 3.1 + 3.2 — `scripts/measure/holdout.py`, `scripts/measure/lag.py`

---

## Context

*"This phase is the entire reason the plan exists."* Everything before it is table stakes; this
is what turns "how do you know you caught it fast enough?" into a query instead of a fumble.

Phase 1's exit criterion just produced its first real data point: run 4, the first genuine daily-
cadence run, measured 90 probed / 15 changed = 16.67%, inside the 3–20% target band. That number
says the two-tier design isn't obviously broken. It says nothing about **recall** — what the
watch layer *misses*. Sami (Rippling, 17:07): *"you can't really tell real quiet from a broken
scanner"* — the only way to tell them apart is an independent source of ground truth that doesn't
depend on the watch layer's own hash comparison. That is what this task builds.

**Scope decision, carried from the conversation that led here:** ground truth in this task is
**hash-level**, not fact-level. The verify layer (extractor, differ, gate) is fully built and
reviewed but has no caller — `diff_facts` has never run against a real snapshot. Wiring it in
before this task would delay the one measurement this project exists to produce, for a fidelity
upgrade that can be layered on later without redesigning Task 3.1/3.2. Hash-level ground truth
directly answers the literal Sajwal question — "if you don't know something changed at all" is a
hash question, not a "which specific job posting" question.

## Decision 0 — `select_holdout` must use consistent hashing, not `random.sample` ★

**Correction, 2026-08-06.** This ADR originally kept the plan's `select_holdout` unchanged —
"the plan's version is correct as written." It is not. Found and fixed after Task 3.1 landed,
by checking the exact stability claim this ADR's own Decision 1 and the plan's docstring both
assert: *"the holdout must be stable across runs, or you are measuring a different population
every month and the trend is meaningless."*

**Measured:** `random.Random(seed).sample(account_ids, size)` maps its random draws to *indices*
in the population array. Removing a single account that was **never even in the holdout** — out
of 20, with the same seed — changed 3 of 5 holdout members (2/5 overlap). The stability the ADR
promised does not hold the moment the account population changes shape at all, which is the
expected, routine case for a growing account list, not an edge case.

**Chosen:** consistent hashing — `sorted(account_ids, key=lambda id: sha256(f"{seed}:{id}"))[:size]`.
Each account's inclusion is decided by its own hash rank relative to the *current* population,
independent of every other account's presence, order, or count. Measured under the identical
scenario: 5/5 overlap (fully stable) when an unrelated account is removed. Under population
*growth* it is not perfectly stable — a newly added account can legitimately rank into the top
`size` and displace an existing member, an unavoidable property of any "k best of N" rule — but
degrades gracefully (4/5 overlap at +5 growth) rather than catastrophically.

**Rejected: the plan's `random.sample`, kept as a documented limitation.** The three tests the
plan specified (deterministic for a fixed population, correct size, caps at population size) all
passed against the broken version — none of them tested population *change*, which is the one
scenario the stability requirement exists for. Same shape as every other self-caught error this
session: a plan artifact that looked right, passed its own narrow tests, and was wrong on the
property that actually mattered. Recorded here rather than silently fixed in code, per this
project's practice of leaving corrections visible.

## Decision 1 — The deep scan runs on its own, more-frequent cadence, on a small holdout ★

**The finding.** The plan's Task 3.1 never states how often `run_deep_scan` runs. If it runs on
the same daily cadence as the watch layer, detection lag can only ever be measured in multiples
of 24 hours — the two measurements would essentially always agree to within a rounding error, and
the number this task exists to produce would be useless.

**Chosen:** the deep scan targets a small, deterministically-selected holdout of accounts (default
5 — roughly a quarter of the current 20-account population, large enough for a nonzero recall
denominator, small enough that hourly fetching stays cheap) and is designed to run **more often
than daily** — hourly is the recommended default. It bypasses confirm-on-change entirely: every
fetch's hash is compared directly against the *previous holdout scan's* hash for that source, no
second-fetch confirmation required. The watch layer keeps its two-tier design in full for these
accounts too — holdout accounts are not excluded from the normal watch pass. They are **doubly
instrumented**: the same accounts, probed both ways, so `compute_recall` compares apples to
apples on the same population over the same window.

**Rejected: same cadence as the watch layer.** Produces a number with no resolution finer than a
day, defeating the purpose.
**Rejected: deep-scan the entire account population.** The whole point of a holdout is that it's
small enough to fetch aggressively without either costing real money (once fact-level extraction
is layered in) or looking like an attack on every source host. A full-population hourly scan is
the two-tier design's cost problem, reintroduced, for a task whose entire point was to stop
needing that.
**Rejected: confirm-on-change for the deep scan.** Confirm-on-change exists to protect the
*expensive* verify layer from cosmetic churn (ADR-0005 Decision 2). The deep scan is *ground
truth* — Task 1.2's measured Greenhouse i18n churn (~17% of fetches) will make the holdout's raw
change rate look noisy, but that noise is exactly what recall computation should be measured
against, not filtered out before it gets there. Filtering it here would make the deep scan
inherit the watch layer's own blind spots, defeating its purpose as an independent check.

**Scope explicitly excluded from this task: scheduling/deployment.** Running this hourly in
production means a new Fly scheduled machine (or a cron trigger on the existing one) — new
infrastructure, a cost decision, a secrets/config decision. That is a shared-system change and
gets its own explicit sign-off, the same way Phase 0 separated Task 0.1 (storage layer, pure/
testable) from Task 0.3 (deploy). This task builds `run_deep_scan` as a callable, tested,
CLI-invokable function — identical in shape to `run_watch_pass` — and stops there.

## Decision 2 — A dedicated `holdout_scans` table, not reuse of `probes`

**Chosen:** a new table, structurally close to `Probe` (reuse the convention: `tenant_id`,
`account_source_id`, `fetched_at`, `content_hash`, `changed`, `status_code`, `latency_ms`,
`bytes`, `error`) but **not** tied to `ScanRun` — the deep scan has no concept of a watch-layer
scan run, and forcing one would mean inventing a fake `ScanRun` row per hourly deep-scan tick or
conflating two operationally distinct concepts in one table.

`changed` is computed against the **most recent prior `holdout_scans` row** for that
`account_source_id` — not against `AccountSource.last_hash`. The holdout must never write to
`AccountSource.last_hash`; that field belongs to the watch layer's own confirm-on-change state,
and a deep-scan write there would corrupt the very state Phase 1's operational pass depends on.
A source's first-ever holdout scan has no prior row to compare against and is not a change —
consistent with every "first observation seeds silently" decision made so far in this project
(ADR-0006 Decision 5, ADR-0007 Decision 4).

**Rejected: reuse `probes` with a `run_type` discriminator column.** Technically workable, and
it's more schema churn on an already-high-volume table (Task 3.4 exists specifically because
`probes` was the one unbounded table) for a population that is a small fraction of the main scan.
Keeping the two separate keeps Task 3.4's retention math simple and keeps "what does this table
mean" answerable without a WHERE clause.

## Decision 3 — Fetch via the existing `fetch_all`, not new fetch code

**Chosen:** `run_deep_scan` calls `scripts.watch.fetcher.fetch_all` directly on the holdout's
`SourceRef` list. This gets robots.txt compliance, per-host concurrency limits, the byte cap, and
the "never raise on one source" posture for free — all of it already built and hardened across
Tasks 1.1–1.3c. Writing a second fetch path for the deep scan would be new code solving an already
-solved problem, and any defect in it would be a defect Phase 1 already found and fixed once.

## Decision 4 — `compute_recall` must match multiple changes per key in order, not collapse to one ★

**The finding.** The plan's reference implementation builds `watch_by_key: dict[key, datetime]`
holding **one** timestamp per `(account_id, source_type)` — "earliest watch detection wins" — and
then matches *every* `DetectedChange` in `deep_changes` against that single entry.

**Measured failure, worked by hand against the plan's own code:** a source that genuinely changes
twice in one measurement window — day 3 and day 10 — with the watch layer catching the day-3
change 6 hours later. The plan's code computes:
- day-3 deep event: lag = day3 − (day3+6h) = **−6h** (correct: watch was 6h slow)
- day-10 deep event: lag = day10 − (day3+6h) ≈ **+7 days** (nonsense: paired against the *first*
  change's watch timestamp, not a real detection of the day-10 change at all)

That second number is not a bound or an edge case — it is a **plausible-looking, silently wrong
statistic**, the exact failure shape this project has been organized around catching all session
(the always-`None` recency filter, the multiplicative sort-key collapse, the mixed-regime cost
figure). A recall report built from it would report "watch caught this in 7 days" for a change it
never detected at all.

**Chosen:** group both `deep_changes` and `watch_changes` by key, sort each group chronologically,
and match position-by-position: the *i*-th real change is compared against the *i*-th watch
detection for that same key. Any deep change beyond the number of watch detections for that key is
a genuine miss. Any watch detection beyond the number of deep changes for that key (the watch
layer "detected" more changes than ground truth confirms happened — plausible if confirm-on-change
let a cosmetic flip through) is recorded as an **extraneous watch detection**, surfaced separately
rather than silently discarded, since it is itself a signal about the watch layer's own precision.

**Rejected: the plan's one-entry-per-key design, kept as a documented v1 limitation.** Considered,
following this project's precedent of deferring a fix until it's measured to matter (ADR-0004,
ADR-0007 Decision 3). Rejected here because the failure isn't a missing refinement — it produces
an actively wrong number on the very first multi-change window, which for a holdout running hourly
against real career pages (Task 1.2's own measurement: this exact class of source changes
detectably) will not be rare. The fix costs a `groupby` and a `zip`; the plan's shortcut buys
nothing worth that risk.

**Correction, 2026-08-06 — matching is nearest-neighbor by proximity, not positional or
chronological-order.** Independent review of the first implementation (commit `f98afe5`) found the
`zip`-after-sort described above still mispairs when a false-positive watch detection lands
*before* the real change: `deep=[h100]`, `watch=[h0 false positive, h104 genuine catch]` — zip
pairs h100 with h0, producing a physically implausible `+100h` lag while flagging the genuine h104
catch as extraneous. A first attempted fix (two-pointer merge, rejecting any watch event
chronologically before its candidate deep event) resolved that but introduced a regression:
`test_lag_is_positive_when_watch_was_faster` — deep=[h12], watch=[h0], watch legitimately beating
deep to the change — now reported a phantom miss (`p50_lag_hours=None`), because deep running more
*often* only makes it more often faster, not *always* faster. Chosen instead: assign each watch
event in a key's group to its nearest deep event by absolute time distance; each deep event takes
whichever assigned watch event is closest as its match, and any others assigned to it are
extraneous. This resolves both the original zip defect and the two-pointer regression, since
proximity — not order — is what actually distinguishes a genuine (possibly early) catch from a
false positive. Also fixed in the same round: `p95_lag_hours` was computed directly on signed
`lag`, which reports the *best* detection instead of the worst whenever lags run predominantly
negative (the expected regime: deep hourly, watch daily). Fixed via `_tail_percentiles()`, which
sorts on `badness = -lag` and negates the result back to `lag` units.

## What this does NOT decide

- **Deployment/scheduling of the deep scan.** Decision 1 explicitly defers this — a follow-on
  task requiring explicit infra sign-off.
- **Fact-level ground truth.** Layering the verify layer (extractor + differ) into the deep scan
  once fact-snapshot storage is decided is a future upgrade, not a redesign — `run_deep_scan`'s
  hash-comparison core stays; a fact-diffing step would sit alongside it.
- **The holdout size default's exact value beyond "roughly a quarter of today's population."**
  Revisit as the account count grows; 5 is sized for today's 20 accounts, not a law.
- **Anomaly/source-health detection (Task 3.3).** Separate task, separate ADR if warranted.

## Consequences

- `holdout_scans` is a second table alongside `probes` measuring similar things for different
  purposes — a reader must know which one to query for which question (operational watch-layer
  behavior vs. ground-truth recall). Worth a one-line note in each model's docstring.
- `compute_recall`'s per-key sequential matching means its inputs must be genuinely representative
  of one coherent measurement window — mixing events from non-overlapping windows into one call
  would misattribute matches across window boundaries. Callers must window-filter before calling.
- Detection lag is only as fine-grained as the deep scan's actual cadence. If the deep scan itself
  only runs hourly, no lag measurement can be more precise than roughly an hour — a real ceiling on
  precision, not a bug, and worth stating whenever this number gets quoted.
