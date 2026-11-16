# First Principles: Know the Customer Better Than They Know Themselves

Working notes on Jordan Crawford's GTM-engineering principles, checked against the underlying
theory, and an honest audit of SignalForce against them. This is the bar the next phase of work is
held to.

## 1. The principle, reduced

A seller can know more about customer 1,001 than that customer knows about itself only because it
has studied customers 1–1,000 **systematically**: what each one *did*, what the problem *cost*, what
they used *before*, and what *set off* the switch. One customer cannot see the pattern from inside
its own case. The cross-case pattern is the information asymmetry, and it is the product a GTM
engineer actually builds.

Every serious school converges on the same move:

| School | What it contributes to the asymmetry |
|---|---|
| Blank, Customer Development | Every ICP statement is a hypothesis with a test and a kill criterion |
| Fitzpatrick, The Mom Test | Only past, specific behavior is data; opinions, compliments and feature requests are not |
| Moesta, JTBD switch interviews | **When**: the push event that reopened the status quo; anxiety and habit are why deals stall |
| Ulwick, ODI | **What to say**: the most underserved outcome (importance high, satisfaction low) |
| Christensen, JTBD | **Who**: a circumstance, not a demographic |
| Dunford | Start from the real alternative (often a spreadsheet, a hire, or nothing) |
| Moore | Compelling reason to buy, budget already exists, one beachhead that leads to adjacent pins |
| Dixon & Adamson, Challenger | Commercial insight: teach the buyer something true about their own business |
| Schwartz | Cold outbound reaches Unaware / Problem-Aware readers; naming their exact situation moves them up |

## 2. Crawford's operating rules

1. **Hierarchy of truth.** What the customer *did* > what the customer *said* > what our team
   *believes*. Weight evidence in that order everywhere.
2. **Start from who already bought**, especially the 10X customers getting outsized value. Contrast
   closed-won against closed-lost and non-customers; a trait common to both is not a signal.
3. **Targeting comes from the problem, not firmographics.** A Pain-Qualified Segment (PQS) is a
   group in a specific, observable, urgent situation the product resolves.
4. **The list is the message.** If you know *why* someone is on the list, you know what to say. The
   message re-describes the targeting with verifiable specifics (record numbers, dates, addresses).
5. **Permissionless Value Prop (PVP).** The message is useful to the recipient even if they never
   reply. True PVPs are rare; don't pretend a pitch is one.
6. **Work backwards.** Take ~50 known-good customers, find where evidence of *their problem* lives
   in public data, narrate your own manual research, abstract the rule, then **holdout-test**: rewind
   time and check whether the rule would have flagged them before they arrived.
7. **Enumerate, then disqualify.** Build the full universe from a complete source (registries,
   licensing boards, filings), then remove non-fits with evidence. Don't pre-filter away true positives.
8. **Cost per right answer**, not cost per lookup. Code and APIs first, paid enrichment next, agents
   for the long tail.
9. **Every claim has a source; every send has a gate.** The bar is a message you'd be proud to receive.

## 3. What the primary sources show (read 2026-11-16)

Read in full: Crawford's Revenue Brew interview (Aug 2026), his On the Edge "About" page, three
Blueprint-generated playbooks (LoanPro, Hint, Quorum), a third-party analysis by Allston Labs, and
the Hennink & Kaiser paper.

### Confirmed in Crawford's own words
- **Dossiers first, then rewind time.** "The very first place to begin is to create these things
  called account dossiers: everything in the CRM, everything [customers have] ever said, and
  everything they've ever done inside of your app." Then compare closed-lost, closed-won and "the
  customers that are just doing bangers", "rewind time to when they came to us", and holdout-test
  whether public data would have identified them. (Revenue Brew)
- **The inversion.** "Start from the customer's pain, find the data that proves the pain, let the
  data write the message. The list is the message." The same idea runs through his churn and health
  work: start from the outcome, work backwards to the predictive signals. (On the Edge)
- **PQS** mirrors "that prospect's situation back to them based on the situation your last
  customer's in." His example: a pool-cleaning company that just added its first technician, with
  Google reviews mentioning scheduling trouble.
- **PVP** is "a message that is independently valuable to the person receiving it." He calls it
  "a much better message" than a PQS.
- **AI's main job is exclusion.** "AI's job is more to figure out what accounts in your [TAM] you
  should never talk to." Score and sort the whole market, then spend human effort on the top 10%.
  This is enumerate-then-disqualify in his words.
- **Empathy is amplified, not replaced.** AI removes mundane work so sellers can get back on the
  phone and in person. Considered purchases still need a human relationship.
- **Where it works best (his own limit):** vertical SaaS, ideally in heavily regulated industries
  with rich public data (licenses per state, Google reviews, government records). Horizontal
  companies "have to pick a vertical."

### What the playbooks show about the craft
- **Hard data over soft signals.** Blueprint says it outright: *stop* "I see you're hiring
  compliance people" ("everyone sees this"), *start* with a government record number, date and
  address. **Job postings, the highest-weighted signal in several SignalForce configs, are the
  example Crawford uses of a soft signal.**
- **Anatomy of an 8.5–9.4/10 PQS (LoanPro):** two public datasets joined into one *compound*
  condition (FDIC consent order × 25%+ loan growth; merger filing × CFPB complaint rate), a
  *derived* metric the buyer probably hasn't computed (complaints per 1,000 loan accounts,
  efficiency ratio trend), about three sentences, no product mention, no meeting ask, and a closing
  diagnostic question ("What's the timeline on the consent order milestones?").
- **The judge is harsh, and that's the point.** Every message is scored /10 on three binary
  checks: *Hyper-Specific*, *Factually Grounded*, *Non-Obvious*. A simulated buyer then writes "I'm
  deleting this because…" and "What would make me reply". On the Hint playbook the PVPs scored
  3.8–6.2 and failed *Factually Grounded* for unverifiable stats ("heat map data", "industry average
  4.2 months"). The PQS section reads "No messages generated for this category." The system would
  rather ship nothing than ship an ungrounded claim.
- **Feasibility is flagged.** Quorum PVPs that need the prospect's internal throughput data are
  labelled as such instead of passed off as cold-sendable.
- **Caveat:** these are auto-generated sample playbooks (LoanPro's uses placeholder names such as
  "Regional Community Bank"). They show the method, not results.

### Corrections and claims to discount
- **Two PVP definitions are in circulation.** Allston Labs' "PVP gate" ("could I say this without
  reading the recipient's file?") is a *specificity* test, which is really the PQS bar. Crawford's
  definition is stricter: *independently valuable*. Use Crawford's.
- **FIND (Focus / Investigate / Narrate / Deploy)** is attributed to Crawford by Allston Labs only.
  I didn't find it in his own pages. Treat it as unverified attribution. The ordering discipline it
  describes (investigate before deploying) is sound either way.
- **"List quality drives 4–8x reply spread, copy 1.5–3x"** is an Allston Labs claim with no data
  or source. Allston sells a competing service. Directionally plausible, not evidence.
- **Allston's useful warnings:** "signals that are detectable but not painful" (technographics
  are the usual offender), and running a PQS once with no reply data fed back into signal weights.
  Both are real gaps in SignalForce (see §5).
- **Commercial context:** Crawford sells a $50/month newsletter and a $2,500/year program with
  tools and courses. Weigh his claims as practitioner opinion from a seller.
- **Saturation, verified:** Hennink & Kaiser, *Soc Sci Med* 292 (2022) 114523: 23 articles (17
  empirical, 6 modelling). Empirical studies saturated within **9–17 interviews or 4–8 focus
  groups**, "particularly those with relatively homogenous study populations and narrowly defined
  objectives". Multi-country, meta-theme and meaning-saturation studies needed more.

## 4. What the evidence does and does not support

- **Supported:** the principle itself, seller-centric messaging failing, narrow beachheads,
  problem-based targeting, holdout validation. These rest on decades of independent theory.
- **Practitioner anecdote, not evidence:** "1,000 interviews", "7 of 10 meetings", Crawford's reply
  rates. Self-reported, commercial source. Benchmark against our own holdout, never his numbers.
- **Interview counts:** saturation research (Guest et al. 2006; Hennink & Kaiser 2022, *Soc Sci Med*
  292:114523) finds themes in roughly 9–17 interviews per *homogeneous* segment. Plan ~12–20 per
  sub-segment; go further only for coverage, references or data access.
- **Stopping rule:** write predictions (trigger, cost, alternative, decision-maker, objection)
  before each interview; stop when they hold ~80%+ for three in a row with no new codes.
- **Hard limits:** Google/Yahoo spam complaints <0.3% (aim <0.1%); CAN-SPAM covers B2B; GDPR
  Art. 14 notice; *hiQ v. LinkedIn* ended in a $500K consent judgment and injunction (Dec 2022) on
  contract and tort claims, so public data is not permission.
- The Henry Ford "faster horse" quote is apocryphal. Don't cite it as Ford.

## 5. SignalForce audited against these principles

### Where it is already strong
- **Provenance.** Signal events carry source, scan run and evidence; the verify layer extracts and
  diffs the underlying fact before a signal exists. This is the evidence-linking foundation.
- **Statistical honesty.** Cohort lift refuses to report below n≥30 and the success-failure
  condition. Measured results are stated with what is *not* yet measured.
- **Guardrails.** Outbound request guard, budget gate, compliance and deliverability skills.
- **Signal Audit.** Auditing watchlist signals against uploaded CRM outcomes is the seed of the
  right validation loop.

### Where it violates first principles
1. **The ICP is the lowest tier of truth.** `gtm-context.md` "Why they buy" rows and the tier list
   are team belief. Nothing in the system derives the ICP from closed-won/lost/10X behavior.
2. **Signal weights are asserted, not learned.** The scoring rubric says "ArXiv paper published —
   strongest buying signal" (weight 3.0). No dataset shows that. Weights should be fit and
   holdout-tested against outcomes, per signal type, per segment.
3. **Signals measure topical activity, not pain.** "Repo uses vLLM" or "posted RL paper" shows the
   team works in the space. It can equally mean they've *solved* it in-house (status quo strong).
   A PQS signal is a *leading indicator of the problem*: turnover in a role, a req open 90+ days,
   a cost spike, a regulatory event, a public complaint.
4. **The holdout measures the wrong thing.** `scripts/measure/holdout.py` measures whether the
   watcher *detected* page changes (recall, lag). That's engineering correctness. Nothing measures
   **predictive validity**: would the rules have ranked known winners above known losers?
5. **Personalization tokens, not PQS/PVP.** `email-writer` says "reference their repo / paper".
   That's "I saw your thing" personalization. There's no step that re-describes the prospect's
   *situation and its cost*, and no PVP variant that delivers standalone value.
6. **Unsourced claims in our own instructions.** Three files assert "50% reply rates for
   resource-first vs 8–15% for demo asks" (attributed to vendor data in one place). That is exactly
   the anecdote-as-evidence pattern the principles reject, and it steers template choice.
7. **No customer-understanding layer.** No dossier/timeline per customer, no won/lost/10X
   analysis skill, no switch-interview or Mom-Test discovery skill, no worst-version-of-the-problem
   segment matrix, no hypothesis log with kill criteria.
8. **Pre-filter, not enumerate-then-disqualify.** Scanners start from keyword hits, so the universe
   is whatever matched the keywords. There's no complete-universe source per vertical.
9. **Status quo is invisible.** "In-house builds" is listed as the primary competitor, yet no
   signal, message or proof addresses the Four Forces (anxiety, habit) that keep in-house in place.
10. **Soft signals carry the most weight.** Hiring and library adoption are weighted 3.0 in the
    inference-infra config. Blueprint names job postings as *the* example of a soft signal anyone
    can see. Signals are also scored one at a time and stacked. Blueprint's best plays are
    *compound conditions* (A × B) that are rare and specific.
11. **No reply data flows back into weights.** The reply webhook and cohort analysis exist, but
    weights are static config. Nothing re-ranks a signal by what it produced.
12. **The vertical question is open.** Crawford's method works best where pain leaves hard
    public records (licences, enforcement actions, complaints). SignalForce's shipped examples are
    horizontal dev and AI infrastructure, where public data is mostly soft (repos, jobs, papers).
    The hard records there would be things like public incident and status-page history, CVEs
    against a stack, deprecations hitting a dependency, or cloud-cost disclosures. Either find
    those or pick a regulated vertical as the beachhead.

## 6. Direction

Invert the pipeline. Today: **keywords → signals → score → message**. First principles:
**customers who bought → why, then (behavior) → where that pain is visible publicly → rule →
holdout → universe → disqualify → message that re-describes the pain**. Scanners stay; they become
the sourcing layer for *validated* pain signals rather than the starting point. See `tasks/todo.md`.

## Sources checked

- Hennink & Kaiser (2022), *Soc Sci Med* 292:114523; Guest, Bunce & Johnson (2006), *Field Methods*
- hiQ v. LinkedIn consent judgment: [Proskauer](https://newmedialaw.proskauer.com/2022/12/08/hiq-and-linkedin-reach-proposed-settlement-in-landmark-scraping-case/), [ZwillGen](https://www.zwillgen.com/alternative-data/hiq-v-linkedin-wrapped-up-web-scraping-lessons-learned/)
- Read in full: [Revenue Brew interview](https://www.revenuebrew.com/stories/jordan-crawford-outbound-sales), [On the Edge: About](https://edge.blueprintgtm.com/about), Blueprint playbooks for [LoanPro](https://playbooks.blueprintgtm.com/loanpro-io), [Hint](https://playbooks.blueprintgtm.com/hint-com) and [Quorum](https://playbooks.blueprintgtm.com/quorumsoftware-com), [Allston Labs on Blueprint GTM](https://allstonlabs.com/library/frameworks/blueprint-gtm) (third party, competing vendor), [Hennink & Kaiser 2022 PDF](https://faisalmustafa.github.io/SLR-Book/resources/papers/hennink2022.pdf)
- Search results only: [Transaction Ep. 55](https://thetransactionpod.com/episodes/inverting-your-go-to-market-strategy-thinking-with-jordan-crawford-ep-55), [On the Edge](https://edge.blueprintgtm.com/about), [Pavilion profile](https://www.joinpavilion.com/blog/the-man-who-mastered-ai-gtm-meet-jordan-crawford), Blueprint public playbooks (LoanPro: FDIC/OCC/CFPB data; Hint: EPA violation records)
