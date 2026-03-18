---
name: champion-tracker
description: Use when monitoring job changes of past customers, positive responders, or engaged prospects, or when a known contact moves to a new company and you need to evaluate the new opportunity
---

# Champion Tracker

## Champion Definition

A champion is anyone who has shown genuine interest in your product:
- Past customer or pilot participant
- Replied positively to cold outreach (even "not now")
- Attended a demo or discovery call
- Engaged with content (open-source contributor, GitHub star, paper citation)

Champions carry context. When they move jobs, they bring that context with them — and arrive at a new company with fresh budget and mandate.

## Champion List Setup

Maintain a dedicated "Champions" table in Clay with the following fields: Name, Current Title, Current Company, Current Domain, Original Signal, Last Interaction Date, Job Change Alert.

**Three monitoring layers (run in parallel):**

1. **Clay job change enrichment** — enable "Job Change" column. Clay pings LinkedIn periodically and flags when company or title changes.
2. **Apollo People Alerts** — go to Apollo → Lists → your champion list → enable "Job Change Alert". Sends email notification on change detection.
3. **LinkedIn Sales Navigator** — add all champions to a saved lead list. Enable "Job change" alerts in the alert settings. Most reliable but requires Sales Nav license.

Review champion alerts weekly during pipeline review.

## Job Change Workflow

When a job change is detected:

1. **Verify the change** — confirm on LinkedIn directly. Check new company name, title, and start date.

2. **Evaluate the new company** — run `prospect-researcher` skill on the new company. Score against ICP criteria from `config/gtm-context.md`.

3. **Route by ICP score:**
   - **ICP grade A or B**: Enrich contact at new company (run `contact-finder`), then generate warm outreach within 48 hours. Flag in HubSpot as "Champion Re-engage".
   - **ICP grade C or D**: Log the move in HubSpot. Add a note with new company. Set a 90-day follow-up task — re-evaluate if their domain signals grow.

4. **Log everything in HubSpot** — update contact record with new company, title, domain. Create a new deal if advancing to outreach.

## Champion Outreach

Reference `config/templates/email-sequences/champion-job-change.md` for the full template.

Key principles for champion outreach:
- **Lead with the relationship**, not the pitch. "Congrats on the move" is the opener, not "we help companies like X".
- **Reference shared history** — name the specific interaction ("when we spoke about your setup at [OldCo]").
- **Be brief** — 3–4 sentences max. They know who you are. No need to re-explain the product.
- **Single CTA** — ask for a 15-minute catch-up, not a demo. Lower barrier.
- **Send within 48 hours** of confirming the move. After 2 weeks, the "congrats on the new role" opener loses credibility.

Do not add champions to cold sequences. Always send individually from a primary inbox, not a sending domain.
