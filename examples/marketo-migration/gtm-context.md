# GTM Context: Conversion (Marketo Migration ICP)

Shared context loaded by all SignalForce skills. Reference this file for company
positioning, ICP definitions, messaging guidelines, and qualification criteria.

---

## Company

| Field | Details |
|---|---|
| Name | Conversion |
| Category | AI-native lifecycle campaign orchestration |
| Stage | Series A ($28M, 2025) |
| Differentiation | Warehouse-native — joins Snowflake/BigQuery traits at send time, not batch-sync |
| Key wins | Teams migrating off Marketo, HubSpot Enterprise, Pardot |
| ICP size | 50–500 employees, B2B SaaS, Salesforce + data warehouse |

---

## Product

**Core offering:** AI-native campaign orchestration that reads directly from the customer's
data warehouse (Snowflake, BigQuery, Databricks) and Salesforce — no reverse ETL middleware,
no batch-sync lag, no custom object constraints.

**Why teams migrate from Marketo/HubSpot:**
- **Warehouse data gap** — Marketo/HubSpot require reverse ETL (Hightouch, Census) to
  activate product usage signals; Conversion joins natively at send time
- **Custom object constraints** — Legacy MAPs limit trigger flexibility; Conversion exposes
  the full Salesforce/warehouse object graph
- **Salesforce sync failures** — HubSpot's bidirectional sync breaks at scale; Conversion
  is Salesforce-native
- **Personalization ceiling** — Static CRM data + slow builders; Conversion embeds AI agents
  with real-time warehouse traits per touch

**Conversion campaign anatomy:**
- Segment: Salesforce SOQL filters + warehouse trait joins (e.g., `product.last_login_at`,
  `account.MRR`, `segment.cohort`)
- Touches: sequence of messages with channel, timing, and agent assignment
- Agent roles: three non-overlapping — execution (owns sends), QA (owns suppression),
  optimization (owns variant selection)
- Triggers: event-based re-entry, optimization thresholds, pipeline projection scenarios

---

## ICP Tiers (Priority Order)

### Tier 1: Warehouse-Ready + Active Migration Signal

| Field | Details |
|---|---|
| Target | Mid-market B2B SaaS, 50–500 employees, Series A–C |
| Tech stack | Snowflake or BigQuery + Salesforce |
| Pain signal | Using Hightouch/Census to feed Marketo/HubSpot from warehouse |
| Budget signal | Series A+ funding, 2+ MOPs engineers on the team |
| Why now | They've already invested in the warehouse; the MAP is now the bottleneck |
| Deal size | $30K–$150K ARR |

### Tier 2: HubSpot Enterprise Ceiling Hitter

| Field | Details |
|---|---|
| Target | B2B SaaS, 30–300 employees, post-Series A |
| Pain signal | Hired a "Marketing Analytics Engineer" or "Marketing Data Engineer" |
| Why it matters | They're papering over HubSpot's limitations with SQL — that's the tell |
| Budget signal | Series A+, marketing team of 5+ |
| Deal size | $20K–$80K ARR |

### Tier 3: Pardot / Eloqua Enterprise Migration

| Field | Details |
|---|---|
| Target | 200–2000 employees, established B2B company |
| Pain signal | "Marketing Technology Architect" job posting or "MAP consolidation" project |
| Sales cycle | Longer (6–12 months) but larger ACV |
| Deal size | $80K–$300K ARR |

### Tier 4: Data-First Startup (Pre-MAP)

| Field | Details |
|---|---|
| Target | 20–100 employees, Series A B2B SaaS |
| Signal | Already on Snowflake, running lifecycle in HubSpot free or Mailchimp |
| Opportunity | Win the MAP decision before it's made |
| Deal size | $10K–$40K ARR |

---

## Buying Committee

| Role | Title | Priority |
|------|-------|----------|
| Champion | VP/Director of Marketing Operations | Primary — feels the pain |
| Champion | Demand Gen Engineer, Marketing Analytics Engineer | Executes campaigns |
| Approver | VP of Marketing, CMO | Owns the budget |
| Influencer | Head of Data, Director of Analytics | Owns the warehouse |

---

## Key Signals to Score (Priority Order)

1. **MOPs job posting** — highest intent signal. An open MOPs engineer role means the
   pain is real and there's headcount to address it. Score: 3.0 weight.
2. **Reverse ETL tool detected** (Hightouch, Census) — they've hit the wall and are
   papering over it. Score: 2.5 weight.
3. **Funding event** — B2B SaaS Series A/B = budget available for tooling upgrade.
   Score: 2.5 weight.
4. **Warehouse + marketing tooling in GitHub** (dbt marketing models, Segment pipelines,
   Snowflake connectors in marketing repos). Score: 2.0 weight.
5. **LinkedIn activity around martech/MOPs** — evaluating, researching, posting about
   MAP limitations. Score: 2.0 weight.

---

## Disqualifiers (Override Any Score)

- Fewer than 20 employees or pre-revenue
- B2C product (no enterprise sales motion)
- Already under contract with a competing warehouse-native MAP
- Marketing team of one (no ops function yet)
- No data warehouse infrastructure in their stack

---

## Outreach Messaging Principles

**What resonates:**
- Lead with the warehouse — "your warehouse already has the data, your MAP can't use it"
- Reference their specific middleware if detectable (Hightouch, Census)
- Be concrete about the 72-hour onboarding window (migrating customers go live fast)
- Reference their Salesforce stack — Conversion's sync is a concrete differentiator

**What to avoid:**
- Generic "AI-powered" claims — everyone says this
- Vague "better personalization" — be specific about warehouse traits at send time
- Asking about their budget — infer from signals and focus on time-to-value

**Best outreach format:**
- Cold email: 3–4 sentences, one concrete signal observed, one specific question
- Example: "Saw you're hiring a Marketing Operations Engineer and running Hightouch
  to Marketo. That combination usually means your warehouse data is closer to your
  campaigns than your MAP is. Curious if the sync latency is the bottleneck or
  something else — worth a 20-minute call?"
