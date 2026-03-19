# SignalForce

> The open-source GTM engineer toolkit — signal-based prospecting, configurable for any ICP

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) ![License MIT](https://img.shields.io/badge/license-MIT-green) ![Tests 448 passing](https://img.shields.io/badge/tests-448%20passing-brightgreen) ![Coverage 91%](https://img.shields.io/badge/coverage-91%25-brightgreen)

---

**Stop sending cold emails nobody reads.** SignalForce finds companies that are actively investing in your domain *right now* — by monitoring GitHub repos, ArXiv papers, HuggingFace model uploads, job postings, funding announcements, and LinkedIn activity — then generates technically credible outreach that references the prospect's actual work, timed to the moment they're thinking about the problem you solve.

**For any vertical.** Whether you sell RL infrastructure, cybersecurity tools, data pipelines, or developer platforms — configure your ICP once and the engine handles the rest. Ships with 4 ready-to-use example configs.

**Two modes.** Run it hands-on with Claude Code skills (research, review, and refine at every step) or fully autonomous via n8n workflows on a daily schedule.

---

## Get Running in 2 Minutes

```bash
# 1. Clone and install
git clone https://github.com/sami2919/SignalForce.git
cd SignalForce
pip install -e ".[dev]"

# 2. Configure your ICP (pick one):
#    Option A — Setup wizard (recommended):
#    Open Claude Code and run /setup
#    It asks what you sell and who you sell to, then generates everything.
#
#    Option B — Copy an example config for your vertical:
cp -r examples/rl-infrastructure/ config/
#    (also available: examples/cybersecurity/, examples/devtools/, examples/data-infra/)

# 3. Add your API keys
cp .env.example .env
# Edit .env with your GitHub token (required) + other API keys (optional)

# 4. Verify
pytest --tb=short -q   # 448 tests, should all pass
```

Open Claude Code and run `/signal-scanner` to find your first target accounts.

---

## Your Weekly Workflow

Here's what a typical week looks like using SignalForce:

| When | What | Skill |
|------|------|-------|
| **Monday morning** | Scan for new signals across all sources | `/signal-scanner` |
| **Monday** | Research top 10 A-tier accounts | `/prospect-researcher` |
| **Tuesday** | Find verified contacts at qualified accounts | `/contact-finder` |
| **Tuesday** | Generate personalized outreach sequences | `/email-writer` or `/resource-offer` |
| **Wednesday** | Add LinkedIn touches to high-priority prospects | `/multi-channel-writer` |
| **Thursday** | Follow up on meetings from the week | `/meeting-followup` |
| **Friday** | Review pipeline metrics, plan next week | `/pipeline-tracker` |

Or set up the n8n workflows and let it run autonomously — signals detected at 7am, contacts enriched by 8am, sequences launched by 9am, every day.

---

## How It Works

Three decoupled layers move data from raw public signals to enrolled sequences and CRM deals.

```
┌─────────────────────────────────────────────────────────────────┐
│                        SIGNAL SOURCES                            │
│  GitHub Repos  ArXiv Papers  HF Models  Jobs  Funding  LinkedIn │
└──────────────────────────┬──────────────────────────────────────┘
                           │ raw API responses / activity data
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CONFIG LOADER + SCANNERS                       │
│  config_loader.py reads config/config.yaml                       │
│  scanners/github_scanner  scanners/arxiv_scanner                 │
│  scanners/hf_scanner  scanners/job_scanner                       │
│  scanners/funding_scanner  scanners/linkedin_scanner             │
│                   → Signal objects (typed JSON)                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ ScanResult JSON → CompanyProfile (ranked)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLAUDE CODE SKILLS                             │
│  signal-scanner  prospect-researcher  contact-finder             │
│  email-writer  resource-offer  multi-channel-writer              │
│  meeting-followup  pipeline-tracker  champion-tracker            │
│  deliverability-manager  compliance-manager  setup  validate     │
│                   → Human-in-the-loop GTM workflow               │
└──────────────────────────┬──────────────────────────────────────┘
                           │ contacts + email copy + deal events
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    n8n AUTOMATION                                 │
│  daily-signal-scan → enrichment-pipeline                         │
│  → sequence-launcher → crm-sync                                  │
│  Instantly.ai sequences, HubSpot deals, Slack alerts             │
└─────────────────────────────────────────────────────────────────┘
```

**Skills** are the primary interface. Each `SKILL.md` tells Claude how to perform a GTM task using the Python scripts as tools. The same scripts also power the n8n workflows — no code duplication between human-driven and automated paths.

---

## Available Skills

Invoke skills in Claude Code with `/skill-name`.

| Skill | When to Use |
|-------|-------------|
| `/setup` | First-time setup — configure your ICP, signal keywords, and voice rules |
| `/validate` | Verify your config is complete and all API keys are working |
| `/signal-scanner` | Weekly: run all scanners, stack signals, get a ranked account table |
| `/prospect-researcher` | Before outreach: deep-dive a company, score ICP fit, map decision-makers |
| `/contact-finder` | After qualification: waterfall enrichment for verified email + LinkedIn |
| `/email-writer` | After enrichment: generate 3-variant signal-based outreach sequences |
| `/resource-offer` | Blueprint-first alternative: offer a resource before asking for a meeting |
| `/multi-channel-writer` | Staggered Email + LinkedIn sequences for dual-channel outreach |
| `/meeting-followup` | After a call: extract outcome, generate follow-up emails, update CRM |
| `/pipeline-tracker` | Weekly: funnel metrics, HubSpot sync, Slack analytics digest |
| `/champion-tracker` | Weekly: monitor job changes, route warm re-engagement |
| `/deliverability-manager` | Domain setup: DNS records, warmup schedules, blacklist monitoring |
| `/compliance-manager` | Monthly: CAN-SPAM/GDPR/CCPA/CASL audit checklist |

---

## Examples

`examples/` contains complete, ready-to-use ICP configurations for four verticals. Copy any one to `config/` as your starting point.

| Example | Target Market | Signal Focus |
|---------|--------------|--------------|
| `rl-infrastructure/` | Reinforcement learning research teams and AI labs | GitHub RL repos, ArXiv RLHF papers, HF model uploads |
| `cybersecurity/` | Security engineering teams at mid-market companies | GitHub security tooling, job postings for SecEng roles |
| `data-infra/` | Data engineering and platform teams | GitHub data pipeline repos, dbt/Spark job postings |
| `devtools/` | Developer tooling buyers at high-growth startups | GitHub activity, funding events, DevEx hiring signals |

Each example contains `config.yaml`, `gtm-context.md`, and a scoring rubric pre-tuned for that vertical.

---

## Configuration

SignalForce is ICP-agnostic. Your target market, signal keywords, ICP tiers, and voice rules live in `config/`:

```
config/               # gitignored — your active config
├── config.yaml       # scanner keywords, scoring weights, ICP tier definitions
└── gtm-context.md    # product positioning, voice rules, qualification criteria
```

`config.yaml` controls what the scanners look for:

```yaml
company:
  name: "My Company"
  product: "What you sell in one line"
  category: "Your market category"

icp:
  tiers:
    - name: "Tier 1 — Enterprise"
      description: "Large orgs with dedicated teams"
      signals: ["large team", "Series B+"]
    - name: "Tier 2 — Mid-Market"
      description: "Growing companies building capability"
      signals: ["growing team", "Series A"]
  maturity_stages: ["EXPLORING", "BUILDING", "SCALING", "EMBEDDED"]
  target_titles: ["Head of Platform", "Staff Engineer", "VP Engineering"]

scanners:
  github:
    enabled: true
    module: scripts.scanners.github_scanner
    keywords: ["your-domain-keyword"]
    topics: ["your-github-topic"]
    libraries: ["key-library-1", "key-library-2"]
  arxiv:
    enabled: true
    module: scripts.scanners.arxiv_scanner
    queries: ["your research area", "related technique"]
  jobs:
    enabled: true
    module: scripts.scanners.job_scanner
    titles: ["Your Target Role 1", "Your Target Role 2"]
    skills: ["key-skill-1", "key-skill-2"]

scoring:
  intent_weights:   # higher = stronger buying signal
    github: 2.5
    arxiv: 3.0
    jobs: 2.0
    funding: 1.5
    linkedin: 3.0
```

`gtm-context.md` is a natural-language file loaded by every skill — it tells Claude about your product, your ICP, your voice rules, and your disqualification criteria.

See `config.example/` for a fully annotated reference configuration, or run `/setup` in Claude Code for a guided setup wizard.

### Environment Variables

All API keys live in `.env` (gitignored). Copy `.env.example` and fill in your keys. Only `GITHUB_TOKEN` is required to run the scanners. Enrichment and CRM keys can be added incrementally.

---

## Custom Scanners

SignalForce ships with six built-in scanners. You can add your own by implementing the scanner interface:

```python
# scripts/scanners/my_scanner.py
from datetime import datetime, UTC
from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

def scan(config: ScannerConfig) -> ScanResult:
    """Fetch signals from your source and return typed results."""
    started = datetime.now(UTC)
    signals = []
    # ... your API calls using config.keywords here ...
    return ScanResult(
        scan_type="my_signal_type",
        started_at=started,
        completed_at=datetime.now(UTC),
        signals_found=signals,
        total_raw_results=len(signals),
        total_after_dedup=len(signals),
    )
```

Then register the module path in `config.yaml`:

```yaml
scanners:
  my_source:
    enabled: true
    module: scripts.scanners.my_scanner
    keywords: ["what-to-search-for"]
```

The scanner runner picks it up automatically — works in both Claude Code skills and n8n workflows.

---

## External APIs

| API | Purpose | Key Required |
|-----|---------|-------------|
| GitHub API | Repo detection | Yes (`GITHUB_TOKEN`) |
| Semantic Scholar | ArXiv paper tracking | Optional (rate limited without) |
| HuggingFace Hub | Model upload detection | No (public API) |
| Apollo.io | Contact enrichment (waterfall step 1) | Yes (`APOLLO_API_KEY`) |
| Hunter.io | Contact enrichment (waterfall step 2) | Yes (`HUNTER_API_KEY`) |
| Prospeo | LinkedIn email enrichment (waterfall step 3) | Yes (`PROSPEO_API_KEY`) |
| ZeroBounce | Email verification | Yes (`ZEROBOUNCE_API_KEY`) |
| Anthropic API | Email copy generation in sequence-launcher | Yes (`ANTHROPIC_API_KEY`) |
| Instantly.ai | Sequence enrollment and delivery events | Yes (`INSTANTLY_API_KEY`) |
| HubSpot | Deal and contact CRM | Yes (`HUBSPOT_ACCESS_TOKEN`) |

---

## Results

Target metrics at steady state (Month 3):

| Metric | Target | Industry Median |
|--------|--------|----------------|
| Open rate | 45–65% | 20–30% |
| Reply rate | 12–20% | 3–5% |
| Positive reply rate | 5–8% | 1–2% |
| Meetings booked/month | 15–30 | — |
| Cost per meeting | $25–50 | — |

Signal-based outreach targets 12–20% reply rate because every email references a specific, recent, real action the prospect took — not a static list attribute.

See [`docs/results-framework.md`](docs/results-framework.md) for full metric definitions, monthly ramp targets, and diagnostic playbooks.

---

## Cost

| Tier | Monthly Cost | Sequences/Week |
|------|-------------|----------------|
| Minimal | ~$61–81 | 10–20 |
| Standard | ~$206–226 | 80–150 |
| Premium | ~$670–740 | 150+ |

The Minimal tier runs on n8n Cloud ($24/mo) + Instantly.ai ($37/mo) + Claude API (~$10–20/mo). All signal scanners use free APIs. See [`docs/cost-analysis.md`](docs/cost-analysis.md) for a tool-by-tool breakdown.

---

## Contributing

See [`docs/architecture.md`](docs/architecture.md) for full system design documentation.

**Adding a new scanner:** Implement `scan(ScannerConfig) -> ScanResult` in `scripts/scanners/`, add the module path to `config.yaml`, add tests mocking all HTTP calls.

**Adding a new skill:** Create `skills/your-skill/SKILL.md` with YAML frontmatter (`name`, `description`). The `description` must start with "Use when..." — this is how Claude selects the right skill.

**Code conventions:** Pydantic models with `frozen=True` for all data structures. Type hints required. Ruff for formatting (`ruff format . && ruff check . --fix`). 80% minimum test coverage.

---

## License

MIT — see [LICENSE](LICENSE).
