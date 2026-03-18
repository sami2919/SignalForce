---
name: setup
description: "Use when configuring SignalForce for a new ICP, when setting up the project for the first time, or when switching to a different target market"
---

# Setup

## Step 1 — Understand the business

Ask the user:

> "What does your company sell, and who do you sell to?"

Wait for their answer before proceeding.

## Step 2 — Auto-generate config

Use `config.example/config.yaml` as the schema template. Based on the user's answer, generate:

**`config/config.yaml`**
- Keywords tuned to their domain (product names, technology terms, research areas)
- Job titles that map to their buyer personas (economic buyer, technical buyer, champion)
- ICP tiers ranked by fit (Tier 1 = ideal, Tier 2 = good, Tier 3 = marginal)
- Scoring weights that match signal value for their market
- Enable scanners that are likely to surface signal; disable those that won't

**`config/gtm-context.md`**
- Product positioning in 2–3 sentences (what it does, for whom, why now)
- Voice and tone rules (formal/informal, technical depth, banned phrases)
- Target personas with pain points and buying triggers per tier

**`config/templates/email-sequences/`**
- One draft 3-email sequence per enabled scanner signal type
- Follow the 4-sentence rule for initial outreach; low-friction CTA

**`config/templates/linkedin-sequences/`**
- One draft connection request + follow-up per enabled signal type
- Keep connection requests under 300 characters

Create `config/` if it does not exist. Write all files before presenting for review.

## Step 3 — Present inferences for review

Show a concise summary:

```
ICP Tiers:     [Tier 1 name] / [Tier 2 name] / [Tier 3 name]
Key signals:   [list of enabled scanners]
Disabled:      [list of disabled scanners and why]
Keywords:      [top 10 keywords]
Buyer titles:  [list]
```

Ask: "What did I get wrong?"

## Step 4 — Iterate on corrections

Apply each correction the user identifies and regenerate the affected section. Re-present the summary. Repeat until the user confirms the config looks correct.

## Step 5 — Validate

Run `/validate` on the generated config before confirming setup is complete. Fix any ERRORs before finishing. Surface WARNs to the user with suggested fixes.

## Notes

- Reference `config.example/config.yaml` for field names, types, and defaults.
- Never copy example values verbatim — always infer values from the user's domain.
- If the user's market has no obvious GitHub or ArXiv signal, disable those scanners and explain why.
