# Architecture — SignalForce

## System Overview

SignalForce is a three-layer signal-based outbound GTM engine that detects buying signals across public data sources and converts them into personalized outreach for your configured ICP. The three layers are intentionally decoupled:

- **Skills** (`skills/*/SKILL.md`) — Claude Code instruction files that define *how* to perform GTM tasks. These are the primary user interface. Claude reads a skill and executes the workflow using the scripts as tools.
- **Scripts** (`scripts/*.py`) — Python modules that interact with external APIs (GitHub, Semantic Scholar, HuggingFace, enrichment providers, CRM). Skills invoke these via CLI or as importable modules.
- **n8n Workflows** (`n8n-workflows/*.json`) — Scheduled automation that orchestrates the scripts autonomously without human input (daily scans, enrichment, CRM sync, analytics).

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        CONFIG LOADER                             │
│  config_loader.py reads config/config.yaml                       │
│  Injects ICP keywords, tier definitions, scanner parameters      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ ScannerConfig per scanner
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                        SIGNAL SOURCES                            │
│  GitHub Repos  ArXiv Papers  HF Models  Jobs  Funding  LinkedIn │
└──────────────────────────┬──────────────────────────────────────┘
                           │ raw API responses / activity data
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PYTHON SCANNERS                             │
│  scanners.github_scanner  scanners.arxiv_scanner                 │
│  scanners.hf_scanner  scanners.job_scanner                       │
│  scanners.funding_scanner  scanners.linkedin_scanner             │
│                   → Signal objects (JSON)                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │ ScanResult JSON files
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      INTENT SCORING                              │
│  intent_scorer.py  +  recency.py                                 │
│  Gojiberry formula: COMBINED = (ICP_Fit × 0.4) + (Intent × 0.6) │
│  Recency decay + signal-type weights + breadth multiplier        │
│                   → ScoringResult per company                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ intent + combined scores
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SIGNAL STACKER                              │
│  signal_stacker.py                                               │
│  Groups by company, deduplicates, applies multipliers            │
│                   → CompanyProfile objects (ranked)              │
└──────────────────────────┬──────────────────────────────────────┘
                           │ ranked profiles + ICP grades
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ENRICHMENT                                  │
│  contact-finder skill + enrichment-pipeline workflow             │
│  Waterfall: Apollo → Hunter → Prospeo                            │
│  ZeroBounce verification                                         │
│                   → Contact objects with verified emails         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ contacts + company profiles
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      OUTREACH GENERATION                         │
│  email-writer / resource-offer / multi-channel-writer skills     │
│  multi_channel_sequencer.py — staggered Email + LinkedIn timing  │
│  Signal-specific templates, 3 variants per contact               │
│                   → GeneratedEmail + SequenceStep objects        │
└──────────────────────────┬──────────────────────────────────────┘
                           │ personalized copy + sequence plan
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SEQUENCES                                   │
│  sequence-launcher workflow + Instantly.ai API                   │
│  Routes by signal type to dedicated campaigns                    │
│                   → leads enrolled in email/LinkedIn sequences   │
└──────────────────────────┬──────────────────────────────────────┘
                           │ engagement events (webhooks)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MEETING + POST-MEETING                      │
│  meeting-followup skill + MeetingOutcome model                   │
│  Outcome extraction → template routing → follow-up sequence      │
│  CRM stage: MEETING_COMPLETED                                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ deal stage events + follow-up emails
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CRM + ANALYTICS                             │
│  pipeline-tracker skill + crm-sync workflow                      │
│  HubSpot deal creation, stage progression                        │
│  Reply classification, Slack alerts, Google Sheets               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Intent-Weighted Scoring

### The Gojiberry Formula

```
COMBINED = (ICP_Fit × 0.4) + (Intent × 0.6)
```

Intent receives 60% weight because **timing beats targeting** — a mediocre ICP fit with strong real-time buying signals outperforms a perfect ICP fit with no activity.

### How Intent Score Is Calculated

For each signal detected for a company:

```
weighted_value = signal_strength × intent_weight × recency_decay
```

Summed across all signals, then scaled by a **breadth multiplier** based on how many distinct signal source types are present.

### Signal-Type Intent Weights

| Signal Type | Weight | Rationale |
|-------------|--------|-----------|
| LinkedIn Activity | 3.0 | Real-time engagement = highest urgency |
| ArXiv Paper | 3.0 | Research publication = active RL work |
| GitHub RL Repo | 2.5 | Code activity = hands-on development |
| HuggingFace Model | 2.5 | Model upload = production-path intent |
| Job Posting | 2.0 | Hiring = budget allocated |
| Funding Event | 1.5 | Capital = future spend, not immediate |

### Recency Decay

Signal value decays exponentially: `decay_factor = 2^(-age_days / half_life)`

| Signal Type | Half-Life | Reasoning |
|-------------|-----------|-----------|
| LinkedIn Activity | 2 days | The 48-hour engagement window |
| GitHub RL Repo | 5 days | Code activity is time-sensitive |
| HuggingFace Model | 7 days | Model uploads remain relevant ~1 week |
| ArXiv Paper | 10 days | Research stays relevant longer |
| Job Posting | 10 days | Hiring cycles are slower |
| Funding Event | 21 days | Post-funding windows last months |

### Breadth Multiplier

Companies active across multiple signal types signal broader, more persistent intent:

| Unique Signal Types | Multiplier |
|--------------------|------------|
| 1 | 1.0× |
| 2 | 1.5× |
| 3 | 2.0× |
| 4+ | 3.0× |

### Grade Thresholds

| Combined Score | Grade |
|---------------|-------|
| ≥ 8.0 | A |
| ≥ 5.0 | B |
| ≥ 2.0 | C |
| < 2.0 | D |

---

## Multi-Channel Sequencing

### Dual-Channel Timing (Email + LinkedIn)

When a prospect has both a verified email and a LinkedIn URL, the sequence is staggered across 8 days:

```
Day 0  ──  Email 1 (problem_focused)
Day 1  ──  LinkedIn connection request (signal_reference note)
Day 3  ──  Email 2 (outcome_focused)
Day 4  ──  LinkedIn follow-up message (resource/insight lead)
Day 7  ──  Email 3 (break_up)
Day 8  ──  LinkedIn second follow-up
```

### Single-Channel Fallbacks

- **Email only**: Days 0, 3, 7 (3 steps)
- **LinkedIn only**: Days 0, 3, 7 (3 steps — connection request, then follow-ups)

The channel plan is determined by `select_primary_channel()` in `multi_channel_sequencer.py` and the full step list is built by `build_sequence()`.

---

## Resource-First Outreach Funnel

Technical buyers (RL researchers, ML leads, simulation engineers) respond poorly to unsolicited demo requests. The **blueprint-before-demo** approach offers a free, relevant resource before asking for anything.

### Why It Works

- Resource-first outreach converts at ~50% reply rate vs. 8-15% for demo asks
- Technical buyers respond to peer knowledge-sharing, not vendor pitches
- The resource creates a reason to respond without requiring a buying decision

### Funnel Structure

```
Email 1 — Offer a free resource tied to the detected signal
Email 2 — Share a specific, non-obvious insight from the resource
Email 3 — Low-friction CTA: resource walkthrough (not a demo)
```

The resource is selected based on signal type using the mapping in `templates/email-sequences/resource-offer-signal.md`. No email in the sequence asks for a meeting or a demo until the prospect has received the full resource.

Default audience: **ICP Tier 1 (AI Labs)** and **Tier 3 (Robotics)**.

---

## Post-Meeting Automation Flow

```
Meeting completed
      │
      ▼
MeetingOutcome extraction (meeting-followup skill)
      │  Fields: outcome, objections, next_steps,
      │          decision_timeline, stakeholders_needed,
      │          follow_up_resources
      ▼
Template routing by outcome
  ├── positive  → 3-email sequence (Day 0, 3, 7)
  ├── neutral   → 3-email sequence (Day 0, 5, 14)
  ├── negative  → 1 email; flag for 6-month re-qualification
  └── no_show   → 2-email sequence (Day 0, 3)
      │
      ▼
Follow-up emails generated (signal-specific, objection-aware)
      │
      ▼
CRM update: DealStage → MEETING_COMPLETED
Stakeholder tasks created if stakeholders_needed is non-empty
Re-qualification reminder set if outcome is negative
```

---

## Component Reference

### Skills

| Name | Type | Purpose | Inputs | Outputs |
|------|------|---------|--------|---------|
| `signal-scanner` | Skill | Orchestrate all scanners, stack signals, grade ICP | Config, lookback days | Ranked CompanyProfile list |
| `prospect-researcher` | Skill | Deep-dive company research, RL maturity assessment | Company name/domain | Research report, ICP score |
| `contact-finder` | Skill | Waterfall enrichment across Apollo/Hunter/Prospeo | Company domain, target titles | Verified Contact objects |
| `email-writer` | Skill | Generate personalized outreach from signal + research | Signal payload, Contact, research | GeneratedEmail (3 variants) |
| `resource-offer` | Skill | Blueprint-first outreach; offer resource before meeting | Signal payload, Contact, research | 3-variant resource-offer sequence |
| `multi-channel-writer` | Skill | Staggered Email + LinkedIn outreach sequences | Contact data, signal type/payload | SequenceStep list + full copy |
| `meeting-followup` | Skill | Extract MeetingOutcome and generate follow-up emails | Meeting notes or MeetingOutcome | Follow-up sequence + CRM actions |
| `pipeline-tracker` | Skill | Sync to HubSpot, generate analytics reports | Deal stage events | HubSpot records, metrics |
| `champion-tracker` | Skill | Monitor job changes of past champions | Champion list, Clay alerts | New opportunity signals |
| `deliverability-manager` | Skill | Configure sending infrastructure, DNS, warmup | Domain list | DNS records, warmup schedule |
| `compliance-manager` | Skill | Manage CAN-SPAM/GDPR/CCPA requirements | Opt-out requests | Suppression lists, audit log |

### Scripts

| Name | Type | Purpose | Inputs | Outputs |
|------|------|---------|--------|---------|
| `scanners/github_scanner.py` | Scanner | Detect orgs with matching repos via GitHub Search API | `ScannerConfig` | `ScanResult` JSON |
| `scanners/arxiv_scanner.py` | Scanner | Track paper authors and their affiliations via Semantic Scholar | `ScannerConfig` | `ScanResult` JSON |
| `scanners/hf_scanner.py` | Scanner | Find model uploads on HuggingFace Hub | `ScannerConfig` | `ScanResult` JSON |
| `scanners/job_scanner.py` | Scanner | Detect target-role job postings at ICP companies | `ScannerConfig` | `ScanResult` JSON |
| `scanners/funding_scanner.py` | Scanner | Find funding events at target-space companies | `ScannerConfig` | `ScanResult` JSON |
| `scanners/linkedin_scanner.py` | Scanner | Process LinkedIn activity data for engagement signals | Activity JSON (data-input mode) | `ScanResult` JSON |
| `scanner_runner.py` | Orchestrator | Discover and run all configured scanners | `config.yaml`, `--lookback-days` | Multiple `ScanResult` JSON files |
| `intent_scorer.py` | Scorer | Gojiberry intent-weighted scoring with recency decay | `list[Signal]`, `icp_fit` float | `ScoringResult` (intent, combined, grade) |
| `recency.py` | Utility | Exponential decay functions for signal freshness | Signal timestamp, half-life | Decay factor (0.0–1.0) |
| `multi_channel_sequencer.py` | Sequencer | Build staggered Email + LinkedIn outreach sequences | Channels, signal type | `list[SequenceStep]` |
| `signal_stacker.py` | Aggregator | Group signals by company, score, grade ICP | Multiple `ScanResult` JSON files | Ranked `CompanyProfile` JSON |
| `models.py` | Data | Pydantic models for all pipeline data structures | — | Type definitions |
| `config.py` | Config | Load and validate all environment variables (API keys) | `.env` file | `AppConfig` singleton |
| `config_loader.py` | Config | Load and validate ICP configuration from `config.yaml` | `config/config.yaml` | `ICPConfig` object |
| `api_client.py` | Infra | Base HTTP client with retry and rate-limit handling | `base_url`, `auth_headers` | Inheritable `BaseAPIClient` |

### n8n Workflows

| Name | Type | Purpose | Trigger | Calls |
|------|------|---------|---------|-------|
| `daily-signal-scan.json` | Orchestrator | Run all 6 scanners, stack signals, alert on A-tier | Cron: 7 AM PST daily | enrichment-pipeline webhook |
| `enrichment-pipeline.json` | Processor | Enrich B+ companies, find contacts, create HubSpot deals | Webhook from daily-signal-scan | sequence-launcher webhook |
| `sequence-launcher.json` | Sender | Generate email copy via Claude, enroll in Instantly.ai | Webhook from enrichment-pipeline | Instantly.ai API, HubSpot API |
| `crm-sync.json` | Sync | Process Instantly reply/open/bounce events, update HubSpot, compute daily analytics | Webhook (Instantly) + Cron (6 PM PST) | HubSpot API, Google Sheets, Slack |

---

## Signal Sources

| Source | Scanner | Signal Type | Data Collection | Half-Life |
|--------|---------|-------------|-----------------|-----------|
| GitHub | `scanners.github_scanner` | `github_repo` | GitHub Search API | 5 days |
| ArXiv / Semantic Scholar | `scanners.arxiv_scanner` | `arxiv_paper` | Semantic Scholar API (affiliation mapping) | 10 days |
| HuggingFace Hub | `scanners.hf_scanner` | `huggingface_model` | HF Hub public API | 7 days |
| Job boards | `scanners.job_scanner` | `job_posting` | Scraped / API | 10 days |
| Crunchbase / funding APIs | `scanners.funding_scanner` | `funding_event` | Funding APIs | 21 days |
| LinkedIn (data-input) | `scanners.linkedin_scanner` | `linkedin_activity` | Sales Navigator / PhantomBuster export | 2 days |

LinkedIn operates in **data-input mode** — the scanner does not call the LinkedIn API directly. Activity data is pre-collected via Sales Navigator export, PhantomBuster, or manual research, then passed as a JSON array. This avoids LinkedIn's API restrictions while still capturing the highest-intent signal in the pipeline.

---

## Data Model Relationships

```
ScanResult
  └─ signals: list[Signal]
       └─ signal_type: str            ← free-form string; scanner sets this (e.g. "github_repo")
       └─ signal_strength: SignalStrength (WEAK | MODERATE | STRONG)
       └─ company_name, company_domain, source_url, raw_data

ScoringResult                          ← produced by IntentScorer
  └─ intent_score: float               ← sum of decay-weighted signal values
  └─ combined_score: float             ← Gojiberry formula output
  └─ icp_score: str (A/B/C/D)         ← free-form grade; thresholds in config.yaml
  └─ signal_count: int
  └─ source_types: int                 ← drives breadth multiplier

CompanyProfile
  └─ signals: list[Signal]            ← aggregated from ScanResults by signal_stacker
  └─ icp_tier: str                    ← free-form tier name from config.yaml
  └─ icp_score: str (A/B/C/D)        ← computed by icp-scoring-model rubric
  └─ domain_maturity: str             ← free-form maturity label (e.g. "PRODUCTIONIZING")
  └─ composite_signal_score: float

Contact
  └─ company_domain                   ← links to CompanyProfile.domain
  └─ email, email_verified
  └─ enrichment_source: EnrichmentSource (APOLLO | HUNTER | PROSPEO | ...)
  └─ confidence_score: float

SequenceStep                           ← produced by multi_channel_sequencer.py
  └─ day: int
  └─ channel: OutreachChannel (EMAIL | LINKEDIN | LINKEDIN_INMAIL)
  └─ action: str
  └─ template_name: str
  └─ variant: str | None

GeneratedEmail
  └─ contact_id                        ← links to Contact.id
  └─ signal_type, signal_reference     ← links back to Signal
  └─ variant: EmailVariant (PROBLEM_FOCUSED | OUTCOME_FOCUSED | SOCIAL_PROOF_FOCUSED)
  └─ template_name

MeetingOutcome                         ← produced by meeting-followup skill
  └─ deal_id                           ← links to Deal.id
  └─ outcome: str (positive | neutral | negative | no_show)
  └─ objections: list[str]
  └─ next_steps: list[str]
  └─ decision_timeline: str | None
  └─ stakeholders_needed: list[str]
  └─ follow_up_resources: list[str]

Deal
  └─ company_profile: CompanyProfile
  └─ contacts: list[Contact]
  └─ emails_sent: list[GeneratedEmail]
  └─ stage: DealStage (SIGNAL_DETECTED → ... → MEETING_COMPLETED → PROPOSAL_SENT)
  └─ hubspot_deal_id, instantly_campaign_id
```

All models use `frozen=True` (Pydantic immutability). Pipeline stages produce new objects rather than mutating existing ones.

---

## Integration Points

| API | Connected Component | Direction | Auth |
|-----|--------------------|-----------|----|
| GitHub API v3 | `scanners/github_scanner.py` | Read | `GITHUB_TOKEN` bearer |
| Semantic Scholar | `scanners/arxiv_scanner.py` (affiliation mapping for ArXiv authors) | Read | `SEMANTIC_SCHOLAR_KEY` (optional) |
| HuggingFace Hub | `scanners/hf_scanner.py` | Read | None (public API) |
| Apollo.io | Contact enrichment (waterfall step 1) | Read | `APOLLO_API_KEY` |
| Hunter.io | Contact enrichment (waterfall step 2) | Read | `HUNTER_API_KEY` |
| Prospeo | Contact enrichment (waterfall step 3) | Read | `PROSPEO_API_KEY` |
| ZeroBounce | Email verification | Read | `ZEROBOUNCE_API_KEY` |
| Anthropic API | Email generation in sequence-launcher | Read | `ANTHROPIC_API_KEY` |
| Instantly.ai | Sequence enrollment + webhook events | Read/Write | `INSTANTLY_API_KEY` |
| HubSpot CRM | Deal and contact management | Read/Write | `HUBSPOT_ACCESS_TOKEN` |
| Slack | A-tier alerts, hot-lead notifications, analytics digest | Write | OAuth2 credential in n8n |
| Google Sheets | Daily analytics append | Write | OAuth2 credential in n8n |

---

## Design Decisions

### Skills-first interface

Claude Code skills are the primary interface rather than a web UI or CLI wrapper. This keeps the system extensible — adding a new GTM task means writing a SKILL.md file, not shipping new application code. The skill instructs Claude how to use existing scripts as tools, which means the same scripts serve both human-in-the-loop (via skills) and fully automated (via n8n) workflows without duplication.

### Pydantic models for all data structures

All data flowing between pipeline components is typed using Pydantic models with `frozen=True`. This enforces immutability (no accidental in-place mutation between stages), provides automatic validation at boundaries, and generates JSON schemas that n8n workflows can validate against. Raw dicts are never passed between components.

### Separate scanners per signal source

Each signal source (GitHub, ArXiv, HuggingFace, job postings, funding, LinkedIn) is a separate script rather than one monolithic scanner. This allows independent scheduling, independent failure handling, and independent rate-limit budgets. A GitHub API rate limit should not block an ArXiv scan. The signal_stacker combines outputs after the fact.

### Config-driven ICP

All ICP definitions — signal keywords, tier names and criteria, target titles, domain maturity labels, and scoring thresholds — live in `config/config.yaml`. A companion `config/gtm-context.md` file provides natural-language context loaded by every skill. This separation means:

- **No code changes required** to retarget the engine for a new ICP. Edit config files, re-run `/validate`, done.
- **`config/` is gitignored** — your active config never ships in the repo. Use `config.example/` as an annotated reference, or copy one of the vertical configs from `examples/`.
- **`scripts/config_loader.py`** handles ICP config loading and validation (separate from `scripts/config.py`, which handles API key env vars).
- **`examples/`** ships four pre-built configs for common verticals (RL infrastructure, cybersecurity, data infrastructure, devtools) so new users can start from a working baseline.

### Intent-over-ICP scoring

The Gojiberry formula weights intent (60%) higher than ICP fit (40%) because outbound timing is the highest-leverage variable. A prospect that perfectly fits the ICP but shows no current activity is less likely to convert than a slightly weaker ICP fit that is actively publishing research and hiring for relevant roles. Recency decay ensures stale signals do not accumulate false weight over time.

### LinkedIn as data-input signal source

LinkedIn's API restrictions make programmatic activity scanning impractical. Instead, the LinkedIn scanner operates in data-input mode: activity data is pre-collected via Sales Navigator, PhantomBuster, or manual research, then fed as a JSON array. This design separates data collection (human or third-party tooling) from signal processing (automated), and gives LinkedIn the shortest half-life (2 days) to reflect its real-time nature.

### Waterfall enrichment

Contact enrichment works top-to-bottom through Apollo → Hunter → Prospeo, stopping at the first verified result. This minimizes API spend (only escalate to more expensive sources when cheaper ones fail) while maximizing coverage. ZeroBounce verification is a separate final step applied to every email regardless of source.

### n8n for automation

n8n was chosen over custom orchestration code because it provides visual debugging of workflow execution, built-in retry configuration per node, and managed credential storage. The Python scripts do all the heavy API interaction; n8n handles only scheduling, data routing between steps, and webhook ingestion from Instantly.ai.
