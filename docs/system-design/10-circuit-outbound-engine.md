# Circuit Outbound Engine — Production-Hardened Interview Narrative

> Standalone study document: `/Users/sami/Desktop/Circuit-Outbound-Engine-One-Pager.md`.
> Research doc: `/Users/sami/Desktop/Circuit-Outbound-Engine-Research.md`.
>
> **SignalForce relevance:** This is the production-hardened version of the outbound engine that SignalForce
> evolved into. It closes all four gaps from the Rippling onsite (John Kutay's interview): deployment,
> database, imprecise impact numbers, and jumping to architecture before saying what the system is.
> It is grounded in SignalForce's real signal philosophy (ICP×0.4 + Intent×0.6, recency decay, breadth
> multiplier, 6+1 signals, "skip a prospect than send garbage") and applies the system design concepts
> from [01](01-system-design-fundamentals.md)–[09](09-video-recommendations.md).

## Why it exists

The Rippling onsite (John Kutay's interview) exposed four gaps on the Circuit outbound engine project:
1. Couldn't answer where it was deployed (it was a laptop)
2. Couldn't name the database
3. Imprecise/contradictory impact numbers (8% vs 48% reply rate, "I can't remember")
4. Jumped to architecture (LangGraph/Pydantic/type-state) before saying what the system was

This doc is the fixed, production-hardened version.

## Framing (Option B, locked)

The prototype ran on a laptop and is kept as a 2-sentence credibility anchor. The production architecture is the impressive centerpiece, and each of the 3 honest weaknesses is eliminated *by design* — not answered with "gap I'd close with more time."

**Integrity guardrail**: every production claim is framed as "designed / would build," NEVER as "what ran" — the follow-up Q&A (esp. "so this ran sharded in prod?" → "no, designed for it, haven't needed it, here's the math") is what lets the depth survive a Bar Raiser without overclaiming.

## What it contains

- **30-sec pitch** (conclusion-first)
- **Reframed business objective**: pipeline-per-dollar + no-garbage constraint
- **Honest-origin + 3-weaknesses-eliminated framing table**
- **Production architecture (eliminates weakness #1)**:
  - Queue topology (1 queue+state-machine → 5 queues, zero-rewrite seam)
  - SQS-over-Kafka justification (research finding: no real system in this space — Apollo/Clay/6sense/Outreach/Salesloft/ZoomInfo — is streaming-first)
  - ALB+ECS Fargate+RDS+ElastiCache multi-AZ + laptop→prod replacement table
  - Sharding math (shard at ~500M prospects, hash(prospect_id)%N, never range-shard) — applies [02-sharding.md](02-sharding.md)
  - HMAC idempotency + transactional outbox (three-layer double-send defense, cite Stripe) — applies [05-ad-click-aggregator.md](05-ad-click-aggregator.md) HMAC pattern
  - DLQ by failure type — applies [04-web-crawler.md](04-web-crawler.md) SQS/DLQ pattern
  - Graceful degradation chains
  - Redis caching with stampede protection — applies [03-caching.md](03-caching.md) cache-aside + stampede
- **Eval harness (eliminates weakness #2 — centerpiece)**:
  - Gate as binary classifier — applies [07-harmful-content-detection.md](07-harmful-content-detection.md) precision-guardrail concept
  - 3-phase labeled-set construction (200 human-rated → 500 reply-tracked → 5K+ learned)
  - PR-curve F_0.5 threshold selection with `select_threshold()` code + no-garbage constraints
  - Gate config versioning, A/B + shadow-mode canary, drift monitoring + alert runbook
  - LLM-gate eval (faithfulness > consistency/Cohen's Kappa > calibration > bias)
- **Upfront schema (eliminates weakness #3)**:
  - 5-stage schema sketch with `gate_decision` as the star (stores full eval trace)
  - Version-everywhere/additive re-runs, idempotency as UNIQUE constraints
  - Organic-vs-designed comparison
- **4 key design decisions**:
  - One-orchestrator/gambler's-ruin (no agent-to-agent chains)
  - Deterministic scoring ICP×0.4+Intent×0.6 with trace (= SignalForce's real scoring formula)
  - Model tiering DeepSeek/Opus
  - Cross-family GPT-4o-mini judge
- **Signal validation methodology**: cohort holdout, zero-out testing, SQO north star — closes the Sajwal gap, applies [08-bot-detection.md](08-bot-detection.md) two-period holdout + [07-harmful-content-detection.md](07-harmful-content-detection.md) importance sampling
- **Precise numbers table** with method stated (UNCHANGED — architecture/eval figures are design targets, labeled as such)
- **The 8 hardest follow-up Q&A** (replaces "honest weaknesses": sharding-math, threshold-without-labels, p99 latency, enrichment-down degradation, double-send defense, evaluating-an-LLM-gate, GDPR/opt-out, what-to-cut-in-Phase-1)
- **GTM-engineering-principle bridge**
- **Trade-offs table**
- **The 8-beat top-down delivery script**

Full 13-table DDL + full Q&A + sources are in the research doc at `/Users/sami/Desktop/Circuit-Outbound-Engine-Research.md`, referenced not duplicated.

## Grounded in

- Sami's real signal philosophy (SignalForce retrospective: ICP×0.4+Intent×0.6, recency decay, breadth multiplier, 6+1 signals, "skip a prospect than send garbage")
- John Kutay's philosophy (gambler's ruin, DRY(E)="Don't Repeat Your Embeddings", determinism, entity resolution, "the diff not the snapshot")
- The 9 system-design references in this directory: two-stage cascade from [05](05-ad-click-aggregator.md)/[04](04-web-crawler.md), SQS/DLQ from [04](04-web-crawler.md), Postgres-vs-NoSQL + Redis from [01](01-system-design-fundamentals.md), sharding-by-domain from [02](02-sharding.md), cache-aside from [03](03-caching.md), cohort holdout/importance sampling from [08](08-bot-detection.md)/[07](07-harmful-content-detection.md)

## The rules it trains

1. **Justify the need before the architecture; justify the choice before the name** — the architecture was right in the Rippling interview, the communication was the gap.
2. **Frame the production design as *designed*, not as *ran*** — impressive depth with honest origin beats impressive depth that unravels under one follow-up.
