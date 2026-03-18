---
name: compliance-manager
description: Use when setting up outbound email compliance, managing opt-out and suppression lists, handling GDPR/CAN-SPAM/CCPA requirements, or when a prospect requests data deletion
---

# Compliance Manager

## Regulatory Requirements

**CAN-SPAM (US):**
- Physical mailing address in every email (registered agent or mailbox — not home address)
- Clear opt-out mechanism (Instantly.ai footer handles this). Honor within 10 days — in practice, immediately.
- Subject lines must not be deceptive.

**GDPR (EU/UK):**
- B2B cold email is permitted under "legitimate interest" — must be professionally relevant.
- Right to erasure: remove all data from all systems within 30 days of request.
- Personal data only in approved systems (HubSpot, Instantly.ai, Clay).

**CCPA (California):**
- Right to know, delete, and opt out of sale. Honor deletion within 45 days.
- Do not "sell" personal data (sharing with data brokers counts as sale).

**CASL (Canada):**
- Implied consent applies for B2B when contact info is publicly available and the email is professionally relevant.
- Include business name, physical address, and unsubscribe mechanism in every email.

## Suppression Lists

Maintain one global suppression CSV synced to Instantly.ai. Categories:

| Category | Add trigger | Remove policy |
|----------|-------------|---------------|
| Opt-outs | Any unsubscribe request | Never |
| Current customers | Deal marked Closed Won in HubSpot | Remove if churned (manual review) |
| Competitors | Manual addition | Ongoing review |
| Negative replies | "Not interested", "stop emailing", "remove me" | Never for opt-outs; 6-month cooling-off for "not now" |
| Hard bounces | Bounce status from Instantly.ai | Never — address is invalid |

Sync schedule: export updated suppression CSV from HubSpot weekly. Upload to Instantly.ai → Settings → Suppression List → replace existing.

## Opt-Out Handling

**Explicit opt-out** (unsubscribe link clicked, or email saying "remove me", "unsubscribe", "stop emailing"):
1. Remove from all active sequences in Instantly.ai immediately
2. Add email to global suppression CSV
3. Mark contact in HubSpot as "Do Not Contact" — set DNC flag
4. Never contact again on any domain or from any alias

**Soft negative** ("not interested", "not the right time", "maybe later"):
1. Remove from current sequence in Instantly.ai
2. Add to a "cooling-off" list with a 6-month re-engage date
3. Log the reply in HubSpot with date and exact response text
4. Do not suppress permanently unless they explicitly ask

**"How did you get my email":**
1. Reply within 24 hours — name the source (Apollo, LinkedIn, public profile)
2. Offer removal. If confirmed: treat as explicit opt-out.

## Data Handling

Personal data (name, email, title, phone, LinkedIn URL) lives only in:
- **HubSpot** — CRM of record
- **Instantly.ai** — active sequences and sending
- **Clay** — enrichment and monitoring

Rules:
- Never commit personal data to git or log files
- Delete local CSV files after import
- Never paste contact data into Slack, Notion, or unapproved tools
- Use only work accounts for GTM tooling

**GDPR deletion request workflow:**
1. Receive request → confirm identity (ask them to reply from the email address)
2. Within 30 days: delete from HubSpot, Instantly.ai, and Clay
3. Reply confirming deletion date
4. Log in a "Deletion Requests" HubSpot list (date + email hash only — no PII)

## Monthly Compliance Audit Checklist

Run on the first Monday of each month:

- [ ] Global suppression list synced to Instantly.ai
- [ ] All active sequences contain unsubscribe footer link
- [ ] Physical mailing address present in email footer
- [ ] No PII committed to git repo (`git log --all -- "*.csv"`)
- [ ] All opt-outs from prior month honored and in suppression list
- [ ] HubSpot DNC flags match suppression CSV
- [ ] No personal data in shared docs, Slack, or Notion
- [ ] Pending deletion requests completed within 30-day window
- [ ] CASL: Canadian prospects contacted only under implied consent
