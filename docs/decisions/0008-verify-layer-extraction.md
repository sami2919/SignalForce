# ADR-0008: Verify-layer extraction

**Status:** Proposed
**Date:** 2026-08-05
**Scope:** Phase 2, Task 2.1 (the extraction half) — `scripts/verify/extractor.py`

---

## Context

The watch layer knows a page's normalized content hash moved. That is all it knows. The verify
layer turns a changed page into structured facts, which Task 2.3's differ then turns into
changes, which Phase 4 scores and Phase 3 measures.

`ANTHROPIC_API_KEY` is set and verified against `claude-opus-5` (live call, 2026-08-05), so
this is unblocked. Three things discovered while reading Phase 1's code change the design, and
none of them are in the plan.

## Decision 1 — Extract from raw HTML, not from the normalized text ★

**The finding.** `scripts/watch/normalize.py` extracts text via `.text(separator=" ")` and says
so explicitly: *"Attributes are excluded implicitly by taking text only."* Every attribute is
gone — including `href`.

ADR-0007 Decision 1 makes a fact's identity a declared stable key, and measured that **50 of 50**
Greenhouse jobs carry a unique id in the URL (`/jobs/5023394008`). **Those ids live in `href`
attributes.** Extracting from normalized text therefore destroys the exact field ADR-0007 depends
on, and the differ silently degrades to matching jobs by title — which is whole-object identity
wearing a hat, and reintroduces the 2-signals-from-0-changes defect ADR-0007 exists to prevent.

**Chosen:** the extractor consumes **raw HTML**. Normalization stays what it is — a hashing aid
for the watch layer, not a content pipeline.

**Rejected: extract from normalized text.** Cheaper in tokens and already computed. It silently
breaks Decision 1 of the ADR written one day earlier. That the two ADRs would have quietly
contradicted each other is the argument for reading the code before writing the brief.

**Rejected: a second normalizer that preserves hrefs.** Plausible — strip scripts and styles but
keep anchors. Rejected for now because it is a token optimisation whose failure mode is silent
data loss, and the token cost it saves is not yet measured. Revisit if extraction cost becomes
material; the gate (Decision 5) bounds it first.

> **AMENDED 2026-08-05 — the rejection above was wrong, and it was wrong because it reasoned
> about an unmeasured cost.** Task 2.1a's Step 5 measured it. An href-preserving strip cuts
> input by **84% on Greenhouse (33,411 → 5,236 tokens) and 99% on railway.app
> (179,561 → 2,662)**, and the job ids survive in both. Per-extraction cost falls from
> $0.167 → $0.026 and $0.898 → $0.013. See the amendment to Decision 5.
>
> The original caveat still stands and is now the acceptance criterion rather than a reason to
> decline: the failure mode of stripping is *silent* data loss. So the switch is gated on
> reproducing the measured raw-HTML baseline — 50/50 jobs with stable ids on Greenhouse, 16 on
> railway.app — not merely on being cheaper. Tracked as Task 2.1c.

**Accepted cost:** raw HTML is many times larger than normalized text, so extraction costs more
tokens per call. That is a cost problem, which the budget gate bounds. Identity loss is a
correctness problem, which nothing downstream can recover from.

## Decision 2 — The body is passed in-memory from watch to verify ★

**The finding.** Nothing in the system retains a page body. `ProbeResult`
(`scripts/watch/fetcher.py:58`) carries `content_hash`, `status_code`, `latency_ms`, `bytes`,
`error`, `robots_blocked` — no body. The `probes` table stores `content_hash` and never the
content. **The fetcher hashes and discards.** At the moment the watch layer decides "this
changed", the bytes that changed no longer exist anywhere.

**Chosen:** the fetcher retains the body **only for sources whose hash differs from the last
one**, and hands it to the verify layer within the same run. Unchanged sources discard as today.

This is the only option that preserves temporal attribution: the extraction describes the exact
observation that triggered it, so Phase 3's detection lag measures one event rather than two.

**Rejected: re-fetch at verify time.** Simplest, no memory cost, no fetcher change. Rejected
because the re-fetch is a *different observation*: the page may have changed again, reverted, or
started failing between detection and extraction. Detection lag would then be measured against a
snapshot that is not the one detected, which quietly corrupts the number Phase 3 exists to
produce. It also doubles fetches for changed sources and gives the site two chances to rate-limit
us for one signal.

**Rejected: persist bodies to the database.** Durable, and it decouples the two layers so verify
could run in a separate process. Rejected because `probes` is already the one unbounded table in
the schema — Task 3.4 exists specifically to stop it consuming Neon's 0.5 GB free tier in ~5
months. Adding page bodies to the highest-volume table makes the problem that task was written
to solve dramatically worse.

**Accepted cost — memory, and it is not free.** Task 1.3a measured the bound: 100 concurrency ×
8 MB cap = 800 MB worst case against 1 GB provisioned, leaving 200 MB headroom. Retained bodies
come out of that headroom. Retention is therefore capped: bodies are held only for changed
sources, only until extraction, and a total-retained-bytes ceiling drops the largest bodies with
a **logged warning** rather than silently. At the measured change rate this is a handful of pages
per run — but the cap is what stops a bad day from OOM-ing the worker, and Task 1.3a's finding is
that a size cap chosen without measurement silently rejects real sources.

**Consequence:** the verify layer is coupled to the watch run's process. That is correct for a
daily scheduled worker and would need revisiting if watch and verify ever split.

## Decision 3 — Structured outputs, not prompt-and-parse ★

**Chosen:** `client.messages.parse()` with a Pydantic model per source type, which constrains the
response to the schema and validates it.

**Rejected: "respond with only valid JSON" plus `json.loads` in a retry loop.** The traditional
approach and the one the model's own training data is full of. It fails in the shape this project
keeps finding: a parse failure is recoverable and loud, but a *successful parse of a
subtly-wrong-shaped object* is silent, and the retry loop makes cost unpredictable in exactly the
runs where the model is struggling. Structured outputs move the guarantee into the API.

**Rejected: assistant-turn prefill to force the JSON opening brace.** The classic trick, and it
returns **HTTP 400** on `claude-opus-5`. Recorded so nobody reintroduces it from memory.

**Note:** structured outputs are incompatible with citations (400). We are not using citations,
but a future "show me where on the page you found this" feature would collide with this decision.

## Decision 4 — One fact schema per source type, each declaring its identity key

**Chosen:** `careers`, `pricing`, `changelog`, `docs`, `blog` each get a Pydantic model, and each
fact type within them declares the field(s) that identify it (ADR-0007 Decision 1). A fact type
without a declared identity key must fail at import, not at diff time.

Careers is the one to get right first: it is the highest-intent source, it is where the identity
key is measurable (`50/50` job ids), and it is what AgentMail's ICP actually turns on.

**Rejected: one generic schema for all source types.** Fewer models to maintain. It would force
the identity key to be generic too, which is precisely the whole-object-identity failure.

## Decision 5 — Cost is bounded by the gate, not by the model choice

**Chosen:** `claude-opus-5` with adaptive thinking, and the budget gate (`select_for_verification`,
the half of Task 2.1 the plan does specify) is what bounds spend.

At the measured scale this is not close: 90 sources at the 3–20% change rate is 3–18 extractions
per day. Choosing a cheaper model to save on 18 calls, before a single extraction-quality number
exists, would be optimising the wrong axis — and extraction quality is what every downstream
number inherits.

> **AMENDED 2026-08-05 — "not close" was an assertion, not a measurement, and it does not
> survive one.** Measured per-extraction cost on raw HTML is **$0.265 (Greenhouse) to $0.916
> (railway.app)**. At 3–18 extractions/day that is **$45–270/month** — not the rounding error
> the original wording implies. The conclusion (keep `claude-opus-5`; bound cost at the gate)
> still holds, but for a different reason than stated: the fix is the **input size**
> (Decision 1's amendment, 84–99% reduction), not the model. Re-derive this arithmetic before
> quoting a cost-per-account figure.
>
> **Prompt caching is marginal, also measured.** Run 2 of the same page read 1,342 cached
> tokens — the system prompt caches correctly, confirming the >512-token prefix — but that is
> **4% of a 33,409-token request**. The page content dominates so completely that caching is
> nearly irrelevant on raw HTML. It becomes material only *after* the input shrinks.

**Rejected: a cheaper model now.** Revisit when there is a measured quality baseline to trade
against, and when account count makes the arithmetic matter. Not before.

**Prompt caching applies:** the per-source-type system prompt is stable across every extraction
of that type, and `claude-opus-5`'s minimum cacheable prefix is 512 tokens. Put the stable
instructions first and the volatile page content last, or the cache never reads.

## What this does NOT decide

- **The gate's ranking function.** `select_for_verification` is specified in the plan and is its
  own task; this ADR only asserts that it, not the model choice, is the cost bound.
- **Where fact snapshots are stored.** The differ needs the previous snapshot to diff against.
  ADR-0007 left this open and it stays open — it is the next thing to decide, and it interacts
  with Task 3.4's retention work.
- **Whether extraction runs inside the watch runner or beside it.** Decision 2 requires the same
  process; it does not require the same function.
- **Account creation for scanner-discovered orgs.** Still open from ADR-0006.

## Consequences

- `ProbeResult` and the fetcher change shape for the first time since Task 1.3a. That code is
  covered by a full review and a real-data run; the retention path needs the same.
- Extraction cost per call is higher than a normalized-text design would be, and is unmeasured.
  Task 2.1 must report measured tokens and dollars per extraction on real pages before anyone
  quotes a cost-per-account figure.
- A page whose body is dropped by the retention cap is detected-but-not-extracted. That is a
  fourth outcome alongside changed / unchanged / degraded, and Phase 3's source health has to be
  able to see it — otherwise it looks like a quiet source.

---

## Appendix — findings (code read, 2026-08-05)

```
IDENTITY KEYS DO NOT SURVIVE NORMALIZATION
  scripts/watch/normalize.py — text = root.text(separator=" ")
  docstring: "Attributes are excluded implicitly by taking text only."
  => href gone => Greenhouse /jobs/5023394008 gone => ADR-0007 Decision 1's
     measured 50/50 stable identity key is unavailable downstream.

NOTHING RETAINS A PAGE BODY
  scripts/watch/fetcher.py:58  ProbeResult{content_hash, status_code,
                               latency_ms, bytes, error, robots_blocked}
  scripts/storage/models.py:82 Probe{content_hash, changed, status_code,
                               latency_ms, bytes, error}
  => the fetcher hashes and discards; at detection time the changed bytes
     exist nowhere.

MEMORY BOUND ALREADY MEASURED (Task 1.3a)
  100 concurrency x 8MB cap = 800MB worst case vs 1GB provisioned
  => 200MB headroom is what retained bodies must fit inside.

API VERIFIED LIVE (2026-08-05)
  claude-opus-5 -> stop_reason=end_turn, in=16 out=4. SDK anthropic 0.112.0.
```
