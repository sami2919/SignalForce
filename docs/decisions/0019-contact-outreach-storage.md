# ADR-0019: Contact, Persona, Audience, and Outreach storage (new Task 5.0)

**Status:** Accepted
**Date:** 2026-08-07
**Scope:** New task, not in the plan's Phase 5 breakdown — `scripts/storage/models.py`
(4 new tables), a migration.

---

## Context

The plan's Task 5.2 (reply webhook) needs to look up an `Outreach` row by
`agentmail_thread_id` to find `triggering_signal_ids` — but no task in the plan's
Phase 5 breakdown creates that table, or `Contact`, `Persona`, or `Audience`. All four
exist only in the plan's early schema sketch (the "PHASE 3-5" bird's-eye view), never
assigned to an actual task. Two of the four already have pure, unwired logic from
earlier tasks: `classify_persona` (Task 4.2, ADR-0017) has no `Persona` row to read
definitions from; `evaluate` (Task 4.2, ADR-0017) has no `Audience` row to read
predicates from. This task closes that gap before Task 5.1/5.2 can be real.

## Decision 1 — Four new tables, matching the plan's schema sketch field-for-field,
with explicit nullability/uniqueness decisions the sketch didn't make

**Chosen:**

```
personas(id, tenant_id FK, name, title_patterns JSON, seniority_min)
  UNIQUE(tenant_id, name)

audiences(id, tenant_id FK, name, predicate JSON, created_at)
  UNIQUE(tenant_id, name)

contacts(id, tenant_id FK, account_id FK, email, name, title, persona_id FK NULL)
  UNIQUE(tenant_id, email)

outreach(id, tenant_id FK, contact_id FK, audience_id FK NULL,
         agentmail_inbox_id, agentmail_thread_id,
         sent_at, replied_at NULL, reply_classification NULL,
         triggering_signal_ids JSON)
  UNIQUE(agentmail_thread_id)
```

`personas.title_patterns` stores the same `tuple[str, ...]` shape `PersonaDefinition`
already uses (ADR-0017); `audiences.predicate` stores the same recursive dict shape
`evaluate` already consumes (ADR-0017) — both a direct serialization of the pure
types that already exist, so a future wiring task converts a DB row into the pure
input with a field copy, same pattern as every other ORM/pure-type pair in this
codebase.

**`outreach.audience_id` is nullable**, diverging from the plan sketch's unmarked
(implicitly non-null) column. A one-off, manually-triggered outreach that isn't the
product of a formal audience predicate is a real, expected case — forcing every
`Outreach` row to trace back to an `Audience` row would make that case impossible to
record rather than merely unusual. `contact_id`/`agentmail_inbox_id`/
`agentmail_thread_id`/`sent_at` stay required — those are true of every outreach
message, audience or not.

**`outreach.agentmail_thread_id` is UNIQUE**, not stated either way in the plan.
Task 5.2's webhook handler looks up an `Outreach` row by this field on every inbound
reply — a unique constraint is both the correct modeling (one outreach message maps
to exactly one AgentMail thread) and turns "multiple rows matched" from a silent
correctness bug into a database-enforced impossibility.

**`personas`/`audiences` get `UNIQUE(tenant_id, name)`; `contacts` gets
`UNIQUE(tenant_id, email)`** — matching `Account`'s existing
`UNIQUE(tenant_id, domain)` convention (a tenant's own contact list shouldn't have two
rows for the same email, the same reasoning that already applies to accounts and
domains).

**Rejected: making everything NOT NULL to match the plan sketch literally.** The
sketch is a birds-eye illustration, not a decided schema — ADR-0001/0010/0012 have
all treated the plan's schema sketches as a starting point to verify, not a contract
to copy without checking, the same posture applied to every reference-code snippet
this session.

## Decision 2 — JSON, not raw dict-typed columns, matching every other JSONB-carrying
table in this codebase

`title_patterns`, `predicate`, and `triggering_signal_ids` all use the project's
established `JSONType` (`JSONB` on Postgres, `JSON` on SQLite — see
`scripts/storage/models.py`'s module-level `JSONType`), the same convention
`SignalEvent.payload`, `Score.trace`, `Account.account_metadata`, and
`FactSnapshot.payload` already use. No new column-type decision here.

## What this does NOT decide

- **Populating these tables from real data.** This task builds the schema only —
  filling `personas`/`audiences` with real tenant-configured rows, and `contacts` with
  real people, is Task 5.1/5.2's problem (or a config-loading task of its own).
- **A `Persona`/`Audience` config-loading path** (e.g. reading `config/gtm-context.md`
  into these tables). Out of scope here — this task is the storage layer only, the
  same "build the table, wire it later" split every other task this project has used.
- **`reply_classification`'s actual taxonomy** (positive/negative/neutral, or
  something richer). Left as a free-text nullable column; Task 5.2's webhook writes
  whatever it decides to write there, a decision for that task.

## Consequences

- `Contact.persona_id` and `Outreach.audience_id`/`Outreach.contact_id` are the first
  FK relationships in this schema connecting the "who to reach" side (contacts,
  personas) to the "why reach them" side (audiences, signal-driven scoring) — a reader
  tracing "why did we email this person" now has a real join path:
  `outreach -> contact -> account -> score/signal_events`, plus
  `outreach -> audience -> predicate` and `outreach.triggering_signal_ids` for the
  specific signals that triggered it.
- `outreach.agentmail_thread_id`'s uniqueness means a caller that tries to record two
  outreach rows for the same thread (a caller bug, not a real scenario) gets a loud
  `IntegrityError`, not a silent duplicate.
