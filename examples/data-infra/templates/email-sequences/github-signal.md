# Email Template: GitHub Data Engineering Signal

## Signal Context

Triggered when a company has active public GitHub repositories demonstrating data engineering investment — Airflow DAGs, dbt projects, Spark pipelines, Kafka consumers, or data platform tooling. Recent commits indicate active pipeline development or infrastructure work.

---

## Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{contact_first_name}}` | Recipient's first name |
| `{{company_name}}` | Company name |
| `{{repo_name}}` | Repository name |
| `{{repo_focus}}` | Short description of what the repo does |
| `{{technical_detail}}` | Specific detail from the repo that shows you looked |
| `{{orchestration_pain}}` | The operational burden implied by their current approach |
| `{{signal_reference}}` | GitHub repo URL |
| `{{sender_name}}` | Sender's full name |

---

## Variant A — Operational Burden

### Email 1 (Day 0)

**Subject:** {{repo_focus}} — who owns the Airflow infra?

{{contact_first_name}}, came across {{repo_name}} — the {{technical_detail}} tells me your team is running a real data engineering operation. The question I always ask teams at this stage: who's on-call when Airflow goes down at 2am? PipelineHQ is a managed orchestration layer that eliminates that operational burden entirely — fully Airflow-compatible, no infra to run. Worth 20 minutes?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{repo_focus}} — who owns the Airflow infra?

{{contact_first_name}}, the pattern we see most often: {{orchestration_pain}} isn't on anyone's roadmap, but it compounds every quarter as pipeline count grows. Happy to share what teams at {{company_name}}'s scale typically find when they add up the hidden cost.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{repo_focus}} — who owns the Airflow infra?

{{contact_first_name}}, not the right time — fair. If {{orchestration_pain}} becomes a bigger conversation as your pipeline count grows, feel free to reach out.

— {{sender_name}}

---

## Variant B — Scale Focused

### Email 1 (Day 0)

**Subject:** Scaling {{repo_focus}} without scaling the infra team

{{contact_first_name}}, {{repo_name}} shows real pipeline investment — specifically {{technical_detail}}. The ceiling for self-managed orchestration is usually infrastructure complexity: the more pipelines you add, the more time goes to maintaining the orchestration layer instead of building pipelines. PipelineHQ handles all of that as managed infrastructure, so your data engineers ship features, not Kubernetes configs. Is a 20-minute technical walkthrough worth it?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: Scaling {{repo_focus}} without scaling the infra team

{{contact_first_name}}, a close analog: a Series C fintech migrated 200+ Airflow DAGs to PipelineHQ and eliminated their data platform on-call rotation entirely — 3 data engineers now spend 100% of their time on pipelines, not infra. Happy to share the migration approach.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: Scaling {{repo_focus}} without scaling the infra team

{{contact_first_name}}, closing the loop — if self-managed orchestration is working well enough for now, that's a reasonable place to be. Reach out if the calculus changes as pipeline count grows.

— {{sender_name}}
