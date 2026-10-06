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

## Production system: watch, verify, score

Beyond the config-driven scanners, `main` includes a persistent, multi-tenant pipeline that watches accounts continuously and measures its own accuracy. It is built from small, separately documented decisions (24 ADRs in [`docs/decisions/`](docs/decisions/)), and operated per [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

| Layer | What it does |
|---|---|
| **Storage** | Postgres with a tenant-scoped schema, SQLAlchemy and Alembic migrations |
| **Watch** | A daily worker probes each account's registered sources (careers pages, repos) with per-host politeness, and re-fetches to confirm a change before recording it |
| **Verify** | Extracts the underlying fact from a changed page, diffs it, and gates spend with a budget |
| **Measure** | An hourly holdout deep scan estimates **recall** and **detection lag**; source-health metrics flag sources that go quiet or unstable |
| **Score** | A scoring engine over verified `signal_events`, with personas and composable audiences, and a read-only dashboard |
| **Outcome loop** | Outreach is recorded, an AgentMail webhook captures replies, and cohort-lift analysis only reports a number once the sample is large enough to mean something |
| **Export** | A tenant's data can be written out as input for [Signal Audit](https://github.com/sami2919/signal-audit) |

It deploys to Fly.io (a web app plus daily and hourly scheduled machines) against Neon Postgres. **Today it runs one tenant, the author's own outbound, and has no outside users.** The schema is multi-tenant, but the live pipeline is configured around that one ICP rather than driven by the `config/config.yaml` described above.

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
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) and [`docs/decisions/`](docs/decisions/): operating the production system and why it is built this way
- [`docs/fireworks-demo.md`](docs/fireworks-demo.md): the optional LLM brief layer, worked for one ICP

---

## Hosted version

An invite-only deployment runs Signal Audit as a web page: upload three CSVs, get the report. Files are held only for the one request (in memory and short-lived temporary files, including framework upload spooling) and deleted before the response is sent; nothing is stored or logged. See [`docs/decisions/0025-invite-only-web-access.md`](docs/decisions/0025-invite-only-web-access.md). To run it yourself, set `SESSION_SECRET` and `DATABASE_URL`, run `alembic upgrade head`, create an invite with `python -m scripts.web.invites create --label you --owner`, and start `uvicorn scripts.web.app:app`. Signed-in users can also keep a watchlist of up to 25 company domains that the daily worker scans, then audit those signals against their CRM outcomes. Outbound fetches refuse non-public addresses; see [`docs/decisions/0026-outbound-request-guard.md`](docs/decisions/0026-outbound-request-guard.md).

Before the first deploy: the image installs `signal-audit` from the tarball of tag `v0.2.0` of github.com/sami2919/signal-audit, and that tag must exist and contain `signal_audit/service.py` (today it is on the signal-audit branch `feat/audit-uploads`, commit `590e93f`, not on `main`). Merge that branch (or tag `590e93f`), tag `v0.2.0`, push the tag, check `curl -sIL https://github.com/sami2919/signal-audit/archive/refs/tags/v0.2.0.tar.gz | grep -m1 '^HTTP'` prints 200, run `fly secrets set SESSION_SECRET=...`, then deploy. If you skip this and the tag lacks `service.py`, the image builds but the app fails on import at boot, so the health check fails. The full steps are in [`docs/RUNBOOK.md`](docs/RUNBOOK.md) section 9.

## Tests

```bash
pytest --tb=short -q
```

The suite has 1,313 tests and all pass on the current `main`.

---

## Contributing

**Adding a scanner:** implement `scan(ScannerConfig) -> ScanResult` in `scripts/scanners/`, add the module path to your config, and add tests that mock all HTTP calls.

**Adding an ICP example:** copy an existing directory in `examples/`, change the keywords and weights, and the config test will check it loads.

**Code conventions:** Pydantic models with `frozen=True` for all data structures. Type hints required. Ruff for formatting (`ruff format . && ruff check . --fix`). 80% minimum test coverage.

---

## License

MIT. See [LICENSE](LICENSE).
