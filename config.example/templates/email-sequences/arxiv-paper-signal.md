# Email Template: ArXiv Paper Signal

## Signal Context

Triggered when a company's researchers publish an RL-related paper on ArXiv (RLHF, GRPO, PPO, reward modeling, policy gradient, DPO, RLAIF, or environment design). This is a high-intent signal: the company is doing serious RL work, has a research function, and is actively pushing forward. The paper is your conversation hook — you have read it.

---

## Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{contact_first_name}}` | Recipient's first name |
| `{{company_name}}` | Company name |
| `{{paper_title}}` | Full title of the ArXiv paper |
| `{{paper_topic}}` | Short description of the paper's technical focus (e.g., "GRPO-based reward shaping") |
| `{{paper_specific_detail}}` | One specific technical detail from the paper (method, finding, or dataset) |
| `{{rl_method}}` | RL method referenced in the paper (e.g., PPO, GRPO, RLHF) |
| `{{environment_challenge}}` | The environment-related challenge implied by the paper (e.g., "high-variance reward environments") |
| `{{signal_reference}}` | Canonical signal reference: paper URL or ArXiv ID |
| `{{sender_name}}` | Sender's full name |

---

## Variant A — Problem-Focused

### Email 1 (Day 0)

**Subject:** {{paper_topic}} environments at scale

{{contact_first_name}}, read your paper on {{paper_topic}} — specifically interested in how you handled {{paper_specific_detail}}. The hardest part of scaling {{rl_method}} beyond research is building environments that are diverse, maintainable, and don't become a second full-time project for the team. Collinear builds production-grade RL environments from your existing workflows so your team can stay focused on the algorithm side. Worth a 20-minute call?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{paper_topic}} environments at scale

{{contact_first_name}}, one thing that came up for a team doing similar {{rl_method}} work: environment maintenance was consuming ~30% of engineering time before they switched to a managed approach. Sharing a short write-up on how Kore.ai cut that overhead while achieving a 91% improvement in agent performance — might be relevant given where you are in your research cycle.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{paper_topic}} environments at scale

{{contact_first_name}}, figured this might not be the right time — RL environment tooling tends to become urgent right when you're trying to scale beyond the research phase. If that moment arrives, I'm at {{sender_name}} and happy to pick this back up.

— {{sender_name}}

---

## Variant B — Outcome-Focused

### Email 1 (Day 0)

**Subject:** Faster iteration on {{rl_method}} environments

{{contact_first_name}}, your ArXiv paper on {{paper_topic}} caught my attention — specifically {{paper_specific_detail}}. Teams running {{rl_method}} at this fidelity typically spend months building and maintaining custom environments before they can run the experiments they actually care about. Collinear eliminates that setup time by generating production-grade environments directly from enterprise data sources. Would it be useful to see a 20-minute demo scoped to your {{environment_challenge}}?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: Faster iteration on {{rl_method}} environments

{{contact_first_name}}, our work with ServiceNow on enterprise workflow simulation might be directly relevant to your setup — they were facing a similar challenge with environment fidelity at scale. Happy to share the technical architecture doc if that would help contextualize the approach.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: Faster iteration on {{rl_method}} environments

{{contact_first_name}}, closing the loop — if environment infrastructure isn't the current bottleneck, no worries at all. The paper is genuinely interesting work and I'll keep an eye on follow-up publications.

— {{sender_name}}

---

## Variant C — Social-Proof-Focused

### Email 1 (Day 0)

**Subject:** {{company_name}} + Collinear on {{rl_method}} environments

{{contact_first_name}}, just finished reading {{paper_title}} — the approach to {{paper_specific_detail}} is exactly the kind of problem we've been working on with research teams doing production {{rl_method}}. Kore.ai used Collinear environments to achieve a 91% improvement in agent performance; I suspect the same infra would map well to your {{environment_challenge}}. Is a 20-minute technical conversation worth it?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{company_name}} + Collinear on {{rl_method}} environments

{{contact_first_name}}, we recently published a technical note on how MasterClass uses Collinear-generated environments for recommendation training — a different domain than yours, but the environment diversity challenge is identical. Linking it here in case it's useful: [insert link].

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{company_name}} + Collinear on {{rl_method}} environments

{{contact_first_name}}, stepping back — if the timing isn't right, I completely understand. Feel free to reach out when environment infrastructure moves up the priority stack.

— {{sender_name}}
