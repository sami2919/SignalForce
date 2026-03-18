---
name: meeting-followup
description: Use when a meeting has been completed and you need to generate follow-up emails, when processing meeting notes to extract next steps and objections, or when routing post-meeting tasks based on meeting outcome
---

# Meeting Follow-Up

## Input

Provide one of:
- Free-text meeting notes (transcript excerpt, CRM note, bullet points)
- Structured `MeetingOutcome` record from `scripts/models.py`

Required fields: deal ID or company name, meeting date, attendees, outcome signal.

## Step 1: Extract Structured Data

From notes, extract and populate a `MeetingOutcome` record:

| Field | What to look for |
|-------|-----------------|
| `outcome` | Buying signal ("loved it", "interested") → `positive`; polite but vague → `neutral`; "not now", "no budget" → `negative`; no attendance → `no_show` |
| `objections` | Any hesitation, technical concern, or blocker raised |
| `next_steps` | Explicit commitments or asks from either party |
| `decision_timeline` | Any deadline or review window mentioned |
| `stakeholders_needed` | Names or roles needed for sign-off |
| `follow_up_resources` | Docs, case studies, or demos promised |

## Step 2: Select Template Sequence

Load `templates/email-sequences/meeting-followup.md` and select the block matching `outcome`:

- `positive` → 3-email sequence (Day 0, 3, 7)
- `neutral` → 3-email sequence (Day 0, 5, 14)
- `negative` → 1 email only; flag for 6-month re-qualification
- `no_show` → 2-email sequence (Day 0, 3)

## Step 3: Generate Follow-Up Emails

For each email in the sequence:

1. Fill all `{{placeholders}}` with data from `MeetingOutcome`
2. Reference specific objections by name — never use generic language
3. Tie resources to what was discussed, not generic product features
4. Keep subject lines under 50 characters
5. CTA must be low-friction: calendar link, async resource, or a direct question

Voice rules (from `.agents/gtm-context.md`): no "just checking in", no "hope this finds you well", no unsolicited demo asks.

## Step 4: CRM and Sequencing Recommendations

Output a CRM action block:

- **Stage update**: advance `DealStage` to `MEETING_COMPLETED`
- **Next touch date**: Day 0 email send date + sequence cadence
- **Stakeholder tasks**: if `stakeholders_needed` is non-empty, create a task to arrange intro
- **Re-qual flag**: if `outcome` is `negative`, set reminder for 6 months

## Output Format

```
## MeetingOutcome Record
[populated record]

## Follow-Up Sequence ([outcome])
### Email 1 — Day 0
Subject: ...
Body: ...

### Email 2 — Day N  (if applicable)
...

## CRM Actions
- Stage: MEETING_COMPLETED
- Next touch: [date]
- Tasks: [list]
```
