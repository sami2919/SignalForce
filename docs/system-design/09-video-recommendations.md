# Worked ML Problem: Video Recommendations

> Source: hellointerview.com ML problem-breakdown "video-recommendations" (no video transcript — webpage only).
> Distilled 2026-08-03.
>
> **SignalForce relevance:** SignalForce's signal scoring is a simplified version of the multi-stage
> retrieval+ranking archetype: scanners (retrieval) → signal_stacker (light ranker) → intent_scorer
> (heavy ranker) → grade assignment (re-ranking/value model). The feedback-loop debiasing and
> exploration/exploitation concepts apply to SignalForce's prospect scoring: the model's decisions
> influence which prospects get emailed, which influences reply data, which trains future scoring.
> The staff-level insight (bottleneck is data quality + eval, not model architecture) maps to SignalForce's
> own bottleneck: signal quality and scoring rubric, not the ML model. Pair with [06-ml-core-concepts.md](06-ml-core-concepts.md).

## The problem

"Up next" recommendations shown while a user watches a video (YouTube/TikTok/Reels). ~1B video catalog, ~1B DAU, **250ms latency budget**, 5-video slate. (Not homepage / search.)

## Business-objective escalation (THIRD instance of the depth move)

| Level | Objective | Why |
|---|---|---|
| Bad | Maximize CTR | Clickbait, greedy behavior |
| Better | Maximize watch time | Favors addictive/low-quality content |
| Better | Quality-adjusted watch time | Watch time + quality signals (ratings, completions, shares) |
| **Best (chosen)** | **Quality-adjusted watch time** (balancing user, creator, platform) | Answers clickbait, retention, creator sustainability |

*(Third instance of the business-objective-escalation depth move — same shape as harmful-content's "minimize views" and bot-detection's "minimize impact subject to FP guardrail": question the obvious metric, reframe to actual value, add counter-balancing objectives. Now confirmed across ALL THREE ML problems.)*

**ML objective**: multiple prediction heads — **watch time (regression, primary)** + auxiliary CTR, like-prob, share-prob, completion-rate, return-visit-prob. Heads feed a **value model** for re-ranking.

## Architecture — multi-stage retrieval + ranking (the recommender archetype)

`Candidate generators (parallel, O(10k) each) → Lightweight ranker (~10k→~100) → Heavy ranker (~100, full features) → Re-ranking layer (value model)`

- **Stage 1 — candidate generation (retrieval)**: multiple generators in parallel. Types: universal ("top 10k platform"), personalized ("from subscriptions"), embedding-based (similar to current video / user history). Low-context generators are **cacheable / pre-computable**.
- **Stage 2 — lightweight ranker**: ~10k→~100, fast features, **optimize for RECALL** (don't discard good candidates). Typically **GBDT (XGBoost/LightGBM)** or skinny MLP, CPU, sub-ms.
- **Stage 3 — heavy ranker**: full features, precise scoring. Transformer-based (see modeling). "Where the real magic happens."
- **Stage 4 — re-ranking**: value model balances engagement, creator success, platform health, diversity, special cases (new-creator promotion, viral content).

**Two-tower / dual encoder retrieval** (cross-link [06-ml-core-concepts.md](06-ml-core-concepts.md)): trained with **triplet loss** `L = max(0, margin + d(user, positive) - d(user, negative))`, parallel towers, **hard negatives**, embeddings in a vector DB / ANN index. Generator types: collaborative filtering, content-based, graph-based (co-watch, creator relationships), embedding similarity. *(This is the canonical embedding interview answer from the core-concepts reference, deployed in production.)*

## Features (organized by update frequency → cacheability)

- **Video content** (computed once at upload, cached long-term): metadata (title/desc/tags), thumbnail CV features, audio features, quality metrics, topic/category embeddings.
- **Video engagement** (frequently updated): historical views/likes/avg-watch-time, velocity (growth rate), creator reputation, monetization/advertiser-friendliness.
- **User profile** (static/slow): topic/lang preferences, subscription embeddings, demographics.
- **User behavioral** (highly dynamic): session (recent watches, searches), long-term prefs (favorite creators/categories), time-of-day/day-of-week, device.
- **Encoding**: light ranker = averaged video embeddings with time windows (last 3, last 10); heavy ranker = full sequence.

## Modeling (benchmark → light → heavy)

- **Benchmark**: random blend of generator outputs + simple CF → compute-vs-quality baseline.
- **Light ranker**: GBDT (CPU-friendly, sub-ms, economical to scale) or distilled MLP from the heavy ranker.
- **Heavy ranker — three compared**: (1) **MLP** (concatenated features) — misses high-order interactions, sparsity hard; (2) **DLRM** (Facebook 2019, sparse/dense two towers) — handles feature heterogeneity but no temporal ordering; (3) **Transformer sequence ranker** (preferred) — models sequences, temporal aspects, item interactions. Components: embedding layers for categoricals, normalization for numerics, positional encoding, action-type tokens, **cross-attention (user history × candidate) + self-attention (within history)**, FFN, residual, **multi-task heads**.
- **Loss**: `L_engage` (watch-time-weighted BCE) + `L_aux` (α·click + β·completion + γ·satisfaction) + **`L_position` (δ·BCE·position_weight — position-bias correction, CRITICAL: without debiasing new models eagerly approximate the current system's output)**. *(Cross-link [06-ml-core-concepts.md](06-ml-core-concepts.md) evaluation/presentation-bias + [05-ad-click-aggregator.md](05-ad-click-aggregator.md) feedback loops.)*

## Serving (offline pre-compute vs online, 250ms budget)

**Offline (pre-computed, cached)**: video embeddings (all videos), user embeddings (periodic refresh), low-context candidate-gen results, model param updates (periodic training cycles).
**Online (real-time)**: ANN lookup → parallel candidate gen → light ranker (CPU, sub-ms/item) → heavy ranker (GPU/TPU, quantized) → re-rank (value model).
**Freshness**: new videos need near-real-time embedding + index insertion; user embeddings update on new behavior; **ByteDance Monolith** for online efficient embedding updates (cross-link [06-ml-core-concepts.md](06-ml-core-concepts.md) online embedding updates / TikTok).

## Cold start

- **New users**: demographics + onboarding preferences → assign to coarse clusters of similar existing users → cluster-level patterns → gather interactions → transition to personalized.
- **New videos**: extract rich features **from content itself** (multimodal — thumbnails, titles, transcripts, video) → **controlled exploration** (diverse but limited audience for initial signals) → shift to personalized once behavioral signal exists. *(Same content-based-embedding-then-blend-behavioral pattern as the core-concepts cold-start lesson.)*

## Exploration vs exploitation

**Thompson sampling / contextual bandits**. Per-slot risk budget: safe for top spots, exploratory for lower positions. More adventurous with new users, conservative as behavior is learned. Per-category exploration (explore where user behavior is varied, exploit where consistent). Senior: UCB, epsilon-greedy at scale, measuring exploration effectiveness, confidence-interval compute overhead.

## Diversity, freshness, multi-objective

- **Diversity**: enforced at **re-ranking (slate-level constraints)**; exposure-penalized loss (prevent overexposure of popular); monitor filter bubbles; periodic offline refresh with **uniformly-sampled impressions** (combat popularity bias).
- **Multi-objective value model** trades off: watch time (revenue) / user satisfaction / **creator sustainability** (new creators can join, best get distribution) / platform health. **Over-optimizing one leg harms the others.**

## Feedback loops & presentation bias (the systemic staff-level concern)

- **Popularity bias** (rich-get-richer): highly-ranked → more exposure → more engagement → higher ranking.
- **Filter bubbles**: narrowing content selection.
- **Creator behavior optimization**: producers optimizing for the algorithm over quality.
- **Mitigations**: **counterfactual logging** (log feedback on videos NOT shown), **inverse-propensity weighting** (debias training data), exposure-penalized loss, diversity constraints, uniform impressions, monitoring diversity + creator-success distribution. Position bias → `L_position` correction.

## Evaluation

**Offline** (per stage — "each stage is a new source of potential error in later stages"): retrieval = **Recall@K** (use inputs BEYOND the generator's 10k for unbiased recall); light ranker = recall (don't discard good); heavy ranker = **NDCG, MAP, precision/recall, diversity**; overall = per-head (watch time, CTR).
**Online — A/B gold standard**: engagement (session watch time, return rate, long-term trends), UX (acceptance, survey, negative feedback), system health (latency/throughput/errors), creator metrics (satisfaction, subscriber conversion). **Novelty effects**: new systems seem better just because they differ from the stale set users already saw — watch for it.

## Level expectations + numbers

1B videos · 1B DAU · 5-slate · 250ms · ~10k/generator → ~100 light → ~100 heavy. Mid = basic two-stage, common signals, NDCG/MAP, scaling awareness. Senior = feature-eng depth (normalization, temporal), multi-stage tradeoffs, serving optimizations (caching, embedding compression, efficient NN), competing objectives, A/B monitoring. **Staff = systemic issues (feedback loops, cold start, DATA QUALITY), creative debiasing, recognition that the bottleneck is often data quality + evaluation methodology, NOT model architecture.**

## Trade-offs

| Decision | Trade-off |
|---|---|
| GBDT vs transformer (light vs heavy) | GBDT CPU-cheap, misses sequences; transformer higher quality, expensive |
| DLRM vs transformer | DLRM sparse/dense heterogeneity, no temporal; transformer sequences natively |
| Single vs multi-task | Multi-task = regularizer + auxiliary signals + better cold-start via task correlations |
| More vs fewer generators | More = recall but latency/cost; fewer = risk missing good recs |

---

**Interview anchor**: Video recs is the recommender archetype — the multi-stage retrieval+ranking architecture is the single most transferable ML system design (powers YouTube, TikTok, LinkedIn, Pinterest, search, RAG retrieval). The **business-objective escalation (quality-adjusted watch time, not CTR)** is the THIRD confirmed instance of the depth move that maps directly to your "structured, precise communication of impact" feedback — across all three ML problems now, the shallow answer optimizes the obvious metric and the deep answer reframes to actual value + counter-objectives. The **staff-level insight here is distinctive**: the bottleneck is usually **data quality + evaluation methodology, not model architecture** — feedback loops, presentation bias, and counterfactual logging are what separate staff from senior (not a bigger transformer). This reframes "depth" itself: depth isn't always a fancier model; it's recognizing where the real bottleneck is. Cross-link all: [06-ml-core-concepts.md](06-ml-core-concepts.md) (embeddings, two-tower, feedback loops, eval), [07-harmful-content-detection.md](07-harmful-content-detection.md) + [08-bot-detection.md](08-bot-detection.md) (business-objective escalation pattern + multitask data-aug + two-stage cascade), [05-ad-click-aggregator.md](05-ad-click-aggregator.md) (stream/feedback-loop + importance-sampled A/B).
