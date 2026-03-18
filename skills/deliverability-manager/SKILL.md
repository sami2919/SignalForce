---
name: deliverability-manager
description: Use when setting up cold email sending infrastructure, configuring DNS records for new sending domains, planning email warmup schedules, or troubleshooting deliverability issues like high bounce rates or spam folder placement
---

# Deliverability Manager

## Domain Strategy

Never send cold email from your primary domain. Buy 3–5 secondary domains (e.g., `getcollinear.ai`, `collinear-ai.com`). Register via Namecheap or Google Domains.

Set up Google Workspace on each domain. Create 2–3 sending accounts per domain (e.g., `sami@`, `team@`, `hello@`). This gives 6–15 sending accounts total — each capped at 25–30 emails/day at full warmup.

**Total capacity at full warmup:** 15 accounts × 30 = 450 emails/day.

## DNS Configuration

Configure all three records before sending a single email.

**SPF** — authorizes Google to send on your behalf:
```
TXT @ "v=spf1 include:_spf.google.com ~all"
```
Why: Receiving servers reject mail from unauthorized senders. `~all` is softfail (safer than `-all` for deliverability).

**DKIM** — cryptographic signature proving the email wasn't tampered with:
- In Google Workspace Admin → Apps → Gmail → Authenticate email → Generate DKIM key
- Add the generated TXT record to DNS (key selector: `google`)

Why: Major providers (Gmail, Outlook) heavily weight DKIM presence for inbox placement.

**DMARC** — policy for handling SPF/DKIM failures:
```
TXT _dmarc "v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain.com; pct=100"
```
Why: Required by Google and Yahoo for bulk senders (>5K/day). Start with `p=quarantine`, move to `p=reject` after 30 days of clean reports.

**Custom tracking domain (CNAME)** — masks tracking links from Instantly.ai:
```
CNAME track "custom.tracking.instantly.ai"
```
Why: Generic tracking domains are flagged by spam filters. Custom subdomain improves deliverability.

Verify all records: MXToolbox → SuperTool → enter domain.

## Warmup Protocol

Use Instantly.ai's built-in warmup or Mailreach. Never skip — domains sent cold from day one get blacklisted.

| Week | Emails/day/account | Action |
|------|--------------------|--------|
| 1–2  | 5                  | Warmup only, no prospects |
| 3–4  | 15                 | Can begin limited prospect sends |
| 5+   | 25–30              | Full capacity |

Warmup sends go to a pool of real inboxes that auto-open, auto-reply, and mark as not spam. Maintain warmup indefinitely — never turn it off.

## Monitoring

Check weekly:
- **MXToolbox Blacklist Check** — enter each sending domain. If listed: stop immediately, delist, rotate.
- **Google Postmaster Tools** — connect sending domains. Track domain reputation (aim for High), spam rate (<0.1%).
- **Instantly.ai dashboard** — bounce rate, open rate, reply rate per campaign.

Thresholds:
- Bounce rate <2%: healthy
- Bounce rate 2–5%: pause and clean list
- Bounce rate >5%: pause campaign, audit list source

## Troubleshooting

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| High bounce rate | Stale or unverified list | Run ZeroBounce on full list before next send |
| Landing in spam | DNS misconfigured or domain flagged | Recheck SPF/DKIM/DMARC via MXToolbox; pause domain 2 weeks |
| Low open rate | Weak subject line or sending time | A/B test subjects; try 8–9am or 4–5pm recipient timezone |
| Blacklisted | Sent too fast or bad list | Stop all sends from domain; submit delisting request; rotate to backup domain |
| Replies going to spam | Reply-to misconfigured | Set reply-to to primary domain inbox |
