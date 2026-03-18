---
name: email-writer
description: Use when generating outreach emails for target accounts, when personalizing email copy based on detected signals, or when creating A/B test variants for cold email campaigns
---

# Email Writer

## Input

- Signal type: `github` | `arxiv` | `hiring` | `funding` | `huggingface` | `champion-job-change`
- Signal payload: specific repo/paper/job title/funding round (be precise)
- Contact: name, title, company
- Company research output from `prospect-researcher`

## Template Selection

| Signal Type | Template |
|-------------|----------|
| Any signal + technical buyer | `config/templates/email-sequences/resource-offer-signal.md` **(RECOMMENDED)** |
| GitHub repo activity | `config/templates/email-sequences/github-signal.md` |
| ArXiv paper | `config/templates/email-sequences/arxiv-paper-signal.md` |
| Job posting | `config/templates/email-sequences/hiring-signal.md` |
| Funding round | `config/templates/email-sequences/funding-signal.md` |
| HuggingFace model upload | `config/templates/email-sequences/huggingface-model-signal.md` |
| Champion changed jobs | `config/templates/email-sequences/champion-job-change.md` |

> **Resource-first outreach gets 50% reply rates vs. 8-15% for demo asks. Default to `resource-offer-signal.md` for ICP Tier 1 and Tier 3. Use signal-specific templates when the prospect is already in a demo pipeline or has explicitly requested product information.**

## Generate 3 Variants

For each variant, write a full 3-email sequence (initial + follow-up 1 + follow-up 2):

- **Variant A — Problem:** Lead with the pain point their signal reveals
- **Variant B — Outcome:** Lead with a proof point (Kore.ai: 91% improvement)
- **Variant C — Social Proof:** Lead with a peer company or co-author signal

## Voice Rules (from `config/gtm-context.md`)

- 4 sentences max on initial email
- Reference their specific technical work (repo name, paper title, job req language)
- Low-friction CTA: "worth a 20-minute call?" not "schedule a demo"
- Never: "I hope this email finds you well", "I noticed your company", "touching base"

## Quality Checklist

Before outputting, verify each email:
- [ ] References specific signal (not generic "I noticed you work in this domain")
- [ ] ≤4 sentences in initial outreach
- [ ] No banned phrases
- [ ] CTA is low-friction and specific
- [ ] Subject line < 50 chars, no clickbait

## Output

Present all 3 variants with their 3-email sequences. End with:

**Recommended pick:** [Variant X] — [one-sentence rationale tied to their specific signal/ICP tier]
