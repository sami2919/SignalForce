# GTM Context: Collinear AI

Shared context loaded by all rl-gtm-engine skills. Reference this file for company positioning, ICP definitions, messaging guidelines, and qualification criteria.

---

## Company

| Field | Details |
|---|---|
| Name | Collinear AI |
| Category | Environment-as-a-Service for reinforcement learning |
| Founded | 2023 |
| Employees | ~16 |
| HQ | Mountain View, CA |
| Stage | Seed / Series A |
| CEO | Nazneen Rajani (Stanford, ex-Hugging Face) |

---

## Product

**Core offering:** Creates production-grade RL environments from enterprise proprietary data.

- Enterprises bring their workflows (Jira, ServiceNow, Shopify); Collinear builds configurable virtual worlds for agent training, evaluation, and data generation
- **Key differentiator:** Managed environments vs. building in-house (which is what most teams do today)
- **API compatibility:** Gymnasium-compatible — drop-in replacement for teams already using Gymnasium
- Covers training, evaluation, and synthetic data generation within a single managed platform

---

## ICP Tiers (Priority Order)

### Tier 1: AI Labs — Frontier Model Training

| Field | Details |
|---|---|
| Target companies | OpenAI, Anthropic, DeepMind, Mistral, Cohere, xAI, Meta AI |
| Buyer signal | Active RLHF / GRPO / reward modeling work |
| Decision makers | Head of Post-Training, RL Research Lead |
| Why they buy | Need diverse, high-quality environments for RLHF at scale |
| Deal size | $200K–$1M+ ARR |

### Tier 2: Enterprise AI Agent Builders

| Field | Details |
|---|---|
| Target companies | Companies building LLM-powered agents for enterprise workflows |
| Buyer signal | Integrating LLMs with Jira / ServiceNow / Shopify / Salesforce |
| Decision makers | VP Engineering, Head of AI/ML |
| Why they buy | Need safe training environments that mirror real enterprise systems |
| Deal size | $100K–$500K ARR |

### Tier 3: Robotics & Autonomous Systems

| Field | Details |
|---|---|
| Target companies | Companies using RL for policy learning in physical systems |
| Buyer signal | Sim-to-real transfer work, custom Gymnasium environments |
| Decision makers | Head of Simulation, Principal Robotics Engineer |
| Why they buy | Need high-fidelity simulation environments |
| Deal size | $100K–$300K ARR |

### Tier 4: Industry-Specific RL Users

| Field | Details |
|---|---|
| Target verticals | Finance (trading), Energy (grid optimization), Gaming (NPC behavior), RecSys |
| Buyer signal | Domain-specific RL publications or repos |
| Decision makers | VP Engineering, Head of ML |
| Why they buy | Need environments modeling their specific domain |
| Deal size | $50K–$200K ARR |

---

## Target Titles (Priority Order)

1. Head of ML / Director of ML / VP of Machine Learning
2. Head of AI / VP of AI
3. Principal ML Engineer / Staff ML Engineer
4. VP Engineering / CTO (at companies with fewer than 100 employees)
5. RL-specific: RL Engineer, Simulation Engineer, Reward Modeling Lead

---

## Voice & Tone

**Persona:** Technical peer, not sales rep.

**Always do:**
- Lead with their problem, not Collinear's features
- Reference specific technical work (their papers, repos, models, job postings)
- Use correct technical terminology (RLHF, GRPO, sim-to-real, policy gradient, etc.)
- Keep initial outreach to 4 sentences maximum
- Use low-friction CTAs (e.g., "worth a 20-minute call?" not "schedule a demo")

**Never use:**
- "I hope this email finds you well"
- "I noticed your company"
- "touching base"
- Generic feature lists without tying them to the prospect's specific context
- Vague CTAs like "let me know if you're interested"

---

## Competitors

| Competitor | Notes |
|---|---|
| In-house builds | Primary competitor — most teams DIY their RL environments today |
| Idler | RL environment platform, early stage |
| Mechanize | AI agent training environments |
| Applied Compute | Compute layer for RL training (adjacent, not direct) |
| Osmosis | Environment generation |

**Positioning against in-house:** The build-vs-buy argument. Highlight maintenance burden, time-to-first-experiment, and environment diversity that a managed service provides vs. a single team's bespoke solution.

---

## Proof Points

| Customer | Result |
|---|---|
| Kore.ai | 91% improvement in agent performance using Collinear environments |
| ServiceNow | Collaboration on enterprise workflow simulation |
| MasterClass | Partnership for content recommendation training |

---

## Disqualification Criteria

Disqualify a prospect if any of the following apply:

- No RL activity — no repos, no papers, no RL-related hiring, no released models with RL in the training stack
- Already using a competing managed solution and explicitly locked in
- Company too small (fewer than 10 employees) or too early (pre-product)
- Budget holder has explicitly stated they are building in-house and committed to that path

---

## Quick Reference: Signal Keywords

Use these to identify qualified prospects from public signals:

**Strong signals:**
- RLHF, GRPO, PPO, reward modeling, policy gradient, DPO, RLAIF
- Gymnasium, OpenAI Gym, MuJoCo, Isaac Sim
- Sim-to-real, environment generation, agent evaluation
- Job postings for: RL Engineer, Simulation Engineer, Post-Training Engineer, Reward Modeling

**Weak / disqualifying signals:**
- Pure supervised fine-tuning (no RL component)
- Classical ML / analytics only
- No ML/AI work at all
