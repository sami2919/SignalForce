# Results Framework — rl-gtm-engine

Metrics definitions, targets, reporting cadence, and diagnostic playbooks for the signal-based outbound pipeline.

---

## Core Metrics Definitions

| Metric | Definition | How It Is Measured |
|--------|------------|-------------------|
| Signals detected | Total unique company signals found across all scanners (GitHub, ArXiv, HF, jobs, funding) | `ScanResult.signals_found` count per run; daily roll-up in Google Sheets |
| Accounts qualified | Signals that pass ICP scoring with grade A or B | `CompanyProfile.icp_score in ["A", "B"]` post signal-stacking |
| Contacts enriched | Unique contacts with a verified email address (`email_verified=True`) | `Contact.email_verified` count; ZeroBounce pass-rate applied |
| Sequences launched | Contacts enrolled in an Instantly.ai campaign | Instantly campaign enrollment events logged in HubSpot |
| Open rate | Emails opened / emails delivered (excludes bounces) | Instantly.ai campaign analytics; synced to Google Sheets by `crm-sync` workflow |
| Reply rate | Replies received / emails delivered | Instantly.ai webhook events (`email_replied`) processed by `crm-sync` |
| Positive reply rate | Replies classified as interested / total replies | Claude-based reply classification in `crm-sync` workflow |
| Meetings booked | Calls or demos confirmed (manually logged or Calendly integration) | HubSpot deal stage `MEETING_SCHEDULED` |
| Cost per meeting | Total monthly tool spend / meetings booked | Manual calculation using cost-analysis.md figures |

---

## Monthly Targets

| Metric | Month 1 | Month 3 | Month 6 |
|--------|---------|---------|---------|
| Signals detected | 50–100 | 150–300 | 300–500 |
| Accounts qualified (A/B) | 15–30 | 50–100 | 100–200 |
| Contacts enriched | 30–60 | 100–200 | 200–400 |
| Sequences launched | 20–40 | 80–150 | 150–300 |
| Open rate | 40–60% | 45–65% | 50–70% |
| Reply rate | 8–15% | 12–20% | 15–25% |
| Positive reply rate | 3–5% | 5–8% | 6–10% |
| Meetings booked | 5–10 | 15–30 | 30–50 |
| Cost per meeting | $50–100 | $25–50 | $15–30 |

**Month 1** reflects pipeline ramp: domains warming, data quality improving, templates being tested.

**Month 3** reflects a fully operational pipeline with warmed domains, A/B-tested copy, and enrichment coverage across all three waterfall sources.

**Month 6** reflects compounding effects: champion job-change signals, referrals from engaged contacts, and optimized ICP filtering reducing wasted outreach.

---

## Grade Distribution Targets

The signal stacker grades accounts A through D. Target distribution at steady state (Month 3+):

| Grade | Target % | Action |
|-------|----------|--------|
| A | 10–15% | Prioritize — personalize outreach, enroll same week |
| B | 25–35% | Contact — use signal-specific template, enroll within 2 weeks |
| C | 30–40% | Nurture — add to low-priority drip, revisit in 30 days |
| D | 20–30% | Skip — log for future re-evaluation |

If D-grade is below 20%, the signal detection criteria are too broad — tighten keyword filters. If A-grade is above 20%, the criteria are too loose — check that disqualification overrides are being applied.

---

## Reporting Cadence

### Daily (automated via `crm-sync` workflow)

The `crm-sync` daily analytics branch runs at 6 PM PST and appends one row to the `Daily Analytics` Google Sheet:

- Date, Total Signals Detected, Accounts Qualified, Contacts Enriched, Sequences Launched
- Open Rate, Reply Rate, Meetings Booked (rolling 7-day)
- Cost USD (manual input monthly), Cost Per Meeting, Tier A Count, Tier B Count, Tier C Count

A Slack digest is posted to `#gtm-analytics` each morning summarizing the previous day.

### Weekly (manual review, 30 minutes)

Every Monday morning, review:

1. **Signal quality**: Are A/B grade accounts actually good ICP fits? Sample 5 accounts and gut-check.
2. **Reply trends**: Are reply rates moving week-over-week? Segment by signal type to identify which sources convert best.
3. **Template performance**: Compare open rate and reply rate across email variants (A/B/C). Deprecate the lowest performer after 50+ sends.
4. **Contact find rate**: Contacts enriched / accounts qualified. Below 60% means enrichment coverage is poor — check which waterfall step is returning the most results and whether keys are valid.

### Monthly (strategic review, 1 hour)

First Monday of each month:

1. Compare actual vs. target metrics from the table above.
2. Calculate cost per meeting for the month.
3. Review HubSpot pipeline for deals stuck in any stage > 14 days.
4. Update champion list — any past contacts who moved to new companies?
5. Adjust scanner lookback windows, signal keywords, or ICP scoring weights if needed.

---

## Diagnostic Playbooks

### Problem: Signals detected is below target

**Threshold**: Less than 50 signals in Month 1 or less than 150 in Month 3.

| Diagnosis | Fix |
|-----------|-----|
| GitHub scanner returning 0 results | Check `GITHUB_TOKEN` validity; verify rate limit with `curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/rate_limit` |
| ArXiv monitor returning 0 results | ArXiv API is public — check network connectivity from n8n host |
| All scanners below target | Expand lookback window: try `--lookback-days 14` or `--lookback-days 30` |
| Signal quality is low (all D-grade) | RL keywords may be matching non-RL repos; tighten search terms in scanner scripts |

### Problem: Reply rate below target

**Threshold**: Below 8% in Month 1 or below 12% by Month 3.

| Diagnosis | Fix |
|-----------|-----|
| Subject lines are generic | Run A/B test: 50% signal-specific subjects (e.g., "saw your PPO paper") vs. pain-point subjects |
| Email body too long | Cut to 4 sentences max. Remove all feature lists. Lead with their specific signal. |
| Signal reference is stale | Check that `signal_date` is within 14 days of send date. Stale signals lose relevance. |
| Sending to wrong titles | Review `Contact.title_category` distribution — are VP Engineering/CTO contacts at large companies (>100 employees) being filtered out? |
| Domain reputation issue | Check open rate: if opens are above 40% but replies below 8%, the message needs work. If opens below 20%, deliverability is the problem. |

### Problem: Deliverability issues (low open rate)

**Threshold**: Open rate below 35%.

| Diagnosis | Fix |
|-----------|-----|
| Domain not warmed | Do not send to real prospects until 4+ weeks of warmup. Check Instantly warmup dashboard. |
| Missing DNS records | Verify SPF, DKIM, DMARC with https://www.mail-tester.com |
| Sending volume too high | Cap at 30 emails/day/account during first 60 days |
| High bounce rate (>3%) | ZeroBounce verification may have failed. Re-run verification on the contact list. |

### Problem: Low contact find rate

**Threshold**: Contacts enriched / accounts qualified below 50%.

| Diagnosis | Fix |
|-----------|-----|
| Apollo free tier exhausted | Upgrade to Apollo Basic ($49/mo) for unlimited exports |
| Hunter API key invalid | Test: `curl "https://api.hunter.io/v2/account?api_key=$HUNTER_API_KEY"` |
| Prospeo key not set | Add `PROSPEO_API_KEY` to n8n variables — it's the third waterfall fallback |
| Targets are researchers without corporate emails | For academic affiliations, use institutional domain patterns manually |

### Problem: HubSpot deals not updating

**Threshold**: Deals stuck in same stage for more than 7 days when Instantly shows activity.

| Diagnosis | Fix |
|-----------|-----|
| Instantly webhook not configured | Verify webhook URL in Instantly matches the `crm-sync` workflow URL exactly |
| HubSpot custom properties missing | Create all properties listed in setup-guide.md Section 5 |
| Reply classification always returning `neutral` | Check Claude API key is valid in n8n variables |

### Problem: Cost per meeting above target

**Threshold**: Above $100 in Month 3+.

| Diagnosis | Fix |
|-----------|-----|
| Too many C-grade accounts being worked | Filter to A/B only in enrichment pipeline; skip C accounts until Month 4+ |
| Enrichment costs increasing | Audit which waterfall step is being used most. If Prospeo (most expensive) is carrying the load, improve Apollo/Hunter coverage. |
| Meetings not being logged | Ensure Calendly or calendar integration is writing `MEETING_SCHEDULED` stage to HubSpot |

---

## Baseline Benchmarks (Cold Email, B2B Technical ICP)

Use these industry benchmarks to contextualize your results:

| Metric | Industry Median | Top Quartile | rl-gtm-engine Target |
|--------|----------------|-------------|---------------------|
| Open rate | 30–40% | 50–60% | 45–65% |
| Reply rate | 3–5% | 8–12% | 12–20% |
| Positive reply rate | 1–2% | 3–5% | 5–8% |
| Meeting-from-sequence rate | 0.5–1% | 2–3% | 3–5% |

rl-gtm-engine targets above-median reply rates because outreach is triggered by real, specific signals rather than static list pulls. The benchmark gap is the core value proposition of signal-based outbound.
