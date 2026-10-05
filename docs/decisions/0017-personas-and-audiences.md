# ADR-0017: Persona classification and composable audience predicates

**Status:** Accepted
**Date:** 2026-08-07
**Scope:** Task 4.2 — `scripts/scoring/personas.py`, `scripts/scoring/audiences.py`

---

## Context

Both pure modules, no DB wiring — same scoping this project has used for every
`measure`/`verify`/`scoring` function so far (`score_account` had no caller for a
whole task; `Persona`/`Contact` ORM tables don't exist yet, since `contacts` is Phase
5 scope). `audiences.py` has a complete reference implementation in the plan;
`personas.py` has none — "Files: Create `scripts/scoring/personas.py`" and one line
of context ("job title → persona subcategory"), no test code, no function signatures.
Both are addressed here before writing either.

## Decision 1 — `audiences.py`: reject a predicate dict with more than one recognized
key, instead of silently evaluating only the first ★

**The finding.** The plan's reference `evaluate` is an if-chain: `if "and" in
predicate: ... if "or" in predicate: ... if "has_signal" in predicate: ...`. A dict
with **two** recognized keys — `{"and": [...], "min_score": 50}`, plausible from a
caller merging predicate fragments, or a config author mistakenly nesting two
conditions in one object instead of wrapping them in `"and"` — silently evaluates only
whichever key the if-chain reaches first (`"and"`, here) and drops `"min_score"`
entirely, with no error and no warning. Reproduced directly: `"and" in predicate` and
`"min_score" in predicate` are both `True` for that dict; the function never notices.

This is the same failure shape this project has repeatedly found and fixed elsewhere
this session — a structurally valid-looking input silently loses part of its meaning
(the soft-404 check, `accounts_probed`, the differ's silent-scalar-skip, the unenforced
`max_cost_usd`). An audience predicate is exactly the kind of thing a rep or a config
file author will hand-edit; a query that silently drops half its condition and returns
more accounts than intended is a lead-quality problem hiding as a working feature.

**Chosen:** `evaluate` counts how many of the five recognized keys (`and`, `or`, `not`,
`has_signal`, `min_score`) are present in the predicate dict. Exactly one is required;
zero or more than one raises `ValueError` with a message naming which keys were found.

**Rejected: keep the plan's if-chain as-is.** Silently correct-by-convention (whoever
authors predicates is expected to never combine keys) is exactly the kind of unenforced
assumption ADR-0009 Decision 1 already rejected once this session ("a real constraint or
it does not exist").

**Rejected: merge multiple keys with an implicit AND.** Tempting (`{"and": [...],
"min_score": 50}` "obviously" means both), but inventing an implicit combination rule
the predicate language never asked for is a bigger, more opinionated change than
rejecting the ambiguity outright — and an author who meant OR would get silently wrong
results forever. Loud failure lets the author fix their predicate once; silent
inference guesses wrong indefinitely.

## Decision 2 — `audiences.py`: a non-dict predicate raises `TypeError` at the point of
recursion, not a confusing downstream error

**Chosen:** each recursive call to `evaluate` checks `isinstance(predicate, dict)`
first and raises `TypeError` naming the actual type received, before doing anything
else. A malformed predicate (a list where an `"and"` value should be a list of dicts
but contains a bare string, for instance) fails at the exact recursion level with a
clear message, not as a `TypeError: string indices must be integers` three frames
away from where the mistake actually is.

**Rejected: let a malformed predicate fail wherever Python happens to raise.** Works,
but the resulting traceback points at `evaluate`'s internals, not at which part of a
potentially deeply nested predicate was actually malformed — the same "loud but
useless" failure mode `ExtractorError`/`ValueError` messages throughout this project
have been written specifically to avoid.

## Decision 3 — `personas.py`: title-pattern + seniority-floor classification, first
match wins by input order

**The gap.** The plan names the file and its purpose (Sajwal 28:49: "job title → persona
subcategory") and the eventual schema (`personas(id, tenant_id, name, title_patterns
JSONB, seniority_min)`), but gives no function signature, no test, no seniority
heuristic — there is nothing here to find a defect in, because nothing was written.

**Chosen:**
- `PersonaDefinition(BaseModel, frozen=True)`: `name: str`, `title_patterns:
  tuple[str, ...]` (case-insensitive substrings matched against a title), `seniority_min:
  int` — matches the eventual DB row shape 1:1, so converting `Persona` ORM rows into
  this input (once that table exists, a future wiring task) is a direct field copy, the
  same pattern `ScoreComponent`/`DetectedChange`/`ProbeOutcome` already established.
- `seniority_level(title: str) -> int`: keyword-based, five tiers (5=C-suite/president,
  4=VP, 3=director/head of, 2=manager/lead/principal, 1=default/IC), case-insensitive
  substring match, **highest** matching tier wins when a title matches keywords at
  multiple tiers (e.g. "VP and Head of Marketing" matches both tier 4 and tier 3 keywords
  — take the higher one, since a title naming multiple roles is at least as senior as its
  most senior-sounding component).
- `classify_persona(title: str, personas: list[PersonaDefinition]) -> PersonaDefinition |
  None`: returns the **first** persona in the input list (by list order — the caller's
  responsibility to order by priority) whose `title_patterns` matches the title AND
  whose `seniority_min` is `<=` the title's inferred seniority level. `None` if nothing
  matches — a title matching no configured persona is a real, expected outcome (most
  titles won't match a narrow ICP persona definition), not an error.

**Rejected: return all matching personas, or the "best" match by some specificity
score.** No specificity signal exists in the input (`title_patterns` are unordered,
unweighted strings) to rank matches by, and returning a list changes every caller's
shape for a feature nothing has asked for yet. First-match-by-input-order is simple,
deterministic, and puts ranking control entirely in the caller's hands (order your
personas list by priority) rather than inventing a scoring rule with no data to justify
it.

**Rejected: infer seniority from `contacts`-table fields (e.g. a LinkedIn seniority
field) instead of parsing the title string.** `contacts` doesn't exist yet (Phase 5).
Title-string parsing is the only data available today, and it composes cleanly with a
richer signal later — `seniority_level` stays a pure string→int function regardless of
where the title string came from.

## What this does NOT decide

- **A `Persona` ORM table / migration.** Same scoping as `score_account` before its
  wiring task — build the pure classifier now, persist definitions and wire a caller
  once `contacts` (Phase 5) gives it something to classify.
- **Which personas an actual tenant configures.** `config/gtm-context.md`/`config.yaml`
  are this project's established per-tenant config surface; persona definitions belong
  there once wiring exists, not hardcoded in this module.
- **Combining `classify_persona`'s output into `AccountFacts.signals` or an audience
  predicate.** That's a wiring-task question once `contacts` exists.

## Consequences

- `evaluate`'s stricter validation is a **behavior change** from the plan's literal
  reference code, not just an internal refactor — a predicate with two recognized keys
  now raises where the plan's version would have silently picked one. Correct, but
  worth stating plainly since this task has no prior committed version to diff against
  (nothing in this codebase has called `evaluate` yet).
- `seniority_level`'s five-tier keyword heuristic is a starting point, same footing as
  `_SOURCE_PRIORITY` (ADR-0009) and the `signal_type` weight table (ADR-0016) — a
  defensible default, not a calibrated model, extend the keyword lists as real title
  data is seen.
