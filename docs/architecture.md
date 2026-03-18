# Architecture — rl-gtm-engine

## System Overview

rl-gtm-engine is a three-layer signal-based outbound GTM engine targeting reinforcement learning infrastructure buyers (Collinear AI's ICP). The three layers are intentionally decoupled:

- **Skills** (`skills/*/SKILL.md`) — Claude Code instruction files that define *how* to perform GTM tasks. These are the primary user interface. Claude reads a skill and executes the workflow using the scripts as tools.
- **Scripts** (`scripts/*.py`) — Python modules that interact with external APIs (GitHub, Semantic Scholar, HuggingFace, enrichment providers, CRM). Skills invoke these via CLI or as importable modules.
- **n8n Workflows** (`n8n-workflows/*.json`) — Scheduled automation that orchestrates the scripts autonomously without human input (daily scans, enrichment, CRM sync, analytics).

---

## Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                    SIGNAL SOURCES                        │
│  GitHub Repos  ArXiv Papers  HF Models  Jobs  Funding   │
└──────────────────────┬──────────────────────────────────┘
                       │ raw API responses
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  PYTHON SCANNERS                         │
│  github_rl_scanner  arxiv_monitor  hf_model_monitor     │
│  job_posting_scanner  funding_tracker                    │
│               → Signal objects (JSON)                    │
└──────────────────────┬──────────────────────────────────┘
                       │ ScanResult JSON files
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  SIGNAL STACKER                          │
│  signal_stacker.py                                       │
│  Groups by company, deduplicates, applies multipliers    │
│               → CompanyProfile objects (ranked)          │
└──────────────────────┬──────────────────────────────────┘
                       │ ranked profiles + ICP grades
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  ENRICHMENT                              │
│  contact-finder skill + enrichment-pipeline workflow     │
│  Waterfall: Apollo → Hunter → Prospeo                    │
│  ZeroBounce verification                                 │
│               → Contact objects with verified emails     │
└──────────────────────┬──────────────────────────────────┘
                       │ contacts + company profiles
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  EMAIL GENERATION                        │
│  email-writer skill + Claude API (Anthropic)             │
│  Signal-specific templates, 3 variants per contact       │
│               → GeneratedEmail objects                   │
└──────────────────────┬──────────────────────────────────┘
                       │ personalized email copy
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  SEQUENCES                               │
│  sequence-launcher workflow + Instantly.ai API           │
│  Routes by signal type to dedicated campaigns            │
│               → leads enrolled in email sequences        │
└──────────────────────┬──────────────────────────────────┘
                       │ engagement events (webhooks)
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  CRM + ANALYTICS                         │
│  pipeline-tracker skill + crm-sync workflow              │
│  HubSpot deal creation, stage progression                │
│  Reply classification, Slack alerts, Google Sheets       │
└─────────────────────────────────────────────────────────┘
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
| `pipeline-tracker` | Skill | Sync to HubSpot, generate analytics reports | Deal stage events | HubSpot records, metrics |
| `champion-tracker` | Skill | Monitor job changes of past champions | Champion list, Clay alerts | New opportunity signals |
| `deliverability-manager` | Skill | Configure sending infrastructure, DNS, warmup | Domain list | DNS records, warmup schedule |
| `compliance-manager` | Skill | Manage CAN-SPAM/GDPR/CCPA requirements | Opt-out requests | Suppression lists, audit log |

### Scripts

| Name | Type | Purpose | Inputs | Outputs |
|------|------|---------|--------|---------|
| `github_rl_scanner.py` | Scanner | Detect orgs with RL repos via GitHub Search API | `--lookback-days`, `--output` | `ScanResult` JSON |
| `arxiv_monitor.py` | Scanner | Track RL paper authors and their affiliations | `--lookback-days`, `--output` | `ScanResult` JSON |
| `hf_model_monitor.py` | Scanner | Find RL model uploads on HuggingFace Hub | `--lookback-days`, `--output` | `ScanResult` JSON |
| `job_posting_scanner.py` | Scanner | Detect RL job postings at target companies | `--lookback-days`, `--output` | `ScanResult` JSON |
| `funding_tracker.py` | Scanner | Find funding events at AI/RL companies | `--lookback-days`, `--output` | `ScanResult` JSON |
| `signal_stacker.py` | Aggregator | Group signals by company, score, grade ICP | Multiple `ScanResult` JSON files | Ranked `CompanyProfile` JSON |
| `models.py` | Data | Pydantic models for all pipeline data structures | — | Type definitions |
| `config.py` | Config | Load and validate all environment variables | `.env` file | `AppConfig` singleton |
| `api_client.py` | Infra | Base HTTP client with retry and rate-limit handling | `base_url`, `auth_headers` | Inheritable `BaseAPIClient` |

### n8n Workflows

| Name | Type | Purpose | Trigger | Calls |
|------|------|---------|---------|-------|
| `daily-signal-scan.json` | Orchestrator | Run all 5 scanners, stack signals, alert on A-tier | Cron: 7 AM PST daily | enrichment-pipeline webhook |
| `enrichment-pipeline.json` | Processor | Enrich B+ companies, find contacts, create HubSpot deals | Webhook from daily-signal-scan | sequence-launcher webhook |
| `sequence-launcher.json` | Sender | Generate email copy via Claude, enroll in Instantly.ai | Webhook from enrichment-pipeline | Instantly.ai API, HubSpot API |
| `crm-sync.json` | Sync | Process Instantly reply/open/bounce events, update HubSpot, compute daily analytics | Webhook (Instantly) + Cron (6 PM PST) | HubSpot API, Google Sheets, Slack |

---

## Data Model Relationships

```
ScanResult
  └─ signals: list[Signal]
       └─ signal_type: SignalType (GITHUB_RL_REPO | ARXIV_PAPER | ...)
       └─ signal_strength: SignalStrength (WEAK | MODERATE | STRONG)
       └─ company_name, company_domain, source_url, raw_data

CompanyProfile
  └─ signals: list[Signal]          ← aggregated from ScanResults by signal_stacker
  └─ icp_tier: ICPTier              ← assigned by prospect-researcher skill
  └─ icp_score: ICPScore (A/B/C/D)  ← computed by icp-scoring-model rubric
  └─ rl_maturity: RLMaturityStage
  └─ composite_signal_score: float

Contact
  └─ company_domain                 ← links to CompanyProfile.domain
  └─ email, email_verified
  └─ enrichment_source: EnrichmentSource (APOLLO | HUNTER | PROSPEO | ...)
  └─ confidence_score: float

GeneratedEmail
  └─ contact_id                     ← links to Contact.id
  └─ signal_type, signal_reference  ← links back to Signal
  └─ variant: EmailVariant (PROBLEM_FOCUSED | OUTCOME_FOCUSED | SOCIAL_PROOF_FOCUSED)
  └─ template_name

Deal
  └─ company_profile: CompanyProfile
  └─ contacts: list[Contact]
  └─ emails_sent: list[GeneratedEmail]
  └─ stage: DealStage (SIGNAL_DETECTED → RESEARCHED → ENRICHED → SEQUENCED → ENGAGED → RESPONDED → MEETING_SCHEDULED)
  └─ hubspot_deal_id, instantly_campaign_id
```

All models use `frozen=True` (Pydantic immutability). Pipeline stages produce new objects rather than mutating existing ones.

---

## Integration Points

| API | Connected Component | Direction | Auth |
|-----|--------------------|-----------|----|
| GitHub API v3 | `github_rl_scanner.py` | Read | `GITHUB_TOKEN` bearer |
| Semantic Scholar | `arxiv_monitor.py` | Read | `SEMANTIC_SCHOLAR_KEY` (optional) |
| HuggingFace Hub | `hf_model_monitor.py` | Read | None (public API) |
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

Each signal source (GitHub, ArXiv, HuggingFace, job postings, funding) is a separate script rather than one monolithic scanner. This allows independent scheduling, independent failure handling, and independent rate-limit budgets. A GitHub API rate limit should not block an ArXiv scan. The signal_stacker combines outputs after the fact.

### Waterfall enrichment

Contact enrichment works top-to-bottom through Apollo → Hunter → Prospeo, stopping at the first verified result. This minimizes API spend (only escalate to more expensive sources when cheaper ones fail) while maximizing coverage. ZeroBounce verification is a separate final step applied to every email regardless of source.

### n8n for automation

n8n was chosen over custom orchestration code because it provides visual debugging of workflow execution, built-in retry configuration per node, and managed credential storage. The Python scripts do all the heavy API interaction; n8n handles only scheduling, data routing between steps, and webhook ingestion from Instantly.ai.
