# SignalForce x Fireworks AI: LLM account-brief demo

This is one worked example of SignalForce pointed at a single ICP: companies building production AI
applications where inference matters. It shows the optional **LLM brief layer** (Fireworks as the inference
backend) turning raw signals into structured account intelligence.

The core engine is not specific to Fireworks or to this ICP. See the [README](../README.md) for the
config-driven engine and the other example verticals.

> The demo script reads a fixed ICP file and account file. To use the brief layer on a different ICP,
> point `ICP_PATH` and `ACCOUNTS_PATH` in `scripts/demo_fireworks_icp.py` at your own files.

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

## Tests

# Run just the Fireworks tests (39 tests)
pytest tests/test_fireworks_client.py tests/test_fireworks_briefer.py tests/test_fireworks_icp_config.py -v
```

Test coverage:

- **Fireworks client** — config resolution, client construction, agent building, completion helper, AppConfig integration
- **Fireworks briefer** — brief generation, JSON parsing, markdown stripping, error handling, why-now context
- **Fireworks ICP config** — config fields, signal categories, scoring weights, outbound angles, seed accounts, schema validation (fit_score range, linkedin_message length, non-empty lists, intent_level values)
