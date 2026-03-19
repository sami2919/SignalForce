---
name: resource-offer
description: Use when generating blueprint-first outreach that offers a free resource instead of asking for a meeting, when targeting technical buyers who respond better to value-add than demo requests, or when implementing the resource-before-demo funnel strategy
---

# Resource Offer

## Why Resource-First

Technical buyers — domain researchers, ML leads, senior engineers — route unsolicited demo asks to the trash. They respond to peers sharing useful knowledge. Offering a free, relevant resource before asking for anything converts at 50% reply rate vs. 8-15% for demo asks. Default to this for ICP Tier 1 and Tier 3 accounts.

## Input

- Signal type: `github` | `arxiv` | `hiring` | `funding` | `huggingface`
- Signal payload: specific repo / paper / job title / round (be precise)
- Contact: name, title, company
- Company research from `prospect-researcher`

## Workflow

**Step 1 — Select the resource.**
Match signal type to resource using the table in `config/templates/email-sequences/resource-offer-signal.md`. The resource must be relevant to the specific signal, not generic.

**Step 2 — Extract a concrete insight.**
Identify one specific, non-obvious takeaway from the resource that applies to this prospect's situation. This becomes the Email 2 payload. Vague insights fail. Specific, quantified ones work.

**Step 3 — Generate the sequence.**
Use `config/templates/email-sequences/resource-offer-signal.md`. Write all three variants (Problem-Focused, Outcome-Focused, Social-Proof-Focused). Fill every placeholder with signal-specific content — no generic substitutions.

**Step 4 — Seven Sweeps copy review.**
Run each email through these passes before output:

1. **Clarity** — Can the reader understand every sentence? Flag jargon, buried points.
2. **Voice** — Does it sound like a peer, not a vendor? Read it aloud.
3. **So What?** — Does every claim answer "why should I care?" Add "which means..." bridges from features to benefits.
4. **Prove It** — Is every claim substantiated? No vague social proof ("trusted by thousands"). Use specific numbers.
5. **Specificity** — Replace vague language with numbers and timeframes. "Save time" → "Save 4 hours/week."
6. **Emotion** — Does the copy make the reader feel something? Paint the "before" state vividly.
7. **Zero Risk** — Have we removed every barrier? Near CTAs, check for unanswered objections.

**Step 5 — Final verify.**
Before output, check each email:
- [ ] Email 1 and 2 contain zero meeting asks
- [ ] Email 3 offers only a resource walkthrough, not a demo
- [ ] First sentence references the exact signal
- [ ] No banned phrases (see `config/gtm-context.md`)
- [ ] 4 sentences max per email
- [ ] Subject line is 2-4 words, lowercase, no punctuation
- [ ] Passed all seven sweeps

## Output

Present all 3 variants with their 3-email sequences. End with:

**Recommended pick:** [Variant X] — [one-sentence rationale tied to their ICP tier and signal type]

**Resource selected:** [Resource title] — [one sentence on why this resource fits this signal]
