# Email Template: GitHub Developer Tooling Signal

## Signal Context

Triggered when a company has active public GitHub repositories demonstrating investment in developer tooling — CI/CD pipelines, internal platform tooling, monorepo configurations, Backstage plugins, or developer portal work. Recent commits indicate active effort to improve developer experience, not a dormant project.

---

## Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{contact_first_name}}` | Recipient's first name |
| `{{company_name}}` | Company name |
| `{{repo_name}}` | Repository name |
| `{{repo_focus}}` | Short description of what the repo does |
| `{{technical_detail}}` | Specific detail from the repo that shows you looked |
| `{{devex_pain}}` | The developer experience friction implied by their current approach |
| `{{signal_reference}}` | GitHub repo URL |
| `{{sender_name}}` | Sender's full name |

---

## Variant A — Bottleneck Focused

### Email 1 (Day 0)

**Subject:** What {{repo_focus}} tells me about {{company_name}}'s bottlenecks

{{contact_first_name}}, came across {{repo_name}} — the {{technical_detail}} tells me your team is investing in developer experience, which usually means you're also dealing with {{devex_pain}}. DevFlow surfaces exactly where time disappears across the SDLC and automates the repetitive parts, so the platform team can focus on higher-leverage work. Worth 20 minutes to see if it maps to where {{company_name}} is right now?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: What {{repo_focus}} tells me about {{company_name}}'s bottlenecks

{{contact_first_name}}, one pattern we see consistently at {{company_name}}'s scale: the bottlenecks that matter most are rarely the ones engineering leaders think they are. DevFlow's SDLC visibility has a way of surfacing surprises. Happy to share what we typically find at teams your size.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: What {{repo_focus}} tells me about {{company_name}}'s bottlenecks

{{contact_first_name}}, not the right time — understood. If {{devex_pain}} becomes a bigger priority as the team scales, feel free to reach out.

— {{sender_name}}

---

## Variant B — Platform ROI Focused

### Email 1 (Day 0)

**Subject:** Measuring the ROI of {{company_name}}'s platform investment

{{contact_first_name}}, {{repo_name}} shows real platform engineering investment — specifically {{technical_detail}}. The challenge at this stage is usually demonstrating ROI: connecting platform work to developer outcomes in a way that justifies continued investment. DevFlow gives you that visibility automatically, without requiring manual tracking. Is a 20-minute walkthrough useful?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: Measuring the ROI of {{company_name}}'s platform investment

{{contact_first_name}}, we worked with a 120-person engineering org that had a similar platform setup — they used DevFlow to show the platform team had saved the equivalent of 3 FTEs in developer toil over one quarter. Happy to share how they structured the measurement.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: Measuring the ROI of {{company_name}}'s platform investment

{{contact_first_name}}, closing the loop — if the platform investment is already well-justified internally, that's a good place to be. Reach out if the conversation around developer productivity metrics comes up.

— {{sender_name}}
