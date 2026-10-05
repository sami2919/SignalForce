# ADR-0015: Scoring engine scaffold

**Status:** Accepted
**Date:** 2026-08-07
**Scope:** Task 4.1 — `scripts/scoring/engine.py` (scaffold only; `_combine` is the
user's own contribution, not scaffolded here)

---

## Context

The plan's Task 4.1 is explicitly split: the surrounding machinery (types, recency
decay, trace recording, `zero_out`) is scaffolded here; the weighting function
`_combine` — how decayed signal contributions turn into one 0-100 score — is
deliberately left for the user to write, since it encodes product opinions ("three
weak signals converging beats one flashy signal," ICP×0.4 + Intent×0.6, "rather skip
a prospect than send garbage") that a scaffold can't manufacture. This ADR covers only
the two places the scaffold, as implemented, deviates from the plan's literal
reference code — both small, both worth stating rather than silently changing.

## Decision 1 — `_combine` takes typed `ScoreComponent` objects, not raw `dict`

**The finding.** The plan's reference `_combine(components: list[dict]) -> float`
takes loose dicts. This project's own conventions (`CLAUDE.md`: "Pydantic models for
all data structures... Never use raw dicts for structured data") have held for every
other module this session — `DetectedChange`, `ProbeOutcome`, `FactChange` are all
typed, specifically so a reader (and an IDE) can see a component's shape without
tracing back to where the dict was built.

**Chosen:** `score_account` builds `ScoreComponent(BaseModel, frozen=True)` instances
(`signal_type`, `base_weight`, `age_days`, `decay`, `decayed_weight`, `is_icp`) and
passes those to `_combine`. The trace dict written into `ScoreResult.trace` is still
built by serializing these (`component.model_dump()`), so the on-disk/logged shape is
identical to the plan's — this only changes what `_combine` itself receives, giving
the user's own code (the part of this system this ADR exists to protect) real
autocomplete and a type error instead of a `KeyError` if a field name is mistyped.

**Rejected: keep raw dicts, matching the plan exactly.** Would be the one function in
this codebase's `measure`/`verify`/`scoring` layer NOT using a typed input, for no
reason beyond matching the plan literally — and the plan's own dicts were never
reviewed against this project's house style the way everything else has been.

## Decision 2 — `score_account` clamps the final score to `[0, 100]`, visibly

**The finding.** `_combine`'s own docstring states the output must be "bounded 0-100,"
but nothing in the plan's scaffold enforces it — a `_combine` implementation that (for
instance) doesn't cap a breadth multiplier could silently produce a score of 340 or
-12, and that value would flow straight into `ScoreResult.score` and, eventually,
`Score.score` in the database, with nothing between it and a rep's dashboard.

**Chosen:** `score_account` clamps `_combine`'s return value to `[0.0, 100.0]` before
rounding, and logs a warning (with the pre-clamp value) if clamping actually changed
anything — visible-but-corrected, not silently corrected, matching this project's
standing posture on unenforced constraints (ADR-0009 Decision 1's whole point:
"`max_cost_usd` is a real constraint or it does not exist"). This is a safety net
around the user's own weighting logic, not a substitute for writing it correctly.

**Rejected: trust `_combine` to self-bound, per its docstring instruction alone.** A
docstring is not enforcement — this project has repeatedly found that an unenforced
"should" (the recency filter that was always `None`, `max_cost_usd` never read,
`accounts_probed` silently wrong) is exactly the failure shape that survives review
and ships. A one-line clamp costs nothing and turns a possible silent range violation
into, at worst, a visible warning.

## What this does NOT decide

- **`_combine`'s actual logic.** That's the user's contribution — this ADR only
  covers the scaffold's interface and safety net around it, never the weighting
  itself.
- **Wiring `score_account` to a caller** (a scheduled scoring pass, `Score` row
  persistence). Task 4.1 is a pure function, same scoping this whole project has used
  for `compute_recall`, `compute_health`, `diff_facts`, etc. — build and test the
  callable first, wire it in a later, explicit task.
- **`account_score`'s placeholder value in `scripts/verify/gate.py`'s `ChangeRef`**
  (currently always `0.0`, per ADR-0009). Feeding a real score into the gate is a
  follow-on wiring decision, not this task's.
