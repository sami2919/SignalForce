# ADR-0004: URL registry and source resolution

**Status:** Accepted
**Date:** 2026-08-04
**Scope:** Phase 1, Task 1.1 — `scripts/registry/`

---

## Context

The watch layer needs to fetch the same pages for the same accounts every day. There are two ways to get a URL for "Acme's careers page":

**Discovery** — search for it each time. A search problem: expensive, flaky, rate-limited, and repeated on every run.
**Retrieval** — look it up in a table. A bandwidth problem: cheap, parallel, cacheable.

Sajwal described Rippling's approach in the interview transcript (25:37):

> "we never do a Google search for the website. We go to the website... The key to that is knowing exactly where to go find the signal. It's like, oh, go to this careers page, and this is the URL for the careers page — versus saying like, go find the careers page and then do it. That's a different story."

Persisting resolution converts `O(accounts × runs)` searches into `O(accounts)` one-time resolution plus `O(accounts × runs)` cheap GETs. At 500 accounts × 4 sources × 365 days that is 2,000 resolutions instead of 730,000 searches.

## Decision 1 — Heuristic path probing, not search or LLM

**Chosen:** probe a fixed list of conventional paths per source type (`/careers`, `/jobs`, `/careers/`, …), first 200 wins.

**Rejected: search engine (SerpAPI, Google).** This is precisely the approach Sajwal named as the wrong one. It also costs per query, rate-limits, returns results that need disambiguation, and would have to be re-run whenever resolution is retried. The project already has `SERPAPI_KEY` wired up, which makes this the tempting path — that is exactly why it needs an explicit rejection.

**Rejected: LLM on the homepage.** High accuracy: fetch `/`, ask a model for the careers link. Roughly $0.001-0.002 per account and genuinely better recall than path probing. Rejected for v1 because it is not needed to prove the architecture, and because resolution accuracy is not the bottleneck — **soft-404 detection is** (Decision 3). Kept as the documented fallback ladder rung when path probing's recall is measured and found wanting. Do not add it before measuring.

**Rejected: sitemap.xml parsing.** More reliable than guessing when a sitemap exists and is current. Rejected as the *primary* method because coverage is inconsistent, sitemaps are frequently stale, and parsing one is more code than probing five paths. Reasonable as a second rung.

**Rejected: manual curation.** Highest quality, and correct at 50 accounts. It does not survive contact with a growing account list, and the point of this phase is a system that runs unattended.

**Accepted cost:** path probing will miss sites using non-conventional paths (`/join-us`, `/life-at-acme`, an ATS subdomain). Recall is unmeasured. **Task 1.1 must record resolution success rate per source type** so the decision to climb the fallback ladder is made on data rather than vibes.

## Decision 2 — GET, not HEAD

**Chosen:** `GET` with redirects followed.

**Rejected: HEAD.** Cheaper — no body transferred — and the obvious choice for existence checks. Rejected because HEAD is widely unreliable in practice: many servers return `405 Method Not Allowed`, CDNs and SPA hosts often answer 200 for every path regardless of routing, and some frameworks route HEAD differently from GET. Worse, the body is needed anyway for Decision 3's soft-404 check, so HEAD would mean fetching twice for any path that responds.

## Decision 3 — Soft-404 detection is mandatory ★

**This is the decision that protects the entire two-tier cost model, and it is not obvious.**

A large fraction of sites answer `200 OK` for paths that do not exist. Single-page apps serve the same shell for every route; many CMSes return a styled "not found" page with a 200; some hosts redirect unknown paths to the homepage. A naive "200 means resolved" check therefore produces registry rows pointing at **the homepage**.

That failure is silent and expensive:

```
  /careers soft-404s to the homepage
        │
        ▼
  account_sources row stores https://acme.com/careers  (looks correct)
        │
        ▼
  watch layer hashes the HOMEPAGE every day
        │
        ▼
  homepages carry rotating testimonials, blog teasers, "N customers" counters
        │
        ▼
  content hash changes almost every run
        │
        ▼
  change rate approaches 100% -> verify layer runs on everything
        │
        ▼
  the two-tier design collapses into a one-tier design, at ~13x the cost,
  and every emitted "signal" is homepage churn
```

Phase 1's exit criterion is a change rate in the 3-20% band. Undetected soft-404s are the single most likely cause of blowing it.

**Chosen detection:** fetch the homepage once per domain, hash it with the same normalizer the watch layer uses, and reject any candidate whose normalized content hash equals the homepage hash. Also reject when the final URL after redirects is the homepage.

This costs one extra fetch per account — amortized over every future run, and reusing `normalize_html` from Task 1.2 rather than inventing a second comparison.

**Rejected: trusting the status code.** The failure this ADR exists to prevent.
**Rejected: checking for the literal string "404" in the body.** Brittle, language-specific, and misses the homepage-shell case entirely, which is the common one.
**Rejected: content-length heuristics.** A real careers page and a homepage are often similar sizes. No signal.

**Accepted limitation:** a site whose careers page genuinely *is* its homepage will be rejected. That is the correct trade — a homepage is not a usable change-detection target regardless of what it is called.

## Decision 4 — Record the final URL after redirects

**Chosen:** follow redirects and store the resolved final URL, not the probed one.

Many `/careers` paths redirect to an ATS: `boards.greenhouse.io/acme`, `jobs.lever.co/acme`, `acme.ashbyhq.com`. That destination is strictly better as a registry entry — more stable, more structured, and far easier to parse in the verify layer than a marketing page. Storing the pre-redirect URL would mean paying for the redirect on every run forever and losing the information about which ATS the company uses.

**Watch for:** a redirect to the homepage is a soft-404 by another name. Decision 3's check must run against the final URL.

## Decision 5 — Respect robots.txt

**Chosen:** fetch and honour `robots.txt` per domain, using `urllib.robotparser` from the standard library. Cache the parsed rules for the duration of a resolution run.

**Rejected: ignoring it.** Sajwal described Rippling crawling at ~100 requests/second across rotating DNS providers, which is a different posture backed by a legal team and an existing commercial relationship with the accounts. This system is one person's project fetching a handful of public pages daily. Respecting robots.txt costs one cached fetch per domain and removes both the ethical question and the most common cause of a domain-level ban — and a ban produces empty results that look exactly like a quiet account, which is the silent-failure mode Phase 3 exists to detect. Not worth inviting at the infrastructure layer.

**Accepted cost:** some accounts will be unresolvable because robots.txt disallows the path. Record that as an explicit `resolution_method = "blocked_by_robots"` rather than a generic failure, so it is distinguishable from a page that does not exist.

## Decision 6 — Resolution must be re-runnable

**Chosen:** resolution is idempotent and can be re-triggered per account. A source that fails repeatedly is marked inactive **and enqueued for re-resolution**, never simply abandoned.

This closes the critical gap flagged in the plan's failure-mode table (#4). Without it: a company restructures its site, `/careers` starts 404ing, `consecutive_failures` hits 5, the source deactivates, and that account produces zero signals forever — with no error, no alert, and an appearance indistinguishable from a quiet account.

**Rejected: resolve once, never again.** Cheapest, and wrong. Sites change. A registry that cannot heal is a registry that decays to uselessness at whatever rate its accounts redesign their websites.

## What this does NOT decide

- The fallback ladder beyond path probing (sitemap, LLM) — gated on measured recall
- Per-source fetch cadence (all sources are probed every run for now; tiering by score is a later optimisation and Fly's scheduler only does daily anyway)
- How `account_sources` rows get created for new accounts (account ingestion is Phase 2)
- Whether to store historical resolutions for audit (no, for now — `resolved_at` plus `resolution_method` is enough)

## Consequences

- One extra homepage fetch per account at resolution time. Amortized to nothing.
- Some accounts will resolve zero sources. That is a legitimate outcome and must be recorded, not treated as an error — Phase 3's source-health metrics need to distinguish "no source exists" from "source broke."
- `resolution_method` becomes a diagnostic field worth querying: a sudden rise in `blocked_by_robots` or a fall in `heuristic` success indicates something changed upstream.
- Resolution recall is unmeasured until Task 1.1 reports it. Do not claim a number for it before then.

---

## Postscript — Decision 3 confirmed in the wild (2026-08-04)

Within minutes of pointing the normalizer at real traffic during Task 1.2:

```
jobs.lever.co/mistral  ->  HTTP 200
                       ->  "Sorry, we couldn't find anything here. The job
                            posting you're looking for might have closed, or
                            it has been removed. (404 error). Jobs powered by"
```

A 200 status carrying a 404 page. A resolver trusting status codes would have
written this into the registry and then hashed an error page daily forever,
emitting nothing and looking exactly like a quiet account.

The homepage-hash comparison in Decision 3 catches the SPA-shell variant of this.
This instance is a different shape — an ATS error page, not a homepage echo — so
Task 1.1 needs a second check: **reject a candidate whose normalized text matches
known not-found phrasing** ("couldn't find anything", "404 error", "no longer
available", "position has been filled"). Substring matching is brittle and
language-specific, which is why it is a supplement to the homepage-hash check
rather than a replacement for it.

Recording the specific measurement so the claim is grounded: 6 fetches of
`boards.greenhouse.io/anthropic` produced 2 distinct hashes (5:1 split), the delta
being an unresolved `tags.new` i18n key. That drove the confirm-on-change decision
now recorded against Task 1.3 in the plan.
