# Plan: Rebuild SignalForce around customer understanding (first principles)

Rationale and audit: `docs/first-principles-gtm.md`. **Status: awaiting approval. Nothing below is built.**

Principle for every item: evidence tier is explicit (did > said > believed), every claim has a
source, every rule is holdout-tested before it drives outbound.

## Phase 0 — Remove what contradicts the principles (small, do first)
- [ ] Remove/flag the unsourced "50% reply rate" claims in `skills/email-writer`, `skills/resource-offer`, `templates/email-sequences/resource-offer-signal.md`
- [ ] Mark signal weights in `templates/scoring-rubrics/icp-scoring-model.md` and example configs as *priors (unvalidated)*, not facts
- [ ] Add `evidence_tier` (did / said / believed) to ICP statements in `config.example/gtm-context.md`

## Phase 1 — Ground truth layer
- [ ] `CustomerDossier` + `DossierEvent` Pydantic models (frozen): source, trigger, calls, decision-makers, time-to-value, usage, expansion/churn, each event tagged with evidence tier and source ref
- [ ] Importer: CRM export CSV (+ optional transcripts) → dossiers, with entity resolution on domain
- [ ] Skill `customer-dossier`: build/refresh a dossier; Mom-Test tagging of transcript sentences (fact/behavior vs opinion/compliment/request); only facts feed the dossier

## Phase 2 — Won / lost / 10X analysis
- [ ] Skill `win-loss-analysis`: separate-cohort lenses, then blinded blend (labels hidden), output 3–5 candidate "reasons they bought" each with supporting behaviors + quotes
- [ ] Discriminating-trait check: report a trait only if its rate differs between won and lost (with interval), not just "common among winners"

## Phase 3 — Pain-Qualified Segments + predictive holdout (the core)
- [ ] `PainSignalHypothesis` model: definition, public source, refresh cadence, cost per right answer, message line it supports, kill criterion
- [ ] `scripts/measure/predictive_holdout.py`: "rewind time" — score accounts using only signals observed before their outcome date; report whether held-out winners rank above losers (AUC / precision@k with intervals), vs random and firmographic baselines
- [ ] Hypothesis log (versioned YAML) with status: proposed → tested → validated / killed
- [ ] Segment matrix skill: worst-version-of-problem scoring (intensity × frequency × cost-of-inaction, then urgency, budget owner, weak alternative, observability)

## Phase 4 — Enumerate, then disqualify
- [ ] `UniverseSource` concept: a complete source per vertical (registry, directory, filings); scanners become disqualify/qualify evidence over the universe instead of the universe itself

## Phase 5 — Messages that re-describe the pain
- [ ] `email-writer` rewrite: PQS variant (situation + cost, every fact source-linked) and PVP variant (standalone value), mapped to awareness level and Four Forces; "proud to receive" bar
- [ ] Judge: reject any draft containing a factual claim without an evidence ref. Use Blueprint's rubric: /10 score plus binary Hyper-Specific / Factually Grounded / Non-Obvious checks, plus a simulated-buyer "I'm deleting this because…" critique. Emit nothing for a segment rather than an ungrounded draft
- [ ] Compound conditions: let a PQS be defined as A × B over joined sources (e.g. signal + derived metric), not only as stacked single signals
- [ ] Reply backflow: re-rank signal weights from classified replies and outcomes (replaces static config weights once n is sufficient)

## Phase 6 — Discovery
- [ ] Skill `switch-interview`: Mom-Test + Moesta script, pre-interview prediction sheet, saturation stopping rule (~80% predictions held ×3, no new codes), Four Forces map per interview

## Open questions for you
1. Do you have real closed-won/lost data (any ICP) to build against, or should Phase 1–3 ship with a synthetic fixture first?
2. Which ICP is the beachhead to prove this on? Crawford's method works best in a regulated vertical with hard public records; our shipped examples are horizontal infra with mostly soft signals (see doc §5 item 12)
3. Order: I'd do Phase 0 → 3 first (the predictive holdout is the single highest-leverage gap), then 5, then 1/2 polish, 4, 6.

## Review
_(filled in after implementation)_
