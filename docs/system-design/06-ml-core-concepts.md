# ML System Design Core Concepts

> Source: hellointerview.com ML system design core-concepts — feature-engineering, embeddings, generalization, evaluation.
> Distilled 2026-08-03.
>
> **SignalForce relevance:** SignalForce's intent scoring (ICP×0.4 + Intent×0.6) is a lightweight version of
> the feature engineering + scoring concepts here. The Bayesian smoothing technique for rates directly
> applies to SignalForce's signal strength normalization (a signal with 2 events shouldn't score the same
> as one with 200). The feedback-loop pitfall is real for SignalForce: the scoring model's decisions
> influence which prospects get emailed, which influences reply data, which trains future scoring. The
> earmarking technique is the interview communication discipline. Pair with the distributed-systems
> references [01](01-system-design-fundamentals.md)–[05](05-ad-click-aggregator.md) for the contrast.

## The ML system design interview shape (vs distributed systems)

Distributed-systems interviews: requirements → entities/API → HLD → deep dives on scale/fault-tolerance/latency. ML-system-design interviews: **define the ML task → data & features → model → training → evaluation → serving/monitoring**. The four core concepts here map to the middle of that flow. The same "justify against the constraint, don't regurgitate" depth discipline applies (see [04-web-crawler.md](04-web-crawler.md) bloom-filter lesson, [05-ad-click-aggregator.md](05-ad-click-aggregator.md) checkpointing lesson).

---

# 1. FEATURE ENGINEERING

## The modern reframe (don't miss this)

Historically = hand-crafting numeric features for logistic regression / GBDTs. **Today's production systems (YouTube, LinkedIn, Meta, Pinterest) lean on transformers/DLRM/multimodal models that consume raw text, images, event sequences directly — the model learns interactions itself.** Hand-tuned numeric features survive mainly in light rankers, tree models, trust-and-safety.

The discussion still matters because **deciding which data sources to expose to the model is a design decision no model can make for itself.** A transformer can learn dwell-time × creator-reputation interactions, but only if both signals are fed to it. Most "model isn't learning what we want" production failures reduce to: a missing source, a stale source, or a source computed inconsistently between training and serving.

→ Modern conversation = "identifying signal sources, choosing how to expose them, keeping them fresh, keeping train/serve in sync." Not low-level feature crafting.

## The 5 signal sources (enumerate THESE, not individual features)

| Source | What | Example signals | Model intake |
|---|---|---|---|
| **Content / Item** | The thing being scored | Post text, thumbnail, audio, metadata | Raw text→tokens, image→patches |
| **Actor / Creator / User** | Who's involved | Taste embedding, account age, verification | Upstream embedding + explicit attrs |
| **Behavior / Engagement** | What happened | Recent watch sequence, view velocity, report rates | Sequence-as-tokens (heavy) or aggregates (light) |
| **Network / Graph** | Relationships | GNN embedding, co-watcher overlap, follower position | Graph embedding as feature |
| **Context / Request** | The call itself | Time of day, device, page, geo, recent searches | Small dense vector at input |

- **Content** dominates when "what does this thing look like" is central (harmful-content detection); tells little for recommendation.
- **Actor**: dominant pattern = "slow-but-rich embedding + fast-but-noisy explicit attributes." Big companies share cross-team user embeddings — common to assume they already exist.
- **Behavioral**: where most engineering pain lives — drifts, leaks, computed inconsistently train vs serve. 10 yrs ago: `clicks_in_last_hour` scalar. Today: raw `(item_id, action, timestamp)` sequence into a transformer.
- **Network**: heavy in adversarial/social domains; GNN embedding is the dominant consumption. Hand-crafted (clustering coefficient, follower ratio) survives where interpretable/auditable signals are needed.
- **Context**: cheap, almost always real-time, surprisingly predictive. **Most candidates forget it entirely — mentioning it signals holistic thinking.**

**Signal velocity**: different signals in the same bucket move at different rates. Content embedding = slow (daily); creator's last-hour report rate = fast (streaming). Cheapest→most expensive: static → daily batch → streaming → request-time. Infra requirements differ completely.

## Encoding by feature shape (decision table)

- **Raw text** → tokenize + transformer encoder (BERT). "Almost no manual feature engineering here in modern systems."
- **Raw images** → patch-encode through ViT.
- **Text + image together** → contrastive alignment in shared space (CLIP). DoorDash DashCLIP: CLIP-style on 32M query-product pairs.
- **Sparse categoricals (IDs, enums)** → learned embedding table, one vector per category. **Hashing trick** for high cardinality: fixed bucket count (10M not 1B), hash IDs in; heavy users dominate their bucket, long-tail share buckets → drift toward "average user" embedding. (1B users × 64-dim = ~256GB → needs hashing.)
- **Sequences**: (a) **Aggregation** = mean of embeddings of last N items, recency-weighted. Cheap, loses ordering, for light rankers (wide funnel, millions of candidates). (b) **Sequence-as-tokens** = raw `(item, action, timestamp)` into transformer, learns temporal structure, heavy ranker (LinkedIn Generative Recommender 1000+ actions; Pinterest TransActV2 16k lifelong actions). **Senior candidates know both: aggregations for the wide funnel, full sequences for the narrow one.**
- **Numeric scalars** (where old-school engineering still matters):
  - **Log-scaling** — default for power-law (views, followers, $). Without it 100K→1M gap dwarfs everything.
  - **Bucketing + embedding** — discretize into 10–100 buckets, embed each. For non-monotonic value→label relationships.
  - **Standardization** (zero mean, unit variance) — matters for linear models, less for trees/embeddings. Params from training data, applied identically at serve.
  - **Bayesian smoothing for rates** — `smoothed = (negatives + α·C) / (views + C)`, α = prior rate (e.g. 2%), C = pseudo-count (e.g. 50). Fixes small-sample rates: video B (8 views, 4 negatives = 50% naive) → ~8.6% smoothed; video C (9K views, 1800 negatives) is actually worst, not A.
  - **Recency**: exponential decay `exp(-Δt/τ)` (τ half-life: 1 day for clicks, 30 days for watch completions); multiple time windows (1h, 1d, 7d — high 1h + normal 7d = unusual session; high 7d + low 1h = cooled off). Production ships all three for the handful of rate features that matter.

## Pitfalls that disqualify candidates

1. **Leakage** — feature unavailable at serve time (moderator label assigned *after* prediction; `total_clicks_lifetime` on the impression being predicted; aggregating over the whole training set when the user is in both train and test). Rule: for every feature ask "could this be known at request time, in production, before the prediction?"
2. **Cold start** — features only exist for entities with history. Fixes: impute average (weak), missing sentinel (let model learn absence), separate feature set for cold cohorts graduating to full model. Training data must include missing instances (can be synthetic).
3. **Feedback loops** — model's decisions influence the features used to train it; over time the feature measures "did the model surface this" not "is this engaging." Fixes: randomized exploration for unbiased data, log model propensity + inverse propensity weighting in the loss. **Name the loop and propose mitigation.**
4. **Adversarial features** — content signals easy to fool; temporal/network signals (unnatural posting bursts, tight subgraphs) harder. Cloudflare catches proxied traffic via temporal/latency patterns not IP reputation; Stripe Radar uses cross-merchant card-network features ("seen 90% of cards before"). **Senior angle: discuss robustness of each feature group, not just predictive power.** A feature 80% accurate today and 30% in 6 months < one 70% accurate forever.
5. **Drift** — statistical properties change without adversarial cause (holiday cart values, new product category, upstream logging change). Monitor feature distributions, alert, retrain (partial fix). Meta (2024) detects feature anomalies at serving time with automated guardrails that drop corrupted features.

## Feature stores + train/serve consistency

Propose a feature store when there's train/serve skew risk (especially behavioral signals — "drift, leak, computed inconsistently"). Ensures the same computation applies identically at training and inference.

## Interview technique: EARMARKING (critical)

"Earmark depth, don't burn time on it." Phrase: *"There's a lot more I'd want to discuss on behavioral signals but I want to keep moving. Let me know if you want me to come back."* Signals depth without spending time demonstrating it. **~10 min for features**: enumerate sources (~3min, 2–3 signals each), encoding (~2min), normalization tricks (~2min), most relevant pitfall (~2min), buffer (~1min). Most common failure = "not knowing when to stop."

---

# 2. EMBEDDINGS

## What + why

An embedding = a list of numbers (e.g. 128-dim float vector) representing an entity (user, product, word, image) where **similar entities get nearby vectors.** Solves one-hot encoding's two problems: wasteful (10M users = 10M-dim one-hot, each learned from scratch) and no generalization (new user = new dimension + retrain).

**Canonical interview answer**: *"I'd represent each user and each video as a 64-dim embedding. The user tower takes demographics + recent watch history; the video tower takes content features. I'd train them so the dot product of a user embedding and a video embedding predicts whether the user watched the video."* (Lands well in ~half of ML SD interviews.)

## How they're trained

Define what "similar" means (task-defined, NOT necessarily semantic — co-watch data makes "similar" = "watched by same people"; co-purchase makes toothbrushes + toothpaste neighbors). Random init → move so similar cluster, dissimilar spread. Production often uses **multiple stacked objectives** (watch-completion, like, diversity regularizer, fairness) — eventually hard to say what the embedding is "about."

**Methods:**
1. **Matrix factorization** — sparse interaction matrix R (users×items) ≈ U·Vᵀ; rows of U / cols of Vᵀ are embeddings. ALS or SGD with regularization. Cheap, well-understood, reasonable baseline for retrieval. Interviewers usually expect you to reach further.
2. **Two-tower / contrastive** — two encoders (query/user vs candidate/item), possibly different inputs/architectures, **both output into the same vector space** (dim 7 in user = same latent concept as dim 7 in item, so dot products are meaningful). Positives from interaction logs; **in-batch negatives** = off-diagonal; loss = **InfoNCE** (treat as classification — pick the positive out of the batch; common for large-batch) or **triplet loss** (anchor closer to positive than negative by a margin). Deploy: pre-compute candidate embeddings offline into ANN index; at serve, run only query tower + nearest-neighbor. Sub-100ms retrieval over billions of items. Used by YouTube recs, LinkedIn feed retrieval, semantic search, RAG, CLIP, SimCSE, face recognition. **Hard negatives** (model thinks relevant but aren't) drive quality; mine periodically with a frozen snapshot (index changes every gradient step).
3. **Graph embeddings** — for explicit structure (follows, citations, co-purchase). **Transductive** (node2vec, DeepWalk): one embedding per training node, biased random walks → word2vec objective; cheap, simple, but **only embeddings for trained nodes — new nodes need retraining.** **Inductive** (GraphSAGE, GNNs): learn a *function* from node features + neighborhood; embed new nodes at inference without retraining — **cold start comes free.** Flagging transductive vs inductive is the differentiating signal. Common pattern: GNN node embedding as a feature in a downstream two-tower/ranker.
4. **Pre-trained + fine-tuning** — BERT (contextual words), CLIP (image-text shared space), sentence-transformers. Phase 1 pre-training (once, by someone else, massive GPU), Phase 2 fine-tune (you, contrastive/two-tower on task data, encoder mostly frozen + small head). "80% of the way with 10% of the compute and data." OpenAI/Cohere/HF sell embedding endpoints — great for prototypes, host your own at scale for cost + fine-tuning control.

## Production usage patterns

1. **As features** — feed embedding into downstream model replacing one-hot+handcrafted; transfers knowledge between tasks. Large companies share embeddings between teams.
2. **For clustering** — k-means on embeddings; user segmentation, topic discovery, near-duplicate detection.
3. **For retrieval (the big one)** — embed candidates offline → ANN index → embed query online → ANN search. Powers retrieval stage of recsys/search/every RAG pipeline. Semantic search understands meaning vs keyword; most production = **hybrid semantic + lexical**. RAG retrieval quality is "almost entirely a function of how good your embeddings are."

## Dimensionality trade-offs

64–128 (high-QPS retrieval, huge-scale recs) | 256–512 (default, sweet spot) | 1024+ (LLM/CLIP, high-stakes ranking). **Matryoshka embeddings**: trained so first 64/128/256 dims are each valid independently → small prefix for fast coarse retrieval, full embedding for re-ranking.

## Evaluation

**Intrinsic** (analogies king−man+woman≈queen, MTEB, word similarity) — quick iteration but doesn't always correlate with production. **Extrinsic** (downstream task — recall@k for retrieval, accuracy for classification, online A/B) — **what matters; anchor on this in interviews.** Add simple intrinsic sanity checks (nearest-neighbor spot checks, cosine-similarity spread).

## Serving (most candidates skip — senior interviewers dig in)

- **Offline indexing**: batch pre-compute candidate embeddings → ANN index (HNSW graphs, IVF partitioning, quantization). Query time: embed query, ask index for top-k.
- **Refresh/freshness**: embeddings go stale (item changed, model retrained, user behavior drifts). Scheduled batch re-embedding + event-driven hot updates.
- **Online embedding updates**: when nightly batch too slow (short-form video, news, fraud) — serve from parameter server, update tables in near-real-time, encoder layers mostly frozen. **TikTok's Monolith** is the canonical example — key to TikTok's fast adaptation. Right answer when interviewer pushes "behavior changes within minutes?"
- **Cold start**: brand-new user/item has no interaction history → **content-based embedding** (from attributes/raw content, no interactions needed), blend in behavioral embedding as interactions accumulate. Classic probe: "new video with 0 views?"

**Interview advice**: be specific — name the loss function, explain negative sampling strategy, pick dimensionality with a reason, have a refresh + cold-start story. Show you've trained/served embeddings, not just read about them.

---

# 3. GENERALIZATION

## Core

Generalization = perform on **unseen** data (the central aim in nearly all industrial ML). Opposed to **memorization** (learn training data by rote).

**Bias-variance**: high bias = **underfit** ("lazy student who skims past examples"); high variance = **overfit** ("memorizes every practice exam word-for-word, can't handle rephrased questions"). Not binary — can overfit some data and underfit other data simultaneously.

**Overfitting signs**: train loss keeps decreasing while validation stops improving / increases (widening gap); dramatic production underperformance vs offline. Causes: high-capacity model + insufficient data, training too long, no regularization, data leakage.
**Underfitting signs**: both losses high, plateauing early. Usually wrong model for the job.

## Train/val/test split + the hold-out strategy trap

Plot train + validation loss over epochs: both high plateau = underfit; both decreasing close together = good fit; train dropping while val rises = overfit.

**Hold-out strategy matters**: stock-prediction example — randomly holding out tickers is deceptive because market-wide trends leak across tickers (Disney not in training but "rest of market dropped 20% in April" makes predicting its drop trivial → false performance impression). **Slice by TIME.** *(Cross-link: [05-ad-click-aggregator.md](05-ad-click-aggregator.md) time-based holdout for temporal leakage; same principle.)*

## Model capacity + data requirements

Capacity ≈ how complex a function the model can represent (trainable params). Low-capacity (linear regression) hard to overfit but underfits complex functions (even a sine wave). High-capacity (deep NNs) learn complex functions but overfit on too little data. **Rule: high-capacity models need more data to generalize well.** GPT-3 175B params; BERT 110M (fine-tunable on thousands of examples); typical image classifier 20–50M. **Huge-model-with-limited-data proposals signal inexperience** — interviewers flag this. Start with a logistic regression baseline (fast, won't overfit, won't learn interactions but is a safe floor).

## Limited-data toolkit

- **Transfer learning** — pre-train on large dataset (ImageNet/BERT), freeze lower layers (general features: edges, common word patterns), fine-tune final task-specific layers. **LoRA** adapters add trainable low-rank layers on a frozen base.
- **Data augmentation** — synthetic examples via transformations (CV: rotations, crops; NLP: harder, paraphrasing). Works best when you understand real corruptions. Not a silver bullet.
- **Self-supervised learning** — unlabeled data, learn representations first (predict masked words, reconstruct corrupted images), then fine-tune on labels.
- **Semi-supervised** — small labeled + large unlabeled (pseudo-labeling, consistency regularization). When labeling is expensive but unlabeled data is plentiful.

## Data drift (DIFFERENT from overfitting — a well-generalized model degrades as the world changes)

Three types: **covariate shift** (input feature distributions change, feature→label relationship same); **prior probability / label drift** (target distribution changes, e.g. fraud 1%→3%); **concept drift** (the relationship itself changes — user prefs evolve, regulations, world events — **the nastiest type**).

Detect: monitor prediction distributions (10× more fraud flags = drift), feature distributions (mean/variance/percentiles; category frequencies), performance metrics on labeled production data, retraining-cadence comparisons.

Handle: (1) **regular retrain** (e.g. weekly — first line of defense); (2) **online learning** (continuous updates, fraud detection; risk of catastrophic forgetting); (3) **online embedding learning** (freeze model weights, update embeddings continuously — TikTok/Instagram reels; "prodigious engineering challenge"); (4) **ensembles across time periods** weighted by current match (hedges drift, raises serving cost); (5) **human-in-the-loop** (route uncertain predictions to humans, their feedback = fresh training data).

## Regularization techniques

Constrain the model during training so it's harder to memorize noise — trade training performance for generalization. A well-regularized model handles distribution shift better.

- **Dropout** — randomly disable neurons (prob p, e.g. 0.5) each step; forces redundant representations; at test all neurons active (scaled). Extremely effective for large networks.
- **Layer normalization** — normalize activations across features within each example; stabilizes training, mild regularization; **replaced batch norm in transformers/modern architectures** (batch norm struggles with small batches + sequence models).
- **L2 (Ridge / weight decay)** — penalize loss by *square* of weights; large weights penalized more; keeps weights small/even. **Default for most models — cheap, effective.** Tune λ on validation; too much → underfit, too little → overfit.
- **L1 (Lasso)** — penalize by *absolute value* of weights; pushes weights to zero → **feature selection + interpretability**; sparse models. For many features where most are unhelpful. Common in linear/logistic, less in deep learning. Lets you prune.
- **Early stopping** — stop when validation performance stops improving for N epochs; use best epoch's model. "Free and effective — not a replacement for other regularization, but a good safety net."

**Interview advice**: be specific — don't say "we need to avoid overfitting"; talk about train vs validation performance and have a plan for what you'd measure. Interviewers are most often concerned with overfitting. Connect everything back to "a model that works for real users in production."

---

# 4. EVALUATION

## 5-step framework

1. **Business objective** — start here, work backward; tethers the metric to something real.
2. **Product metrics** — user-facing success indicators.
3. **ML metrics** — technical metrics aligned with product goals, measurable without new inputs.
4. **Evaluation methodology** — offline + online; offline is a proxy for online geared toward rapid iteration.
5. **Address challenges** — imbalance, labeling cost, fairness, feedback loops.

## Offline vs online

| | Offline | Online |
|---|---|---|
| Purpose | Rapid iteration, cheap | Real-world validation |
| Setup | Held-out test sets, historical data | A/B, shadow mode, interleaving |
| Risk | Low (no user impact) | Higher (user-facing) |
| Challenge | **Proxy gap** — metrics may not correlate with real outcomes | Slower, more expensive |

**Critical**: offline evaluation must **correlate** with online outcomes. If offline gains don't translate to online wins, revisit labeling or bias correction.

## Classification metrics (content moderation, spam, fraud)

- **Precision** = TP/(TP+FP) — "when model says positive, how often right?"
- **Recall** = TP/(TP+FN) — "what % of all positives caught?"
- **F1** = harmonic mean of P and R.
- **ROC-AUC** — distinguish classes across thresholds, 0–1. **WARNING: misleading on imbalanced data** (true negatives dominate the curve).
- **PR-AUC** — better for imbalanced data (99% negative → use PR-AUC, not ROC-AUC).

**Accuracy is useless on imbalanced data.** Threshold = cost of FP vs FN (content moderation: FP frustrates users, FN = brand/safety risk → operating point on PR curve). Methodology: shadow mode (predict, no action, reviewers validate) → A/B. Offline: balanced/stratified test set, PR curve for threshold. Challenges: class imbalance, label efficiency (random sampling poor for rare positives — stratified/active learning), estimating prevalence, feedback loops (inject randomness, golden sets).

## Recommender metrics (product/video recs, friend suggestions)

Value tied to **ordering + diversity**, not single yes/no.
- **MRR** (mean reciprocal rank) — avg of 1/position for first relevant result; sensitive to first relevant item; "top pick" use cases.
- **NDCG** — relevance scores discounted by position (log discount), normalized by ideal ranking; **all-rounder.**
- **Hit@K / Recall@K** — fraction of sessions with ≥1 relevant item in top K.
- **Coverage** — proportion of catalog shown (cold-start sellers, long-tail).
- **Calibration** — score distribution matches observed engagement probabilities.

Methodology: **leave-one-interaction-out** (each user in train + test with different timestamps) — **watch for temporal leakage** (tomorrow's interactions in today's training = spectacular meaningless scores). Online: **shadow-rank mode** (reorder but serve baseline, compare CTR on changed positions) → A/B. Measure ≥1 short-term AND ≥1 long-term metric — **if they diverge, you've found a trap** (short-term CTR can cannibalize long-term retention; interviewers push here). **Interleaving**: show one *mixed* list to the same user (paired comparison — every click is evidence for one ranker and against the other) → variance drops sharply, **10-20x less traffic** than full A/B.

## Search / IR metrics (web search, e-commerce, code, enterprise)

- **Precision@k / Recall@k**, **MRR**, **NDCG@k** (k = product param, e.g. 10 above-fold), **MAP** (avg precision at each relevant item, averaged across queries), **Hit/Success@k**.
- **Click logs biased by presentation bias** → inverse propensity weighting or deterministic interleaving.
- Challenges: query ambiguity ("jaguar" = animal/car/team → intent classification, diversification); long-tail sparse judgments (active learning, query clustering, LLM zero-shot eval); freshness/recency (time-decay, classify time-sensitive vs evergreen); feedback loops (popular→more clicks→higher→more clicks).

## Generative AI metrics (chat, code gen, image, support bots)

"Correctness" is subjective. Use a **portfolio**: **BLEU/ROUGE/METEOR** (overlap, cheap, brittle) + **BERTScore/BLEURT** (semantic similarity) + **factuality/hallucination rate** (task-specific checkers) + **toxicity/bias** (Perspective/hate-speech models) + **diversity** (self-BLEU, distinct-n) + **human ratings** (pairwise preference / Likert) + **custom** ("% refusals, % hallucinations"). Strategy: automated filters (quick, high-recall) + periodic human eval (slow, high-precision). **Hallucination severity explodes on rare/niche prompts — target them deliberately in test sets.** Maintain a **golden canary** set served by a legacy model for drift detection. Challenges: subjective quality (multi-reference, expert review, preference learning), safety (false-negative rates critical — missing problematic output > false positives; red-team testing), evaluation cost (active learning for uncertain outputs), distribution shift (rolling time windows, stable benchmark canaries).

## Cross-cutting: feedback loops + calibration + the offline/online gap

Feedback loops everywhere: model trains on its own echo chamber. Mitigations: exploration traffic (ε-greedy, Thompson sampling), golden sets unaffected by model decisions, inverse propensity weighting, **log ALL candidates + features not just the ranked list** (A/B can fail silently if treatment collects data control never sees).

**Calibration**: predicted score distribution matches observed outcomes (recommender + genAI confidence vs correctness).

**Image gen appendix**: FID (Fréchet Inception Distance — distribution similarity to real, lower better), CLIP score (text-image alignment, higher better). **Text**: perplexity (lower better), BLEU/ROUGE/BERTScore.

**No single metric tells the whole story** — use complementary metrics aligned to business objectives.

---

**Interview anchor**: ML system design is a different skill family from the distributed-systems memories, but the *depth discipline* is identical — justify against the constraint, don't regurgitate. Specific ML instances of that discipline: don't propose a huge model with limited data (generalization), don't use ROC-AUC on imbalanced data (evaluation), don't pick a dimensionality without a reason (embeddings), don't forget the context/request signal source (features), **earmark depth instead of burning time** (features). The earmarking technique is the ML analog of the crawler's "do math when it informs a decision" — both are about *managing interview time to show depth efficiently*. This foundation feeds the three ML problem-breakdowns: [07-harmful-content-detection.md](07-harmful-content-detection.md), [08-bot-detection.md](08-bot-detection.md), [09-video-recommendations.md](09-video-recommendations.md).
