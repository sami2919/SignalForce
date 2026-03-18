---
name: prospect-researcher
description: Use when evaluating a specific company's fit for your ICP, when needing to score an account against ICP criteria, or when preparing for outreach to a new target
---

# Prospect Researcher

## Input

Company name or domain. Optionally: known signal type (GitHub, ArXiv, hiring, funding).

## Steps

**1. Firmographics** — web search for: headcount, funding stage, HQ, founding year, investors.

**2. Technographics** — look for: tech stack, open-source repos, domain-specific keywords from `config/gtm-context.md`.

**3. Domain Maturity** — classify using evidence based on maturity stages defined in `config/gtm-context.md`:
- PRODUCTIONIZING: domain technology in production + papers or 3+ domain engineers
- SCALING: multiple active repos or hiring ≥2 domain-specific roles
- BUILDING: one active repo (commits <90 days) or recent preprint
- EXPLORING: domain technology mentioned in blog/talk/JD but no active code
- NONE: no detectable domain activity

**4. Team Mapping** — find decision makers matching priority titles from `config/gtm-context.md`.

**5. Competitive Landscape** — note any competitor signals: in-house build indicators, known vendor mentions.

**6. Score using** `templates/scoring-rubrics/icp-scoring-model.md`:

```
weighted_score = (signal_strength * 0.30) + (domain_maturity * 0.25) +
                 (company_fit * 0.20) + (budget * 0.15) + (accessibility * 0.10)
```

Apply disqualification overrides before scoring.

## Output

```
## [Company Name] — Grade [A/B/C/D]

**Weighted Score:** X.X / 5.0
**ICP Tier:** [1-4 or None]
**Domain Maturity:** [stage]
**Funding:** [stage, amount, date]
**Headcount:** ~N

### Dimension Scores
| Dimension        | Points | Weight | Contribution |
|------------------|--------|--------|-------------|
| Signal Strength  |        | 0.30   |             |
| Domain Maturity  |        | 0.25   |             |
| Company Fit      |        | 0.20   |             |
| Budget           |        | 0.15   |             |
| Accessibility    |        | 0.10   |             |

### Key Contacts
- [Name], [Title] — [LinkedIn URL if found]

### Messaging Angles
- [Specific technical hook tied to their work]

### Recommended Next Step
[Run contact-finder / skip / nurture]
```
