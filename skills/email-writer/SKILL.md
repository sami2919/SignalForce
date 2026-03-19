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

## Writing Principles

- **Write like a peer, not a vendor.** Use contractions. Read it aloud. If it sounds like marketing copy, rewrite it.
- **Every sentence must earn its place.** Cold email is ruthlessly short. If a sentence doesn't move the reader toward replying, cut it.
- **Personalization must connect to the problem.** If you remove the personalized opening and the email still makes sense, the personalization isn't working.
- **Lead with their world, not yours.** "You/your" should dominate over "I/we." Don't open with who you are.
- **One ask, low friction.** Interest-based CTAs ("Worth exploring?" / "Would this be useful?") beat meeting requests.

## Subject Lines

Short, boring, internal-looking. The subject line's only job is to get the email opened.

- 2-4 words, lowercase, no punctuation
- Should look like it came from a colleague, not a vendor
- Examples: "reply rates", "hiring ops", "Q2 forecast", "environment question"
- Never: product pitches, urgency words, emojis, ALL CAPS

## Voice Rules (from `config/gtm-context.md`)

- 4 sentences max on initial email
- Reference their specific technical work (repo name, paper title, job req language)
- Low-friction CTA: "worth a 20-minute call?" not "schedule a demo"
- Never: "I hope this email finds you well", "I noticed your company", "touching base"

## Response Handling

When a reply comes in, classify and respond within the SLA:

| Reply Type | SLA | Action |
|---|---|---|
| Positive ("Yes, let's talk") | 5 min | Book meeting, send calendar link |
| Curious ("Tell me more") | 1 hr | Send one proof point, re-offer value |
| Objection ("Too small/early") | Same day | Acknowledge → brief proof → micro-commit |
| Timing ("Not now, Q3") | Same day | Set reminder, polite close |
| Referral ("Talk to our CTO") | 1 hr | Reach out to referral, mention introducer |
| Hard no | 24 hr | Polite close, mark in CRM |

## A/B Testing

When generating variants, design them as testable splits:

| Element | Test Approach |
|---|---|
| Subject lines | Question vs. statement |
| First line | Signal-reference vs. pain-point vs. question |
| CTA | Direct ask vs. soft offer vs. value offer |
| Length | Short (50w) vs. medium (100w) |

Send 50/50 split to first 100 prospects. Wait 48h, measure opens + replies. Winner goes to remaining list.

## Quality Checklist

Before outputting, verify each email:
- [ ] References specific signal (not generic "I noticed you work in this domain")
- [ ] ≤4 sentences in initial outreach
- [ ] No banned phrases
- [ ] CTA is low-friction and specific
- [ ] Subject line is 2-4 words, lowercase, no punctuation
- [ ] Personalization connects to the problem (not decorative)
- [ ] "You/your" dominates over "I/we"

## Output

Present all 3 variants with their 3-email sequences. End with:

**Recommended pick:** [Variant X] — [one-sentence rationale tied to their specific signal/ICP tier]

**A/B test suggestion:** [Which element to test first and why]
