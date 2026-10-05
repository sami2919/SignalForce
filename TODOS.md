# TODOS

## P2: Community Config Repository

**What:** Create a separate GitHub repo (e.g., signalforce-configs) for community-contributed ICP configurations.

**Why:** Network effects — new users browse configs for their vertical instead of starting from scratch.

**Pros:** Viral adoption, reduced onboarding friction, community engagement.

**Cons:** Maintenance burden, quality control of submitted configs.

**Context:** Accepted as P2 during CEO review (2026-03-18). Depends on configurable ICP refactor shipping first. Users would submit PRs with their `config.yaml` + `gtm-context.md` + templates for their vertical.

**Effort:** M (human: ~1 week / CC: ~2 hours)

**Depends on:** Configurable ICP feature (this refactor)

---

## Signal Audit follow-ons (from /plan-ceo-review, 2026-09-30)

Design: `~/.gstack/projects/sami2919-visitor-intent-pipeline/sami-main-design-20260929-205620.md`. Phase 1a (file-adapter Signal Audit in a new `signal-audit` repo) is the active work; the items below are deliberately deferred.

### P2: Postgres adapter + signal_events migration
**What:** Read the audit's inputs straight from Postgres; add `source_family`, `source_event_id`, `verified`, `evidence_ref` to `signal_events` using expand → backfill (`legacy:<id>`) → contract (unique index on tenant, source, source_event_id); add an `audit_runs` table and a `signal-audit diff` command.
**Why:** Removes the CSV export step once real use proves the audit is wanted.
**Trigger:** The first partner export works end to end through the file adapter.
**Effort:** M (human ~1 week / CC ~1 day). **Depends on:** phase 1a shipped. **Gotcha:** run `fly machine update` on the worker and holdout machines after each deploy (see fly.toml).

### P3: Mixed model + PyMC validation
**What:** Replace the Fit-stratified Wilson table with statsmodels `BinomialBayesMixedGLM` (account random intercept), validated against PyMC; nightly 200-seed calibration.
**Why:** Handles overlapping account-weeks properly at scale.
**Trigger:** A partner with more than ~2,000 exposed account-weeks per signal type.
**Effort:** S-M (human ~4 days / CC ~0.5 day).

### P2: Evidence Router (phase 2)
**What:** Live first-party ingest (a queue for the real-time lane only), routing with receipts (source, age, confidence) to Slack and the CRM, freshness SLAs with alerts, evidence feeding scoring weights, claim-checked drafts and pages.
**Trigger:** One partner asks for a second audit run or for live routing.
**Effort:** L-XL (human ~6 weeks / CC ~1-2 weeks).

### P3: Pre-send Verifier
**What:** An API/webhook checkpoint that re-verifies each personalization fact against live sources before any tool sends, and blocks stale or unsupported claims with a reason.
**Trigger:** Evidence Router live.
**Effort:** M (human ~3 weeks / CC ~2-3 days). **Risk:** depends on other tools' send paths.
