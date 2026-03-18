# Cost Analysis — rl-gtm-engine

Monthly cost breakdown for running the full signal-based outbound pipeline. All figures are in USD and reflect list pricing as of early 2026.

---

## Tool-by-Tool Breakdown

| Tool | Purpose in Pipeline | Monthly Cost | Free Tier |
|------|--------------------|--------------|-----------|
| n8n Cloud (Starter) | Workflow automation, scheduling, webhook ingestion | $24 | 2,500 executions/month (not sufficient for production) |
| Instantly.ai (Growth) | Cold email sequencing, deliverability management | $37 | None — API access requires paid plan |
| Anthropic API (Claude) | Email copy generation via sequence-launcher workflow | $30–50 | None — pay-as-you-go |
| Apollo.io | Contact enrichment (waterfall step 1) | $0 | 50 export credits/month — sufficient for testing, not production |
| HubSpot CRM | Deal tracking, contact management, pipeline reporting | $0 | Full CRM is free |
| ZeroBounce | Email verification before Instantly enrollment | $0–16 | 100 validations/month free; $16/mo for 2,000 |
| Hunter.io (Starter) | Contact enrichment (waterfall step 2, optional) | $0–34 | 25 requests/month free |
| Prospeo | LinkedIn email enrichment (waterfall step 3, optional) | $0 | 75 credits/month free |
| Google Sheets | Daily analytics storage | $0 | Free |
| Slack | A-tier signal alerts, hot-lead notifications, analytics digest | $0 | Free for this usage |
| GitHub API | RL repo detection (signal scanner) | $0 | 5,000 requests/hour with free account |
| Semantic Scholar | ArXiv paper tracking (signal scanner) | $0 | Free (rate limited without key) |
| HuggingFace Hub | RL model upload detection (signal scanner) | $0 | Free |
| LinkedIn Sales Navigator | Manual prospect research (optional) | $100 | None |
| Clay Explorer | Advanced enrichment + persona building (optional) | $314 | None |

---

## Budget Tiers

### Minimal ($61/month)

Minimum viable setup. Covers automation, sequences, and email generation. Relies on free tiers for enrichment.

| Tool | Cost |
|------|------|
| n8n Cloud | $24 |
| Instantly.ai | $37 |
| Anthropic API | ~$10–20 (low volume) |
| All enrichment tools | $0 (free tiers) |
| **Total** | **~$61–81/month** |

**Limitations:** Apollo free tier caps at 50 exports/month. Hunter free tier caps at 25 requests. Expect lower contact find rates until you upgrade enrichment. Suitable for testing and early pipeline development (targeting 10–20 sequences/week).

### Standard ($505/month)

Full production setup without LinkedIn Sales Navigator or Clay. Covers all signal sources, production enrichment volume, and email verification at scale.

| Tool | Cost |
|------|------|
| n8n Cloud | $24 |
| Instantly.ai | $37 |
| Anthropic API | $30–50 |
| Apollo.io (Basic) | $49 |
| Hunter.io (Starter) | $34 |
| ZeroBounce | $16 |
| Prospeo | $16 |
| **Total** | **~$206–226/month** |

> Note: With optimized enrichment (Apollo covers most cases, Hunter/Prospeo as fallback), the realistic Standard tier is $206–226/month, not $505. The $505 figure applies when LinkedIn Sales Navigator is included.

**With LinkedIn Sales Nav:**

| Tool | Cost |
|------|------|
| Standard tools above | $206–226 |
| LinkedIn Sales Navigator | $100 |
| **Total** | **~$306–326/month** |

### Premium ($800/month)

Full stack including Clay for advanced enrichment and persona building. Suitable for teams running 100+ sequences/week with high-touch personalization.

| Tool | Cost |
|------|------|
| Standard tools | $206–226 |
| LinkedIn Sales Navigator | $100 |
| Clay Explorer | $314 |
| Anthropic API (high volume) | $50–100 |
| **Total** | **~$670–740/month** |

---

## Cost Per Output (Standard Tier)

At Standard tier with the pipeline running at target capacity (Month 3):

| Metric | Volume | Cost Attribution |
|--------|--------|-----------------|
| Signals detected | 150–300/month | Scanner costs: $0 |
| Contacts enriched | 100–200/month | ~$1.00–2.00/contact |
| Emails generated | 100–200/month | ~$0.15–0.50/email (Claude API) |
| Sequences launched | 80–150/month | Included in Instantly flat fee |
| Meetings booked | 15–30/month | ~$7–15/meeting at Standard tier |

---

## Comparison vs. Alternatives

| Alternative | Annual Cost | Notes |
|-------------|-------------|-------|
| rl-gtm-engine (Standard) | ~$2,500–3,900/year | Fully automated, runs 24/7 |
| rl-gtm-engine (Premium) | ~$8,000–9,000/year | High-touch with Clay |
| AI SDR tool (e.g., Artisan, 11x) | $40,000–60,000/year | Less customizable for technical ICPs |
| Full-time junior SDR | $80,000–120,000/year | Salary + benefits + ramp time |
| Full-time senior SDR | $120,000–160,000/year | With commission at quota |

rl-gtm-engine targets a technical ICP (RL researchers and engineers) where generic AI SDR tools produce poor results. The skills-based approach allows personalization at a level that off-the-shelf tools cannot match for this segment.

---

## Cost Scaling Notes

**Anthropic API costs** scale with email volume. Roughly:
- 100 emails/month: ~$10–15
- 500 emails/month: ~$30–50
- 2,000 emails/month: ~$100–150

**Apollo.io** offers volume discounts at higher tiers. If enrichment becomes the bottleneck, moving to Apollo Professional ($99/mo) gives unlimited exports.

**n8n self-hosted** eliminates the $24/month n8n Cloud fee at the cost of infrastructure management time. Docker on a $5/month VPS works for low-volume pipelines.

**ZeroBounce** pricing is consumption-based: $16/mo covers 2,000 validations. At Standard tier with 100–200 contacts/month, free tier (100/month) is often sufficient in Month 1.
