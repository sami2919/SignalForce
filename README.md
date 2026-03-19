# SignalForce

> A Signal-Based Outbound Engine for Technical Products — Built with Claude Code Skills, n8n, and Python

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) ![License MIT](https://img.shields.io/badge/license-MIT-green) ![Tests](https://img.shields.io/badge/tests-pytest-brightgreen)

---

## The Problem

Traditional outbound sales fails for technical products sold to tiny, specialized markets. Generic list pulls miss the buyers who are actively building now. Spray-and-blast cadences get ignored by engineers who can spot a templated sequence in the first sentence. And manual prospecting at the research depth these buyers require does not scale.

The result: low reply rates, wasted enrichment spend, and SDRs who cannot hold a credible conversation with a Staff ML Engineer.

## The Solution

SignalForce continuously monitors public signal sources — GitHub commits, ArXiv papers, Hugging Face model uploads, job postings, and funding announcements — to identify companies that are actively investing in a technical domain right now. When a strong signal is detected, the pipeline enriches contacts, generates technically credible outreach personalized to that specific signal, and enrolls the contact in a sequenced campaign. The result is outreach that references the prospect's actual work, sent at the moment they are most likely to be thinking about the problem you solve.

The engine runs autonomously via n8n workflows on a daily schedule, with Claude Code skills available for human-in-the-loop review, research, and copy generation at any step.

---

## Architecture Overview

Three decoupled layers move data from raw public signals to enrolled email sequences and CRM deals.

```
┌─────────────────────────────────────────────────────────┐
│                    SIGNAL SOURCES                        │
│  GitHub Repos  ArXiv Papers  HF Models  Jobs  Funding   │
└──────────────────────┬──────────────────────────────────┘
                       │ raw API responses
                       ▼
┌─────────────────────────────────────────────────────────┐
│               LAYER 1: PYTHON SCANNERS                   │
│  github_rl_scanner  arxiv_monitor  hf_model_monitor     │
│  job_posting_scanner  funding_tracker  signal_stacker    │
│               → Signal objects (typed JSON)              │
└──────────────────────┬──────────────────────────────────┘
                       │ ScanResult → CompanyProfile (ranked + graded)
                       ▼
┌─────────────────────────────────────────────────────────┐
│             LAYER 2: CLAUDE CODE SKILLS                  │
│  signal-scanner  prospect-researcher  contact-finder     │
│  email-writer  pipeline-tracker  champion-tracker        │
│  deliverability-manager  compliance-manager              │
│               → Human-in-the-loop GTM workflow           │
└──────────────────────┬──────────────────────────────────┘
                       │ contacts + email copy + deal events
                       ▼
┌─────────────────────────────────────────────────────────┐
│             LAYER 3: n8n AUTOMATION                      │
│  daily-signal-scan → enrichment-pipeline                 │
│  → sequence-launcher → crm-sync                          │
│  Instantly.ai sequences, HubSpot deals, Slack alerts     │
└─────────────────────────────────────────────────────────┘
```

**Skills** are the primary interface. Each SKILL.md tells Claude how to perform a GTM task using the Python scripts as tools. The same scripts also power the n8n workflows — no code duplication between human-driven and automated paths.

---

## What's Included

### Skills (8)

| Skill | Description |
|-------|-------------|
| `signal-scanner` | Orchestrate all five scanners, stack and grade signals by ICP fit |
| `prospect-researcher` | Deep-dive company research, RL maturity classification, weighted ICP scoring |
| `contact-finder` | Waterfall enrichment: Apollo → Hunter → Prospeo → ZeroBounce verification |
| `email-writer` | Generate 3-variant personalized outreach sequences from signal payload |
| `pipeline-tracker` | Sync deal stages to HubSpot, generate weekly funnel reports |
| `champion-tracker` | Monitor job changes of past champions, route warm re-engagement |
| `deliverability-manager` | DNS setup (SPF/DKIM/DMARC), warmup protocols, blacklist monitoring |
| `compliance-manager` | CAN-SPAM/GDPR/CCPA/CASL suppression lists and audit checklists |

### Python Scripts (6)

| Script | Type | Description |
|--------|------|-------------|
| `github_rl_scanner.py` | Scanner | Detect orgs with active domain-specific repos via GitHub Search API |
| `arxiv_monitor.py` | Scanner | Track paper authors and institutional affiliations via Semantic Scholar |
| `hf_model_monitor.py` | Scanner | Find model uploads on HuggingFace Hub matching target criteria |
| `job_posting_scanner.py` | Scanner | Detect target-role job postings at companies in the ICP |
| `funding_tracker.py` | Scanner | Find funding events at companies in the target space |
| `signal_stacker.py` | Aggregator | Group signals by company, deduplicate, apply ICP scoring, output ranked profiles |

### n8n Workflows (4)

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `daily-signal-scan.json` | Cron: 7 AM daily | Run all scanners, stack signals, alert on top-tier accounts |
| `enrichment-pipeline.json` | Webhook | Enrich B+ accounts, find contacts, create HubSpot deals |
| `sequence-launcher.json` | Webhook | Generate email copy via Claude API, enroll in Instantly.ai |
| `crm-sync.json` | Webhook + Cron | Process reply/open/bounce events, update HubSpot, write analytics to Sheets |

### Templates (6 email sequences + 1 scoring rubric)

| Template | Signal Type |
|----------|-------------|
| `github-rl-signal.md` | GitHub repository activity |
| `arxiv-paper-signal.md` | ArXiv paper publication |
| `hiring-signal.md` | Target-role job posting |
| `funding-signal.md` | Funding round announcement |
| `huggingface-model-signal.md` | HuggingFace model upload |
| `champion-job-change.md` | Past champion changed companies |
| `icp-scoring-model.md` | Weighted scoring rubric (5 dimensions) |

---

## Quick Start

**Prerequisites:** Python 3.11+, n8n instance (Cloud or self-hosted), Instantly.ai account, HubSpot CRM (free tier works).

### 1. Clone

```bash
git clone https://github.com/your-org/SignalForce.git
cd SignalForce
```

### 2. Install

```bash
pip install -e ".[dev]"
```

### 3. Configure

```bash
cp .env.example .env
```

Open `.env` and fill in your API keys. At minimum, set `GITHUB_TOKEN`. See the [External APIs](#external-apis) table below for what each key unlocks.

### 4. Test

```bash
pytest --cov=scripts --cov-report=term-missing -v
```

All tests mock external HTTP calls — no real API credentials required to run the suite.

### 5. Run your first scan

Open Claude Code and invoke the signal-scanner skill:

```
/signal-scanner
```

Claude will validate your API keys, run all configured scanners, stack the results, and present a ranked table of target accounts with recommended next actions.

To run a scanner directly from the CLI:

```bash
python -m scripts.github_rl_scanner --lookback-days 7 --output /tmp/signals.json
python -m scripts.signal_stacker --inputs /tmp/signals.json --output /tmp/stacked.json
```

---

## Skills Reference

Skills are Claude Code instruction files located in `skills/*/SKILL.md`. Invoke them in Claude Code with `/skill-name`.

### `/signal-scanner`

Runs all five signal scanners, feeds results through `signal_stacker`, and presents a graded account table (A/B/C/D). Recommends the next action per account tier. Use this as the entry point for every prospecting cycle.

**When to use:** Weekly cadence, or before a focused outreach push.

### `/prospect-researcher`

Takes a company name or domain and produces a structured research report: firmographics, RL maturity classification (PRODUCTIONIZING → SCALING → BUILDING → EXPLORING → NONE), team mapping against target titles, competitive landscape, and a weighted ICP score across five dimensions.

**When to use:** Before outreach to any Grade A account, or when a signal needs manual validation.

### `/contact-finder`

Runs waterfall enrichment in order: Apollo.io → Hunter.io → Prospeo → PeopleDataLabs, stopping at the first verified result per contact. Always applies ZeroBounce validation as a final step. Surfaces gaps for manual LinkedIn outreach.

**When to use:** After a company is qualified (Grade A or B) and research is complete.

### `/email-writer`

Takes a signal payload, contact details, and prospect research. Selects the matching email template, then generates three copy variants — Problem-focused, Outcome-focused, Social Proof-focused — each as a full 3-email sequence (initial + two follow-ups). Enforces voice rules: 4-sentence maximum, specific technical reference, low-friction CTA.

**When to use:** After contact enrichment, before sequence enrollment.

### `/pipeline-tracker`

Syncs active sequences to HubSpot using custom deal properties (signal source, ICP grade, RL maturity, composite score). Generates a formatted weekly report covering signals, open rate, reply rate, meetings, and cost per meeting. Sends Slack notifications for A-tier replies and booked meetings.

**When to use:** Weekly pipeline review, or after a batch of sequences launches.

### `/champion-tracker`

Monitors job changes across three parallel channels (Clay, Apollo alerts, LinkedIn Sales Nav). When a past champion moves companies, runs `prospect-researcher` on the new company and routes to warm re-engagement or a 90-day follow-up task based on ICP grade. Champion outreach goes from a primary inbox, never a sending domain.

**When to use:** Weekly champion list review, or when a job change alert fires.

### `/deliverability-manager`

Generates DNS configuration (SPF, DKIM, DMARC, custom CNAME), warmup schedules per sending account, and monitoring checklists. Includes a troubleshooting table for common symptoms (high bounce, spam folder, blacklist).

**When to use:** When setting up new sending domains, or diagnosing delivery problems.

### `/compliance-manager`

Manages suppression lists, opt-out workflows, and GDPR deletion requests. Produces a monthly compliance audit checklist covering CAN-SPAM, GDPR, CCPA, and CASL. Documents where personal data is permitted to live and how to handle "how did you get my email" replies.

**When to use:** Monthly compliance audit, or when handling any opt-out or deletion request.

---

## Signal Sources

| Source | What It Detects | API Used |
|--------|----------------|----------|
| GitHub | Organizations with recent commits to domain-specific repos | GitHub Search API v3 |
| ArXiv / Semantic Scholar | Paper authors and their institutional affiliations | Semantic Scholar API |
| HuggingFace Hub | Model uploads tagged with target-domain identifiers | HuggingFace Hub API (public) |
| Job Postings | Companies hiring for target engineering roles | Configurable job board APIs |
| Funding | Recent funding events at companies in the target space | Funding data APIs |

Signals are typed with a strength rating (WEAK / MODERATE / STRONG) and aggregated by company using `signal_stacker.py`. Companies with signals across multiple sources receive a multiplier. Final ICP grade (A/B/C/D) combines composite signal score with ICP scoring rubric weights.

---

## External APIs

| API | Purpose | Key Required |
|-----|---------|-------------|
| GitHub API | Repo detection | Yes (`GITHUB_TOKEN`) |
| Semantic Scholar | Paper tracking | Optional (rate limited without) |
| HuggingFace Hub | Model upload detection | No (public API) |
| Apollo.io | Contact enrichment (waterfall step 1) | Yes (`APOLLO_API_KEY`) |
| Hunter.io | Contact enrichment (waterfall step 2) | Yes (`HUNTER_API_KEY`) |
| Prospeo | LinkedIn email enrichment (waterfall step 3) | Yes (`PROSPEO_API_KEY`) |
| ZeroBounce | Email verification | Yes (`ZEROBOUNCE_API_KEY`) |
| Anthropic API | Email copy generation in sequence-launcher | Yes (`ANTHROPIC_API_KEY`) |
| Instantly.ai | Sequence enrollment and delivery events | Yes (`INSTANTLY_API_KEY`) |
| HubSpot | Deal and contact CRM | Yes (`HUBSPOT_ACCESS_TOKEN`) |

Only `GITHUB_TOKEN` is required to run the scanners. Enrichment and automation keys can be added incrementally as you scale.

---

## Cost

Three budget tiers. All figures in USD/month.

| Tier | Monthly Cost | Sequences/Week | Best For |
|------|-------------|----------------|----------|
| Minimal | ~$61–81 | 10–20 | Testing, pipeline development |
| Standard | ~$206–226 | 80–150 | Full production, one operator |
| Premium | ~$670–740 | 150+ | High-touch with Clay, larger team |

**Comparison:**

| Alternative | Annual Cost |
|-------------|-------------|
| SignalForce (Standard) | ~$2,500–3,900/yr |
| AI SDR tool (Artisan, 11x) | $40,000–60,000/yr |
| Full-time junior SDR | $80,000–120,000/yr |

The Minimal tier runs on n8n Cloud ($24/mo) + Instantly.ai ($37/mo) + Claude API (~$10–20/mo at low volume). All signal scanners use free APIs. Enrichment runs on free tiers (Apollo: 50 exports/mo, Hunter: 25 requests/mo, Prospeo: 75 credits/mo).

See [`docs/cost-analysis.md`](docs/cost-analysis.md) for the full tool-by-tool breakdown and scaling notes.

---

## Customization

SignalForce is domain-agnostic. The target market, ICP definitions, signal keywords, and voice rules live entirely in one file: `.agents/gtm-context.md`.

To adapt this engine for your product:

**1. Replace `.agents/gtm-context.md`**

Edit the file to describe your company, product, ICP tiers, target titles, voice rules, and signal keywords. All eight skills load this file and use it to drive every decision — scoring, contact targeting, email tone, disqualification criteria.

**2. Update signal keywords in the scanners**

Each scanner script has a configurable list of domain-specific keywords (e.g., `RLHF`, `PPO`, `Gymnasium` for RL). Update these to match your ICP's technical vocabulary. The keywords appear at the top of each scanner file as constants.

**3. Update the ICP scoring rubric**

`templates/scoring-rubrics/icp-scoring-model.md` defines the weighted scoring dimensions. Adjust the dimension weights and scoring criteria to match what matters most for your ICP.

**4. Update email templates**

`templates/email-sequences/` contains one template per signal type. Update these to reflect your product's proof points and the specific technical hooks relevant to your ICP.

That is the full customization surface. The scanners, stacker, enrichment waterfall, n8n workflows, and skills all remain unchanged.

---

## Results

Target metrics at steady state (Month 3):

| Metric | Target |
|--------|--------|
| Open rate | 45–65% |
| Reply rate | 12–20% |
| Positive reply rate | 5–8% |
| Meetings booked/month | 15–30 |
| Cost per meeting | $25–50 |

For context: industry median reply rate for cold B2B email is 3–5%. Signal-based outreach targets 12–20% because every email references a specific, recent, real action the prospect took — not a static list attribute.

See [`docs/results-framework.md`](docs/results-framework.md) for metric definitions, monthly ramp targets (Month 1 → Month 3 → Month 6), grade distribution targets, weekly reporting cadence, and diagnostic playbooks for low signals, low reply rate, deliverability issues, and CRM sync failures.

---

## Contributing

### Adding a new signal source

1. Create `scripts/your_source_scanner.py` following the pattern in `github_rl_scanner.py`. The script must accept `--lookback-days` and `--output` CLI arguments and write a `ScanResult` JSON file.
2. Add the new scanner to the `signal-scanner` skill's steps in `skills/signal-scanner/SKILL.md`.
3. Add the scanner to the `daily-signal-scan.json` n8n workflow.
4. Write tests in `tests/` — mock all HTTP calls. Maintain 80%+ coverage.

### Adding a new skill

1. Create `skills/your-skill/SKILL.md` with YAML frontmatter (`name`, `description`) and a concise workflow under 500 words.
2. The `description` field must start with "Use when..." — this is how Claude selects the right skill.
3. Reference `.agents/gtm-context.md` for any ICP or voice logic rather than hardcoding it in the skill.

### Code conventions

- Pydantic models with `frozen=True` for all data structures — no raw dicts between components.
- Type hints required on all function signatures.
- Ruff for formatting and linting (`ruff format . && ruff check . --fix`).
- Never commit secrets — all API keys via `.env` loaded through `scripts/config.py`.

---

## License

MIT — see [LICENSE](LICENSE).

This project is a reference implementation. Fork it, adapt `.agents/gtm-context.md` to your ICP, and run it for any technical product sold to a specialist market.
