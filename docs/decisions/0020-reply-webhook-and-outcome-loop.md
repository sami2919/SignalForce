# ADR-0020: AgentMail reply webhook and outcome loop

**Status:** Accepted
**Date:** 2026-08-07
**Scope:** Task 5.2 — `scripts/web/routes_webhooks.py`, new `svix` dependency

---

## Context

Same standard as Task 5.1: verified against AgentMail's real docs and the real `svix`
library source (via `gh api repos/svix/svix-webhooks`, after two rounds of web-doc
fetches gave summarized, partially wrong information — see Decision 1) before writing
any code. Found three real corrections to the plan's spec, one of them a flaw in the
plan's own stated design *principle*, not just its reference code.

## Decision 1 — `svix.Webhook.verify()` returns the parsed JSON payload; verified
against the ACTUALLY INSTALLED package, not documentation or a GitHub branch ★

**Three different answers, three different sources, in order:**

1. A WebFetch against AgentMail's webhook-verification docs page implied usage like
   `msg = wh.verify(request.get_data(), request.headers)` — suggesting `verify()`
   returns the parsed payload.
2. Pulling the Python source from GitHub's `main` branch (`gh api
   repos/svix/svix-webhooks/contents/python/svix/webhooks.py`) showed
   `verify(self, data, headers) -> None`, calling the inner verifier with
   `json_parse=False` — suggesting it returns nothing, contradicting (1).
3. **Installing the actual package this project depends on (`svix>=1.24`, resolved to
   1.99.1) and reading the code that will actually run** (`inspect.getsource`, in this
   environment, not fetched) showed `svix.webhooks.Webhook.verify` calls
   `self._inner.verify(data, headers)` with **no** `json_parse` argument, so the
   underlying `standardwebhooks.Webhook.verify`'s default `json_parse: bool = True`
   applies — **it returns the parsed JSON payload as a dict**, contradicting (2) as
   well.

**Chosen:** trust (3) — the installed package's actual source — over both external doc
summaries and even a same-repo GitHub branch that turned out not to match what's
published. `payload = wh.verify(raw_body, headers)` returns the verified, parsed
payload directly; no separate `json.loads()` needed.

**The lesson, stated plainly:** for a security-relevant external library, neither a doc
summary nor a same-project GitHub branch is a substitute for reading the code that will
actually execute. Three sources gave three different answers on this exact question;
only installing the real dependency and inspecting its real source in this environment
resolved it. Same standard this project has applied to its own reference code all
session, extended one level further — to a dependency's dependency.

**Rejected: trust either doc summary or the GitHub branch without local verification.**
Would have shipped code that either double-parses a dict as if it were raw bytes, or
crashes expecting a dict where `None`/bytes was actually returned — a `TypeError` on the
very first real webhook delivery, exactly the failure this project's whole practice of
verification-before-trust exists to prevent.

## Decision 2 — The real payload is deeply nested; `event_type` is the discriminator,
not `event`, and `thread_id`/`text` live under `message`

**Verified via `docs.agentmail.to/api-reference/webhooks/events/message-received.md`:**

```json
{
  "type": "event",
  "event_type": "message.received",
  "event_id": "...",
  "message": {"thread_id": "...", "text": "...", "...": "..."},
  "thread": {"...": "..."}
}
```

The plan's own test posts a flat `{"event": "message.received", "thread_id": ...,
"text": ...}` — none of those top-level keys exist in the real payload. A handler
written against the plan's literal test would silently never match a single real
webhook delivery (every field access would be `None`/`KeyError`), the exact "looks
tested, matches nothing real" shape this project has repeatedly found in plan
reference code.

**Chosen:** read `payload["event_type"]`, and for `message.received`, read
`payload["message"]["thread_id"]` / `payload["message"]["text"]`.

## Decision 3 — HTTP status codes are NOT uniformly 200; the plan's "webhooks must
never 500" principle is right for permanent non-matches and wrong for transient
failures ★

**The finding.** The plan states, as a blanket rule: *"webhooks must never 500 —
senders retry forever."* Its own one worked example (`test_unknown_thread_is_ignored_
not_errored`) is a case where that's correct: an unknown `thread_id` will **never**
resolve on retry — the `Outreach` row that isn't there now will not spontaneously
appear later, so retrying is pure waste and 200 (stop retrying) is right. But
generalizing that to *every* failure mode is wrong for the opposite reason: a
genuinely transient failure (a DB connection blip, a momentary Neon hiccup) is exactly
what Svix's retry mechanism exists to recover from. Returning 200 for a transient
failure doesn't avoid a problem — it **silently and permanently discards that reply's
outcome data**, because Svix will never retry a request that reported success. That's
the same "confident wrong answer beats a visible failure" shape this project has
found and corrected in a dozen other places this session, just discovered in the
plan's stated *principle* this time, not its code.

**Chosen — three distinct response classes, not one blanket rule:**

| Situation | Status | Why |
|---|---|---|
| Missing `AGENTMAIL_WEBHOOK_SECRET` | 500 | A real server misconfiguration, not a request problem — must be visible as an operational failure, not swallowed as if the request itself were bad. |
| Invalid signature | 401 | A genuine security rejection. This is the one boundary that must reject, not accept-and-ignore — an unverified request is not a webhook this system can trust at all. |
| Unknown `thread_id`, non-`message.received` event, missing `thread_id`, unparseable JSON after verification | 200 | Permanent non-matches — retrying changes nothing. Matches the plan's own correctly-reasoned example exactly. |
| Any other exception during processing (DB error, etc.) | 500 | Transient failures are what Svix's retry exists for. Reporting fake success here means this specific reply's outcome is gone forever, not delayed. |

**Rejected: the plan's literal blanket "never 500."** Correct for one case, silently
data-lossy for another — the exact kind of unstated, wrong generalization this
project's whole practice of verifying plan reference code (not just trusting it)
exists to catch, extended here to a stated *design principle* rather than a code
snippet.

## Decision 4 — First reply wins; a later reply on an already-answered thread is
logged, not silently overwritten

**Chosen:** `Outreach.replied_at` is set only if currently `NULL`. A second webhook
delivery for a thread that already has a recorded reply is logged (visible) and
otherwise a no-op — the *first* reply is the outcome event Task 5.3's cohort lift
analysis cares about ("did this person reply at all, and how fast"), and overwriting
`replied_at` with a later timestamp would corrupt that number for no benefit.

**Rejected: always overwrite with the latest reply's timestamp.** Would make detection
lag noisy across an ongoing conversation for no analytical benefit — the plan's own
Task 5.3 measures reply rate and (implicitly) time-to-first-reply, not "time of most
recent message."

## Decision 5 — `AGENTMAIL_WEBHOOK_SECRET` follows the established `os.environ.get(...)`
convention, not the legacy `scripts/config.py`

Matches every other credential this session has added (`ANTHROPIC_API_KEY` in
`extractor.py`) — `scripts/config.py`'s `AppConfig` is legacy, scanner-scoped, and has
a known unfixed bug (extra `.env` keys raise `ValidationError`, per Task 2.2's ledger
note) that every newer module has deliberately routed around.

## What this does NOT decide

- **Reply classification** (positive/negative/neutral). `reply_classification` stays
  `NULL` — this task only records *that* and *when* a reply happened, not its content.
  A future task can add sentiment/interest classification without touching this
  handler's core outcome-recording logic.
- **Rate limiting or dedup beyond Svix's own `svix-id`.** Svix's own retry semantics
  (same `svix-id` on a retried delivery) are assumed sufficient; this task adds no
  additional idempotency layer beyond the "first reply wins" rule in Decision 4, which
  already makes a duplicate delivery for the same reply harmless.

## Consequences

- `pyproject.toml` gains a new dependency: `svix`.
- This is the first route in this codebase that reads the raw request body directly
  (`await request.body()`) instead of a Pydantic request model — necessary because
  signature verification must run against the exact bytes AgentMail signed, before any
  parsing. A future webhook integration hits the same constraint.
- The three-tier status-code design (500 config / 401 security / 200 permanent-non-match
  / 500 transient-failure) is more branches than the plan's one-line rule, and that's
  the point — collapsing "the request is permanently unmatchable" and "we had a
  recoverable server hiccup" into one code path is exactly what silently lost the
  distinction that matters for reliably capturing outcome data.
