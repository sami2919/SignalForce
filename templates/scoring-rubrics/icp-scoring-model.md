# ICP Scoring Model — Collinear AI

Use this rubric to score and grade every inbound signal before outreach. Only contact prospects who score B or above. Disqualification overrides trump any numeric score.

---

## Updated Scoring Formula (v2)

### Formula

```
COMBINED_SCORE = (ICP_Fit × 0.4) + (Intent_Signal × 0.6)
```

Intent receives 60% weight because timing beats targeting — a moderately good fit company actively publishing RL research now is a better prospect than a perfect-fit company with no recent signals.

---

### ICP Fit Score (0–5)

ICP Fit is a weighted composite of four dimensions:

| Dimension | Weight of ICP Fit | Details |
|-----------|-------------------|---------|
| RL Maturity | 40% | Depth of RL embedded in core technical work |
| Company Fit / Tier | 30% | Match to ICP tier definitions (see Legacy v1 below) |
| Budget Likelihood | 20% | Proxy indicators for spend capacity |
| Accessibility | 10% | Quality of contact data for highest-priority decision maker |

```
ICP_Fit = (rl_maturity_pts × 0.40) +
          (company_fit_pts  × 0.30) +
          (budget_pts       × 0.20) +
          (accessibility_pts × 0.10)
```

Maximum ICP Fit = 5 × (0.40 + 0.30 + 0.20 + 0.10) = 5.0

---

### Intent Score Calculation

```
per_signal_value = signal_strength × intent_weight × recency_decay

intent_score = sum(per_signal_value for each signal) × breadth_multiplier
```

**Intent Weights by Signal Type:**

| Signal Type | Intent Weight | Rationale |
|-------------|--------------|-----------|
| ArXiv paper published | 3.0 | Strongest buying signal — active research output |
| GitHub RL repo created/updated | 2.5 | Active code = production intent |
| HuggingFace model uploaded | 2.5 | Active experimentation |
| Hiring (RL/ML job postings) | 2.0 | Team growth precedes tooling spend |
| Funding event | 1.5 | Budget available but intent indirect |

**Recency Decay Half-Lives:**

Signals decay exponentially. After one half-life, the signal contributes 50% of its original value.

| Signal Type | Half-Life |
|-------------|-----------|
| LinkedIn activity | 2 days |
| GitHub activity | 5 days |
| HuggingFace upload | 7 days |
| ArXiv publication | 10 days |
| Job posting | 10 days |
| Funding announcement | 21 days |

**Breadth Multiplier:**

Corroboration across multiple source types multiplies confidence.

| Unique Source Types | Multiplier |
|--------------------|------------|
| 1 | 1.0× |
| 2 | 1.5× |
| 3 | 2.0× |
| 4+ | 3.0× |

---

### Grade Thresholds (v2)

| Grade | Combined Score | Action |
|-------|---------------|--------|
| A | ≥ 8.0 | Prioritize — personalize outreach, fast-track |
| B | ≥ 5.0 | Contact — use standard signal-specific template |
| C | ≥ 2.0 | Nurture — add to lower-priority sequence, revisit in 30 days |
| D | < 2.0 | Skip — do not contact; log for future re-evaluation |

---

### Worked Example (v2 Intent Scoring)

**Prospect:** Acme Robotics (Series B, 120 employees, sim-to-real work)

**Step 1 — Calculate ICP Fit:**

| Dimension | Evidence | Points | Weight | Contribution |
|-----------|----------|--------|--------|--------------|
| RL Maturity | 2 active RL repos, commits last 30 days → SCALING | 4 | 0.40 | 1.60 |
| Company Fit | Robotics sim-to-real → Tier 3 | 3 | 0.30 | 0.90 |
| Budget Likelihood | Series B, 120 employees | 5 | 0.20 | 1.00 |
| Accessibility | Verified email for Head of Simulation | 5 | 0.10 | 0.50 |
| **ICP Fit** | | | | **4.00** |

**Step 2 — Calculate Intent Score:**

Signals detected: 1 ArXiv paper (7 days ago, strength=3), 1 GitHub repo (3 days ago, strength=2)

| Signal | Strength | Intent Weight | Recency Decay (half-life) | Days Old | Decay Factor | Weighted Value |
|--------|----------|--------------|--------------------------|----------|--------------|----------------|
| ArXiv paper | 3 | 3.0 | 10d | 7d | 0.616 | 3 × 3.0 × 0.616 = 5.54 |
| GitHub repo | 2 | 2.5 | 5d | 3d | 0.659 | 2 × 2.5 × 0.659 = 3.30 |

Sum = 8.84, Breadth multiplier (2 unique types) = 1.5×

**Intent Score = 8.84 × 1.5 = 13.26**

**Step 3 — Combined Score:**

```
COMBINED = (4.00 × 0.4) + (13.26 × 0.6) = 1.60 + 7.96 = 9.56
```

**Grade: A** — Prioritize outreach. Strong recent signals + solid ICP fit.

---

## Legacy Scoring Formula (v1)

> The formula below is retained for reference and backward compatibility. New scoring uses the v2 intent-weighted formula above.

### Dimensions and Weights

| # | Dimension | Weight |
|---|-----------|--------|
| 1 | Signal Strength | 30% |
| 2 | RL Maturity | 25% |
| 3 | Company Fit | 20% |
| 4 | Budget Likelihood | 15% |
| 5 | Accessibility | 10% |
| **Total** | | **100%** |

---

## Dimension 1: Signal Strength (weight = 0.30)

Composite score produced by the signal stacker (`scripts/signal_stacker.py`). Reflects both the magnitude and the multi-source corroboration of RL activity.

| Raw score | Tier | Points |
|-----------|------|--------|
| Composite ≥ 9, signals from 2+ independent sources | A-tier | 5 |
| Composite ≥ 5 | B-tier | 4 |
| Composite ≥ 2 | C-tier | 2 |
| Composite < 2 | D-tier | 0 |

**Note:** A "source" is one of: GitHub repos, ArXiv papers, Hugging Face model uploads, job postings, or funding announcements. Corroboration across sources multiplies confidence.

---

## Dimension 2: RL Maturity (weight = 0.25)

Assess how deeply RL is embedded in the company's core technical work.

| Level | Evidence | Points |
|-------|----------|--------|
| PRODUCTIONIZING | RL running in production AND (publishing research papers OR dedicated RL team with 3+ engineers) | 5 |
| SCALING | Multiple active RL repos OR actively hiring ≥2 RL roles | 4 |
| BUILDING | At least one active RL repo with commits in the last 90 days, or a preprint on ArXiv | 2 |
| EXPLORING | RL mentioned in a blog post, conference talk, or job description but no active code or papers | 1 |
| NONE | No detectable RL activity | 0 |

---

## Dimension 3: Company Fit (weight = 0.20)

Match to Collinear's ICP tier definitions (see `.agents/gtm-context.md`).

| ICP Tier | Description | Points |
|----------|-------------|--------|
| Tier 1 | AI Lab — frontier model training (OpenAI, Anthropic, DeepMind, Mistral, Cohere, xAI, Meta AI) | 5 |
| Tier 2 | Enterprise AI Agent Builder — LLM-powered agents over enterprise workflows (Jira, ServiceNow, Shopify) | 4 |
| Tier 3 | Robotics & Autonomous Systems — policy learning, sim-to-real | 3 |
| Tier 4 | Industry-Specific RL — finance, energy, gaming, recommendation systems | 2 |
| None | Does not fit any tier | 0 |

---

## Dimension 4: Budget Likelihood (weight = 0.15)

Proxy indicators for budget authority and spend capacity.

| Signal | Points |
|--------|--------|
| Recently funded Series A or later (announced in last 12 months) OR 500+ employees | 5 |
| Funded startup (seed or later) with 20–499 employees | 3 |
| Early-stage or funding status unclear | 1 |
| Pre-revenue or fewer than 10 employees | 0 |

---

## Dimension 5: Accessibility (weight = 0.10)

Quality of contact data available for the highest-priority decision maker.

| Contact status | Points |
|----------------|--------|
| Verified email for Head of ML / Director of ML / VP ML | 5 |
| Verified email for VP Engineering or CTO (at companies ≤ 100 employees) | 3 |
| LinkedIn profile only — no verified email | 1 |
| No contact identified | 0 |

---

## Weighted Score Formula (v1)

```
weighted_score = (
    (signal_strength_pts * 0.30) +
    (rl_maturity_pts     * 0.25) +
    (company_fit_pts     * 0.20) +
    (budget_pts          * 0.15) +
    (accessibility_pts   * 0.10)
)
```

Maximum possible score: `5 * (0.30 + 0.25 + 0.20 + 0.15 + 0.10) = 5 * 1.00 = 5.0`

Weight verification: `0.30 + 0.25 + 0.20 + 0.15 + 0.10 = 1.00` ✓

---

## Grade Thresholds (v1)

| Grade | Weighted Score | Action |
|-------|---------------|--------|
| A | ≥ 4.0 | Prioritize — personalize outreach, fast-track |
| B | ≥ 3.0 | Contact — use standard signal-specific template |
| C | ≥ 2.0 | Nurture — add to lower-priority sequence, revisit in 30 days |
| D | < 2.0 | Skip — do not contact; log for future re-evaluation |

---

## Disqualification Overrides

Any one of the following conditions immediately disqualifies a prospect **regardless of numeric score**:

1. **No RL activity** — no repos, papers, RL-related job postings, or RL-trained models anywhere in their public footprint.
2. **Locked into a competitor** — company has explicitly committed to a competing managed environment platform.
3. **Too small / too early** — fewer than 10 employees or pre-product stage.
4. **Committed to in-house** — a decision maker has publicly stated they are building environments in-house and are not evaluating vendors.

Log all disqualified prospects with the override reason for future review.

---

## Worked Example (v1)

**Prospect:** Acme Robotics (Series B, 120 employees, sim-to-real work)

| Dimension | Evidence | Raw Points | Weight | Contribution |
|-----------|----------|------------|--------|-------------|
| Signal Strength | Composite = 7 (GitHub + ArXiv) → B-tier | 4 | 0.30 | 1.20 |
| RL Maturity | 2 active RL repos, commits last 30 days → SCALING | 4 | 0.25 | 1.00 |
| Company Fit | Robotics sim-to-real work → Tier 3 | 3 | 0.20 | 0.60 |
| Budget Likelihood | Series B, 120 employees | 5 | 0.15 | 0.75 |
| Accessibility | Verified email for Head of Simulation | 5 | 0.10 | 0.50 |
| **Total** | | | | **4.05** |

**Grade: A** — Prioritize outreach. Use `github-rl-signal.md` template, reference their sim-to-real repos directly.
