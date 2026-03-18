---
name: resource-offer
description: Use when generating blueprint-first outreach that offers a free resource instead of asking for a meeting, when targeting technical buyers who respond better to value-add than demo requests, or when implementing the resource-before-demo funnel strategy
---

# Resource Offer

## Why Resource-First

Technical buyers — RL researchers, ML leads, simulation engineers — route unsolicited demo asks to the trash. They respond to peers sharing useful knowledge. Offering a free, relevant resource before asking for anything converts at 50% reply rate vs. 8-15% for demo asks. Default to this for ICP Tier 1 (AI Labs) and Tier 3 (Robotics).

## Input

- Signal type: `github` | `arxiv` | `hiring` | `funding` | `huggingface`
- Signal payload: specific repo / paper / job title / round (be precise)
- Contact: name, title, company
- Company research from `prospect-researcher`

## Workflow

**Step 1 — Select the resource.**
Match signal type to resource using the table in `templates/email-sequences/resource-offer-signal.md`. The resource must be relevant to the specific signal, not generic.

**Step 2 — Extract a concrete insight.**
Identify one specific, non-obvious takeaway from the resource that applies to this prospect's situation. This becomes the Email 2 payload. Vague insights ("environments matter") fail. Specific ones ("teams that instrument environment reward variance before scaling reduce dead-run rate by ~40%") work.

**Step 3 — Generate the sequence.**
Use `templates/email-sequences/resource-offer-signal.md`. Write all three variants (Problem-Focused, Outcome-Focused, Social-Proof-Focused). Fill every placeholder with signal-specific content — no generic substitutions.

**Step 4 — Verify.**
Before output, check each email:
- [ ] Email 1 and 2 contain zero meeting asks
- [ ] Email 3 offers only a resource walkthrough, not a demo
- [ ] First sentence references the exact signal
- [ ] No banned phrases (see `.agents/gtm-context.md`)
- [ ] 4 sentences max per email
- [ ] Subject line under 50 characters

## Output

Present all 3 variants with their 3-email sequences. End with:

**Recommended pick:** [Variant X] — [one-sentence rationale tied to their ICP tier and signal type]

**Resource selected:** [Resource title] — [one sentence on why this resource fits this signal]
