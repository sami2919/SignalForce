# Worked ML Problem: Bot Detection

> Source: hellointerview.com ML problem-breakdown "bot-detection" + NoteGPT transcript "Bot Detection ML System Design Problem Breakdown" (Stefan — ex-Meta).
> Distilled 2026-08-03.
>
> **SignalForce relevance:** SignalForce's signal robustness question (can a prospect game the signals?)
> maps to bot detection's adversarial-robustness lesson: content signals are weakest because easiest to
> fake; temporal/network signals strongest. SignalForce's GitHub stars + ArXiv papers can be gamed
> (star-buying, paper spam), but funding + job postings are harder to fake. The two-stage distillation
> cascade (lightweight filter → heavy classifier, 80-90% compute reduction) maps to SignalForce's
> scanner → scorer pipeline. Pair with [06-ml-core-concepts.md](06-ml-core-concepts.md) and
> [07-harmful-content-detection.md](07-harmful-content-detection.md).

## The problem — "ML street fighting" (deeply adversarial)

Bots = automated malicious actors (fake accounts, friend-request/message spam, duplicate/harmful content, misinformation). Stefan frames this as adversarial ML, not theory — bots constantly adapt to evade detection.

**Clarifying nuggets** (staff move = summarize these back): (1) **high raw prevalence but low after heuristics** — 50%+ of activity is bots unremediated, simple rate limiters cut to **<1%** → acute class imbalance post-filter; (2) **adversarial** — different retraining freq, approaches not the same as strictly supervised; (3) **labels scarce** — investigators produce ~low-100s/week, expensive, inexact. Scale ~500M DAU. Bots show inhuman behaviors (posting frequency, circadian-rhythm violations — awake 48h). Ban is the action, sometimes held back to not reveal the signal. FP cost = real users blocked → engagement dip; appeals exist but bots game them too (sob story about grandma).

## Business-objective escalation (THE depth move — second instance)

| Level | Objective | Why it's wrong/right |
|---|---|---|
| Stupid | "Maximize bots detected" | Infinite — ban the dumbest bots repeatedly as they respawn; number is meaningless |
| Seductive-bad | "Maximize model accuracy" | Business doesn't care about your accuracy; you can control it but it's the wrong thing |
| Good | "Minimize impact of bot activity on legitimate users" | Tractable, lets you **ignore benign bots** (a bot just browsing/answering questions may not matter) |
| **Great (needs counter-metric)** | **"...subject to false-positive constraints"** (e.g. 95% of actions on actual bots) | Without the FP guardrail, ban-all-users is the degenerate solution |

*(Same shape as harmful-content's "minimize views subject to precision guardrail" — question the obvious objective, justify the reframe, add a counter-metric. This is the literal "structured, precise communication of impact" from your Rippling feedback.)*

**ML objective**: bot classifier, run **when actions take place** (impact happens on action, not browsing — browsing may not matter), subject to FP constraints → implies **calibration** (raw 0-1 score ≠ probability; calibrated 60/40 means actually 60% bot). Business threshold (95%) → calibrated threshold → action.

## High-level design

Classifier (triggered on user action) → **calibration** → tiered action: **ban** (high prob) / **limit** (mid prob — soft, e.g. post once an hour, minimizes collateral damage) / **label** (sample lower-scoring for new labels).

Two non-obvious additions that show depth:
- **Non-parametric memory**: banned users' content → **vector DB / ANN index** → distance-to-removed-content as a feature. Catches a bot posting the same meme slightly differently — immediate memory. (Augments parametric logistic/NN/GBDT with kNN.)
- **Unsupervised bot detection** → feeds labels back into the classifier (the adversarial outer loop: bots mutate to pass the classifier; you need a way to find the ones you're NOT catching today).

## Data sources (creativity under scarcity — "better data beats better models")

- **Ground truth**: ~100s/week investigator labels — highest quality, extremely scarce. Use strategically on accounts near decision boundaries / new patterns.
- **Weak supervision**: user/account reports, content-level reports, appeal outcomes — noisy but correlate (reports ladder to account level; objective is impact on users, bad content is the impact).
- **Network-based unsupervised**: IP clusters, behavioral similarity clusters, registration patterns — a banned account's IP moments ago likely = same entity (not perfect — cell IP rotation, proxies). Identifies whole bot networks.
- **Unsupervised sequence data**: 99% legitimate after heuristics → find the anomalies (the exceptions to normal behavior = candidate new bots).
- **Synthetic data** (CALEB-style conditional GANs) — augments rare patterns but may not capture real adversarial behavior.
- **Survivorship bias**: as detection improves, observed bots become more sophisticated (simple ones filtered out).

## Features (framework + few indicative examples — thousands possible, don't burn time)

- **Activity patterns** (MOST robust — hardest to fake): posting cadence, variance of post times, circadian-rhythm coverage (can you detect sleep?), burstiness (max action frequency). Over multiple time windows (hourly/daily/weekly) with entropy/variance.
- **Content signals** (WEAKEST — easiest to fool): typo frequency, backspace rate (copy-paste vs typing), language quality (bots more refined, less slang), semantic diversity. Alternative: index bot content in ANN, use distance/count rather than learning content features (content overfits + is the easiest thing for a bot author to change).
- **Network topology**: follower/following ratio, network growth rate, clustering coefficients, graph embeddings (bots generate synthetic networks + interact with each other).
- **Account metadata**: registration age, verification, profile completeness, login geography, device diversity, username patterns.
- **Real-time behavioral** (feedback loop): content-flag count, rate-limits applied, evasion patterns post-flagging, appeal frequency — change over time, tip account into bot category.
- **Critical temporal caveat**: many features unavailable at account creation → model must handle missing data gracefully (missing sentinel / separate cold-start feature set — cross-link [06-ml-core-concepts.md](06-ml-core-concepts.md) cold-start pitfall).

## Modeling (benchmark → organic-evolution → mega-model → chosen late-fusion)

- **Benchmark**: logistic regression + hand-engineered features. "Frustratingly effective" + the canary that warns when a future release backslides below it.
- **Organic evolution** (not what you propose — what systems look like after years): logistic for content + logistic for behavioral + GBDT → vote ensemble. Uncorrelated models (different data) but hard to optimize, lots of surface area.
- **Mega model** (reject): content-heavy end-to-end. Some end-to-end advantages but unclear internals + **content is the EASIEST thing for a bot author to change** (harder to change IP ranges / action frequency / patterns) → content overfits and is adversarially fragile.
- **Chosen: late-fusion multi-modal** — (1) **Network/graph branch**: **GraphSAGE** (inductive — cold-start for new accounts, no retraining; summarize IP clusters as edges; k=2 hops, relation-specific weights, neighbor-sampling fan-out cap). (2) **Sequence branch**: **GRU not transformer** — scale (run on every action) makes a heavy transformer need a massive GPU fleet; GRU retains less state than LSTM, summarizes "visited profile A → followed B → posted XYZ" (last ~200 events, 5-min buckets, bidirectional). (3) **Dense counters**: MLP. All branches → embeddings → **attention layer** (cross-attention lets timeline query graph and vice versa) → MLP (64→32→1) → sigmoid bot score.

**Pre-training (labels ~1000 — can't train rich branches from scratch)**: graph branch self-supervised (predict whether two nodes connected by an edge, **censor the edge** — rich training set, fine-tune later; also mask node attributes, shuffle pairs). Sequence branch self-supervised (predict next element from previous actions, cross-entropy, **weight by account importance** — bots that most negatively impact users matter more, cap weights). **Multitask**: add "is this account reported" task (substantially more data) → learn close to bot-or-not before fine-tuning on limited labels. Alignment pass (fusion rewarded when branches agree).

## Inference + evaluation

**Inference cost**: GRU cheaper than transformer but still expensive. Pruning/quantization + caching (graph embeddings stable unless graph changes) → ~2x, not 10x → need GPUs. **Two-stage (teacher-student distillation)**: lightweight filter (logistic regression, predicts the bot classifier's OUTPUT not ground truth) → if high score pass to heavy classifier, if unlikely-to-ban drop. **Reduces compute 80-90%.** CRITICAL failure mode: if the filter discards accounts and you never label them, malicious users find ways to be discarded → system fails silently. Fix: **sample from discarded accounts for labeling** (higher-scored first) → assess filter recall + get labels + retrain classifier + retrain filter.

**Evaluation**: online = A/B reflecting the business objective (user reports, spam prevalence) + **counter-metric** (label for FPs, verify aggregate precision at 90/95%). **Importance sampling** — score ~0 needs few samples, score ~50% needs more (more density there); need several hundred labels for error bars on 1% prevalence. A/B contamination risk (graph inputs span users on both models — randomize by session, control downstream). Offline = **PR-AUC** (not ROC-AUC — acute imbalance), Precision@Recall90, F1, impact-weighted metrics, early-detection rate, network coverage, fairness across demographics. **KEY**: assemble a dataset reflective of online — **two-period holdout**: train on data ≥2 weeks old, measure on the following 2 weeks (tests drift/generalization to unseen behaviors — "future bots differ from past bots").

## Deep dive — anomaly detection (find the bots supervised misses)

Failure mode: supervised model gets great at detecting behaviors bots STOPPED using; bots change entirely. Anomaly detection on unlabeled data surfaces new patterns → seed labels.

- **Isolation forests** (from random forests): random splits (not greedy Gini); anomalous points need **fewer splits to separate** from the cluster; aggregate depth across trees → anomaly score. Fast (CPU if-statements), handles missing values. Struggles with contextual/coordinated anomalies.
- **Autoencoders**: compress input → small encoding → reconstruct; anomaly = **hard to reconstruct** (learns common patterns, fails on rare). Learns nonlinear relationships trees can't. **Pathology**: can learn to reconstruct anything including anomalies (too many params) → useless.
- **Ensemble both** — sum/average anomaly scores, rank accounts for labeling. The point: surface examples supervised misses; "we care about accounts that are weird BECAUSE they may be bots, not just weird."

**Calibration deep dive** (webpage): histogram binning (decent, simple), isotonic regression (good but hard with limited data), **Platt scaling** (winner — sigmoid with 2 params on hold-out).

## Level expectations + numbers

500M DAU · <1% bots post-heuristic · ~100s investigator labels/week · graph k=2 · sequence last ~200 events 5-min buckets · MLP 64→32→1 · two-stage 80-90% compute reduction · <1% FP guardrail · pretraining 30-60 days raw events. Mid = workable + sensible; senior = quick workable → deep dives, modeling range, business-objective + eval reasoning; staff = full-scope business→modeling depth, capacity/optimization, unique improvement directions, realistic vulnerability ID, focus on what matters to the business (not abstract accuracy).

---

**Interview anchor**: Bot detection is the *second instance* of the business-objective-escalation depth move (after harmful content's "minimize views"). The pattern is now confirmed across both ML problems: the shallow candidate optimizes the obvious metric ("detect most bots" / "remove most harmful"); the deep candidate reframes to the actual business harm ("minimize impact on legitimate users") AND adds a counter-metric ("subject to FP constraints") to prevent the degenerate solution. This is *prioritization at the objective level* — exactly the "prioritization and impact" your feedback said was unstructured. It also reinforces the adversarial-robustness lesson from [06-ml-core-concepts.md](06-ml-core-concepts.md) (content features are weakest because easiest to fake; temporal/network features strongest) and the self-supervised-pretraining + multitask-data-augmentation patterns from harmful content. Cross-link [07-harmful-content-detection.md](07-harmful-content-detection.md), [06-ml-core-concepts.md](06-ml-core-concepts.md), [05-ad-click-aggregator.md](05-ad-click-aggregator.md) (two-stage distillation cascade is the same pattern).
