# ADR-0023: Recording a sent outreach message (`record_outreach`)

**Status:** Accepted
**Date:** 2026-08-07
**Scope:** New Task 5.5 — closes a gap surfaced while running Task 5.1/5.2's
end-to-end reply-webhook test against production: `AgentMailClient.send()` (Task
5.1) and the `Outreach` table (Task 5.0) both exist, but nothing connects them.
Sending a real message today creates no `Outreach` row, so Task 5.2's reply webhook
has no row to match a real inbound reply against — the exact case the
first-reply-wins / cohort-lift design (ADR-0020, ADR-0021) assumes will exist.

---

## Context

Verified before writing anything (read-only query, `DATABASE_URL_DIRECT`, allowed
under the standing no-production-writes-outside-app-code rule): production has one
tenant (`agentmail`, id 1), 268+ real ICP `accounts` from the Phase 2 scanner, and
**zero** rows in `contacts` and `outreach` — this task's wiring would create the
first rows in either table.

**Design question this surfaces:** `Contact.account_id` is `NOT NULL` (ADR-0019).
Given only an email address, should `record_outreach` auto-create an `Account` from
the email's domain, or require the caller to supply an existing `account_id`?

## Decision 1 — caller supplies `account_id`; no domain-derived auto-create ★

**Chosen:** `record_outreach(session, *, tenant_id, account_id, contact_email, ...)`
takes `account_id` as a required argument. It does not attempt to derive or upsert
an `Account` from the email's domain.

**Reasoning.** In this system outreach is never generic — it always follows from a
persona/audience match against a *known* account the watch/scoring pipeline
already resolved (Phase 1-4). The caller (a future outreach-orchestration task)
always has that `account_id` in hand before it ever calls `send()`. Auto-deriving
an account from the domain is actively wrong for the common real case anyway: a
contact's email domain is not reliably the company's canonical domain (personal
addresses, `gmail.com`, subdomains, email-forwarding services), so a
domain-derivation path would either silently create garbage `Account` rows for
non-ICP domains or silently fail in a way that's easy to miss. Requiring the caller
to supply `account_id` pushes that judgment to the place that actually has the
context to make it correctly.

**Rejected: auto-create `Account` by domain.** Convenient for a quick script, wrong
for the system's actual shape — accounts are supposed to be the output of the
resolver/scanner pipeline (Phase 1/2), not incidentally created as a side effect of
sending an email.

## Decision 2 — `Contact` is find-or-create by `(tenant_id, email)`; `Outreach` is
insert-only, relying on the existing `agentmail_thread_id` unique constraint

**Chosen:** `record_outreach` looks up an existing `Contact` by
`(tenant_id, email)` (the constraint ADR-0019 already declared) and reuses it if
found, creating one only if absent. `Outreach` is always a fresh insert — the same
`(tenant_id, contact)` pair can have many outreach rows over time (follow-ups,
re-engagement), but `agentmail_thread_id` staying globally unique (ADR-0019) means
calling this function twice for the same real AgentMail thread raises
`IntegrityError` rather than silently duplicating the row. Callers that retry a
failed record (as opposed to a failed send) must catch that and treat it as
"already recorded," not corruption.

**Rejected: upsert `Outreach` by thread_id.** Would silently swallow a genuine bug
(calling this twice for the same send) instead of surfacing it — the same
"silent-no-op" shape this project has repeatedly found and rejected elsewhere
(soft-404s, the `pushed:` qualifier, `accounts_probed`, the truncation ceiling).

## Decision 3 — recording is a separate call, not built into `AgentMailClient.send()`

**Chosen:** `record_outreach` lives in `scripts/outreach/recorder.py`, a plain
function taking a `Session`, called by a caller *after* `send()` succeeds.
`AgentMailClient` (Task 5.1) stays a thin, DB-free wrapper over AgentMail's REST
API, matching every other API client in this project (`github_scanner`,
`funding_scanner`, etc. never import `scripts.storage`).

**Rejected: have `send()` record internally.** Would give the AgentMail client a
database dependency none of its siblings have, and conflates two independently
failable operations (the HTTP send; the DB write) into one call whose partial
failure mode ("message sent but not recorded" vs. "recorded but never sent") the
caller can no longer distinguish or handle differently.

## Verification (this task, against production)

Reused the real thread from the deploy-verification send earlier this session
(`thread_id=2e1cd50d-f882-4e82-888e-f24b9248c30e`, sent to
`abdussamidec6@gmail.com`, confirmed delivered) rather than sending a second
message. Since that recipient is the developer's personal test address, not a real
ICP account, it is recorded against a dedicated, clearly-labeled harness account
(`domain="signalforce-harness.internal"`, `name="SignalForce Test Harness"`) —
kept structurally separate from the 268+ real scanner-sourced accounts, so no test
data is misattributed to a real prospect company.

## What this does NOT decide

- **Automatic recording from a real outreach-sending workflow.** No such workflow
  exists yet (NOT in Scope per the original plan's Phase 5 boundary) — this task
  only builds the primitive a future one will call.
- **Cleanup/removal of the harness account+contact+outreach row after this test.**
  Left in production, clearly labeled, as the honest record of what was actually
  verified — consistent with this session's "verify against real infrastructure,
  keep the evidence" practice throughout Phase 0-5.
