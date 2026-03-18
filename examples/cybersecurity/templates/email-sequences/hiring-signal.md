# Email Template: Hiring Signal — Security Role

## Signal Context

Triggered when a company posts job openings for AppSec or DevSecOps roles: Application Security Engineer, Security Engineer, DevSecOps Lead, AppSec Architect. Hiring for these roles signals budget and mandate to build or mature a security function — and typically exposes a gap between current tooling and what the new hire will need to be effective.

---

## Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{contact_first_name}}` | Recipient's first name |
| `{{company_name}}` | Company name |
| `{{job_title}}` | The specific role being hired for |
| `{{security_focus}}` | Technical focus inferred from the job posting |
| `{{tooling_gap}}` | The tooling gap implied by what the JD requires |
| `{{signal_reference}}` | Job posting URL |
| `{{sender_name}}` | Sender's full name |

---

## Variant A — Problem-Focused

### Email 1 (Day 0)

**Subject:** {{job_title}} hire at {{company_name}} — tooling question

{{contact_first_name}}, saw {{company_name}} is hiring for {{security_focus}} — the JD implies you'll be {{tooling_gap}}. New AppSec hires typically spend the first 2–3 months assembling tooling coverage before they can run a meaningful audit. SecureAPI gives them automated API DAST from day one, so the hire is productive immediately. Worth a 20-minute conversation before that person starts?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{job_title}} hire at {{company_name}} — tooling question

{{contact_first_name}}, one thing teams often discover after the first AppSec hire: the tooling gap takes longer to close than expected, especially for API coverage. Happy to share how similar teams structured their AppSec stack to be immediately effective.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{job_title}} hire at {{company_name}} — tooling question

{{contact_first_name}}, figured you're deep in interviews. If tooling coverage becomes a conversation once the {{job_title}} is onboard, feel free to loop me in.

— {{sender_name}}

---

## Variant B — Outcome-Focused

### Email 1 (Day 0)

**Subject:** Getting your {{job_title}} productive from week one at {{company_name}}

{{contact_first_name}}, {{company_name}}'s open {{job_title}} role signals a serious investment in {{security_focus}}. The fastest path to ROI on that hire is having automated API coverage in place — without it, the first months go toward tooling setup, not actual security work. SecureAPI integrates with your CI/CD in under a day and covers OWASP API Top 10 automatically. Is a quick technical walkthrough useful before you finalize the hire?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: Getting your {{job_title}} productive from week one at {{company_name}}

{{contact_first_name}}, a close analog: we helped a Series B SaaS company ramp their first AppSec hire in under two weeks with automated API testing already running. Happy to share the onboarding architecture so you can evaluate build-vs-buy with a concrete reference.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: Getting your {{job_title}} productive from week one at {{company_name}}

{{contact_first_name}}, stepping back — if the plan is to build tooling in-house, that's a reasonable call with the right hire. Feel free to reach out once the {{job_title}} is onboard and has a clearer picture of what coverage gaps exist.

— {{sender_name}}
