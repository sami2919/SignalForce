---
name: prospect-researcher
description: Use when evaluating a specific company's fit for RL infrastructure sales, when needing to score an account against ICP criteria, or when preparing for outreach to a new target
---

# Prospect Researcher

## Input

Company name or domain. Optionally: known signal type (GitHub, ArXiv, hiring, funding).

## Steps

**1. Firmographics** — web search for: headcount, funding stage, HQ, founding year, investors.

**2. Technographics** — look for: tech stack, open-source repos, RL keywords (RLHF, GRPO, PPO, Gymnasium, MuJoCo, sim-to-real, reward modeling, DPO, RLAIF, policy gradient).

**3. RL Maturity** — classify using evidence:
- PRODUCTIONIZING: RL in production + papers or 3+ RL engineers
- SCALING: multiple active RL repos or hiring ≥2 RL roles
- BUILDING: one active RL repo (commits <90 days) or ArXiv preprint
- EXPLORING: RL mentioned in blog/talk/JD but no active code
- NONE: no detectable RL activity

**4. Team Mapping** — find decision makers matching priority titles from `.agents/gtm-context.md` (Head of ML, VP ML, Principal ML Eng, VP Eng/CTO at <100 employees, RL Engineer).

**5. Competitive Landscape** — note any competitor signals: in-house build indicators, Idler/Mechanize/Osmosis mentions.

**6. Score using** `templates/scoring-rubrics/icp-scoring-model.md`:

```
weighted_score = (signal_strength * 0.30) + (rl_maturity * 0.25) +
                 (company_fit * 0.20) + (budget * 0.15) + (accessibility * 0.10)
```

Apply disqualification overrides before scoring.

## Output

```
## [Company Name] — Grade [A/B/C/D]

**Weighted Score:** X.X / 5.0
**ICP Tier:** [1-4 or None]
**RL Maturity:** [stage]
**Funding:** [stage, amount, date]
**Headcount:** ~N

### Dimension Scores
| Dimension       | Points | Weight | Contribution |
|-----------------|--------|--------|-------------|
| Signal Strength |        | 0.30   |             |
| RL Maturity     |        | 0.25   |             |
| Company Fit     |        | 0.20   |             |
| Budget          |        | 0.15   |             |
| Accessibility   |        | 0.10   |             |

### Key Contacts
- [Name], [Title] — [LinkedIn URL if found]

### Messaging Angles
- [Specific technical hook tied to their work]

### Recommended Next Step
[Run contact-finder / skip / nurture]
```
