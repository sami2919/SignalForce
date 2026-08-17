# System Design Knowledge Base

This directory consolidates system design interview prep and architectural references.
It exists inside SignalForce because every project needs a deployment + DB + scaling story,
and these concepts directly inform how SignalForce's architecture would scale.

## Why this lives here

The Rippling onsite exposed a gap: strong product instincts, weak infrastructure depth.
These references close that gap by distilling worked interview problems and core concepts
into a reusable vocabulary. They are cross-linked so you can follow the graph from any entry point.

The same principles that govern SignalForce (deterministic collectors, scored output,
"skip a prospect than send garbage") appear at scale in these notes — sharding, caching,
queue topologies, eval harnesses. The through-line is: **justify the need before the
architecture; justify the choice before the name.**

## Files

### Core concepts (distributed systems)

| File | Topic | Key takeaway |
|------|-------|--------------|
| [01-system-design-fundamentals.md](01-system-design-fundamentals.md) | Scaling, DBs, load balancers, APIs, protocols, auth | The vocabulary to answer "where does it run / what DB / how does it scale" |
| [02-sharding.md](02-sharding.md) | Shard keys, distribution strategies, hotspots, cross-shard, saga | When to shard (do the math first), hash + consistent hashing as default |
| [03-caching.md](03-caching.md) | 4 cache layers, 4 architectures, eviction, stampede, consistency, hot keys | Cache-aside is default; justify caching against a quantified bottleneck |

### Worked problems (distributed systems)

| File | Problem | Key lesson |
|------|---------|------------|
| [04-web-crawler.md](04-web-crawler.md) | Crawl 10B pages in 5 days | 6-step roadmap; don't name-drop bloom filter without justifying the constraint |
| [05-ad-click-aggregator.md](05-ad-click-aggregator.md) | 10K clicks/sec, 1-min granularity | Batch→stream evolution; don't regurgitate checkpointing for small windows; hybrid Lambda+Kappa is fine |

### Core concepts (ML system design)

| File | Topic | Key takeaway |
|------|-------|--------------|
| [06-ml-core-concepts.md](06-ml-core-concepts.md) | Feature engineering, embeddings, generalization, evaluation | Different skill family from distributed systems; earmark depth, don't burn time |

### Worked problems (ML system design)

| File | Problem | Key lesson |
|------|---------|------------|
| [07-harmful-content-detection.md](07-harmful-content-detection.md) | Content moderation at 1B posts/day | Business-objective escalation: "minimize views of harmful" not "remove all harmful" |
| [08-bot-detection.md](08-bot-detection.md) | Adversarial bot detection at 500M DAU | Same escalation pattern + adversarial robustness: content features weakest, temporal/network strongest |
| [09-video-recommendations.md](09-video-recommendations.md) | YouTube-style "up next" recs | Multi-stage retrieval+ranking archetype; staff insight: bottleneck is data quality + eval, not model architecture |

### Project-specific interview narrative

| File | Topic |
|------|-------|
| [10-circuit-outbound-engine.md](10-circuit-outbound-engine.md) | Production-hardened canonical narrative for the Circuit outbound engine — closes all Rippling onsite gaps |

## Cross-link graph

```
Fundamentals (01) ──┬── Sharding (02) ─── Caching (03)
                    │                         │
                    ├── Web Crawler (04) ─────┤
                    │                         │
                    └── Ad Click Agg (05) ────┘
                              │
                    ML Core (06) ──┬── Harmful Content (07)
                                  ├── Bot Detection (08)
                                  └── Video Recs (09)
                                        │
                    Circuit One-Pager (10) ── references all above
```

## The meta-lessons (appear across multiple files — that's why they matter)

1. **Don't name-drop a technique without justifying it against the actual constraint.**
   - Bloom filter (crawler) · Checkpointing (ad-click) · LangGraph (Rippling interview)
   - The shallow move: "I'll use X because it helps." The deep move: set up the constraint, then choose.

2. **Business-objective escalation — question the obvious metric, reframe to actual value, add a counter-metric.**
   - Harmful content: "minimize views" not "remove all" · Bot detection: "minimize impact subject to FP guardrail"
   - Video recs: "quality-adjusted watch time" not "CTR" · SignalForce: "pipeline-per-dollar + no-garbage constraint"

3. **Do math when it informs a decision, not to look smart.**
   - Crawler: how many machines for 10B pages in 5 days? · Sharding: do you even need to shard?
   - SignalForce: at what prospect count does the single-DB model break?

4. **Favor practicality over academic purity.**
   - Ad-click: hybrid Lambda+Kappa is fine · Crawler: multiple DNS providers round-robin
   - SignalForce: laptop prototype was real; production design is the impressive part
