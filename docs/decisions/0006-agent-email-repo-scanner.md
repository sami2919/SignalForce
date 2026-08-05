# ADR-0006: Agent+email repo scanner — query strategy and recency

**Status:** Accepted
**Date:** 2026-08-04
**Scope:** Phase 2, Task 2.2 — `scripts/scanners/agent_email_scanner.py`

---

## Context

The signal: a GitHub repo that depends on **both** an agent framework (`openai-agents`,
`langgraph`, `crewai`, `mastra`, `agno`, `autogen`, `pydantic-ai`) **and** an email library
(`resend`, `sendgrid`, `nodemailer`, `postmark`, `mailgun`), owned by an Organization rather
than a User, first seen recently. A team shipping an agent that touches email is solving the
exact problem AgentMail sells a solution to, and is solving it right now.

Intersection, not union. An agent framework alone means "building agents" (weak, and there are
169,344 such files). An email library alone means "sends email" (meaningless). Both, in one
repo, recently, is the whole signal.

The plan (Task 2.2, Step 3) sketched N framework queries + M email-lib queries, then a set
intersection on `full_name`. The reasoning was that GitHub code search ANDs terms *within a
file*, so a combined query would miss the common layout where the framework and the email
library are imported in different source files.

**That reasoning is sound and the conclusion is still wrong.** All decisions below rest on
measurements taken against the live API on 2026-08-04, recorded in the appendix.

## Decision 1 — Manifest-scoped combined queries, not repo-set intersection ★

**This is the decision the whole task turns on.**

**Chosen:** one query per (framework, email-lib, manifest) triple, of the form

```
"langgraph" "resend" filename:pyproject.toml
"mastra" "resend" filename:package.json
"crewai" "sendgrid" filename:requirements.txt
```

**Rejected: N + M queries, set-intersected on repo (the plan's design).**
GitHub code search refuses to page past 1000 results — page 11 returns HTTP 422 `Cannot access
beyond the first 1000 results`. `"langgraph" language:python` matches 169,344 files, so **0.59%
of the corpus is reachable**; `"resend" language:python` matches 56,928, so 1.76% is reachable.
Intersecting a 0.6% sample with a 1.8% sample does not produce "repos with both" — it produces
whatever the two truncated result windows happen to share, which is governed by GitHub's result
ordering, not by the signal. Observed ordering was near-alphabetical by owner, so the design
would have silently become "org-owned agent+email repos whose owner name starts with A".

The failure is invisible: it returns *some* results, and they are *correct* results. Nothing
errors. It would have been read as a working scanner with disappointing yield.

**Rejected: combined queries over all code (no `filename:` scope).**
This is the design the plan argued against, and the objection is real: `"langgraph" "resend"`
finds files containing both strings, missing repos that import the framework in `agent.py` and
the email client in `notify.py`. Manifest scoping dissolves the objection rather than accepting
it — `pyproject.toml`, `requirements.txt`, and `package.json` declare **every** dependency of a
repo in a single file, whatever the source layout. File-level AND on a manifest *is* repo-level
AND on dependencies. It is also strictly more precise: a manifest entry is a deliberate,
declared dependency, not a string in a README, a tutorial comment, or a lockfile artifact.
Measured: org-owned density rose from ~10% (all-code) to ~25% (manifest-scoped).

**Rejected: boolean `OR` to collapse the matrix.**
`("langgraph" OR "crewai") "resend"` returns HTTP 422 `ERROR_TYPE_QUERY_PARSING_FATAL`. Bare
`"langgraph" OR "crewai"` parses but returns 29,984 — *fewer* than `"langgraph"` alone at
169,344, so it is demonstrably not computing a union. Unusable, and dangerous precisely because
the bare form does not error.

**Accepted cost — stdlib and vendored libraries are invisible.** `smtplib` is in the Python
standard library and will never appear in a manifest. It is dropped from the matrix rather than
silently under-matched. Any repo whose email path is raw `smtplib` is missed by design; that is
also the weakest end of the signal (an agent posting through stdlib SMTP is less likely to be a
product than one that pulled in Resend).

**Accepted cost — the matrix is ~60 queries.** 6 Python frameworks × 4 Python email libs × 2
manifests = 48, plus 3 JS/TS frameworks × 4 JS email libs × 1 manifest = 12. At the documented
10 requests/minute that is ~6 minutes for first pages, ~15 minutes worst case with paging. This
runs on a daily scheduled worker. Wall-clock is not a constraint worth optimising against.

**Accepted cost — monorepos.** A monorepo whose root `package.json` lists both dependencies
scores as one signal even if the agent and the mailer are unrelated packages. Acceptable: the
owning org is still the entity we care about.

## Decision 2 — Never send a qualifier the endpoint does not support ★

**Measured trap.** `/search/code` accepts `pushed:>2026-07-05` and `stars:>5` without complaint
and returns **`total_count: 0` with HTTP 200**. These are repo-search qualifiers; code search
neither supports nor rejects them. There is no error, no warning, no `incomplete_results` flag.

This is the same silent-failure shape as ADR-0004's soft-404 and the `accounts_probed` bug from
Task 1.3b: a plausible-looking wrong answer that survives review because nothing complains. It
is recorded as a decision rather than a footnote because the temptation is strong — filtering
recency in the query is the obvious first instinct, and it would have produced a scanner that
reported zero signals forever while looking perfectly healthy.

**Chosen:** the permitted qualifier set is `language:`, `filename:`, `path:`, `extension:`,
`repo:`, `org:`, `user:`, `size:` — nothing else. Every other filter is applied client-side.

**Enforced by:** a canary test asserting that a known-good query returns `total_count > 0`, so
a future qualifier addition that silently zeroes the corpus fails the suite instead of the
scanner. A test asserting "no signals" cannot distinguish a broken query from a quiet market;
a test asserting a non-empty corpus can.

## Decision 3 — Recency comes from core-API enrichment, after filtering

**Measured:** the `repository` object embedded in a code-search item is **minimal**. It carries
`full_name`, `html_url`, `description`, `fork`, and a full `owner` (including `owner.type`). It
does **not** carry `pushed_at`, `created_at`, or `stargazers_count`.

The plan's reference implementation reads `repo.get("pushed_at")` and guards with `if pushed:`.
That is always `None`, so the cutoff branch never executes and **every repo passes the recency
filter**. `repo.get("stargazers_count", 0)` is always `0`. Both would have shipped as working
code emitting a `stars` field that was structurally always zero.

**Chosen:** a second pass against `GET /repos/{full_name}` on the *surviving* candidate set
only — after dedup and after the org filter (Decision 4).

The hard constraint in the brief was "no per-repo follow-up call inside the search loop," which
is correct: `/search/code` is capped at 10/min. But `/repos/{owner}/{repo}` is not a search
endpoint. Verified against `/rate_limit`: `core` = **5000/hour**, `search` = 30/min, `graphql` =
5000/hour — separate buckets, separately accounted. Enriching 50–150 candidates costs 50–150 of
5000 hourly core requests. The constraint is honoured (nothing per-repo happens inside the
search loop) and recency becomes affordable rather than impossible.

`GET /repos/BerriAI/litellm` was confirmed to return `created_at`, `pushed_at`, `updated_at`,
`stargazers_count`, `archived`, and `fork`.

**Rejected: GraphQL batching.** Genuinely better — one request could enrich 100 repos instead
of 100 requests. Rejected because it needs a second HTTP path, a query-document builder, and
its own error taxonomy, none of which `scripts/api_client.py` provides, in exchange for saving
~150 requests out of a 5000/hour budget that is otherwise unused. Revisit if the candidate set
exceeds ~1000 per run.

**Rejected: dropping recency.** Recency *is* the intent. "Shipped an agent that emails" is a
weak signal; "shipped one this month" is the signal. Without it the scanner returns a static
list of every such repo ever, which is a directory, not a trigger.

**Rejected: `size:` as a freshness proxy.** No relationship to time.

## Decision 4 — Filter free before you pay: org gate precedes enrichment

**Chosen pipeline order:** search → dedup on `full_name` → drop `fork: true` → drop
`owner.type != "Organization"` → **then** enrich the survivors → then apply recency.

`owner.type` and `fork` are present in the search payload at zero marginal cost, and the org
gate is the most selective filter available (~75% of candidates are personal accounts). Running
it before enrichment cuts core-API calls by roughly 4×. Ordering filters by
(selectivity ÷ cost) is the only reason this stays comfortably inside budget.

`fork: true` is dropped because a fork inherits its parent's manifest — a fork of an agent
template is evidence about the parent, not about the forking org.

**Accepted cost:** GitHub Enterprise-style orgs that publish under a personal account are
missed. Personal side projects are not buyers; this trade is the point of the filter.

## Decision 5 — "First seen" means first seen *by us*, and run 1 seeds silently ★

**Ruled by the user, 2026-08-04.**

**Chosen:** a `repo_observations` table keyed `(tenant_id, full_name)` with `first_seen_at`.
A candidate is new iff it has no row. Emission is once-per-repo, forever.

**Cold start:** a run where the tenant has **zero** `repo_observations` rows is a *seeding*
run. It records every candidate and emits **nothing**. Recorded explicitly on the `scan_runs`
row so a seeding run is never misread as "the scanner found nothing" — the distinction between
zero signals and zero because we were seeding is exactly the ambiguity Phase 3 exists to remove.

**Rejected: `created_at` within the lookback window.** Cleanest reading of "new repo", and
free once enriched. Rejected because it misses the stronger buying signal: an *established*
company adding an email dependency to an agent repo it has had for a year. That is a team
that just decided to make their agent send mail — closer to the moment of intent than a
brand-new repo, which is as likely to be a weekend prototype.

**Rejected: `pushed_at` within the lookback window.** Barely filters. Any repo surfacing in a
manifest query is, almost by construction, recently pushed. It would have looked like a working
filter while removing nearly nothing — the same class of defect as the always-`None` recency
guard in Decision 3.

**Accepted cost — the signal is now relative to our observation history, not to the world.**
A repo that added `resend` six months before we started scanning emits on the day we first see
it. That is honest ("new to us") but must never be reported as "shipped this week". The payload
carries `created_at` and `pushed_at` alongside `first_seen_at` so the two notions stay
distinguishable downstream, and Phase 3's detection lag has a real observation timestamp to
measure against.

**Accepted cost — the ledger is load-bearing state.** If `repo_observations` is ever truncated,
the next run re-seeds and silently suppresses a day of signals. It is not a cache.

**Consequence — enrichment is demoted and cheapened.** With recency answered from our own state,
`GET /repos` is no longer a gating filter: it supplies payload metadata (`stars`, `created_at`,
`pushed_at`) and the `archived` check, which is unavailable in the search payload. It therefore
runs on the **new-to-us set only** — a handful per day at steady state, versus every org
candidate on every run. Decision 3's budget analysis holds with room to spare; only the seeding
run enriches at full width.

**Ledger records all org-owned candidates; emission additionally requires not-archived.** An
archived repo is recorded (so it is not re-evaluated daily) but emits no signal — a dead repo
is not a buying signal. Accepted cost: a repo that is un-archived later never emits.

## What this does NOT decide

- **Persistence of the signals themselves.** Writing these into `signal_events` is Task 2.3,
  and is blocked on account creation below — `SignalEvent.account_id` is non-nullable while
  this scanner discovers orgs that have no `accounts` row yet. Note the Task 0.1 finding:
  JSON columns are not `MutableDict`-wrapped, so `SignalEvent.payload` must be assigned as a
  whole new dict, never mutated in place.
- **Account creation.** Whether an org discovered here becomes an `accounts` row, and how it
  joins the Phase 1 watch registry.
- **Scoring.** Signal strength beyond a flat `STRONG` is Phase 4.
- **The framework and email-lib lists themselves.** They belong in `config/config.yaml` under
  the scanner's `custom_params`, not hardcoded, so the matrix is tunable without a deploy.

## Consequences

- Every query in the matrix is exhaustively enumerable (measured totals 20–572, all under the
  1000 ceiling). The scanner has **no truncation bias**, which is a property worth asserting:
  if a pair's `total_count` ever exceeds 1000, that pair has silently become a sample and must
  log a warning rather than quietly returning its first 1000.
- Two rate-limit budgets must be tracked separately in logs — search requests and core requests
  are not fungible, and conflating them is how a "we have plenty of quota" claim goes wrong.
- Recall is unmeasured. Task 2.2 must report org-owned candidate count, enrichment count, and
  post-recency signal count per run, so the decision to widen the matrix is made on data. Do
  not claim a yield number before then.
- The manifest approach cannot see private repos, and cannot see a company that builds this
  internally. This scanner finds public builders. That is a real ceiling on the signal, not a
  bug to fix.

---

## Appendix — measurements (live API, 2026-08-04, token scope `public_repo`)

```
PAGING CEILING
  "langgraph" language:python                   total=169344  page 11 -> 422 (max 1000)
  "resend" language:python                      total= 56928  -> 1.76% reachable
  sort=indexed&order=desc                       IGNORED — byte-identical to unsorted

COMBINED (all code)          total   uniq_p1   org_p1
  "openai-agents" "resend"      20      18        5
  "crewai" "sendgrid"          155      80        8
  "langgraph" "sendgrid"       390      86        8
  "langgraph" "smtplib"        572      93       10
  "mastra" "resend" (ts)       207      59       12
  "langgraph" "resend"         497      91        —

MANIFEST-SCOPED             total   uniq_p1   org_p1   org%
  filename:requirements.txt   230      95        8      8%
  filename:pyproject.toml     182      85       21     25%
  filename:package.json       117      97       21     22%
  package.json @openai/agents  80      76        6      8%

SILENT-ZERO QUALIFIERS
  ... pushed:>2026-07-05      total=0   HTTP 200   (no error)
  ... stars:>5                total=0   HTTP 200   (no error)

BOOLEAN OR
  ("langgraph" OR "crewai") "resend"   -> 422 QUERY_PARSING_FATAL
  "langgraph" OR "crewai"              -> 29984  (< langgraph alone; not a union)

RATE BUCKETS (/rate_limit)
  core 5000/hr · search 30/min · graphql 5000/hr    (separate accounting)
  GET /repos/{full_name} -> created_at, pushed_at, stargazers_count, archived, fork

CODE-SEARCH repository OBJECT
  HAS: full_name, html_url, description, fork, owner{login,type}
  LACKS: pushed_at, created_at, stargazers_count
  => plan's `if pushed:` recency guard is a no-op; every repo passes
```
