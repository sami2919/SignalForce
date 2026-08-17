# Worked Problem: Ad Click Aggregator

> Source: hellointerview.com problem-breakdown "ad-click-aggregator" + NoteGPT transcript "Design an Ad Click Aggregator w/ Ex-Meta Staff Engineer" (Evan).
> Distilled 2026-08-03.
>
> **SignalForce relevance:** SignalForce's outcome_tracker (SQLAlchemy feedback loop) is a simplified version
> of the aggregator's stream→OLAP pipeline. The HMAC-signed impression-id idempotency pattern applies to
> SignalForce's signal deduplication (preventing the same GitHub repo event from being counted twice across
> scanner runs). The two-stage cascade (lightweight filter → heavy classifier) maps to SignalForce's
> ICP-fit scoring → intent scoring split. The hybrid Lambda+Kappa "practicality over purity" lesson is the
> most transferable interview insight.

## Infra vs product design questions — different roadmap

Evan splits system design questions into two flavors with different roadmaps:
- **Product design** (Ticketmaster, Uber, Dropbox — user-facing): requirements → **core entities + API** → HLD → deep dives.
- **Infrastructure design** (web crawler, ad click aggregator — not directly user-facing): requirements → **system interface + data flow** → HLD → deep dives. (Core entities/API make less sense when there's no user-facing CRUD surface.)

Recognizing which flavor you're in = the first structured-communication win. Picking the wrong roadmap (e.g. forcing an API design onto a crawler) is an early red flag.

## The problem

Collect + aggregate ad clicks so advertisers can query performance. Scale (ask the interviewer): **10M active ads, 10K clicks/sec peak** (~1K avg, ~100M clicks/day).

**Functional**: (1) user clicks ad → redirected to advertiser's site; (2) advertisers query click metrics over time, **minimum 1-minute granularity**.
**Out of scope**: ad targeting/serving, cross-device tracking, offline channels.

**Non-functional (quantified — don't just write "scalability"; put it in context + quantify)**:
- Scalability — support peak 10K clicks/sec
- Low-latency analytics — query response **<1 second**
- Fault tolerance + high data integrity — don't lose clicks (clicks = money)
- Near real-time — data available asap, at least within the 1-min granularity
- Idempotency — one user clicking one ad instance many times counts as ONE

**System interface**: inputs = click data (from users) + advertiser queries; outputs = redirection + aggregated metrics.
**Data flow**: click comes in → user redirected → validate (idempotency) → log raw click → aggregate → queryable by advertisers. (This list informs the HLD.)

## High-level design — the redirect nuance + 3 query solutions (bad→good→great)

**Click tracking & redirect**: browser clicks ad → POST to click processor service → returns 302 redirect to advertiser.
- *Naive*: send the redirect URL to the browser; it navigates + sends click event in parallel. **Problem**: ad blockers / sophisticated users extract the redirect URL from the DOM and navigate directly, bypassing click logging.
- *Chosen*: ad placement service sends only the **ad ID** to the browser (not the URL). Click processor looks up the redirect URL from the ads DB, logs the click, THEN returns the 302. Forces every click through the server — can't subvert logging. Also lets you append tracking query params.

**Querying metrics — the core of the problem** (Evan builds this up bad→good→great to show level expectations):

**❌ Bad (fails even mid-level)**: single DB (Cassandra) stores raw click events `{event_id, ad_id, user_id, timestamp}`; query service runs `SELECT COUNT(*), COUNT(DISTINCT user_id) ... GROUP BY ad_id` over a time window.
- Cassandra = LSM-tree (writes go to in-memory **memtable**, periodically flushed to disk as **SSTable**). Optimized for writes + fast point lookups by row key, but **NOT range queries or aggregations**. At 10K clicks/sec the GROUP BY over time windows is far slower than the <1s NFR. (Note: 10K writes/sec isn't actually that much — a well-tuned Postgres/DynamoDB could handle it; Cassandra is the "literature" default but not the only option.)

**✅ Good (passing for mid-level)**: separate write-optimized store from read-optimized store.
- Cassandra (raw events) → **Spark** map-reduce batch job (cron every ~5 min) aggregates by `ad_id + minute` → **OLAP database** (columnar — Redshift/Snowflake/BigQuery; columnar optimizes COUNT/SUM/AVG across millions of rows; chosen over time-series DBs due to high cardinality + multi-dimensional queries) → query service reads OLAP.
- **Why two DBs**: (1) reduces contention (write-heavy vs read-heavy workloads compete for threads); (2) fault isolation (read path down ≠ write path down; can backfill).
- Problem: 5-min delay — not real-time. Running Spark more frequently hits overhead limits.

**✅✅ Great (senior/staff starting point)**: stream processing.
- Click processor → **Kafka/Kinesis** click event stream → **Flink** stream aggregator (keeps in-memory counts per ad_id per minute window) → OLAP DB.
- **Aggregation window** = 1 minute (the period data is grouped by). **Flush interval** (e.g. 10s) = how often partial intermediate results are flushed — so an advertiser can read *partial* data 10s into the current minute (shown as a dotted/incomplete bar on the graph). Minute-boundary aggregation with sub-minute freshness.
- Flink advantages over raw Kafka consumers: windowed aggregations with **event-time semantics** (out-of-order events land in the correct minute bucket), **watermarks** to safely close windows, **exactly-once** guarantees, built-in fault tolerance.
- Many senior/staff candidates *start* here (they know it's a stream-processing question). Mid-level candidates start at the batch solution; interviewer nudges "I don't like that 5-min interval, how do you do better?" → they arrive at the stream solution.

## Deep dive 1 — Scalability (10K clicks/sec)

- Click processor + ad placement: horizontal scale behind a load balancer / AWS API gateway (auto-scale on CPU/memory thresholds).
- **Stream sharding**: Kinesis limit = 1MB/s OR 1000 records/s per shard → must shard. **Shard by ad_id** (natural choice — all events for an ad on one shard).
- Flink: one job/task per shard; since each Flink instance owns its own set of ad IDs, **no distributed contention** (no two Flink jobs responsible for the same ad_id).
- OLAP DB: shard by **advertiser_id** (the most common query is "show me MY ads' performance" — all of one advertiser's ads on one node).

**Hot shard problem** (a popular ad — Nike/LeBron — overwhelms one shard): the **celebrity problem** again (same as Messi/Taylor Swift in the sharding/caching references). Fix: append `ad_id:0..N` to the partition key for high-traffic ads, spreading one ad across N shards. Click processor must know what's popular (by ad spend / past volume). Flink: keep a **single Flink task per ad_id even for hot ones**, aggregating across the set of shards it's spread over (Flink can aggregate across multiple Kinesis shards). *(Cross-link: [02-sharding.md](02-sharding.md) celebrity problem + [03-caching.md](03-caching.md) hot keys — same fix shape.)*

## Deep dive 2 — Fault tolerance + data integrity

- Streams (Kafka/Kinesis) are distributed/fault-tolerant/HA by default — assume always up.
- **Enable 7-day retention** on the stream: even after Flink reads events, keep them 7 days. If Flink goes down and comes back, it reads from where it left off (cursor/offset). Configurable.
- **Flink checkpointing** — periodically writes state to persistent storage (S3), default ~every 15 min. **Evan's nuance (THE depth lesson here)**: checkpointing DOESN'T MAKE SENSE for small aggregation windows. Our window is 1 min → at most 1 min of data to re-read off the stream (10K×60 = 600K events, not many); checkpointing halfway through just writes unnecessary data to S3. **Rule of thumb: if aggregation window < 5 min, probably don't checkpoint.** Saying "I know candidates bring up checkpointing, but because of the small windows I'd opt NOT to use it" shows sophistication → distinguishes senior/staff. *(This is the SAME lesson as the crawler's bloom filter: don't regurgitate a technique without justifying it against the actual constraint. Third appearance of the depth principle.)*
- **Reconciliation** (the big data-integrity move): despite retention/checkpointing, transient Flink processing errors, bad code pushes, out-of-order events can cause slight inaccuracies. Clicks = money → high integrity required. So: Kinesis dumps raw events to **S3** (via connectors / Firehose) → **Spark** map-reduce batch job (daily) re-aggregates all raw events → **reconciliation worker** compares Spark output to Flink's OLAP data, overwrites if different, alerts the team + logs/observes the inconsistency rate (rising rate = something's broken).
- **This combines batch (correctness) + stream (real-time) = a hybrid Lambda + Kappa architecture** — neither pure Lambda nor pure Kappa, and Evan says that's FINE. Adapting textbook patterns to business needs shows seniority. "Practicality should almost always be favored over abstract academic purity." A staff candidate who recognizes this nuance (vs. rigidly forcing one pattern) is the tell. *(This is the same "practical not academic" instinct Sajwal rewarded with the multiple-DNS-providers-round-robin answer — cross-link [04-web-crawler.md](04-web-crawler.md).)*

**Lambda vs Kappa** (define if asked):
- **Kappa** = stream-only; treat all data as a continuous stream; rely solely on the real-time layer. (What we had before adding reconciliation.)
- **Lambda** = batch + real-time speed layer; real-time layer not guaranteed accurate, batch layer overwrites after N minutes.
- Hybrid is valid and common.

## Deep dive 3 — Idempotency (prevent abuse)

- **Don't dedup on user_id**: users may not be logged in; retargeting means the same ad shown Monday and Thursday are *different ad impressions* and should each be a valid click — you want one click per **ad impression**, not per user per ad.
- **Ad impression ID**: ad placement service generates a unique impression ID per ad *instance* per user (1000 users seeing the same ad = 1000 different impression IDs). Sent with the ad to the browser. On click, browser sends `ad_id + impression_id` to click processor.
- Click processor checks Redis: is this impression_id already there? If yes → duplicate, drop it. If no → put on stream.
- **The fabrication attack**: a malicious user can just POST with a *made-up* impression_id (change a character each time) — not in Redis, so it gets counted. Fix: **HMAC-sign the impression ID** (with timestamp) using a private key in the ad placement service. Browser sends `ad_id + impression_id + signed_impression_id`. Click processor **verifies the signature first** (is this legit / tampered?), THEN checks Redis for duplicate. The signature binds the impression ID to the specific ad_id, preventing harvesting + replay against other ads. (HMAC = microseconds, symmetric hash — no slow asymmetric crypto.)
- **Webpage ordering nuance**: write to the stream FIRST, THEN add to cache — so no clicks are lost if the cache update fails (reconciliation catches downstream duplicates, but lost clicks are unrecoverable).
- **Cache sizing**: ~100M impressions/day × 16 bytes ≈ 1.6GB → fits easily in a distributed Redis Cluster with replica + persistence (RDB/AOF).
- **Why dedup before the stream (not in Flink)**: duplicate clicks arriving on either side of a minute boundary would be counted as two separate clicks if dedup happens in Flink.

## Deep dive 4 — Low-latency query serving

Pre-aggregation via stream processing solves most of it. For large time windows (days/weeks/years): **rollup pre-aggregation** — nightly cron builds daily/weekly aggregated tables; advertisers query the coarse table first, drill down to fine. Trade storage space for query performance. (Cross-link: [03-caching.md](03-caching.md) — rollups are a precompute/cache pattern.)

## Level expectations

- **Mid**: 80% breadth / 20% depth. Batch (Spark) solution is approaching passing; interviewer probes follow-ups. Even the stream solution + competent follow-up answers would pass.
- **Senior**: ~60-70% breadth / 30-40% depth. Get to the Kappa (stream) architecture; show depth in 1-2 places (Kinesis scaling, retention policies, OR idempotency). Strong Lambda justification could also pass.
- **Staff**: breeze through breadth, HLD fast, spend time going deep. Find a place of intimate familiarity from past work and **teach the interviewer something**. Telltale sign of a great staff performance: the interviewer leaves having learned something. (Same bar as the crawler problem.)

## Final architecture (components)

Browser → LB/API gateway → click processor service (looks up redirect URL in ads DB, verifies HMAC signature, checks Redis dedup cache, writes to stream, updates cache) → 302 redirect. Stream (Kafka/Kinesis, sharded by ad_id, 7-day retention) → Flink (per-shard, in-memory minute-window aggregation, 10s flush interval, NO checkpointing for small windows) → OLAP DB (sharded by advertiser_id). Stream also → S3 (raw events via Firehose/connector) → Spark daily batch → reconciliation worker → fixes OLAP + alerts. Query service → advertisers. Redis Cluster for dedup (HMAC-signed impression IDs).

## Trade-offs to articulate

| Decision | Trade-off |
|---|---|
| Client-side vs server-side redirect | Simplicity vs guaranteed click tracking (ad blockers bypass client-side) |
| Batch (Spark) vs Stream (Flink) | Simplicity/correctness vs real-time latency |
| Single DB vs separate write/read stores | Contention + fault isolation (separate) vs simplicity (single) |
| Cassandra vs Postgres for event store | Cassandra write-optimized but poor at aggregations; 10K wps isn't actually that much — Postgres/DynamoDB can handle it |
| Checkpointing on vs off | State recovery vs unnecessary for small (<5min) windows — opting OFF shows nuance |
| Pure Lambda / Kappa vs hybrid | Academic purity vs practical business needs — hybrid favored |
| Dedup before stream vs in Flink | Accuracy (before) vs simplicity (in Flink) — before stream avoids boundary double-counts |
| HMAC vs DB lookup to validate impression ID | HMAC = microseconds, no extra DB call; DB lookup = simpler but extra hop |

---

**Interview anchor (why this matters for your gap):** This problem adds two new depth-lesson instances on top of the crawler's bloom-filter one:
1. **"Don't regurgitate checkpointing for small windows"** = the literal "more depth in technical explanations" from your feedback. The shallow move is naming checkpointing because you read it helps fault tolerance. The deep move is justifying *against* it because the aggregation window is 1 min so there's almost no state to recover and checkpointing just wastes S3 writes. Same shape as "don't name-drop LangGraph before saying what the system does."
2. **"Favor practicality over academic purity — a hybrid Lambda+Kappa is fine"** = the "structured, precise" communication of trade-offs. The shallow move is rigidly picking one textbook pattern. The deep move is adapting patterns to the business need (real-time speed layer + daily batch reconciliation for money-critical integrity) and articulating *why*. This is exactly the kind of answer Sajwal rewarded (practical DNS round-robin) and John was probing for.
The infra-vs-product roadmap distinction is also a direct "structured communication" win: pick the right frame upfront. Cross-link all four: [01-system-design-fundamentals.md](01-system-design-fundamentals.md), [02-sharding.md](02-sharding.md), [03-caching.md](03-caching.md), [04-web-crawler.md](04-web-crawler.md).
