# Magic / Loyalist GTM System: Design

Status: draft for approval. Date: 2026-11-16. Base: SignalForce.

## 1. Intent

Sami is meeting Magic's founding growth engineer, who is interested in SignalForce. Magic
(SoHo, NYC) sells **Loyalist**, an agentic guest CRM for restaurants, hotels and members clubs
(about $4M ARR, 1,000+ venues, field-led sales). Their Founding GTM Engineer posting asks for two
things:

1. **Programmatic outbound, end to end:** targeting, sequencing, reply handling, and the
   infrastructure behind it (sending domains, warmup, deliverability).
2. **Lead scoring and lifecycle:** score every account on signals such as new openings, chef/GM
   changes, and groups switching reservation or POS systems. Then build the lifecycle automation
   from first touch to closed, onboarded and expanding.

The deliverable is a working system built on SignalForce that demonstrates both jobs **on public
data only**, plus a learning loop that improves the system from its own results. It must also make
obvious how it would plug into Magic's real stack once internal data exists.

**North star:** find as many accounts as possible that are in a buying window, and get the best
results from them. Recall and outcome quality beat speed. Exhaustive verification of targeting
evidence is not a goal.

Background research: the "Customer 1,001" brief (in conversation; summarized in §3) and
`docs/first-principles-gtm.md`.

## 2. Goals, non-goals, anti-goals

**Goals**
- A complete account universe for NYC upscale, full-service, group-owned hospitality, built from
  public data and modeled as Person → Group → Concept → Venue → Outlet.
- Signals for openings, chef/GM changes and reservation/POS switches, each with evidence and a
  timestamp.
- A calibrated "in buying window" probability and a priority rank for every account.
- Contact discovery for top-ranked accounts.
- An outbound design that runs end to end: sending infrastructure, multi-channel sequences that
  mix automated and human steps, reply handling.
- A lifecycle model from Target to Expanding/At-risk, where one signal feed drives
  stage-dependent playbooks.
- A learning loop: evals, recall measurement, Bayesian weight updates, message bandits and
  proposal generation.

**Non-goals (for the demo)**
- Cities beyond NYC (the design must extend to them; the demo doesn't).
- A production CRM integration. Use an interface with one adapter, chosen once Magic's CRM is
  known.
- A mobile field-logging app. A minimal logging endpoint or form is enough.
- Real-time anything. A daily or weekly cadence is fine.

**Anti-goals (failure even if it technically works)**
- Sending real email to restaurants in Magic's name before Sami works there. The demo produces
  drafts and seed-inbox sends only.
- Burning the market: double-touching an account, ignoring an unsubscribe, or mass-blasting a
  universe of a few thousand venues.
- Quoting a wrong fact *to a prospect*, e.g. their own opening date or address.
- LinkedIn scraping or automated Instagram DMs (ToS / *hiQ* risk).
- A learning loop that changes prompts, rules or code on its own.
- Hard-filtering accounts out early on firmographics (kills recall).

## 3. Context (from research)

- **Best-fit customer:** chef/operator-led groups of 2–6 full-service venues, often alumni of
  Eleven Madison Park, Thomas Keller Restaurant Group, Momofuku or Major Food Group, opening their
  next venue. They run Resy, OpenTable, SevenRooms or Tock plus Toast, and keep guest knowledge in
  notes fields and managers' heads.
- **Worst version of the problem:** guest knowledge has to cross a boundary. New venue, manager
  turnover, or platform change (Tock venues moved onto Resy in Aug 2026; SevenRooms is owned by
  DoorDash).
- **Public labeled positives:** customer logos and quotes on loyalist.com and in press
  (MFG, EMP, The Noortwyck, Glendale, Grassfed, Happy Cooking, Le Bernardin, COTE, Atomix, etc.).
- **Units conflict:** "1,000+ venues" vs "hundreds of brands". Venue ≠ concept ≠ group.
  Duplicates and wrong location counts are called out in the job post.
- **Free signal sources (NYC):** NY SLA pending licenses (data.ny.gov), NYC DOHMH inspections
  (records dated 1/1/1900 = not yet inspected; CAMIS is a stable venue ID), community board liquor
  notices, building permits, press (Eater, Resy blog, Grub Street), venue websites (booking
  widgets, team pages, private-dining pages).
- **Tool facts checked 2026-11:**
  - Apollo-style databases are thin for independent restaurant owners.
  - Google Places is billed at the highest tier of any requested field.
  - Clay bills Data Credits plus Actions (since March 2026).
  - Smartlead has the fuller API, webhooks and per-inbox metrics; Instantly is simpler.
  - Nooks runs about $4–5K per seat per year and is SDR-volume oriented.
  - Technographic vendors crawl monthly and carry false positives.

## 4. Approaches considered

| | Approach | Trade-off | Verdict |
|---|---|---|---|
| A | **Clay at the center.** SignalForce pushes signals into Clay; Clay enriches, routes and hands off to the sender and CRM | Fastest and familiar to Magic's growth team. But flat tables fight the venue hierarchy, every step costs Actions, and the logic can't be versioned or tested | Rejected |
| B | **Code first.** SignalForce is the system of record, and every vendor is replaced by our own code | Maximum control and lowest unit cost. But it rebuilds commodity tools (sending, warmup, enrichment) and gives Magic a codebase to maintain | Rejected |
| **C** | **Hybrid.** SignalForce is the brain: entity graph, public-data signals, switch detection, window model, scores, evidence, learning loop. Commodity work goes to swappable vendors behind interfaces (Clay for long-tail enrichment, Smartlead for sending, Magic's CRM for pipeline) | Engineering goes where no vendor competes (restaurant public data and entity resolution), and the rest stays modest and replaceable | **Chosen by Sami** |

## 5. Decided by Sami

- Approach **C**.
- **Recall-first:** cast wide, rank, don't filter; link possible duplicates rather than merging.
- **Buying window** includes pre-opening (filing → opening) *and* chef/GM changes and
  reservation/POS switches at open venues.
- **Verification scope:** targeting may use unverified evidence. Only facts quoted to a prospect
  get a check.
- **Learning loop autonomy:** auto-apply numeric parameters within bounds; *propose* everything
  else (prompts, rules, new signals, promotions to code) for human approval after evals pass.
- **Tools:** use popular GTM tools where they beat building (see §7).

## 5a. Claude's calls (after builder review; Sami can override)

- **Unit of account.** The **Group** is the account for ranking, sequencing, backtest and
  lifecycle; a single-venue operator is a group of one. The **Venue** is the unit for signals, the
  universe and location counts. A group's score aggregates its venues' signals (noisy-OR across
  venues). The graph lives in **new tables beside** the existing `Account` model. `Account` is not
  re-keyed, because domains are missing or shared across venues.
- **Universe definition (recall-first).** The candidate universe is every NYC venue with an
  on-premise liquor license (SLA) or a DOHMH full-service restaurant record, including single
  venues. Fit is *scored*, never filtered. The recall-audit denominator is new openings that carry
  an on-premise liquor license. That rule is deterministic, broad and checkable.
- **Customer dates for the backtest.** A customer's "became customer" date is the earliest public
  evidence of the relationship: press, a dated quote, or the logo's first Wayback Machine
  appearance on loyalist.com. This is an upper bound. Where no date exists, the account counts
  only in the static ranking test, not the lead-time test. The meeting should present the
  lead-time result as indicative.
- **Learning-loop build scope.** Fully built and run on real public data: recall audit,
  window-curve refit, miss investigation. Built as tested modules exercised on simulated outcomes:
  Beta-binomial updates, Thompson-sampling allocator, holdout and exploration assignment. Built as
  an interface plus one working proposer: the proposal engine, whose proposer is "missed opening →
  which source would have caught it".
- **Deployment.** An isolated database and tenant for the demo, not the shared multi-tenant
  deployment, so schema work is free and restaurant contact data isn't co-located with other
  tenants.
- **Angles and judge.** One angle per signal family: opening, people change, platform switch,
  alumni/relationship. The judge uses Blueprint's checks (hyper-specific, factually grounded
  against our evidence, non-obvious), scored out of 10 with a simulated-owner critique, plus the
  voice rules in the gtm-context file.
- **Research brief.** The "Customer 1,001" brief gets committed at
  `docs/research/magic-customer-1001-brief.md` before planning, so the builder has it.

## 6. Architecture

```
public sources ──► ingest (deterministic) ──► raw records + evidence
                                   │
                                   ▼
             entity resolution (rules → Splink → agent on residue)
                                   │
                                   ▼
        graph: Person / Group / Concept / Venue / Outlet  (+ "possibly same" links)
                                   │
           signals ◄── watch layer (widget/POS diff), LLM extractors (press, team pages)
                                   │
                                   ▼
     window model + noisy-OR scoring  ──►  ranked accounts with traces
                                   │
          contact waterfall (cheap → Clay → agent)  ──► contacts
                                   │
     sequencer (state machine: auto + human steps) ──► Smartlead / tasks / CRM
                                   │
          replies (webhook → classifier) ──► routing ──► lifecycle stage
                                   │
                learning loop (evals, recall audit, Bayesian updates, bandit, proposals)
```

### 6.1 Which kind of code for which job

**Promotion ladder:** agents discover → repeated patterns become a single LLM call → fully
understood patterns become deterministic code. The loop proposes promotions; a human approves.

| Component | Method | Why |
|---|---|---|
| Ingest SLA, DOHMH, permits, CB notices | Deterministic | Structured; one parser per source |
| Booking widget / POS detection | Deterministic (existing watch layer: hash, confirm, extract, diff) | Known script domains; we need *when* a switch happened, which monthly vendor crawls can't give |
| Exact-key joins (CAMIS, license ID, Place ID, domain) | Deterministic | Stable keys |
| Fuzzy matching (LLC ↔ trading name ↔ Place) | Probabilistic (Splink) | Calibrated match probabilities |
| Filing-to-opening timing | Probabilistic (survival curve) | §6.4 |
| Window probability and score | Probabilistic (noisy-OR with timing decay) | Recall-friendly, and each contribution stays explainable |
| Press → {concept, people, opening date, group, address} | Single LLM call, fixed schema | Unstructured, high volume |
| Team/about page → owner, chef, GM, roles | Single LLM call, fixed schema | Same |
| Reply classification | Single LLM call, fixed category set | Bounded |
| LLC → group ownership when rules and Splink fail | Agent, budgeted per account | A different path per case |
| Contact for a top-ranked account when the waterfall fails | Agent, budgeted | The long tail |
| New signal-source discovery; cities without open data | Agent, results proposed for promotion | Discovery |
| Pre-walk-in briefing for the top ~50 accounts | Agent | High value per account |
| Drafting messages | LLM + human approval | Quality where a person reads it |
| Suppression, unsubscribes, send caps, sequence state, contact de-dup across sequences, CRM stage writes | **Deterministic, always** | Errors can't be undone |

### 6.2 Data model

- **Nodes:** `Person`, `Group` (operating company), `Concept` (brand), `Venue` (physical
  location, keyed by CAMIS / Place ID / address), `Outlet` (bar, private dining room or rooftop
  inside a venue or hotel).
- **Edges:** `owns`, `operates`, `employs(role, since)`, `alumni_of`, `invested_in`, `referred`,
  `attended_event`, `possibly_same(p)`.
- **Records:** `SourceRecord` (raw row plus provenance), `Signal` (type, entity, observed_at,
  source, evidence_ref, extractor version), `Score` (with trace), `Contact`, `Touch`
  (channel, human or auto, outcome), `Reply`, `LifecycleEvent`.
- **Rule:** a location count comes from reconciling at least two sources. Disagreements are flagged.
- Pydantic `frozen=True` models, following repo conventions. Persist in Postgres, extending
  `scripts/storage`.

### 6.3 Signals

| Family | Signal | Source | Meaning at a prospect | Meaning at a customer |
|---|---|---|---|---|
| Opening | SLA pending original, CB notice, DOHMH not-yet-inspected, permit, "opening soon" press | Open data, CB sites, press | Trigger | Expansion |
| People | New chef, GM, marketing or guest-relations hire; departure | Press, team pages (diffed), Culinary Agents | New decision-maker | Champion risk |
| Platform | Reservation widget change (e.g. Tock→Resy, OpenTable→SevenRooms), POS link change | Watch layer on venue sites | Switch moment | Integration risk; CX alert |
| Relationship | Alumni edge to a customer, investor edge, customer referral | Press, team pages, investor lists | Priority boost | n/a |
| Seasonal | Private-dining page, holiday events push | Venue sites | Angle and timing | Journey suggestion |

### 6.4 Buying-window model (needs no Magic data)

- Join SLA filing date to the DOHMH *first inspection* date at the same resolved venue. The first
  inspection stands in for the opening date.
- Fit an empirical filing-to-opening distribution, stratified by license class and borough. Use a
  Kaplan–Meier style curve; filings that haven't opened yet are censored.
- For each live filing, output P(opens within t) and a recommended outreach window. Default
  outreach window: 30–120 days before the estimated opening through 90 days after. The loop
  refines this.
- For people and platform signals, a window decays from the observation date. Half-lives start as
  priors and are updated by the loop.

### 6.5 Scoring

- `P(in window) = 1 − Π(1 − p_i · decay_i)` over an account's signals (noisy-OR). `p_i` is the
  per-signal-type precision prior.
- `priority = P(in window) × Fit × Relationship`.
  - Fit: venue count, full-service, price tier, wine program, private dining, premium booking
    platform tier.
  - Relationship: alumni, investor or referral edges.
- Reuse the `scripts/scoring/engine.py` trace pattern, so every score can be replayed and any
  signal zeroed out to see its effect.
- No hard filters except true disqualifiers (closed venue, existing customer for the prospect
  playbook, suppressed).
- **Backtest:** rewind time on the public Loyalist customer list. Did their filings, press or
  people signals precede them becoming customers? Report how well the score ranks these known
  positives (AUC / precision@k against unlabeled venues), not "accuracy". Unlabeled venues are not
  proven negatives.

### 6.6 Contacts

- **Waterfall:** team page and press (owner names) → email-pattern lookup (Prospeo/Hunter) →
  Clay waterfall for the residue → verification (ZeroBounce) → agent for top-ranked accounts still
  unresolved.
- Also capture the venue phone and Instagram handle as channels. Track cost per verified contact.
- Apollo only after a 50-record accuracy test on this vertical.

### 6.7 Outbound infrastructure

- **Sender:** Smartlead, called by API, with webhooks back into SignalForce, behind a `Sender`
  interface.
- **Domains:** 3 secondary domains × 2 inboxes, mixed Google Workspace and Microsoft 365, ≤30
  sends per inbox per day at full warmup. SPF, DKIM and DMARC with alignment; one-click
  unsubscribe (RFC 8058); physical address.
- **Warmup:** built-in warmup plus a slow ramp of real sends over about 3–4 weeks.
- **Monitoring:** Google Postmaster Tools, DMARC aggregate reports, seed-inbox placement tests.
- **Hard stops in the outbound guard:** spam complaint rate >0.1%, bounce rate >2%, any domain on
  a blocklist.
- **Global suppression:** unsubscribes and hard no's propagate to all tools within 48h.
- **Demo:** infrastructure configured and documented; sends only to seed inboxes.

### 6.8 Sequencing

- A state machine per (account, contact) with typed steps: `email` (auto), `call_task`,
  `instagram_dm_task`, `walk_in_task`, `dinner_invite`, `event_invite` (all human).
- Timing rules: calls and walk-ins only in the off-service window (default 2:00–4:30pm local; the
  loop can tune it).
- One active sequence per group at a time (deterministic de-dup across venues of the same group).
- Walk-in tasks are batched into neighborhood routes.
- **Dialer:** a plain dialer (Aircall/Twilio) behind a `Dialer` interface. Nooks only if call
  volume ever justifies it.

### 6.9 Reply handling

- Smartlead webhook → fixed-category classifier: positive, curious, referral ("talk to my GM"),
  wrong timing, OOO, unsubscribe, hard no.
- **Routing:**
  - positive → booking link (sales meeting scheduler);
  - referral → new contact plus a fresh sequence;
  - timing → reminder at the stated date;
  - unsubscribe / hard no → suppression.
- A human approves outgoing reply drafts in the demo and early operation.

### 6.10 Lifecycle

- **Stages:** Target → Engaged → Meeting → Opportunity → Won → Onboarding → Live → Expanding /
  At-risk / Churned.
- **One signal feed, stage-specific playbooks** (§6.3 table).
  - At Won, a context handoff record carries the account's evidence-linked history and sales
    notes to CX.
  - At Live, opening signals at the group create expansion tasks; people and platform signals
    create at-risk alerts.
- CRM behind a `CRM` interface, with one adapter. Attio or HubSpot, whichever Magic runs; demo with
  a local adapter if unknown.

### 6.11 Learning loop

**Fast to slow feedback ladder:** offline evals (instant) → human edit/reject reason codes (hours)
→ positive-reply rate and reply quality (days) → meetings and converting walk-ins (weeks) → won,
onboarded, expanded (months; this ground truth overrides everything faster).

**Recall audit (public ground truth):** every week, each newly first-inspected NYC venue that
fits the universe is checked:
- Was it flagged before it opened, and with how many days of lead time?
- Misses get a cheap investigation: which source would have caught it.

Recall and median lead time are the loop's headline metrics.

**Auto-applied (numbers only, within bounds):**
- Per-signal precision priors and half-lives: Beta-binomial updates, pooled across related
  segments; minimum evidence before any change; maximum change per update.
- Window-model curves, refit weekly.
- Message-angle allocation: Thompson sampling over angles. The objective is *qualified* replies;
  spam complaints and unsubscribes are penalties.
- Off-service calling window, send timing.
- Every change is versioned with before/after values and can be rolled back.

**Proposed (human approves after evals pass):**
- Prompt changes (extractors, drafter, judge, classifier) from clustered failures and human edits.
- New signals or sources from the win/loss/miss hypothesis agent, backtested before proposal.
- Promotions down the ladder (agent pattern → LLM call → deterministic rule).
- Rule changes (disqualifiers, sequencing rules).

**Never touched by the loop:** suppression, unsubscribe handling, send caps, compliance rules,
guard thresholds.

**Bias controls:**
- A random holdout of eligible accounts receives no outreach.
- An exploration budget of 10–15% of touches goes to lower-ranked accounts.
- The objective is qualified meetings, not raw replies.

**Evals:** in-repo eval runner. Versioned golden sets per LLM component, built from human
corrections. Each component has an accuracy floor it must hold to ship. Optional self-hosted
Langfuse for agent trace browsing.

### 6.12 Tools summary

| Need | Tool | Alternative and why not |
|---|---|---|
| Open data | Socrata APIs (direct) | n/a |
| Web change / widget detection | SignalForce watch layer | BuiltWith/technologychecker: monthly, can't time switches |
| Semantic web search (press, chef moves) | Exa, budgeted | RSS alone misses the long tail; RSS used too |
| Crawling / page fetch | Existing fetcher, Firecrawl for JS-heavy sites | n/a |
| Canonical location key | Google Places (field-masked, cached) | n/a |
| Entity resolution | Rules + Splink | All-LLM: confident and wrong |
| Enrichment waterfall | Prospeo/Hunter → Clay (residue) → ZeroBounce | Apollo-first: thin coverage for owners |
| Sending + warmup | Smartlead | Instantly: thinner API |
| Dialer | Aircall/Twilio | Nooks: cost and volume mismatch |
| Scheduler | Cal.com or Magic's existing tool | n/a |
| CRM | Magic's CRM via adapter (Attio/HubSpot) | n/a |
| Orchestration | Python workers (existing Fly setup); n8n only for CRM glue | Logic in n8n is hard to test |
| LLM evals / traces | In-repo runner; optional Langfuse | Braintrust/LangSmith: fine, not needed |

## 7. Constraints

- Public data only until Magic shares internal data. Respect robots.txt and ToS. No LinkedIn
  scraping, no automated IG DMs.
- CAN-SPAM, Google/Yahoo/Microsoft bulk-sender rules. GDPR/PECR if UK/EU venues are ever in scope.
- Repo conventions: Pydantic frozen models, type hints, ruff, TDD with ≥80% coverage, mocked HTTP
  in tests, every script importable and runnable as a CLI, ADRs for decisions.
- Cost discipline: cheapest reliable method first; agents run only on residue and the top N, with
  per-account budgets.

## 8. Demo scope (for the meeting)

1. NYC SLA + DOHMH ingest and the resolved Group/Venue graph, with location-count reconciliation.
2. Filing-to-opening window curve from public data.
3. Booking-widget crawl of resolved venues, with platform distribution and any detected switches.
4. Backtest of the score against public Loyalist customers.
5. Top ~25 ranked accounts, each with evidence trace and window estimate.
6. Contacts for the top 10, and 3 drafted messages per angle through the judge (no sends).
7. Recall audit run on the last N weeks of openings.
8. Deliverability, sequencing, reply-handling and lifecycle designs documented, with the
   sequencer and classifier running against fixtures and seed inboxes.

## 9. Left to the builder

- Package layout inside SignalForce. **Claude's call:** new packages under `scripts/` (e.g.
  `scripts/hospitality/`) plus a new example config. Reuse existing storage, watch, scoring and
  outreach modules rather than forking the repo.
- Exact dataset IDs and field mappings, verified on the portals at build time.
- Splink blocking rules and thresholds; Beta prior parameters; bandit details.
- Which LLM model per component (cheapest that passes its eval floor).
- Demo presentation format.

## 10. Questions for the Magic meeting

1. What is the canonical unit of account (venue, concept, group, contract)?
2. Which CRM, sender, scheduler and enrichment tools are in use today?
3. Of recent wins, what share started from a walk-in, dinner, event, referral or inbound, and how
   many involved an opening within 6 months?
4. What does a lost deal look like (SevenRooms built-in CRM, do nothing, price)?
5. How much revenue comes from new venues inside existing groups?
6. Is any outbound email running now, and from which domains?
