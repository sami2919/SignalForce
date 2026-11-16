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
- Event intelligence for the field team: rank conferences, festivals and dinners by expected
  qualified meetings per dollar, then build likely-attendee meeting lists for the chosen ones
  (§6.12).
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

### 6.3a Customer detection: the Loyalist embed fingerprint

**Finding (research, 2026-11-16).** Loyalist customer websites carry Loyalist embeds:
`api.eatloyalist.com/signup/form` (guest signup/waitlist forms) and `agent.eatloyalist.com`
(agents). A plain fetch found them on 12 customer sites: Hawthorne & Wood, Bluebird, Próximo,
Fork, High Street, Los Félix, Krüs, Füm, Rabbit Ears, starr-restaurants.com and others. Grassfed's
Rabbit Ears site is essentially a Loyalist waitlist form.

**Mechanism.**
- Add `eatloyalist.com` hosts to the widget-detection fingerprint list in the watch layer. Detection
  is deterministic and runs in the same crawl as booking-widget and POS detection.
- Detection runs on every crawled venue site. The Firecrawl fallback applies when the embed is
  injected by JavaScript (§6.13).
- Each detection is stored as a `Signal(type=loyalist_embed)` with the evidence snippet and
  `observed_at`.
- An embed that *appears* on a site we already crawl is dated to the crawl where it first showed
  up. An embed that *disappears* is a churn signal.

**Uses.**
1. **Labeled positives at scale.** Detected venues join the public logo list as customer labels.
   That replaces ~25 marketing-selected logos with every customer whose site carries an embed. The
   backtest (§6.5) and the lookalike seeds for Exa (§6.13) both use this larger set.
2. **Automatic customer flag.** A detected venue, and its group via the graph, leaves prospect
   playbooks and enters customer playbooks (§6.10): expansion on opening signals, at-risk on
   people or platform signals. This prevents cold-emailing an existing customer.
3. **Dated new-customer feed for the learning loop.** New embeds on the weekly crawl are dated
   labels. Without Magic's CRM, they let the loop update signal precision priors (§6.11): which
   signals appeared in the months before an embed showed up.
4. **Penetration map.** Customers per neighborhood or city against the universe size, used for
   territory planning and to pick where peer social proof is strongest.

**Limits.**
- *Undercounts.* Customers who don't embed a Loyalist form on their site are invisible to this
  method, so it is a lower bound. Logos, press and Magic's CRM fill the gap later.
- *First-seen date ≠ signing date.* The first crawl that sees an embed is an upper bound on the
  start date, and only for sites crawled before that point. Historical sites can't be dated
  because web.archive.org is unreachable in this session.
- *Sensitive output.* A list of Magic's customers derived from their own embeds is competitively
  sensitive. Use it only inside the system (labels, suppression, playbooks). Never export or
  display it outside an authenticated view.

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
- **Backtest:** labels are the public customer list plus every venue with a detected Loyalist
  embed (§6.3a). Rewind time on these. Did their filings, press or
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

### 6.12 Events: ranking and meeting lists

**Why.** Magic sells in person. Picking the right rooms and arriving with a list of who to meet
is outbound for a field team. Sami's decision: **rank events first, then build meeting lists**
for the chosen events.

**Hypothesis to test.** Large trade shows (e.g. the NRA Show, May 22–25, 2027, Chicago) skew
toward chains and suppliers. The ICP (chef-led groups of 2–6 upscale venues) is denser at:
- curated hospitality conferences (The Welcome Conference, StarChefs);
- James Beard events and award ceremonies;
- food and wine festivals where chefs cook (NYC Wine & Food Festival etc.);
- local operator groups (NYC Hospitality Alliance).

Festival chef lineups and award lists are public, so they work as near-complete attendee lists for
chefs.

**Approaches.**
1. **Public sources (chosen as the core).** Events go in a registry; the attendee data comes from
   public pages.
2. **Purchased event-intelligence data (add-on).** Vendors such as Luminik sell attendee data for
   events like the NRA Show. Allowed only after it passes a 50-record accuracy test on this
   vertical and its provenance is acceptable.
3. **Sponsorship with badge scanning.** Real opt-in lists, but costly and mostly post-event.
   Magic's business decision; Part 1's ranking supplies the numbers for it.

**Data model additions.**
- `Event`: name, series, dates, city, type (trade show, curated conference, festival, awards,
  local meetup, Magic-hosted dinner), cost estimate, source.
- `EventAppearance`: links Person → Event with a role (speaker, panelist, festival chef, award
  nominee, exhibitor staff, sponsor, past-recap appearance), a source and an attendance
  probability.
- This builds on the `attended_event` edge already in the graph.

**Method split.**

| Job | Method |
|---|---|
| Discovering events (new series, local meetups, festivals) | Agent + Exa, budgeted; results proposed for the registry |
| Recurring event calendar (annual series, expected dates) | Deterministic registry, re-checked each cycle |
| Speaker / lineup / exhibitor / award pages → appearances | Single LLM call, fixed schema |
| Matching appearances to Person/Group | Same entity resolution as §6.1 (rules → Splink → agent on residue) |
| Attendance probability by role | Probabilistic; priors by role, updated from logged attendance |
| Event score, list ranking | Probabilistic (formulas below) |
| Pre-event outreach scheduling, suppression, de-dup with other sequences | Deterministic |

**Part 1: event ranking.**
```
event_value = Σ_people P(attend) × account_priority × P(meeting | event_type)
event_score = event_value / (ticket + travel + sponsorship cost)
```
- `account_priority` comes from §6.5, so people at in-window groups count more.
- `P(attend)` priors by role. Speaker, festival chef and award nominee at the awards event start
  near-certain; exhibitor staff are likely; a past-recap appearance only is lower.
- `P(meeting | event_type)` starts as a prior. After each event, logged meetings update it. This
  is a numeric parameter, so the loop **auto-applies** it (§6.11). The output answers the job
  post's "what each channel and event produced".

**Part 2: meeting lists for chosen events.**
- Rank likely attendees by `P(attend) × account_priority × in-window now`.
- Customers who are attending are flagged as warm intros or co-hosts, not targets.
- Pre-event sequence 2–3 weeks out ("are you at X? 15 minutes there?") through §6.8. It respects
  one-active-sequence-per-group and global suppression.
- At-event: reps get a mobile-friendly list with each person's evidence and a one-tap touch log.
  Post-event: logged touches feed the lifecycle and the loop.
- The same ranking produces invite lists for Magic-hosted dinners.

**Guardrails.**
- No scraping of gated event apps (Swapcard, Whova, Brella) or LinkedIn event attendee lists.
- Ignore "attendee list for sale" offers; they are a known scam pattern.
- Purchased lists only via approach 2's test.

**Demo scope addition.** NYC-relevant event registry for the next 12 months. Ranked events
with their scores. A likely-attendee meeting list for the top event, matched to the graph.

### 6.13 Firecrawl, Exa and Clay: where each fits

Rule: cheap deterministic code first; these tools only where code can't reach. Every result
they return is a *candidate*. It is resolved into the graph and scored like any other signal,
never trusted as-is.

**Firecrawl: fetch and extract (reuses `scripts/firecrawl_client.py` and the existing Firecrawl
scanners).**
- *Widget detection fallback:* the existing fetcher runs first. If it finds no booking widget,
  a Firecrawl rendered scrape runs, because Resy, SevenRooms and Tock widgets are often injected
  by JavaScript. Credits are only spent on pages that need rendering.
- *Page discovery:* the map endpoint locates team, private-dining, press and locations pages.
- *Schema extraction:* team pages → {owner, chef, GM, roles}; locations pages → {venues,
  addresses}; festival, speaker and award pages → {person, restaurant, group, role}. This is the
  "single LLM call, fixed schema" tier from §6.1.
- *Not used for:* change detection. The SignalForce watch layer owns history and diffs.
- Respect robots.txt (the existing resolver rule applies).

**Exa: discovery and lookalikes.**
- *Lookalikes from customers:* `findSimilar` seeded with each public Loyalist customer's site and
  press coverage (e.g. the Resy write-up of Oriana) returns similar groups and articles. They
  become candidate accounts tagged `source=lookalike(seed)`. This applies working backwards from
  customers directly.
- *Press signals:* date-filtered searches for openings, second locations and chef/GM moves,
  covering what RSS misses.
- *Event discovery:* festival lineups, award lists, speaker pages (§6.12).
- *Websets:* optional, for spot-checking universe coverage. It is a separate paid plan, so it
  isn't in the demo path.

**Clay (Claygent + enrichment waterfall): long tail, contacts, and integration with Magic's
stack.**
- *Where:* only on residue and the top N. Entity questions rules and Splink couldn't settle
  ("who owns this LLC", "who is the GM"), and contacts the cheap waterfall step (team page →
  pattern lookup) couldn't find. Clay bills every step, so it never runs universe-wide.
- *How:* SignalForce pushes scored accounts with evidence into a Clay table (webhook/API).
  Claygent and Clay's email waterfall fill the contact fields, and the results sync back to
  SignalForce.
- *Why Clay and not only our own agent:* Magic's growth team likely works in Clay (the GTM job
  was posted in Clay's community), and Clay's data providers add contact coverage. Our own
  Claude agent stays for entity questions, where it is cheaper per run and versioned in the repo.

**Demo budget on free credits (limits to be confirmed at key setup).**

| Step | Tool | Volume |
|---|---|---|
| Lookalikes of ~20 Loyalist customers | Exa findSimilar | ~20 calls |
| Opening / chef-move press, last 90 days | Exa search | ~50 searches |
| Widget check where the cheap fetcher found nothing | Firecrawl scrape | ~100–200 pages |
| Team / event pages → fields | Firecrawl extract | ~50 pages |
| Ownership + contacts for the top 25 | Claygent + waterfall | 25 rows |

### 6.14 Tools summary

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

## 7a. Differentiation: why this beats prompting Claude directly

Sami's requirement: the system must be clearly better than asking Claude "find companies with
these signals". Claude runs *inside* the system as extractor, judge and long-tail agent. The
system adds what a single prompt can't have:

| Prompting Claude | This system |
|---|---|
| Returns what is findable and salient (mostly published press) | Enumerates the complete universe from government records |
| Can't say what it missed | Measures recall against public ground truth (DOHMH first inspections) and lead time in days |
| Sees the current web only | Keeps history and diffs; dates platform switches (live crawl + Wayback Machine) |
| Lags press | Catches filings before press, with a calibrated window from the filing→opening curve |
| Duplicates, wrong location counts | One resolved Group/Venue graph with alumni, investor and customer edges |
| Non-reproducible ranking | Deterministic, traced scores |
| Answers | Acts: sequences, suppression, reply routing, lifecycle, event lists |
| Doesn't learn | Updates numbers from outcomes; proposes its own improvements |

**Head-to-head benchmark (a demo deliverable).** Fix a cutoff date. Ground truth is the
on-premise-licensed NYC venues first inspected in the N weeks after the cutoff. Compare:
- a plain Claude run (with web search, documented prompt, run 3× to show variance), asked to
  find NYC restaurant groups opening a new venue, as of the cutoff;
- SignalForce's ranked list as of the cutoff.

Report hits, median days of lead time, duplicates/errors, and run-to-run variance.

**Fairness note.** Running Claude today about a past cutoff leaks hindsight: it can find press
published after the cutoff. That biases the test *in Claude's favor*, so a SignalForce win is
conservative; state this in the demo. SignalForce must use only data dated before the cutoff
(original application dates from the active/inactive license datasets, not today's pending
snapshot, since filings leave "pending" once licensed). After the meeting, run a forward test
(both lists frozen today, scored as openings happen) as the clean version.

## 8. Demo scope (for the meeting)

**Constraint (Sami, 2026-11-16):** the meeting is in 2–3 days, and tools run on free trial or
signup credits only. Build order is priority order; if time runs out, cut from the bottom.

**Real, on real data (priority order):**
1. SLA + DOHMH ingest and a simplified graph: exact keys + fuzzy-name rules. Splink is deferred.
2. Filing→opening window curve.
3. Scores with traces for the universe.
4. Recall audit + the head-to-head benchmark against plain Claude (§7a).
5. Widget crawl of a few hundred top venues, including the Loyalist embed fingerprint (§6.3a),
   to grow the customer labels and flag existing customers. Wayback Machine history to date past
   switches only if web.archive.org becomes reachable.
6. Backtest against public Loyalist customers.
7. Top-10 contacts via free-tier enrichment; 3 drafts per angle through the judge.
8. Event registry + one ranked meeting list (§6.12).

**Shown but simulated:** sending infrastructure (documented; warmup can't finish in time);
sequencer and reply classifier on fixtures; local CRM adapter; Bayesian updates and bandit on
simulated outcomes.

### Original full demo scope (post-meeting target)

1. NYC SLA + DOHMH ingest and the resolved Group/Venue graph, with location-count reconciliation.
2. Filing-to-opening window curve from public data.
3. Booking-widget crawl of resolved venues, with platform distribution and any detected switches.
4. Backtest of the score against public Loyalist customers.
5. Top ~25 ranked accounts, each with evidence trace and window estimate.
6. Contacts for the top 10, and 3 drafted messages per angle through the judge (no sends).
7. Recall audit run on the last N weeks of openings.
8. Event registry, ranked events, and a likely-attendee meeting list for the top event (§6.12).
9. Deliverability, sequencing, reply-handling and lifecycle designs documented, with the
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
