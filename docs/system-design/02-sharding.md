# Sharding in System Design

> Source: NoteGPT transcript "Sharding in System Design Interviews w Meta Staff Engineer" (Evan, ex-Meta staff eng, hellointerview.com).
> Distilled 2026-08-03.
>
> **SignalForce relevance:** SignalForce currently runs on a single DB with ~448 tests. At what prospect
> count does the single-DB model break? The sharding math below applies directly: if SignalForce monitors
> 2M+ prospects across multiple ICPs, sharding by `prospect_id` with consistent hashing is the scaling path.
> Pair with [01-system-design-fundamentals.md](01-system-design-fundamentals.md) for the layer beneath.

## 1. Why sharding exists

Start: single AWS RDS Postgres — say 70TB storage, 10K writes/sec. Traffic grows, you outgrow it (need 20K writes/sec, or storage approaching ceiling, queries slowing, backups taking forever).
- **Vertical scaling first** — bigger machine. AWS offers up to ~140TB, ~50K writes/sec. This is a TON of throughput; most companies never hit it. Works for a long time.
- **When even bigger hardware isn't enough** (global, saturated CPU/storage/IO) → **sharding**: split data across multiple machines so no single DB holds everything. Each shard = standalone DB (own CPU, memory, storage, connection pool), holds a subset; together = full dataset. Scale by adding shards.
- Sharding solves scaling but introduces: how to choose shard key, how to route queries, hot shards, rebalancing, operational complexity.

## 2. Shard key — 3 properties (the first thing you say in an interview)

A good shard key has: **high cardinality** (lots of unique values → spread across shards), **even distribution** (each shard ~same data), **query alignment** (matches how you query — "get all posts for a user" → shard by user_id keeps it on one shard, one DB hit).

**Good**: user_id (social app — profile/posts), order_id (e-commerce — retrieve/create/review orders).
**Bad**: `is_premium` boolean (only 2 groups, capped at 2 shards, stuck when full); `creation_date` when users query recent data (all traffic → newest shard = hotspot).

## 3. Distribution strategies (3)

1. **Range-based** — split ranges (0–10M, 10M–20M…). Simple, intuitive. Problems: early days only first shard has data; if user IDs monotonically increase, all new/active users pile on the highest range = hotspot. Fine if data grows steadily in clean ranges; not production default.
2. **Hash-based** — `hash(key) mod N`. Even distribution (hash scrambles input). Problem: **rebalancing** — adding a shard changes mod N → mod N+1, almost everything moves = operational nightmare. → fix with **consistent hashing**: place keys AND shards on a virtual ring; from key's hash, walk right to the next DB. **Virtual nodes** eliminate the giant reshuffle. **Industry standard = hash-based + consistent hashing.** In an interview, if you say "shard by user_id," senior+ interviewers assume this; juniors may be asked to explain it.
3. **Directory-based** — lookup table mapping each key → shard. Flexible (move a hot user by updating the mapping; redistribute easily). Downsides: extra hop = latency on every request, and the directory is a **single point of failure**. Almost never the right answer in interviews — invites derailing follow-ups. Default to hash + consistent hashing.

## 4. Challenges (the follow-up questions)

**Hotspots / load imbalance — the celebrity problem.** Shard by user_id, Messi lands on shard 1 → all profile views/comments/likes/messages go to shard 1, orders of magnitude more traffic. Fixes:
- **Compound shard key** — hash `user_id + n` (n = number of shards to spread over) or `user_id + time`; spreads one user's data across multiple shards.
- **Dedicated celebrity shard** — detect high-traffic users, route them (via directory lookup) to a special shard (maybe bigger hardware). Most systems don't need this; only for extreme outliers like social media.

**Cross-shard operations.** Query needs data from multiple shards → fan out, query many/all shards, aggregate in memory, return. Happens when query doesn't align with shard key (e.g. "top 10 popular posts across platform" when sharded by user_id). Can't eliminate entirely. Fixes:
- Good shard key aligned to common queries (first line of defense).
- **Cache the result** (Redis) — first request does the expensive scatter-gather, then cache with ~5min expiry. Trades latency for staleness — fine for feeds/leaderboards/trending.
- **Denormalize** — repeat data so related info lives together on one shard (read hits one shard, but writes go to 2 places). Pay extra on writes, make reads cheaper.
- **Signal**: constant cross-shard queries for a common use case = (a) wrong shard key [most likely], (b) cache/precompute, or (c) denormalize. Cross-shard should be the exception, not the norm.

**Consistency.** Single DB = one atomic transaction (Bob −$5, Alice +$5, all-or-nothing). Different shards = can't be one atomic op; if deduction succeeds but credit fails → inconsistent state.
- **2PC (two-phase commit)** — central coordinator asks all shards "ready?", waits for all yes, then "commit." Ensures consistency but **slow + fragile** (any shard/coordinator down mid-protocol → stuck lock). Production usually avoids 2PC.
- **Avoid cross-shard transactions** — golden rule: keep transaction data on one shard when possible (not always achievable — Bob and Alice can't be guaranteed on same shard).
- **Saga pattern** — sequence of smaller ops, each with a **compensating/undo action**. Step 1: deduct $5 from Bob. Step 2: add $5 to Alice. If step 2 fails, don't magic-rollback — run the compensating action (refund Bob $5). Not atomic, but never ends in a broken state.

## 5. How sharding comes up in interviews — the script

Bring it up in **deep dives**, satisfying a non-functional scaling requirement. **Don't reflexively shard — do the math first.** It's often MORE impressive to show you don't need to shard:
- **Storage**: 500M users × 5KB = 2.5TB → single Postgres handles it, no shard. If 10–100x growth, then shard.
- **Write throughput**: 50K writes/sec peak → single DB struggles → shard.
- **Read throughput**: 100M DAU × multiple queries → exceeds thresholds even with read replicas → shard.
- Modern hardware goes far (140TB, 50K writes/sec). Justify the need with numbers.

**When sharding IS justified — 4 steps:**
1. **Propose shard key based on access pattern** — "most queries are user-centric (feed, followers, likes), so shard by user_id."
2. **Choose distribution strategy** — "hash-based sharding with consistent hashing to distribute evenly." (Often skippable at senior+; say it at junior/mid.)
3. **Call out trade-offs** — "global queries get expensive (trending posts → query all shards, aggregate). Handle by caching/precomputing trending content with a background job."
4. **Address growth** — "start with 10 shards for headroom; consistent hashing makes adding shards and resharding later smooth."

---

**Interview anchor (Sajwal's 2M-account question from the Rippling onsite):** His question — "monthly vendor monitoring across 2M accounts, how do you go about it?" — is a sharding/scale problem wearing a signals costume. The cheap-detection + verification tiering you gave is right instinct, but the depth to add: (1) shard the account set by a high-cardinality key (account_id) with consistent hashing so resharding is cheap as you grow past 2M; (2) the "did we capture it fast enough" question maps to hotspots + cross-shard aggregation — cache the diff results, accept staleness for non-critical accounts; (3) for the 500-account "utmost accuracy" variant, you DON'T shard — full coverage on one shard, completeness > filtering. The reflexive "shard everything" is wrong; the math-driven "shard only when justified" is what staff interviewers want. See [01-system-design-fundamentals.md](01-system-design-fundamentals.md) for the LB/DB layer beneath.
