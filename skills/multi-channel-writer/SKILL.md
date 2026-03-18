---
name: multi-channel-writer
description: Use when generating coordinated outreach across email and LinkedIn, when building staggered multi-channel sequences, or when a prospect hasn't responded to single-channel outreach
---

# Multi-Channel Writer

## Input

- Contact data: name, title, company, email (yes/no), LinkedIn URL (yes/no)
- Signal type: `github` | `arxiv` | `hiring` | `funding` | `huggingface`
- Signal payload: specific detail (repo name, paper title, job title, etc.)
- Company research from `prospect-researcher`

## Step 1 — Determine Channels

Call `select_primary_channel(has_email, has_linkedin)` from `scripts/multi_channel_sequencer.py`.

| Available | Sequence |
|-----------|----------|
| Email + LinkedIn | Dual channel (6 steps) |
| Email only | Email only (3 steps) |
| LinkedIn only | LinkedIn only (3 steps) |

## Step 2 — Build Sequence

Call `build_sequence(channels, signal_type)`. This returns the ordered `SequenceStep` list with days, channels, actions, and template names.

## Step 3 — Generate Copy

For each step, write the actual message using the mapped template:

**Email templates** → `templates/email-sequences/`
**LinkedIn templates** → `templates/linkedin-sequences/`

Fill all placeholders from the signal payload and contact data. Never leave a placeholder unfilled.

Connection request notes must be ≤300 characters. Count before outputting.

## Step 4 — Present the Full Plan

Output a single table showing the complete sequence:

| Day | Channel | Action | Subject / Opening line |
|-----|---------|--------|------------------------|

Then present the full copy for each step in order.

## Voice Rules

- Email: 4 sentences max on Day 0. Reference the specific signal. Low-friction CTA.
- LinkedIn connection: ≤300 chars, zero product mention, peer-to-peer tone.
- LinkedIn follow-ups: lead with a resource or insight, no pitch unless they ask.
- Never: "I hope this email finds you well", "touching base", "I noticed your company".

## Quality Checklist

Before outputting, verify:
- [ ] Connection request notes are ≤300 characters
- [ ] Day 0 email is ≤4 sentences
- [ ] No placeholder left as `{{placeholder}}`
- [ ] No product mention in LinkedIn connection note
- [ ] Steps are in ascending day order
- [ ] Each step references the specific signal, not generic RL interest
