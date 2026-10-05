# SignalForce

> **An open-source, config-driven GTM signal engine. Point it at any ICP.** It watches public activity for companies that are *actively* investing in the problem you solve, stacks the signals, and ranks accounts by fit and timing.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) ![License MIT](https://img.shields.io/badge/license-MIT-green)

A static account list tells you who *fits* your ICP. It does not tell you who is in a buying window right now. SignalForce reads the public trail a buying team leaves behind (repos, job posts, papers, model uploads, funding, LinkedIn activity), scores each account on **fit** and **intent**, and gives you a ranked list with the evidence behind every score.

**Nothing about the engine is specific to one market.** Your ICP, signal keywords, scoring weights and target titles live in one YAML file. Moving from selling API security to selling inference infrastructure is a config change, not a code change.

---

## One engine, any ICP

The Python scripts are a thin signal-collection layer: they fetch and filter whatever your config asks for. Everything market-specific lives in `config/config.yaml`:

- **ICP tiers**: who you sell to, with the signals that identify each tier
- **Scanner settings**: GitHub topics and libraries, arXiv queries, Hugging Face tags, job titles and skills, funding keywords, LinkedIn keywords
- **Scoring**: intent weight per signal type, recency half-lives, fit-versus-intent balance, and grade thresholds
- **Target titles and disqualifiers**: who to contact and what rules an account out

Seven example configurations ship in [`examples/`](examples/). Copy one to `config/` and you are scanning a different market:

| Example | What the ICP is selling | Category |
|---|---|---|
| [`inference-infra`](examples/inference-infra/config.yaml) | Managed LLM inference and serving | AI inference infrastructure |
| [`rl-infrastructure`](examples/rl-infrastructure/config.yaml) | Environment-as-a-Service for reinforcement learning | RL infrastructure |
| [`cybersecurity`](examples/cybersecurity/config.yaml) | API security testing | Application security / DevSecOps |
| [`data-infra`](examples/data-infra/config.yaml) | Data pipeline orchestration | Data infrastructure |
| [`devtools`](examples/devtools/config.yaml) | Developer productivity platform | Developer tooling |
| [`kana-ai-first`](examples/kana-ai-first/config.yaml) | Agentic marketing platform | AI-first demand generation |
| [`map-migration`](examples/map-migration/config.yaml) | Lifecycle campaign orchestration | Marketing automation |

A test ([`tests/test_example_configs.py`](tests/test_example_configs.py)) loads every example through the real config loader, so each one is known to be valid.

---

## Worked example: an inference-infrastructure ICP

Take a vendor of open-source-based LLM inference and serving (the vLLM ecosystem). Its buyers are teams for whom latency or GPU cost has become a real problem, and those teams leave signals long before they talk to anyone. [`examples/inference-infra/config.yaml`](examples/inference-infra/config.yaml) maps them:

| Source | What it watches for | Why it indicates a buying window |
|---|---|---|
| **GitHub** | Repos using `vllm`, `sglang`, `tensorrt-llm`, Triton; topics such as `llm-serving`, `speculative-decoding` | The team runs models itself, so the serving layer is a live decision |
| **Jobs** | Inference engineer, LLM serving engineer, GPU infrastructure engineer | Hiring for this role means the cost or scale problem is funded and owned |
| **Hugging Face** | Quantized uploads (AWQ, GPTQ, GGUF, FP8) | The team is optimising models for serving |
| **arXiv** | KV cache, continuous batching, speculative decoding | Research-led teams building serving expertise |
| **Funding** | AI-infrastructure and AI-native rounds | New budget, new GPU spend |
| **LinkedIn** | Posts about inference latency, GPU cost, vLLM | Public pain, in the buyer's own words |

Each signal carries a weight and a recency half-life, and the stacker rewards **independent sources agreeing**: the summed signal strength is multiplied by ×1.5 for two distinct signal types, ×2 for three and ×3 for four or more. An account with a serving-library repo, an inference-engineer job post and a GPU-cost post therefore ranks above one with a single loud signal. In this config, hiring and serving-library adoption carry the most weight (3.0 each), because they show the problem is owned and funded. Funding news weighs 1.5, because it shows budget, not need.

**The same pattern fits any ICP where buying intent leaves a public trail**, which includes most developer-tools, infrastructure and AI vendors. To adapt it, change the keywords and weights, not the code.

**If you already have strong inbound**, the scoring layer is source-agnostic: signals in, ranked accounts out. A [custom scanner](#custom-scanners) can feed it your own signals alongside the public ones, so the accounts reaching out to you and the accounts you would reach out to share one ranking.

---

## Get running

```bash
git clone https://github.com/sami2919/SignalForce.git
cd SignalForce
pip install -e ".[dev]"

# Pick your ICP: either a shipped example or your own
cp -r examples/inference-infra/ config/        # or cybersecurity, data-infra, devtools, ...

cp .env.example .env                           # add GITHUB_TOKEN (required) and optional keys
pytest --tb=short -q
```

Then open Claude Code and run `/signal-scanner` to find your first target accounts. Or run `/setup`, which asks what you sell and who you sell to and generates the config for you.

### Two ways to run it

**Hands-on, with Claude Code skills.** Research, review and refine at every step: `/signal-scanner` (rank accounts), `/prospect-researcher` (deep-dive one), `/contact-finder`, `/email-writer`, `/multi-channel-writer`, `/meeting-followup`, `/pipeline-tracker`, plus `/setup` and `/validate`. Skills are listed in [`skills/`](skills/).

**Autonomous, with n8n.** Four importable workflows in [`n8n-workflows/`](n8n-workflows/) (`daily-signal-scan` → `enrichment-pipeline` → `sequence-launcher` → `crm-sync`) run the same scripts on a schedule. See [`docs/n8n-setup-guide.md`](docs/n8n-setup-guide.md).

---

## How it works

Three decoupled layers move data from raw public signals to ranked accounts and outreach.

```
┌─────────────────────────────────────────────────────────────────┐
│                        SIGNAL SOURCES                            │
│  GitHub Repos  ArXiv Papers  HF Models  Jobs  Funding  LinkedIn │
└──────────────────────────┬──────────────────────────────────────┘
                           │ raw API responses / activity data
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CONFIG LOADER + SCANNERS                       │
│  config_loader.py reads config/config.yaml (your ICP)            │
│  scanners/*  →  typed Signal objects                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │ ScanResult → CompanyProfile (ranked)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              SCORING + CLAUDE CODE SKILLS                         │
│  Intent scoring with recency decay, ICP fit, signal stacking     │
│  Research, contact finding, copywriting (human in the loop)      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ contacts + copy + deal events
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    n8n AUTOMATION (optional)                      │
│  Daily scan → enrichment → sequences → CRM sync                  │
└─────────────────────────────────────────────────────────────────┘
```

An optional LLM layer turns signals into structured account briefs (fit score, why-now, persona, outreach angle) using either Claude or Fireworks as the backend. See [`docs/fireworks-demo.md`](docs/fireworks-demo.md) for one worked ICP built that way.

---

## Signal scanners

Six built-in scanners collect live signals:

| Scanner | Source | Key required |
|---|---|---|
| GitHub | Repo detection | `GITHUB_TOKEN` |
| ArXiv | Research paper tracking | Optional (Semantic Scholar) |
| HuggingFace | Model upload detection | No (public API) |
| Jobs | Job posting scanner | `SERPAPI_KEY` |
| Funding | Funding round scanner | `SERPAPI_KEY` |
| LinkedIn | LinkedIn activity | `SERPAPI_KEY` |

Each scanner returns typed `Signal` objects with configurable keywords, scoring weights and ICP tier definitions.

### Custom scanners

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

## Docs

- [`docs/user-guide.md`](docs/user-guide.md) and [`docs/setup-guide.md`](docs/setup-guide.md): setup and day-to-day use
- [`docs/architecture.md`](docs/architecture.md): how the layers fit together
- [`docs/n8n-setup-guide.md`](docs/n8n-setup-guide.md): autonomous operation
- [`docs/fireworks-demo.md`](docs/fireworks-demo.md): the optional LLM brief layer, worked for one ICP

---

## Tests

```bash
pytest --tb=short -q
```

The suite has 695 tests. At the time of writing, 693 pass and 2 fail: `tests/marops/test_cli.py::test_run_happy_path` and `tests/test_fireworks_client.py::TestAppConfigIntegration::test_appconfig_fireworks_defaults_none`. Both predate the config examples and are unrelated to the engine's scanners and scoring.

---

## Contributing

**Adding a scanner:** implement `scan(ScannerConfig) -> ScanResult` in `scripts/scanners/`, add the module path to your config, and add tests that mock all HTTP calls.

**Adding an ICP example:** copy an existing directory in `examples/`, change the keywords and weights, and the config test will check it loads.

**Code conventions:** Pydantic models with `frozen=True` for all data structures. Type hints required. Ruff for formatting (`ruff format . && ruff check . --fix`). 80% minimum test coverage.

---

## License

MIT. See [LICENSE](LICENSE).
