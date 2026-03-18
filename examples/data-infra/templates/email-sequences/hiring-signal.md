# Email Template: Hiring Signal — Data Engineering Role

## Signal Context

Triggered when a company posts job openings for data engineering roles: Data Engineer, Senior Data Engineer, Data Platform Engineer, Analytics Engineer. A surge in data engineering hiring signals that the team is scaling pipeline complexity — and typically about to hit the limits of whatever orchestration layer they're running today.

---

## Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{contact_first_name}}` | Recipient's first name |
| `{{company_name}}` | Company name |
| `{{job_title}}` | The specific role being hired for |
| `{{job_count}}` | Number of open data engineering roles |
| `{{data_focus}}` | Technical focus inferred from the job posting |
| `{{scale_challenge}}` | The infrastructure challenge implied by the hiring signal |
| `{{signal_reference}}` | Job posting URL |
| `{{sender_name}}` | Sender's full name |

---

## Variant A — Problem-Focused

### Email 1 (Day 0)

**Subject:** {{job_count > 1 ? job_count + " data engineering hires" : "Data engineering hire"}} at {{company_name}} — pipeline infra question

{{contact_first_name}}, saw {{company_name}} is hiring for {{data_focus}} — that level of investment usually means pipeline complexity is outpacing your current orchestration setup. New data engineers typically spend weeks ramping on whichever self-managed Airflow (or equivalent) you're running before they can ship pipelines. PipelineHQ eliminates that ramp with fully managed orchestration. Worth 20 minutes before those hires start?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: Data engineering hire at {{company_name}} — pipeline infra question

{{contact_first_name}}, {{scale_challenge}} is usually what surfaces once a team goes from 3 to 8 data engineers — the orchestration layer that worked fine at the smaller scale starts creating operational drag. Happy to share what that inflection typically looks like.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: Data engineering hire at {{company_name}} — pipeline infra question

{{contact_first_name}}, figured you're heads-down in interviews. If orchestration infrastructure becomes a conversation once those engineers are onboard, feel free to loop me in.

— {{sender_name}}

---

## Variant B — Outcome-Focused

### Email 1 (Day 0)

**Subject:** Getting {{company_name}}'s new data engineers shipping pipelines from day one

{{contact_first_name}}, {{company_name}}'s open {{job_title}} roles signal serious investment in {{data_focus}}. The fastest path to ROI on those hires is having managed orchestration in place so new engineers ship pipelines immediately rather than ramping on infra. PipelineHQ is a drop-in Airflow replacement — fully managed, no Kubernetes, SLA monitoring included. Is a quick technical walkthrough useful?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: Getting {{company_name}}'s new data engineers shipping pipelines from day one

{{contact_first_name}}, we recently helped a media company onboard 4 new data engineers in parallel — managed orchestration meant each one was running their first pipeline within 48 hours. Happy to share the onboarding architecture as a reference.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: Getting {{company_name}}'s new data engineers shipping pipelines from day one

{{contact_first_name}}, stepping back — if your current orchestration setup scales well with the team, that's a solid position to be in. Feel free to reach out if the infra conversation comes up once those hires are ramped.

— {{sender_name}}
