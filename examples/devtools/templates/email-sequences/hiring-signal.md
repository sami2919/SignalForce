# Email Template: Hiring Signal — Platform or DevEx Role

## Signal Context

Triggered when a company posts job openings for platform or developer experience roles: Platform Engineer, DevEx Engineer, Internal Tools Engineer, Developer Portal Engineer. Hiring for these roles signals that developer productivity pain has reached the point where dedicated headcount is justified — and typically means the team is about to start building tooling from scratch without visibility into where bottlenecks actually are.

---

## Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{contact_first_name}}` | Recipient's first name |
| `{{company_name}}` | Company name |
| `{{job_title}}` | The specific role being hired for |
| `{{devex_focus}}` | Technical focus inferred from the job posting |
| `{{tooling_challenge}}` | The tooling or visibility challenge implied by the role |
| `{{signal_reference}}` | Job posting URL |
| `{{sender_name}}` | Sender's full name |

---

## Variant A — Problem-Focused

### Email 1 (Day 0)

**Subject:** {{job_title}} hire at {{company_name}} — where do they start?

{{contact_first_name}}, saw {{company_name}} is hiring for {{devex_focus}} — the first challenge for that hire is usually figuring out where developer time actually goes before building anything. Without SDLC visibility, platform investments are educated guesses. DevFlow gives your new {{job_title}} a data-driven map of bottlenecks from day one. Worth 20 minutes before that person starts?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{job_title}} hire at {{company_name}} — where do they start?

{{contact_first_name}}, one thing new platform hires consistently discover: the bottlenecks leadership thinks exist aren't always the ones costing the most developer time. DevFlow's onboarding audit usually surfaces 2–3 surprises. Happy to share what we typically find.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{job_title}} hire at {{company_name}} — where do they start?

{{contact_first_name}}, figured you're in the middle of interviews. If {{tooling_challenge}} is still unresolved once the {{job_title}} is onboard, feel free to loop me in then.

— {{sender_name}}

---

## Variant B — Outcome-Focused

### Email 1 (Day 0)

**Subject:** Getting your {{job_title}} to first impact faster at {{company_name}}

{{contact_first_name}}, {{company_name}}'s open {{job_title}} role signals real investment in developer experience. The fastest path to demonstrating impact is having SDLC visibility in place before building tooling — so every platform decision is justified by data, not instinct. DevFlow gives your new hire that foundation in the first week. Is a quick walkthrough useful before you finalize the hire?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: Getting your {{job_title}} to first impact faster at {{company_name}}

{{contact_first_name}}, we helped a 200-person engineering org onboard their first Head of Platform Engineering — DevFlow gave them a bottleneck map in 48 hours that shaped their entire first-quarter roadmap. Happy to share the approach if it's a useful reference.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: Getting your {{job_title}} to first impact faster at {{company_name}}

{{contact_first_name}}, stepping back — if you have a clear plan for what the {{job_title}} will build first, that's a good place to be. Feel free to reach out once they're onboard and have a clearer picture of the scope.

— {{sender_name}}
