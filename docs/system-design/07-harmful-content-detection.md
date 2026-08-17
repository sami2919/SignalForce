# Worked ML Problem: Harmful Content Detection

> Source: hellointerview.com ML problem-breakdown "harmful-content" + NoteGPT transcript "Harmful Content Detection / Content Moderation ML System Design Problem Breakdown" (Stefan — ex-Meta senior manager, ran the "dangerous content" org; ~2000 interviews conducted).
> Distilled 2026-08-03.
>
> **SignalForce relevance:** SignalForce's "skip a prospect than send garbage" principle (D-grade skip) is
> the analog of the precision guardrail here — both systems prioritize false-positive cost over raw recall.
> The two-stage cascade (lightweight filter → heavy classifier) maps to SignalForce's ICP-fit gate →
> intent-scoring split. The multitask data-augmentation pattern (report-prediction head ~1000x more data)
> applies to SignalForce's use of weak signals (LinkedIn data-input, G2 reviews) as supplementary training
> data. The business-objective escalation is THE interview depth move. Pair with [06-ml-core-concepts.md](06-ml-core-concepts.md).

## The ML system design framework (6 steps — different from distributed systems)

Distributed-systems roadmap: requirements → entities/API → HLD → deep dives on scale/fault-tolerance. **ML roadmap**: (1) **problem framing** → (2) **high-level design** (a block diagram, NOT DBs/query patterns) → (3) **data & features** → (4) **modeling** → (5) **inference & evaluation** → (6) **deep dives**.

**Role-variant context** (know before the interview): two axes — research-focus (pumping papers ↔ business results) and infra/software emphasis (research scientist ↔ full-stack ML engineer). Applied ML (the middle) is what this framework targets; ML-infra interviews expect less modeling depth, research-oriented expect more. The ML engineer role spans data/features, modeling, inference pipelines, evaluation, iteration — easy to get lost in one aspect and not cover the rest, hence the framework.

**Senior/staff signal**: the interviewer is assessing whether you'll be productive joining the team. For senior+ you should DRIVE (not be driven) — if the interviewer is driving, it suggests you haven't built these systems before. Leave room for deep dives; don't crowd out all the time talking.

## Step 1 — Problem framing (THE staff differentiator)

Three sub-steps: **clarify** (constraints, product operation, users, consequences) → **establish business objective** (where senior/staff separate — ML objectives often MISALIGN with business objectives) → **distill to ML objective**.

**Clarifying questions + assumptions** (record on whiteboard for alignment): content types (text + images, video excluded); what to detect (nudity, violence, terrorism, human trafficking — "everything"); action on detection (remove / demote / ban); FP/FN consequences (Facebook: protect free expression → only auto-act above human-performance confidence = **95% precision threshold**); scale (~1B posts/day, **<1% harmful**, **50k labeled examples** 50/50); posts only (not comments).

**The business-objective escalation** (this is the literal "depth" move — the first sign of a staff candidate):

| Level | Objective | Why it's better/worse |
|---|---|---|
| Bad | "Remove as much harmful content as possible" | Incentivizes excessive false positives; systems make mistakes with real ramifications |
| OK | "Remove as much as possible subject to a precision guardrail (95%)" | Builds in the precision/recall trade-off; probably passes |
| **Great (chosen)** | **"Minimize the number of VIEWS of harmful content, subject to precision guardrails"** | Focuses on actual harm = exposure, not just existence. Prioritizes viral content. Deprioritizes harmful content with 0 views (low harm). |

**Why the great objective changes the system**: if you only need to suppress *views* of known harmful content, you don't need to classify at post-creation time — you can be a little late, as long as you catch it before the majority of views. This changes WHEN you run classification and what you optimize. *(This is the same "reframe the objective to align with actual value" depth move as the ad-click checkpointing nuance — the shallow answer optimizes the obvious metric; the deep answer reframes it.)*

**ML objective**: binary classification (harmful / benign) at a point in time → action downstream. Multi-label possible (content can be multiple harmful categories simultaneously — softmax inappropriate).

## Step 2 — High-level design (block diagram, not a DB exercise)

Posts created/viewed → trigger classification → model → **calibration** → if >95% confidence **delete**, else **demote** (or human moderator review, limited capacity). Don't over-invest here — it's a communication tool to refer back to, not assessed on whiteboarding. The interesting parts (feedback loops, how actions affect data over time) only become clear once you have the sketch.

## Step 3 — Data & features ("better data beats better models")

**Be creative with data sources** — this is where candidates stand out, especially under data scarcity (50k labeled is not much). But don't over-invest time; first few ideas are usually the best.

- **Supervised**: 50k hand-labeled (most valuable). Public NSFW datasets (lacks platform-specific features, bias risk). Need FRESH labels over time (data drift is a common degradation cause).
- **Semi-supervised**: **user reports** (~10M vs 50k labeled = ~1000x the data). Correlated with true label but imperfect (adversarial / incorrect reports). Normalize by views.
- **Self-supervised**: **comments** ("Gross!", "disgusting") as signals — a model trained to predict comments from post bodies learns useful representations; orders of magnitude more data. Not perfect (someone says "gross" to a friend's birthday post) but correlated. Show a hypothesis for HOW each source helps, not just that it exists.

**Features** (constrain the discussion — nearly infinite features; adding some can make the model worse. Hypothesis-driven, keep moving):
- **Direct content** (text, image → multimodal). Poor candidates focus ONLY here.
- **Behavioral**: negative reactions, shares with captions, comments. **Must normalize** — unnormalized skews (millions of views → some negative reactions inevitable; 25/50 negative is more telling). Use **ratios** (negative_reactions/view); ratios unstable at low view counts → **Bayesian averaging** with a prior. Behavioral features change over time → re-classification as post gains viewership (not just at creation).
- **Creator**: **slow-but-rich user embedding** (profile, group memberships, posting history) + **fast-but-noisy contextual features** (last-N postings harmful count, account age, login countries — catches hacked/bot accounts). New accounts disproportionately violate (they don't care about the account).

## Step 4 — Modeling (load-bearing — where candidates get in over their skis)

Three approaches, built up bad→great (Evan's pattern again):

- **Bad: independent unimodal models** — text BERT + image CNN + behavioral logistic regression, max score, threshold. Interpretable + high performance BUT **no cross-modal interaction** (benign image + harmful-text context missed) and hard to add behavioral/user features. Not passing.
- **OK: embeddings → MLP (late fusion)** — separate encoders, concatenate embeddings + dense features, MLP. Some interaction but MLPs aren't great at multimodal. Multiple images → average/max pool embeddings. Problem: 50k examples insufficient to train end-to-end.
- **Great (chosen): multimodal transformer** — ViT image patches + text tokens, joint cross-attention (early fusion for text+images), fuse dense behavioral features late (inference optimization — text/image embeddings rarely change so they're cacheable; behavioral features update, re-run cheaply). Transformers learn long-range relationships; surprisingly effective across ML — candidates without a transformer solution stand out (negatively).

**Solving data scarcity — multitask learning** (the key move): add a **report-prediction head** (MSE on report rate). ~10M reports vs 50k labeled ≈ multiply data ~1000x. Multitask exploits correlation between tasks → robust representations. Add **subtype heads** (nudity, violence) for **interpretability** — "0.9 harmful + 0.89 nudity" tells you WHY, not just that it's harmful. Loss = `α·L_primary + β·L_reports` (α high to favor primary; ignore report head at inference). Optional **view-weighting** term `min(log(1+views), c)` — aligns with business objective (focus on high-view content) but power-law distributed so log + cap prevents singular examples dominating.

**Class imbalance (<1%)**: **balanced sampling** (upweight positives, no empty-positive minibatches — they're unhelpful) + **loss weighting**. Both needed — imbalance too acute for loss terms alone.

**Fusion / freezing**: early fusion for text+images, late fusion for dense behavioral features (inference optimization). Production: one team produces image embeddings consumed by dozens of systems (customer support, content moderation, ranking) → plays into where you freeze parameters.

## Step 5 — Inference & evaluation

**Inference cost** — the multimodal transformer is parameter-rich, expensive, needs GPU. Optimize:
- **Two-stage / cascaded architecture** (like recsys retrieval→ranking): a **lightweight model** (LightGBM/XGBoost tree model, or MLP) runs on everything; only borderline passes to the heavyweight model. Train the lightweight model via **distillation** (teacher-student — predicts the heavyweight's output, less likely to pass things the heavyweight would flag). Tunable threshold (run heavy on 10% or 1%). **Must sample from the lightweight classifier in production** to get heavyweight scores for evaluation + catch misses (lightweight saying "no" to actually-harmful content = recall hurt).
- **Calibration**: raw score 0-1 ≠ 95% confidence. **Isotonic regression** — reviewers label at each score band, learn a raw→calibrated transformation. Calibrated scores drive delete/demote.
- **Quantization-aware training** + **encoder caching** (identical images/text across posts avoid redundant forward passes).

**Evaluation**:
- **Online** (expensive — random sampling needs ~100 labels to find 1 harmful). **Label-efficiency**: an A/B only matters where the two models **DISAGREE** (if both delete or both ignore, no performance difference — only the at-odds cases show the delta). **Importance sampling** — stratified by classifier score, spend labels on borderline (most content scored .99 by either is likely positive → down-sample extreme scores, reweight for unbiased estimates).
- **Offline**: **PR-AUC** (NOT ROC-AUC — acute class imbalance saturates ROC-AUC fast and tells you little), **Recall@Precision95** (aligned with the 95% action threshold — what proportion of harmful content did we catch at that confidence). Offline metrics are **tainted by data collection** (human bias / prior production classifier bias). **Bias/fairness**: error rates across groups — new vs old users (systems penalize new users → vicious cycle where they never make it on the platform).
- **Feedback loop**: production model removes content before views → **positive suppression** (few positive examples with behavioral data → model falsely learns behavioral indicators = benign). Fix: holdout to predict views. *(Cross-link [06-ml-core-concepts.md](06-ml-core-concepts.md) feedback-loop pitfall.)*

## Step 6 — Deep dives (deferred topics + interviewer curveballs)

- **User embeddings** (how to train): bad = categorical user ID → jointly learned embedding (**overfits, memorizes past violators, brittle**). Better = auxiliary model. **Transductive GCN** (social graph, predict edges) — learns interesting relationships but **static snapshot**, new users need retraining, embedding shifts break downstream models trained on old embeddings. **Inductive GraphSAGE** (features + neighborhood → embedding function, **cold-start comes free**, generalizes to unseen users) — more complex, larger, non-trivial inference, needs aggressive caching. *(Same transductive-vs-inductive lesson as [06-ml-core-concepts.md](06-ml-core-concepts.md) embeddings — the differentiating signal in interviews.)*
- **Adversarial creators**: model fails to generalize in adversarial domain (gun → "go n", out-of-vocab → garbage embedding → can't retrain meaningfully). Fixes: lower-level tokenizers (byte-level), models trained robust to perturbations, **data augmentation** (disturb positives in ways that keep them harmful but make confident decisions difficult).

## Level expectations

| Level | Expectation |
|---|---|
| Mid | Work through independently, good handle on modeling/features, some evaluation idea, emerging depth. Credibly-workable solution. |
| Senior | Substantially more depth, generalizable knowledge across domains (recs/forecasting/classification), nuggets of what works/doesn't + research read. |
| Staff | **Novel insights**, wide breadth, **clever business-objective formulation** (the first sign), strong modeling depth, brings experience the interviewer isn't familiar with AND explains it well enough to **level up the interviewer**. |

## Concrete numbers

1B posts/day · <1% harmful · 50k labeled (50/50) · ~10M reports · 95% precision auto-removal threshold · multimodal transformer (ViT + text + cross-attention) · two-stage cascade (distilled lightweight filter → heavy model) + caching + quantization · weighted multi-task loss (BCE + MSE) with log-view weighting · PR-AUC + Recall@Precision95 + importance-sampled A/B.

## Trade-offs to articulate

| Decision | Trade-off |
|---|---|
| Independent classifiers vs MLP vs multimodal transformer | Interpretability/perf vs cross-modal interaction quality; transformer needs more data/compute |
| Early vs late fusion | Early = better interaction learning; late = cacheable content embeddings, cheap re-scoring as behavior changes |
| Multitask (report head) | ~1000x data + interpretability vs added complexity + must weight α high to protect primary task |
| Two-stage cascade | Huge inference cost savings vs recall risk (lightweight "no" on harmful) + must sample for eval |
| Transductive vs inductive user embeddings | Transductive richer but static/cold-start-fails; inductive cold-start-free but complex/costly |
| PR-AUC vs ROC-AUC | PR-AUC handles acute imbalance; ROC-AUC saturates and misleads |
| "Remove all harmful" vs "minimize views of harmful" objectives |后者 aligns with actual harm, changes when/what you classify — the staff move |

---

**Interview anchor (why this matters for your gap):** This problem is the cleanest illustration of the "structured, precise communication of impact" your feedback asked for — via the **business-objective escalation**. The shallow candidate says "remove as much harmful content as possible" (sounds right, incentivizes false positives). The deep candidate reframes to "minimize views of harmful content subject to a precision guardrail" — because that's the actual business harm (exposure, not existence), and it changes the system (you can classify late, you optimize for high-view content, you deprioritize zero-view harmful posts). That reframe is *identical in shape* to the ad-click "don't regurgitate checkpointing" and the crawler "don't name-drop bloom filter": **question the obvious objective, justify the reframe against the real constraint.** It's also the "more depth in technical explanations" — picking PR-AUC over ROC-AUC *because* <1% prevalence saturates ROC-AUC, not just naming PR-AUC. And it's the "prioritization and impact" the feedback named — the business-objective escalation IS prioritization at the highest level. The 6-step ML framework is the structured-communication frame (parallel to the distributed-systems 6-step roadmap from [04-web-crawler.md](04-web-crawler.md)). Cross-link all: [06-ml-core-concepts.md](06-ml-core-concepts.md), [05-ad-click-aggregator.md](05-ad-click-aggregator.md), [04-web-crawler.md](04-web-crawler.md), [01-system-design-fundamentals.md](01-system-design-fundamentals.md).
