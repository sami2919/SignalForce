# Resource-First Email Sequence

## Signal Context

Resource-first outreach leads with a free, relevant resource instead of asking for a meeting. Gojiberry AI data shows 50% reply rates for resource-first vs. 8-15% for demo asks. The mechanism: technical buyers respond to peers sharing knowledge, not sales reps requesting time. By offering something useful before asking for anything, you establish credibility and create reciprocity without triggering the "another vendor" mental filter.

This template works with any signal type. The signal determines which resource you offer.

---

## Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{contact_first_name}}` | Recipient's first name |
| `{{company_name}}` | Company name |
| `{{signal_reference}}` | The specific signal (repo name, paper title, job posting, funding round, model name) |
| `{{resource_title}}` | Title of the resource being offered |
| `{{resource_description}}` | One-line description of what the resource covers |
| `{{resource_insight}}` | A specific, concrete takeaway from the resource (used in Email 2) |
| `{{sender_name}}` | Sender's full name |

---

## Resource Selection

| Signal Type | Recommended Resource |
|-------------|---------------------|
| GitHub repo activity | "Guide: Scaling RL Environments from 1 to 5 Engineers" |
| ArXiv paper | "Framework: Environment Infrastructure Decisions for RL Research Teams" |
| Job posting (RL role) | "Checklist: Onboarding RL Engineers Without Environment Debt" |
| Funding round | "Playbook: RL Infrastructure Buildout for Post-Series A Teams" |
| HuggingFace model upload | "Benchmark: RLHF Environment Quality vs. Training Performance" |

---

## Sequence

### Email 1: Day 0 — Offer the Resource

#### Variant A: Problem-Focused

**Subject:** {{resource_title}}

{{contact_first_name}}, saw {{signal_reference}} and it immediately reminded me of a framework we put together on {{resource_description}}. Most teams hit the same environment scaling problems at your stage, and this covers the decisions that tend to get painful later. Happy to share — figured it might save you some decisions.

— {{sender_name}}

---

#### Variant B: Outcome-Focused

**Subject:** {{resource_title}}

{{contact_first_name}}, {{signal_reference}} is exactly the kind of work we built {{resource_title}} around — {{resource_description}}. Teams that worked through it before scaling cut environment-related engineering overhead by roughly 30%. Happy to share — figured it might save you some decisions.

— {{sender_name}}

---

#### Variant C: Social-Proof-Focused

**Subject:** {{resource_title}}

{{contact_first_name}}, after {{signal_reference}} we put together {{resource_title}} with input from teams at Kore.ai and ServiceNow who hit the same infrastructure fork. It covers {{resource_description}} — the decisions they wished they'd made earlier. Happy to share — figured it might save you some decisions.

— {{sender_name}}

---

### Email 2: Day 4 — Share an Insight FROM the Resource

*(2-3 sentences. Deliver a specific, concrete takeaway from the resource. This is not a follow-up ping — it is a second piece of value.)*

**Subject:** Re: {{resource_title}}

{{contact_first_name}}, one finding from {{resource_title}} that tends to resonate: {{resource_insight}}. Sharing it in case it's useful regardless of whether you want the full doc.

— {{sender_name}}

---

### Email 3: Day 8 — Low-Friction Conversation Offer

*(2 sentences. Offer a conversation about the resource content only — not a demo or pitch.)*

**Subject:** Re: {{resource_title}}

{{contact_first_name}}, if it would be useful, I'm happy to walk through the section of {{resource_title}} most relevant to where {{company_name}} is right now — 15 minutes, no pitch. Let me know.

— {{sender_name}}

---

## Rules

- Email 1 and Email 2 never ask for a meeting or call.
- Email 3 offers a conversation scoped to the resource only — not a demo, not a pitch.
- First sentence always references the specific signal (repo, paper, posting, round, model).
- No banned phrases: "I hope this email finds you well", "I noticed your company", "touching base", "let me know if you're interested".
- 4 sentences max per email.
- Tone: technical peer sharing knowledge, not sales rep qualifying a lead.
