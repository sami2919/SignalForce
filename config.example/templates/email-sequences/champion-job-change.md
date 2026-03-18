# Email Template: Champion Job Change

## Signal Context

Triggered when a known contact — someone who has previously engaged with Collinear, evaluated the product, attended a demo, or worked at a customer account — changes companies and moves into a role at a new organization that fits the ICP. This is the highest-intent warm outreach scenario. The contact already understands the product and the value proposition. Lead with the relationship, not the pitch. Do not treat this like cold outreach.

---

## Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{contact_first_name}}` | Recipient's first name |
| `{{new_company}}` | Their new company name |
| `{{new_title}}` | Their new job title |
| `{{previous_company}}` | Their previous company name |
| `{{prior_relationship}}` | Brief description of how you know them (e.g., "you evaluated Collinear last year", "you were at Kore.ai when they adopted Collinear") |
| `{{new_company_rl_signal}}` | What RL signal exists at the new company (e.g., "active RLHF repo on GitHub", "three open RL Engineer roles") |
| `{{new_company_challenge}}` | The likely environment challenge at the new company given their RL signal |
| `{{shared_context}}` | Something specific from the prior relationship that's relevant (e.g., "the environment diversity problem we talked through at Kore.ai") |
| `{{sender_name}}` | Sender's full name |

---

## Variant A — Problem-Focused

### Email 1 (Day 0)

**Subject:** Congrats on {{new_company}} — same environment problem?

{{contact_first_name}}, congrats on the move to {{new_company}} as {{new_title}} — well deserved. Given {{new_company_rl_signal}}, I'm guessing {{new_company_challenge}} is already on your radar. You saw firsthand at {{previous_company}} how that plays out. Curious whether the same conversation is worth having at {{new_company}} — 20 minutes?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: Congrats on {{new_company}} — same environment problem?

{{contact_first_name}}, since {{prior_relationship}}, we've shipped several improvements to environment generation speed and fidelity — including the exact pain point around {{shared_context}}. Happy to do a quick demo refresh scoped specifically to {{new_company}}'s setup.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: Congrats on {{new_company}} — same environment problem?

{{contact_first_name}}, no worries — first 90 days in a new role are brutal. Reach out whenever the timing is right.

— {{sender_name}}

---

## Variant B — Outcome-Focused

### Email 1 (Day 0)

**Subject:** {{new_company}} + Collinear — worth revisiting?

{{contact_first_name}}, saw you landed at {{new_company}} as {{new_title}} — congratulations. Given {{new_company_rl_signal}}, you're likely facing the same environment infrastructure question you navigated at {{previous_company}}. Except now you have the benefit of already knowing what Collinear does and how it maps. Want to pick up where we left off, scoped to {{new_company}}'s stack?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{new_company}} + Collinear — worth revisiting?

{{contact_first_name}}, since you were last in the product, we've added [specific new feature relevant to their stack — e.g., "native ServiceNow environment templates" or "GRPO reward signal debugging tooling"]. Might change the calculus for {{new_company}}'s use case. Happy to show you the delta.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{new_company}} + Collinear — worth revisiting?

{{contact_first_name}}, figured you're still in ramp mode — makes sense. I'll check back in a few months once you've had time to assess the RL infrastructure landscape at {{new_company}}.

— {{sender_name}}

---

## Variant C — Social-Proof-Focused

### Email 1 (Day 0)

**Subject:** From {{previous_company}} to {{new_company}} — same Collinear question?

{{contact_first_name}}, great to see the move to {{new_company}} — {{new_title}} is a big step. You were part of the conversation at {{previous_company}} around {{shared_context}}, and given {{new_company_rl_signal}}, it sounds like {{new_company_challenge}} is in your path again. Kore.ai (whom you know) got to a 91% agent performance improvement by solving exactly that. Worth 20 minutes to see if the same approach fits {{new_company}}'s architecture?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: From {{previous_company}} to {{new_company}} — same Collinear question?

{{contact_first_name}}, one update since we last spoke: we've expanded the environment library to cover [relevant domain — e.g., "additional enterprise workflow connectors" or "expanded robotics sim templates"]. If {{new_company}}'s stack includes that layer, it changes the onboarding timeline significantly.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: From {{previous_company}} to {{new_company}} — same Collinear question?

{{contact_first_name}}, stepping back — you know where to find me when the time is right. Congrats again on the new role.

— {{sender_name}}
