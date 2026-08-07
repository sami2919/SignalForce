# ADR-0021: Cohort lift analysis

**Status:** Accepted
**Date:** 2026-08-07
**Scope:** Task 5.3 — `scripts/measure/cohort.py`

---

## Context

The plan gives Task 5.3 less detail than any prior task this session: a target output
example ("Accounts with agent_email_repo replied at 11.2% vs 3.1% baseline, n=180 and
n=1,400, p=0.003"), a bare interface signature (`compute_lift(cohort_a, cohort_b) ->
LiftReport`), and one guard instruction ("require n≥30 per arm or return
`insufficient_data`") — no reference code, no test, no exact `LiftReport` schema, no
formula. Designed from scratch here, same footing as Task 4.2's `personas.py`.

## Decision 1 — The plan's stated guard ("n≥30 per arm") is insufficient on its own;
add the actual statistical validity condition for a two-proportion z-test ★

**The finding.** "n≥30" is the common rule of thumb for the Central Limit Theorem
applying to a **mean** — it is not the correct validity condition for a **proportion**
z-test. The condition that actually matters here is the success-failure condition:
both `n·p̂ ≥ 5` and `n·(1-p̂) ≥ 5` for each arm (a common, slightly more conservative
variant uses 10). A cohort can satisfy `n≥30` while having almost no successes — n=180
with 2 replies (p̂≈0.011) gives `n·p̂ ≈ 2`, well under 5, meaning the normal
approximation the z-test depends on is not reliable, even though the plan's literal
`n≥30` guard alone would let this run and report a p-value anyway. That's a
statistically confident-looking number built on a shaky approximation — the exact
"looks measured, isn't actually valid" shape this project has repeatedly found and
corrected in other tasks' plan code, found here in a plan's stated *validation rule*
instead.

**Chosen:** `compute_lift` requires **both** conditions before computing a z-test:
`n ≥ 30` per arm (the plan's stated floor, kept) **and** `n·p̂ ≥ 5` and `n·(1-p̂) ≥ 5`
for each arm (the actual proportion-test validity condition). Either one failing sets
`insufficient_data=True` and nulls the statistical fields — rates and sample sizes are
still reported (there's no reason to hide real counts just because the test itself
isn't valid), only the z-test output is withheld.

**Rejected: the plan's `n≥30` guard alone.** Passes its own stated bar while still
reporting a p-value on data where the normal approximation isn't trustworthy — this
project exists partly to answer "how do you know the signal works," and a
methodologically shaky number answering that question wrong is worse than visibly
declining to answer it.

## Decision 2 — `LiftReport` reports both absolute and relative lift, not one
ambiguous scalar

**Chosen:** `absolute_lift = rate_a - rate_b` (percentage-point difference, e.g. "+8.1
points") and `relative_lift = rate_a / rate_b - 1` (e.g. "+261%", `None` if `rate_b`
is `0` to avoid a division by zero) are both reported. "Lift" is genuinely ambiguous
in casual usage — a marketer reading "3.6x lift" and an analyst reading "+8.1 points"
are both reasonable interpretations of the plan's own target phrasing
("11.2% vs 3.1%"), and picking only one silently forecloses the other.

**Rejected: a single `lift: float` field.** Whichever definition is chosen, a reader
has to guess (or go read the source) which one it is — reporting both costs one extra
field and removes the ambiguity entirely.

## Decision 3 — The normal CDF is computed via `math.erf` (stdlib), not a new
`scipy`/`numpy` dependency

**Chosen:** the two-tailed p-value from a z-score uses the closed-form standard normal
CDF, `Φ(z) = 0.5 * (1 + erf(z / √2))`, via Python's stdlib `math.erf` — exact, no
external dependency. `scipy`/`numpy` aren't dependencies of this project today, and a
single well-known closed-form calculation doesn't justify adding either for one
function, the same "boring, minimal dependencies" posture this project has held
throughout (Task 3.4/4.1's engine also stayed stdlib-only for their own math).

## Decision 4 — `cohort_a` is the convention for "the group with the signal," matching
the plan's own example ordering; `z_score`/`absolute_lift`/`relative_lift` are all
signed A-relative-to-B

Not stated by the plan; made explicit here so a future caller doesn't have to guess
which argument position means "treatment" — matches the plan's own phrasing exactly
("accounts with X" = `cohort_a`, "baseline" = `cohort_b`).

## Decision 5 — A defensive `SE > 0` guard stays in the code as a provable no-op,
verified rather than assumed

**Investigated, then corrected before shipping:** a first draft of this ADR treated
"both cohorts have the exact same reply rate" as a distinct `z_score=None` case
requiring its own handling, on the theory that identical rates make the pooled
standard error `0` (a division by zero). Worked the algebra by hand before writing the
test: two cohorts at an *identical, valid* rate (e.g. 15/30 vs 15/30, both clearing
Decision 1's guard) give `pooled = 0.5`, `SE ≈ 0.129 > 0`, and `z = (p_a - p_b) / SE =
0 / 0.129 = 0.0` — a perfectly well-defined z-score of exactly zero ("no detectable
lift"), not a division by zero at all. The division-by-zero case (`SE = 0`, meaning
pooled proportion is exactly `0` or exactly `1`) requires **both** cohorts' successes
to be `0` (or both fully saturated at `100%`) — and that condition, on its own,
*always* fails Decision 1's success-failure guard (`n·p̂ ≥ 5` cannot hold when
`p̂ = 0`) for at least one arm. So `SE = 0` can never actually occur once Decision 1's
guard has already passed — it is a structurally unreachable state, not a distinct case
needing its own handling.

**Chosen:** keep an explicit `SE > 0` check in the code anyway, as a defensive
guard against a future change to Decision 1's guard order or logic — but document it
as provably redundant given the current guard, the same accepted-guard class as
several other tasks this session (retention.py, recall_report.py, wiring.py,
audiences.py all have one), rather than writing a test that cannot actually be
triggered through the public function.

**Rejected: leave the incorrect first draft's framing in place.** Would have shipped
a code comment (and a test) asserting something false about when a z-score is
undefined — caught only by tracing the actual arithmetic by hand instead of trusting
the first intuition about what "identical rates" implies.

## What this does NOT decide

- **Wiring `compute_lift` to real `Outreach`/signal data.** Same scoping as every
  other pure `measure`/`scoring` function this session — build and test the callable
  first, wire it in a later, explicit task once there's enough real reply data to be
  worth querying.
- **Multiple-comparison correction** (running many cohort comparisons and needing a
  Bonferroni-style adjustment). Out of scope until there's a caller running more than
  one comparison at a time.
