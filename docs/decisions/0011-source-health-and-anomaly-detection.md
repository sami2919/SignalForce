# ADR-0011: Source health and silent-breakage detection

**Status:** Accepted
**Date:** 2026-08-06
**Scope:** Phase 3, Task 3.3 — `scripts/measure/health.py`

---

## Context

Sami (Rippling, 17:07): *"you can't really tell real quiet from a broken scanner."* The plan's
Task 3.3 answers this with `SourceHealth` carrying three rates — `fetch_success_rate` (network),
`parse_success_rate` (extraction), `zero_result_rate` (structural drift: the page loads fine but
the parser now finds nothing) — and `detect_anomaly` flagging a >3σ spike in the trailing baseline.

**The gap the plan doesn't mention:** `zero_result_rate` and `parse_success_rate` are extraction
outcomes. They can only be computed from the verify layer (`scripts/verify/extractor.py`), which
is fully built and reviewed (Task 2.1a/2.1c) but has **no caller anywhere in the codebase** — it
has never run against a real snapshot in production. `Probe` (the watch layer's only per-fetch
record) carries `status_code`, `error`, `content_hash`, `changed`, `bytes` — fetch-level facts
only. There is no "how many jobs did we find" field anywhere upstream of the unwired extractor.

**The tempting shortcut — use `Probe.bytes` as a zero-result proxy — is already disproven by this
project's own data.** Task 1.3a measured, on real pages: `neon.com/changelog` 2.7MB raw / 18,805
chars normalized; `neon.com/blog` 3.8MB raw / 2,076 chars normalized. Raw transport size doesn't
even rank-correlate with content size on JS-heavy sites, let alone with "zero parsed results."
Building `zero_result_rate` from `bytes` would silently reintroduce the exact defect that comment
in `fetcher.py` exists to warn against — a metric that looks like it measures content and doesn't.

## Decision 1 — Ship `fetch_success_rate` for real today; leave the other two `None`, not faked

**Chosen:** `SourceHealth.parse_success_rate` and `SourceHealth.zero_result_rate` are
`float | None`, populated only once something calls the verify layer and records an extraction
outcome per probe. `compute_health` computes `fetch_success_rate` from real `Probe` data
(`status_code` in 2xx and no `error` = success) and leaves the other two `None`. `detect_anomaly`
is generalized to take a metric name and direction rather than being hardcoded to
`zero_result_rate` (Decision 2), and simply isn't called with a metric that's `None` yet.

**Rejected: fake `zero_result_rate` from `bytes` or `changed`.** Two candidates considered and
both rejected on measured grounds. `bytes`: disproven above. `changed` (treating "unchanged" as
"zero result"): actively wrong in the other direction — Phase 1's own exit-criterion measurement
(ADR-0010's Decision 1 context) found ~83–97% of daily probes are `changed=False` by design; that
is the system working, not a structural failure. An anomaly detector fed that signal would fire
almost every day and get silenced by the first on-call engineer who reads it, which is worse than
not building it.

**Rejected: block Task 3.3 entirely on verify-layer wiring.** `fetch_success_rate` alone is a real,
non-redundant signal — see Decision 3 — and is fully computable from data that exists right now.
Deferring the whole task to wait on a wiring decision that has already been explicitly punted twice
this phase (ADR-0010's scope note, Task 2.1's "still open" note) would block a measurable, useful
piece of work behind an unrelated one. Building the honest subset now and wiring the rest in later
is the same shape as every other "measure what's real, defer what isn't" call this project has
made (ADR-0007 Decision 5's degraded flag, ADR-0010's hash-level-not-fact-level scoping).

## Decision 2 — `detect_anomaly` takes a metric name and direction, not a hardcoded field

**The finding.** The plan's `detect_anomaly(current, trailing)` hardcodes `zero_result_rate` and
one direction ("current above the trailing mean is bad"). `fetch_success_rate`'s bad direction is
the opposite — a *drop* is the failure, not a rise. Keeping the plan's function as-is and adding a
second, near-identical function for `fetch_success_rate` would duplicate the whole
mean/stdev/sigma/flat-baseline-guard body for a difference of one comparison operator.

**Chosen:** `detect_anomaly(current: float, trailing: list[float], *, metric_name: str,
source_type: str, direction: Literal["high_is_bad", "low_is_bad"]) -> Anomaly | None`. The
statistics (mean, stdev, the flat-baseline 3σ-equivalent guard) are identical regardless of
direction; only the comparison and the message text change. Callers pass the specific field
(`fetch_success_rate` today, `zero_result_rate`/`parse_success_rate` once wired) and its known
direction. This is the minimal generalization that avoids duplicating a 30-line statistical
function for a one-line difference — not a speculative plugin system, just parameterizing the one
axis that concretely varies between the metric this task can compute and the metrics a later task
will add to the same struct.

**Rejected: keep the plan's `zero_result_rate`-specific signature and let it sit unused until
wiring lands.** Ships a function with a single call site (test-only), pointed at a field this task
cannot populate — a null test of nothing, immediately dead code review would flag on sight.

## Decision 3 — `fetch_success_rate` anomaly detection is not redundant with `consecutive_failures`

**Why this is worth building even without the other two rates.** `AccountSource.consecutive_failures`
(ADR-0004/1.3b) deactivates one source after repeated failures — per-source, hard threshold,
reactive. `compute_health`'s `fetch_success_rate` aggregates across every `AccountSource` of a
given `source_type` for one tenant on one day. A host-wide ban (a shared ATS platform starts 403ing
this project's user agent) degrades the aggregate rate immediately, well before any single source
crosses its own consecutive-failure threshold — the two signals catch different failure shapes at
different timescales, the same complementary-layers reasoning as the watch/verify two-tier design
itself (ADR-0005).

## Decision 4 — `compute_health` is a pure function over a minimal `ProbeOutcome`, not the ORM `Probe`

**Chosen:** a small `ProbeOutcome(BaseModel, frozen=True)` — `source_type`, `fetched_at`,
`succeeded: bool` — decoupled from the SQLAlchemy `Probe` row, matching the established pattern
(`DetectedChange` in `scripts/measure/lag.py`, `FactChange` in `scripts/verify/differ.py`): pure,
independently testable, no DB session needed in tests. The caller (a future wiring task, matching
`run_deep_scan`'s "read → compute → write" shape) maps `Probe` rows to `ProbeOutcome` and groups by
`(source_type, date(fetched_at))` before calling `compute_health`.

**Rejected: `compute_health(probes: list[Probe], ...)` taking the ORM model directly**, as the
plan's signature literally states. Every other `measure/`/`verify/` module in this project takes a
plain Pydantic input specifically so its core logic has zero DB coupling. Taking the ORM class
would be the first exception, for no benefit — nothing in the computation touches ORM-only
behavior (relationships, lazy loading), so there's no reason to pay that coupling cost.

## What this does NOT decide

- **Wiring `compute_health`/`detect_anomaly` into the scheduled worker or the verify layer.** This
  task builds and tests the pure functions, same scoping principle as Task 3.2 (`compute_recall`
  had no caller either, until the deep scan existed to feed it). A future task wires: (a) the
  daily worker calls `compute_health` after the watch pass and persists a `source_health` row, and
  (b) once the verify layer gets a caller, extraction results feed `parse_success_rate` and
  `zero_result_rate` into the same struct.
- **A `source_health` DB table / migration.** The plan's schema sketch includes one
  (`source_health(id, tenant_id, source_type, run_date, ...)`), but persisting requires a caller
  that has data to persist, which doesn't exist until the wiring task above. Building the table now
  would be dead schema, the same shape Decision 1 already rejected for the unused field.
- **Alerting delivery** (Slack, email, PagerDuty). `detect_anomaly` returns a value; what happens
  with it is out of scope here.

## Consequences

- `SourceHealth.parse_success_rate` / `.zero_result_rate` being `Optional` means any code reading
  them must handle `None` explicitly — by design, so a caller can't accidentally treat "not yet
  measured" as "measured zero."
- `fetch_success_rate`-only anomaly detection ships real but partial: Task 3.3 does not close the
  literal Sajwal gap ("you can't tell real quiet from a broken parser") until the verify layer is
  wired — it closes the narrower "you can't tell real quiet from a broken *fetcher*" gap today.
  This is worth stating plainly whenever this task gets referenced as "done."
