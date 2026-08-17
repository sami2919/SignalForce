# SignalForce

> **An open-source GTM intelligence engine that uses Fireworks AI to turn raw signals into structured account intelligence.**

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) ![License MIT](https://img.shields.io/badge/license-MIT-green) ![Tests 604 passing](https://img.shields.io/badge/tests-604%20passing-brightgreen) ![Fireworks AI](https://img.shields.io/badge/inference-Fireworks%20AI-orange)

SignalForce monitors public activity — GitHub repos, job postings, funding rounds, research papers, LinkedIn, G2 reviews — to find companies *actively* investing in a problem, then uses **Fireworks AI** as the inference layer to generate structured account intelligence: fit scores, why-now reasoning, pain points, buyer personas, and outreach angles.

Built as a Fireworks-powered GTM workflow demo.

---

**Stop sending cold emails nobody reads.** SignalForce monitors public activity — GitHub repos, job postings, funding rounds, research papers, LinkedIn — to find companies actively investing in the problem you solve, then generates outreach that references their actual work.

SignalForce uses Fireworks to convert raw GTM signals into structured account intelligence for AI companies with inference-heavy workloads.

What it does:

- Scans for signals using a Fireworks-targeted ICP (production AI apps, inference latency/cost, open-source models, AI infrastructure hiring)
- Uses Fireworks AI as the inference layer to analyze each account
- Returns structured JSON: fit score, intent level, matched signals, why-now reasoning, fireworks relevance, recommended persona, outbound angle, LinkedIn message, cold email
- Prints a polished terminal demo and saves results to `outputs/fireworks_icp_demo.json`

Run it:

```bash
git clone https://github.com/sami2919/signalforce-fireworks.git
cd signalforce-fireworks && pip install -e ".[dev]"

export FIREWORKS_API_KEY=your_key_here
python scripts/demo_fireworks_icp.py
```

---

## Fireworks AI Demo

The Fireworks demo configures SignalForce around companies building production AI applications where inference matters: speed, cost, scale, open-source model flexibility, and model customization.

### The workflow

1. Loads a Fireworks-style ICP ([`configs/icps/fireworks_ai.yaml`](configs/icps/fireworks_ai.yaml)).
2. Reads raw company signals from seeded demo accounts ([`examples/fireworks-demo/accounts.json`](examples/fireworks-demo/accounts.json)).
3. Uses Fireworks to generate structured account intelligence.
4. Outputs fit score, why-now reasoning, likely pain points, buyer persona, and outreach angle.
5. Saves structured JSON to `outputs/fireworks_icp_demo.json`.

### Run the demo

```bash
export FIREWORKS_API_KEY=your_key_here
python scripts/demo_fireworks_icp.py
```

Or via the CLI:

```bash
python -m scripts.marops.cli fireworks-demo
```

### Example output

```
🔥 SignalForce x Fireworks ICP Demo

  Using Fireworks as the inference layer to turn raw GTM signals
  into structured account intelligence.

  Loaded ICP:          fireworks_ai
  Loaded demo accounts: 3

  Top Fireworks-fit accounts:

  1. Voice AI Support Startup — 94/100
     Intent:           Urgent
     Why now:           Real-time voice workflows make inference latency a direct product bottleneck.
     Fireworks fit:     Fireworks can help serve low-latency inference for streaming AI interactions.
     Persona:           Head of AI Infrastructure
     Outbound angle:    Low-latency inference for production voice AI
     LinkedIn message:  Saw your team is hiring around real-time AI and streaming responses. Curious if inference latency has become a bottleneck as usage grows.
     Cold email:        Scaling real-time AI inference

  2. Cursor-like AI Coding Platform — 88/100
     ...

  3. Enterprise RAG Platform — 82/100
     ...

  Saved structured output to outputs/fireworks_icp_demo.json
```

### Why Fireworks?

Fireworks is a strong fit for this workflow because GTM automation needs fast, structured outputs that can plug into systems like Slack, HubSpot, or outbound tools.

SignalForce uses Fireworks to convert raw signals into predictable JSON fields:

- `fit_score`
- `intent_level`
- `matched_signals`
- `why_now`
- `fireworks_relevance`
- `recommended_persona`
- `outbound_angle`
- `linkedin_message`
- `cold_email_subject`
- `cold_email_body`

This demonstrates Fireworks powering a real business workflow, not just a chatbot.

### Fireworks ICP configuration

The ICP config at [`configs/icps/fireworks_ai.yaml`](configs/icps/fireworks_ai.yaml) defines what makes a company a strong Fireworks-fit account:

| Category | What it targets |
|---|---|
| **Ideal segments** | AI-native startups, developer tools, AI coding assistants, AI agents, voice AI, customer support AI, RAG/search, enterprise AI platforms, ML infrastructure, workflow automation AI |
| **Buyer personas** | CTO, VP Engineering, Head of AI, Head of Infrastructure, Head of ML Platform, Staff ML Engineer, Founding AI Engineer |
| **Positive signals** | Inference/ML infrastructure hiring, GitHub activity around vLLM/Triton/CUDA/agents, website mentions of low-latency/production AI, recent funding + AI product launches |
| **Scoring weights** | AI product signal (30), inference/latency signal (25), hiring signal (20), open-source model signal (15), funding/growth signal (10) |
| **Outbound angles** | Latency, cost, model flexibility, scale — each with trigger keywords and a pre-written angle |

### Seeded demo accounts

Three seeded accounts cover diverse AI inference use cases ([`examples/fireworks-demo/accounts.json`](examples/fireworks-demo/accounts.json)):

| Account | Industry | Key signals |
|---|---|---|
| Cursor-like AI Coding Platform | AI coding assistant | Low-latency code generation, open-source model evals, ML infra hiring |
| Voice AI Support Startup | Voice AI | Sub-second latency, streaming responses, Series A raised |
| Enterprise RAG Platform | Enterprise AI search | Multi-model support, inference cost content, enterprise expansion |

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                      SIGNAL INPUT                                │
│  Seeded accounts (or live scanners: GitHub, jobs, funding, etc) │
└──────────────────────────┬──────────────────────────────────────┘
                           │ raw company signals
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ICP CONFIG                                     │
│  configs/icps/fireworks_ai.yaml                                   │
│  Segments, personas, signals, scoring weights, outbound angles   │
└──────────────────────────┬──────────────────────────────────────┘
                           │ prompt + schema
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FIREWORKS AI INFERENCE                         │
│  scripts/fireworks_client.py → OpenAI-compatible API             │
│  scripts/marops/fireworks_icp_schema.py → FireworksICPBrief      │
│  Model: accounts/fireworks/models/glm-5p2                        │
│  → Structured JSON validated by Pydantic schema                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ FireworksICPBrief objects (ranked)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OUTPUT                                         │
│  Polished terminal display + outputs/fireworks_icp_demo.json     │
│  fit_score, intent_level, matched_signals, why_now,              │
│  fireworks_relevance, persona, angle, LinkedIn, cold email       │
└─────────────────────────────────────────────────────────────────┘
```

**The Python scripts collect and structure signals** — Fireworks AI does the reasoning: analyzing accounts against the ICP, scoring fit, identifying pain points, and generating outreach copy. The output is validated JSON that can plug into Slack, HubSpot, or outbound tools.

---

## Architecture

```
scripts/
├── fireworks_client.py              # Core Fireworks AI client (OpenAI-compatible)
├── demo_fireworks_icp.py            # Single-command demo script
├── config.py                        # AppConfig with Fireworks env vars
├── api_client.py                    # Base HTTP client with retry/backoff
├── icp_fit_scorer.py                # Keyword-based ICP fit scoring
├── intent_scorer.py                 # Signal intent scoring
├── signal_aggregator.py             # Multi-source signal aggregation
├── signal_stacker.py                # Signal stacking + ranking
├── models.py                        # Core Signal + CompanyProfile models
├── marops/
│   ├── fireworks_icp_schema.py      # FireworksICPBrief Pydantic schema
│   ├── fireworks_briefer.py         # Fireworks-powered brief generator
│   ├── briefer.py                   # Claude-powered brief generator (alternative)
│   ├── cli.py                       # CLI (--backend fireworks / fireworks-demo)
│   ├── models.py                    # MarOps brief models
│   └── renderer.py                  # Jinja2 HTML renderer
└── scanners/
    ├── github_scanner.py            # GitHub repo detection
    ├── job_scanner.py               # Job posting scanner
    ├── funding_scanner.py           # Funding round scanner
    ├── arxiv_scanner.py             # Research paper scanner
    ├── hf_scanner.py                # HuggingFace model scanner
    └── linkedin_scanner.py          # LinkedIn activity scanner

configs/
└── icps/
    └── fireworks_ai.yaml            # Fireworks ICP configuration

examples/
├── fireworks-demo/
│   └── accounts.json                # Seeded demo accounts
└── fireworks-agents/                # Reference implementation

tests/
├── test_fireworks_client.py         # 15 tests — client, config, agents
├── test_fireworks_briefer.py        # 7 tests — brief generation, JSON parsing
├── test_fireworks_icp_config.py     # 17 tests — config, accounts, schema
└── ...                              # 565 more tests across the engine
```

---

## Get Running in 2 Minutes

```bash
# 1. Clone and install
git clone https://github.com/sami2919/signalforce-fireworks.git
cd signalforce-fireworks
pip install -e ".[dev]"

# 2. Add your Fireworks API key
export FIREWORKS_API_KEY=your_key_here

# 3. Run the demo
python scripts/demo_fireworks_icp.py

# 4. Verify tests
pytest --tb=short -q   # 604 tests, should all pass
```


### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FIREWORKS_API_KEY` | Yes | — | Fireworks AI API key |
| `FIREWORKS_BASE_URL` | No | `https://api.fireworks.ai/inference/v1` | Fireworks inference endpoint |
| `FIREWORKS_MODEL` | No | `accounts/fireworks/models/glm-5p2` | Fireworks model ID |
| `GITHUB_TOKEN` | No | — | GitHub API token (for live scanners) |
| `ANTHROPIC_API_KEY` | No | — | Alternative Claude backend |

Copy `.env.example` to `.env` and fill in your keys.

---

## Fireworks Integration Details

### The key pattern

Fireworks model IDs contain slashes (`accounts/fireworks/models/glm-5p2`). Passing that directly as an OpenAI Agents SDK model name triggers `UserError: Unknown prefix: accounts`. The workaround in `scripts/fireworks_client.py`:

```python
from openai import AsyncOpenAI
from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled

set_tracing_disabled(True)  # Tracing posts to OpenAI; we're using Fireworks

client = AsyncOpenAI(
    base_url="https://api.fireworks.ai/inference/v1",
    api_key=fireworks_api_key,
)

agent = Agent(
    name="SignalAnalyzer",
    instructions="You analyze sales signals and rank accounts.",
    model=OpenAIChatCompletionsModel(
        model="accounts/fireworks/models/glm-5p2",
        openai_client=client,  # ← explicit client avoids the prefix error
    ),
    tools=[my_function_tool],
)

result = Runner.run_sync(agent, "Analyze these accounts...")
```

### Using the Fireworks client

```python
from scripts.fireworks_client import (
    build_fireworks_agent,
    run_agent_sync,
    fireworks_completion,
)

# Agent-based (with tools):
agent = build_fireworks_agent(
    name="MyAgent",
    instructions="You are a helpful assistant.",
    tools=[my_tool],
)
result = run_agent_sync(agent, "Hello")

# Simple completion (no agents SDK):
text = fireworks_completion(prompt="Write a poem.", temperature=0.7)
```

### FireworksICPBrief schema

The structured output schema ([`scripts/marops/fireworks_icp_schema.py`](scripts/marops/fireworks_icp_schema.py)):

| Field | Type | Validation |
|-------|------|------------|
| `account_name` | `str` | — |
| `fit_score` | `int` | 0–100 |
| `intent_level` | `Literal` | Low / Medium / High / Urgent |
| `matched_signals` | `list[str]` | Non-empty |
| `why_now` | `str` | — |
| `fireworks_relevance` | `str` | — |
| `likely_pain_points` | `list[str]` | Non-empty |
| `recommended_persona` | `str` | — |
| `outbound_angle` | `str` | — |
| `linkedin_message` | `str` | Under 500 characters |
| `cold_email_subject` | `str` | — |
| `cold_email_body` | `str` | — |

---

## Signal Scanners

SignalForce ships with six built-in scanners for live signal collection:

| Scanner | Source | Key Required |
|---------|--------|-------------|
| GitHub | Repo detection | `GITHUB_TOKEN` |
| ArXiv | Research paper tracking | Optional (Semantic Scholar) |
| HuggingFace | Model upload detection | No (public API) |
| Jobs | Job posting scanner | `SERPAPI_KEY` |
| Funding | Funding round scanner | `SERPAPI_KEY` |
| LinkedIn | LinkedIn activity | `SERPAPI_KEY` |

Each scanner returns typed `Signal` objects with configurable keywords, scoring weights, and ICP tier definitions.

### Custom Scanners

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

---

## Tests

```bash
# Run all 604 tests
pytest --tb=short -q

# Run just the Fireworks tests (39 tests)
pytest tests/test_fireworks_client.py tests/test_fireworks_briefer.py tests/test_fireworks_icp_config.py -v
```

Test coverage:

- **Fireworks client** — config resolution, client construction, agent building, completion helper, AppConfig integration
- **Fireworks briefer** — brief generation, JSON parsing, markdown stripping, error handling, why-now context
- **Fireworks ICP config** — config fields, signal categories, scoring weights, outbound angles, seed accounts, schema validation (fit_score range, linkedin_message length, non-empty lists, intent_level values)

---

## Contributing

**Adding a new scanner:** Implement `scan(ScannerConfig) -> ScanResult` in `scripts/scanners/`, add the module path to your config, add tests mocking all HTTP calls.

**Code conventions:** Pydantic models with `frozen=True` for all data structures. Type hints required. Ruff for formatting (`ruff format . && ruff check . --fix`). 80% minimum test coverage.

---

## License

MIT — see [LICENSE](LICENSE).
