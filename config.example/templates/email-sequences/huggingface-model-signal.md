# Email Template: Hugging Face Model Signal

## Signal Context

Triggered when a company or its researchers upload a model to Hugging Face Hub that was trained using RL techniques (RLHF, GRPO, DPO, PPO, RLAIF, reward modeling). Model card language, training stack metadata, and dataset references are the evidence. Publishing to HF Hub signals the team is past the research stage — they have a working training pipeline and are sharing artifacts, which implies they are iterating on environments and training configurations at scale.

---

## Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{contact_first_name}}` | Recipient's first name |
| `{{company_name}}` | Company name |
| `{{model_name}}` | HF Hub model name (e.g., `acme-ai/rl-agent-v2`) |
| `{{training_method}}` | RL training method used (e.g., GRPO, RLHF, PPO) |
| `{{model_domain}}` | What the model does (e.g., "enterprise workflow agent", "robotic manipulation policy") |
| `{{model_detail}}` | Specific technical detail from the model card: training data, reward function, environment setup |
| `{{environment_implication}}` | The environment challenge implied by their training setup |
| `{{signal_reference}}` | HF Hub model URL |
| `{{sender_name}}` | Sender's full name |

---

## Variant A — Problem-Focused

### Email 1 (Day 0)

**Subject:** {{training_method}} environment layer behind {{model_name}}

{{contact_first_name}}, saw {{model_name}} on Hugging Face — the {{model_detail}} in the model card shows serious {{training_method}} work. The part that rarely makes it into model cards: the environment infrastructure required to get there, and the ongoing cost of maintaining it as you iterate on reward functions and training distributions. Collinear manages that environment layer so your team can focus on the model, not the scaffolding. Worth 20 minutes?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{training_method}} environment layer behind {{model_name}}

{{contact_first_name}}, Kore.ai was running a similar {{training_method}} pipeline before adopting Collinear — after the switch, agent performance improved 91% and environment maintenance dropped off the engineering backlog entirely. Happy to share the architecture comparison if it helps frame the build-vs-buy decision.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{training_method}} environment layer behind {{model_name}}

{{contact_first_name}}, figured this might not be a priority right now — environment infrastructure tends to become urgent when you're preparing the next training run or onboarding a new RL engineer. Feel free to reach out then.

— {{sender_name}}

---

## Variant B — Outcome-Focused

### Email 1 (Day 0)

**Subject:** Faster {{training_method}} iteration at {{company_name}}

{{contact_first_name}}, {{model_name}} demonstrates you're running real {{training_method}} pipelines for {{model_domain}}. The bottleneck for teams at this stage is usually environment diversity and iteration speed — each new reward function or distribution shift requires environment changes that slow down the experiment cycle. Collinear generates Gymnasium-compatible environments from your existing data and keeps them synchronized with production, so iteration time drops significantly. Is a 20-minute technical walkthrough useful?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: Faster {{training_method}} iteration at {{company_name}}

{{contact_first_name}}, our work with ServiceNow on enterprise workflow simulation involved a very similar challenge to {{environment_implication}} — environments that needed to reflect real system state to produce valid training signal. Happy to walk through how we approached that architecture.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: Faster {{training_method}} iteration at {{company_name}}

{{contact_first_name}}, closing the loop — if your current environment setup is working well enough for the next training run, that's a fine place to be. Reach out if the calculus shifts.

— {{sender_name}}

---

## Variant C — Social-Proof-Focused

### Email 1 (Day 0)

**Subject:** {{company_name}}'s {{training_method}} pipeline — environment layer

{{contact_first_name}}, {{model_name}} on HF Hub puts {{company_name}} in the same category as teams we work with who are doing serious {{training_method}} for {{model_domain}}. Kore.ai saw a 91% improvement in agent performance after moving their RL environment layer to Collinear; MasterClass uses the same infrastructure for recommendation policy training. Given {{model_detail}}, I suspect there's a fit. Worth a 20-minute call?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{company_name}}'s {{training_method}} pipeline — environment layer

{{contact_first_name}}, we published a technical overview of how managed environments accelerate {{training_method}} iteration cycles — includes benchmarks on experiment throughput vs. in-house approaches. Sharing in case it's useful: [insert link].

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{company_name}}'s {{training_method}} pipeline — environment layer

{{contact_first_name}}, stepping back — {{model_name}} is impressive work regardless. If environment infrastructure becomes a conversation as you scale the pipeline, feel free to reach out.

— {{sender_name}}
