# Email Template: GitHub Security Signal

## Signal Context

Triggered when a company has active public GitHub repositories demonstrating security tooling or API security work — DAST configurations, custom fuzzing harnesses, OWASP tooling integrations, or security testing pipelines. Recent commits indicate active investment in automated security, not a dormant experiment.

---

## Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{contact_first_name}}` | Recipient's first name |
| `{{company_name}}` | Company name |
| `{{repo_name}}` | Repository name |
| `{{repo_focus}}` | Short description of what the repo does |
| `{{technical_detail}}` | Specific detail from the repo that shows you looked |
| `{{security_gap}}` | The coverage gap or risk implied by their current approach |
| `{{signal_reference}}` | GitHub repo URL |
| `{{sender_name}}` | Sender's full name |

---

## Variant A — Coverage Gap

### Email 1 (Day 0)

**Subject:** {{repo_focus}} — API coverage question

{{contact_first_name}}, came across {{repo_name}} — the {{technical_detail}} approach covers static analysis well, but SAST alone typically misses 60% of API security issues that only appear at runtime. SecureAPI runs full DAST coverage against your API endpoints in CI without requiring manual test authoring. Worth 20 minutes to see if there's a gap worth closing?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: {{repo_focus}} — API coverage question

{{contact_first_name}}, the pattern we see most often with teams at {{company_name}}'s stage: SAST catches code-level issues, but business logic flaws — BOLA, IDOR, broken auth — require runtime testing. Happy to walk through how that maps to your current stack.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: {{repo_focus}} — API coverage question

{{contact_first_name}}, not the right time — fair enough. If {{security_gap}} becomes a priority after your next penetration test or compliance audit, feel free to reach out.

— {{sender_name}}

---

## Variant B — Shift Left

### Email 1 (Day 0)

**Subject:** Catching API vulnerabilities before they reach {{company_name}}'s prod

{{contact_first_name}}, reviewed {{repo_name}} — specifically the {{technical_detail}}. Your team has solid security hygiene; the gap is usually runtime API coverage that runs on every PR, not just quarterly pen tests. SecureAPI plugs into your existing CI/CD and catches OWASP API Top 10 issues before merge. Is a 20-minute technical walkthrough useful?

— {{sender_name}}

---

### Email 2 (Day 3)

**Subject:** Re: Catching API vulnerabilities before they reach {{company_name}}'s prod

{{contact_first_name}}, we recently worked with a fintech team that had a similar setup — strong SAST, no automated API runtime testing. They found 14 auth bypass vulnerabilities in their first scan. Happy to share the technical breakdown.

— {{sender_name}}

---

### Email 3 (Day 7)

**Subject:** Re: Catching API vulnerabilities before they reach {{company_name}}'s prod

{{contact_first_name}}, stepping back — if your current coverage is working well enough, that's a reasonable place to be. Reach out if the calculus changes after your next pentest.

— {{sender_name}}
