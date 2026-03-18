# Email Template: Funding Signal

## Signal Context

Triggered when an AI company announces a funding round (Series A or later) and shows RL signals in their technical footprint. Fresh funding means a mandate to scale, a budget that just expanded, and a leadership team under pressure to show results quickly. The window is narrow — reach out within 2 weeks of the announcement while the "what do we build next?" conversation is still live.

---

## Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{contact_first_name}}` | Recipient's first name |
| `{{company_name}}` | Company name |
| `{{funding_amount}}` | Round size (e.g., "$40M") |
| `{{funding_round}}` | Round designation (e.g., "Series A", "Series B") |
| `{{funding_date}}` | Approximate date or month of announcement |
| `{{rl_signal}}` | The RL-related signal that put them in scope (e.g., "your RLHF pipeline repo", "your post-training job posting") |
| `{{scale_challenge}}` | The scaling challenge fresh funding implies (e.g., "scaling your RLHF training pipeline") |
| `{{icp_tier}}` | ICP tier label (e.g., "enterprise agent builder", "AI lab") |
| `{{signal_reference}}` | Funding announcement URL or TechCrunch/Crunchbase link |
| `{{sender_name}}` | Sender's full name |

---

## Variant A — Problem-Focused

### Email 1 (Day 0)

**Subject:** {{company_name}}'s {{funding_round}} and the environment problem

{{contact_first_name}}, congratulations on the {{funding_amount}} {{funding_round}} — given {{rl_signal}}, it's clear {{scale_challenge}} is on the roadmap. The infrastructure decision that usually surfaces right after a raise: build RL environments in-house or use a managed layer that scales with your ambitions. Collinear gives you production-grade, Gymnasium-compatible environments from your existing workflow data so you're not burning new headcount on environment maintenance. Worth a 20-minute call this week?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{company_name}}'s {{funding_round}} and the environment problem

{{contact_first_name}}, one data point: Kore.ai made this decision shortly after their last raise and achieved a 91% improvement in agent performance while keeping their RL team focused on algorithms rather than infrastructure. Happy to walk through how they structured the decision if it's useful context.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{company_name}}'s {{funding_round}} and the environment problem

{{contact_first_name}}, figured you're heads-down on post-raise priorities right now — bad timing. If environment infrastructure comes up as headcount scales, feel free to reach back out.

— {{sender_name}}

---

## Variant B — Outcome-Focused

### Email 1 (Day 0)

**Subject:** Shipping RL faster after {{company_name}}'s {{funding_round}}

{{contact_first_name}}, saw the {{funding_amount}} {{funding_round}} announcement — and given {{rl_signal}}, the pressure to ship RL results quickly is now real. The fastest path from raise to production is not building environments from scratch. Collinear provides a managed environment platform that drops in as a Gymnasium replacement and generates training environments directly from your enterprise data. Could shave months off your first production RL milestone. Is 20 minutes worth it?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: Shipping RL faster after {{company_name}}'s {{funding_round}}

{{contact_first_name}}, our ServiceNow collaboration demonstrates how a managed environment approach maps onto enterprise workflow data at scale — similar to what {{company_name}} is likely building. Happy to share the architecture writeup if the technical fit question is still open.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: Shipping RL faster after {{company_name}}'s {{funding_round}}

{{contact_first_name}}, stepping back — post-raise calendars are brutal and this may simply not be the right moment. Reach out whenever environment infrastructure moves up the stack.

— {{sender_name}}

---

## Variant C — Social-Proof-Focused

### Email 1 (Day 0)

**Subject:** {{company_name}} post-{{funding_round}}: environment infrastructure

{{contact_first_name}}, the {{funding_amount}} {{funding_round}} and {{rl_signal}} put {{company_name}} in the same category as teams we work with at Kore.ai, ServiceNow, and MasterClass — all using Collinear to manage their RL environment layer after a similar inflection point. Kore.ai in particular saw a 91% agent performance improvement after moving off in-house environments. Worth 20 minutes to see if the same architecture fits your stack?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{company_name}} post-{{funding_round}}: environment infrastructure

{{contact_first_name}}, our CEO Nazneen Rajani (ex-Hugging Face) recently wrote about the environment infrastructure decisions that separate fast-moving RL teams from slow ones post-funding — sharing the piece in case it's timely: [insert link].

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{company_name}} post-{{funding_round}}: environment infrastructure

{{contact_first_name}}, figured this might not be the right time in the post-raise sprint. Happy to reconnect once the immediate priorities settle.

— {{sender_name}}
