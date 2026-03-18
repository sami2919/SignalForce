# Email Template: Hiring Signal

## Signal Context

Triggered when a company posts job openings for RL-specific roles: RL Engineer, Simulation Engineer, Post-Training Engineer, Reward Modeling Lead, or adjacent titles (Agent Training Engineer, Policy Optimization Researcher). Hiring for these roles is a leading indicator of investment — the company has budget and a mandate to build. It also implies they are about to face the environment infrastructure problem at scale, if they haven't already.

---

## Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{contact_first_name}}` | Recipient's first name |
| `{{company_name}}` | Company name |
| `{{job_title}}` | The specific role being hired for (e.g., "RL Engineer", "Simulation Engineer") |
| `{{job_count}}` | Number of RL-related open roles (if more than one) |
| `{{rl_focus}}` | Technical focus inferred from the job posting (e.g., "reward modeling for LLM post-training") |
| `{{environment_implication}}` | The environment challenge implied by the role (e.g., "building training environments from scratch") |
| `{{signal_reference}}` | Job posting URL or LinkedIn link |
| `{{sender_name}}` | Sender's full name |

---

## Variant A — Problem-Focused

### Email 1 (Day 0)

**Subject:** {{job_title}} hire at {{company_name}} — environment question

{{contact_first_name}}, saw {{company_name}} is hiring for {{rl_focus}} — the job description implies you'll be {{environment_implication}}. That environment build usually consumes the first 2–4 months of a new RL engineer's ramp, before they can run a single training experiment. Collinear eliminates that ramp by delivering production-grade environments from your existing workflow data, so the hire is productive from week one. Worth a 20-minute conversation before that person starts?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{job_title}} hire at {{company_name}} — environment question

{{contact_first_name}}, one thing teams often discover after the first RL hire: maintaining the environment codebase competes directly with running experiments. Kore.ai short-circuited that tradeoff with Collinear and saw a 91% improvement in agent performance — happy to share how their team structured it.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{job_title}} hire at {{company_name}} — environment question

{{contact_first_name}}, figured you're deep in interviews right now — bad timing on my end. If environment infrastructure becomes a topic once the hire is on board, feel free to loop me in then.

— {{sender_name}}

---

## Variant B — Outcome-Focused

### Email 1 (Day 0)

**Subject:** Getting your {{job_title}} productive faster at {{company_name}}

{{contact_first_name}}, {{company_name}}'s open {{job_title}} role signals you're investing seriously in {{rl_focus}}. The fastest path to ROI on that hire is having a ready environment layer — without one, the first months go toward infrastructure, not experiments. Collinear provides a Gymnasium-compatible managed environment platform so your new engineer can run training on day one. Is a quick technical walkthrough useful before you finalize the hire?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: Getting your {{job_title}} productive faster at {{company_name}}

{{contact_first_name}}, our work with ServiceNow on enterprise workflow simulation is a close analog to what your {{job_title}} will likely be building — happy to share the architecture so you can evaluate the build-vs-buy tradeoff with a concrete reference point.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: Getting your {{job_title}} productive faster at {{company_name}}

{{contact_first_name}}, stepping back — if the plan is to build in-house, that's a reasonable call with the right team. Feel free to reach out once the {{job_title}} is onboard and you have a clearer picture of the scope.

— {{sender_name}}

---

## Variant C — Social-Proof-Focused

### Email 1 (Day 0)

**Subject:** {{company_name}} hiring for {{rl_focus}}

{{contact_first_name}}, noticed {{company_name}} is hiring {{job_count > 1 ? job_count + " RL roles" : "a " + job_title}} focused on {{rl_focus}}. Teams at Kore.ai and ServiceNow faced the same ramp-up challenge — environment infrastructure consuming engineer time before any experiments ran. Both now use Collinear to manage that layer, and Kore.ai reported a 91% improvement in agent performance after the switch. Worth 20 minutes to see if the same approach fits {{company_name}}'s setup?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{company_name}} hiring for {{rl_focus}}

{{contact_first_name}}, we put together a short guide on structuring RL environment infrastructure for teams scaling from 1 to 5 RL engineers — covers the key decision points around managed vs. custom. Happy to send it over if useful.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{company_name}} hiring for {{rl_focus}}

{{contact_first_name}}, figured this might not be the right time in the hiring cycle. Good luck with the search — reach out if environment infrastructure becomes a conversation topic down the road.

— {{sender_name}}
