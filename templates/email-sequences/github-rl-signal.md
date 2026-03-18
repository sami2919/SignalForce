# Email Template: GitHub RL Signal

## Signal Context

Triggered when a company has one or more active public GitHub repositories demonstrating RL work — Gymnasium environments, policy gradient implementations, reward modeling code, sim-to-real pipelines, or custom training harnesses. Recent commits (within 90 days) indicate active development, not a dormant experiment. The repo is your conversation hook — you have reviewed it.

---

## Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{contact_first_name}}` | Recipient's first name |
| `{{company_name}}` | Company name |
| `{{repo_name}}` | Repository name (e.g., `acme/rl-trading-env`) |
| `{{repo_focus}}` | Short description of what the repo does (e.g., "custom MuJoCo environment for robotic grasping") |
| `{{technical_detail}}` | Specific detail from the repo: a file, pattern, or implementation choice that shows you looked |
| `{{rl_method}}` | RL method used in the repo (e.g., PPO, SAC, GRPO) |
| `{{pain_point}}` | The scaling or maintenance challenge implied by their current approach |
| `{{signal_reference}}` | GitHub repo URL |
| `{{sender_name}}` | Sender's full name |

---

## Variant A — Problem-Focused

### Email 1 (Day 0)

**Subject:** Scaling {{repo_focus}} past the bespoke stage

{{contact_first_name}}, came across {{repo_name}} — the {{technical_detail}} approach is solid for early-stage work, but maintaining a custom environment alongside {{rl_method}} training at scale tends to become a serious engineering tax. Collinear generates and manages production-grade Gymnasium-compatible environments from your existing data, so the environment layer stops being a bottleneck. Worth 20 minutes to see if it maps to where {{company_name}} is headed?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: Scaling {{repo_focus}} past the bespoke stage

{{contact_first_name}}, one pattern we see often with teams at {{company_name}}'s stage: as the number of training scenarios grows, the in-house environment codebase starts diverging from production behavior in subtle ways. Attaching a short case study on how Kore.ai used managed environments to cut that drift and improve agent performance by 91% — might be a useful data point.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: Scaling {{repo_focus}} past the bespoke stage

{{contact_first_name}}, figured this might not be on the radar right now — environment infrastructure tends to become urgent right when you're trying to scale experiment throughput. Happy to revisit whenever the timing is better.

— {{sender_name}}

---

## Variant B — Outcome-Focused

### Email 1 (Day 0)

**Subject:** More experiments per sprint from {{repo_name}}

{{contact_first_name}}, reviewed {{repo_name}} — specifically the {{technical_detail}} — and it's clear your team is serious about {{rl_method}}. The ceiling for bespoke environments is usually environment diversity: the more scenarios you need to cover, the slower new experiment cycles get. Collinear plugs in as a Gymnasium-compatible managed layer so you can run 10x more training configurations without growing the infra team. Is a 20-minute technical walkthrough worth it?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: More experiments per sprint from {{repo_name}}

{{contact_first_name}}, our ServiceNow collaboration involved a similar challenge — enterprise workflow environments that needed to stay synchronized with production system state. Happy to walk through the technical architecture if the fidelity problem is something your team is hitting.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: More experiments per sprint from {{repo_name}}

{{contact_first_name}}, closing the loop — if custom environments are working well enough for now, that's a totally reasonable place to be. If the calculus changes when you're hiring your third RL engineer, feel free to reach out.

— {{sender_name}}

---

## Variant C — Social-Proof-Focused

### Email 1 (Day 0)

**Subject:** {{company_name}}'s {{rl_method}} environment layer

{{contact_first_name}}, {{repo_name}} shows you're doing real {{rl_method}} work — the {{technical_detail}} implementation in particular. Kore.ai was in a similar position building custom Gymnasium environments; after switching to Collinear they got 91% better agent performance and stopped maintaining environment code altogether. Curious whether {{pain_point}} is something {{company_name}} is actively solving. Worth a 20-minute call?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{company_name}}'s {{rl_method}} environment layer

{{contact_first_name}}, we published a technical comparison of managed vs. in-house environment approaches last month — covers maintenance burden, environment diversity, and time-to-first-experiment benchmarks. Sharing in case it's useful context: [insert link].

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{company_name}}'s {{rl_method}} environment layer

{{contact_first_name}}, stepping back — if the in-house approach is the right call for where {{company_name}} is today, I respect that. Reach out if the calculus shifts.

— {{sender_name}}
