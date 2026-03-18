---
name: pipeline-tracker
description: Use when needing to sync outbound activity to CRM, generate pipeline analytics, create weekly reports, or track conversion metrics across the outbound funnel
---

# Pipeline Tracker

## HubSpot Setup

### Custom Properties (create once)

| Property | Type | Values |
|----------|------|--------|
| `signal_source` | Enum | github, arxiv, huggingface, hiring, funding |
| `icp_tier` | Enum | tier1, tier2, tier3, tier4 |
| `domain_maturity` | Enum | productionizing, scaling, building, exploring, none |
| `composite_score` | Number | 0–25 |
| `icp_grade` | Enum | A, B, C, D |
| `sequence_name` | String | e.g. github-signal-varA |
| `signal_date` | Date | date signal was detected |

Create via: HubSpot → Settings → Properties → Contacts/Deals → Create property.

## Auto-Population

When a prospect enters a sequence:
1. Create/update Contact with all custom properties from signal stacker output
2. Create Deal linked to Contact: name = `[Company] — [Signal Type] — [Date]`
3. Set Deal stage to `Sequence Active`
4. Set `sequence_name` to the template variant being used

## Deal Stage Mapping

| Email Event | Deal Stage |
|-------------|------------|
| Sequence started | Sequence Active |
| Email opened (2+) | Engaged |
| Link clicked | Engaged |
| Reply received | Replied |
| Meeting booked | Meeting Booked |
| No response after sequence | Sequence Ended — No Response |

## Weekly Report

Pull from HubSpot and present:

```
## Outbound Report — Week of [date]

| Metric | This Week | Last Week | Trend |
|--------|-----------|-----------|-------|
| Signals detected | | | |
| Accounts qualified (B+) | | | |
| Sequences started | | | |
| Open rate | | | |
| Reply rate | | | |
| Meetings booked | | | |
| Cost per meeting (est.) | | | |

### Top Accounts by ICP Grade
[table: Company | Grade | Stage | Signal Source]

### Action Items
[any A-grade accounts stalled — flag for manual follow-up]
```

## Slack Notifications

Send to `#outbound-signals` channel for:
- Grade A account replies
- Meeting booked
- Champion job change detected (trigger `champion-job-change` template)
