# Caching in System Design

> Source: NoteGPT transcript "Caching in System Design Interviews w Meta Staff Engineer" (Evan, ex-Meta staff eng, hellointerview.com).
> Distilled 2026-08-03.
>
> **SignalForce relevance:** SignalForce's signal scoring uses recency-weighted decay (half-life per signal
> type). Caching is the natural extension — cache the expensive scanner results (GitHub API, ArXiv, G2 pages)
> with TTLs matched to signal half-lives. The cache-aside pattern + stampede protection apply directly to
> the scanner pipeline. Pair with [02-sharding.md](02-sharding.md) for cross-shard query caching.

## 0. The core trade-off (one number to remember)

Disk (SSD) access ≈ **1 millisecond**. Memory (RAM) ≈ **100 nanoseconds**. That's **~10,000x faster**. Caching trades a bit of storage + complexity for that speed by keeping frequently used data in a faster layer (usually memory) so you don't reach back to the slower source every time.

## 1. Where to cache — 4 layers

1. **External cache** (most common in interviews) — dedicated service (Redis/Memcached) on its own server, separate from app + DB. App checks cache → hit returns instantly; miss → fall back to DB, store copy back in cache, return. **Shared global view**: multiple app servers reuse the same cache (once one fetches it, others hit cache). **Default for interviews.**
2. **In-process cache** — data in the app server's own memory. Fastest possible (no network hop). But each server has its own → inconsistencies + wasted memory (one server's cache invisible to others). Bring up only for ultra-low-latency needs (config data, small lookup tables every request depends on). Not the default.
3. **CDN** (content delivery network) — geographically distributed edge servers caching content closer to users. Optimizes **network latency**, not memory-vs-disk. Without CDN: user in Australia → origin in Virginia = 300–350ms round trip. With CDN: nearest edge = 20–40ms. Miss → CDN fetches from origin (S3/blob), caches, returns. Modern CDNs also cache API responses / HTML / run edge logic, but in interviews the impactful use case is **media delivery** (images, video, static assets) for global users.
4. **Client-side cache** — browser HTTP cache / localStorage, or mobile app memory/disk. Fastest (data never leaves device) but least control (staleness, validation hard). Relevant only for offline functionality or client-heavy workloads (Strava caching run data offline, syncing on reconnect). Least important for interviews.

## 2. Cache architectures — 4 (the read/write order)

1. **Cache-aside** (default, the one to know cold) — app checks cache first; hit → return; miss → app fetches from DB, stores in cache, returns. Cache stays lean (only caches what's actually requested). Downside: cache miss adds latency (DB hit + store + return). **If you remember one, make it this.**
2. **Write-through** — app writes to cache first; cache **synchronously** writes to DB before returning. Write not complete until both updated. Requires a library/framework (Spring Cache, Hazelcast) — Redis/Memcached don't natively do this. Slower writes (wait for both). Can **pollute cache** with data never read again. **Dual-write problem**: if cache succeeds but DB fails (or vice versa) → inconsistent state; needs retry/error logic, perfect consistency hard in distributed systems. Use only when reads must always return fresh data AND slower writes are tolerable. Less common than cache-aside.
3. **Write-behind / write-back** — like write-through but cache writes to DB **asynchronously in background** (batched later). Writes much faster. Risk: if cache crashes before flush → **data loss**. Use only when high write throughput > immediate consistency (analytics/metrics pipelines where occasional loss is OK). As a novice, avoid unless strongly justified — invites more follow-ups than you want.
4. **Read-through** — like cache-aside but the **cache itself** does the DB lookup on miss (cache acts as proxy). This is how **CDNs work**. Bring up only for CDN/edge caching; for app-level caching cache-aside is the default (no special framework needed).

**Naming tip**: interviewers don't care about the exact terms — just describe the behavior clearly. Forget "cache-aside"? Say "check cache first, if not there go to DB then update cache." Understanding > memorizing names.

## 3. Eviction policies — 4

- **LRU** (least recently used) — evicts items not used recently. **Most common / default in interviews.**
- **LFU** (least frequently used) — evicts by access count, even if used recently. Use when access pattern is highly skewed (a few items read way more than others).
- **FIFO** (first in first out) — oldest removed for newest. Dead simple, rarely the right choice.
- **TTL** (time to live) — each item expires after a set time (e.g. 5min). Great for data that goes stale (user sessions, API responses). Super common when freshness matters more than recency/frequency.

Implementation detail (linked list / priority queue tracking access order) is almost always out of scope — don't go there unless asked.

## 4. The hard problems (what interviewers probe)

**Cache stampede / thundering herd** — popular TTL entry expires → flood of requests all rebuild the same cache key simultaneously → thousands of DB hits, can take the DB down. Example: homepage feed cached 60s, 100K req/sec, all miss at once at expiry. Fixes:
- **Request coalescing / single-flight** — only the first request rebuilds the key; the rest wait and read from cache when it's ready.
- **Cache warming** — proactively refresh popular keys just before expiry (e.g. at 55s for a 60s TTL), so it never actually expires.

**Cache consistency** (the most common probe) — cache and DB return different values for the same data. Happens because most systems **read from cache, write to DB** → window where cache holds stale data. Example: user updates profile pic (DB updated), but old pic still in cache → others see old one until eviction. No perfect fix; strategies:
- **Invalidate on write** — when DB updates, proactively delete that key from cache → next read misses, fetches fresh, repopulates. (Best when consistency matters.)
- **Short TTLs** — if some staleness is acceptable, keep the entry but with a short TTL (e.g. 60s) so it self-corrects quickly.
- **Accept eventual consistency** — totally valid for feeds, analytics, metrics. "5-min TTL on profile data, some users see a stale image for 5 min, that's fine" is a legitimate justification.

**Hot keys** — one cache entry gets way more traffic than everything else; even with great overall hit rate, that single key overloads one Redis node/shard. Example: Twitter, everyone viewing Taylor Swift's profile → that key gets millions/sec. Caching scales reads but doesn't make the system magically infinite. Fixes:
- **Replicate hot keys** — put Taylor Swift's data on each cache instance/shard; app load-balances evenly across them. (Requires understanding cache sharding/clustering — see [02-sharding.md](02-sharding.md).)
- **Local fallback cache** — use in-process caching for extremely hot values so repeated requests never even hit Redis (store in app memory).

## 5. How to talk about caching in an interview — the script

**When to bring it up** — deep dives, when discussing scale or latency in non-functional requirements. **Don't add a cache just to add a cache** — throwing it down without justification is a red flag (even if you're right, the lack of justification is wrong). Bring it up when ONE of these is true:
1. **Read-heavy workload straining DB** — "100M DAU × 20 req/day = 2B reads, more than DB can handle → cache in front to take read load off."
2. **Expensive queries** — computing a personalized newsfeed joins posts/followers/likes across tables → cache the result (Redis, 60s TTL).
3. **High DB CPU** — (real life, not interview — you won't have metrics).
4. **Latency requirements** — non-functional req says 100ms response; DB query too slow → must cache.

Pattern: **identify the bottleneck → quantify with rough numbers → explain how caching solves it.**

**The 5-step introduction** (do these in order):
1. **Identify the bottleneck** — the thing causing the issue (read load, expensive query, latency).
2. **Decide what to cache + the cache key** — not everything; focus on data read frequently, that doesn't change often, expensive to fetch/compute. **Be explicit about the key** (junior/mid candidates say "I'll add a cache" — the follow-up is always "what are you caching? what's the key? what values?").
3. **Choose the architecture** — "cache-aside on read: check Redis first, hit returns, miss queries DB, stores in Redis, returns."
4. **Mention the eviction policy** — LRU / LFU / TTL, with justification relevant to your system.
5. **Address the relevant downsides** — don't list all three mechanically; think about YOUR system. TTL on a popular key → stampede risk (single-flight/cache warming)? Stale data → consistency problem (invalidate-on-write / short TTL / accept eventual)? Hot keys → replicate / local fallback?

---

**Interview anchors (ties to SignalForce context):**
- **SignalForce scanner caching**: scanner results (GitHub repos, ArXiv papers, G2 reviews) are expensive to fetch and have natural staleness thresholds (signal half-lives: GitHub 5d, ArXiv 10d, G2 21d). Cache-aside with TTL matched to half-life is the natural pattern. Stampede risk: if all scanners run on the same schedule and their cache keys all expire at once → stagger TTLs or single-flight the rebuild.
- **Will's take-home hypotheticals (Rippling onsite)**: your "cheap scan → cache page hashes + snapshot metadata + prior claims ledger; expensive path starts from the diff" answer WAS cache-aside + cache warming applied to a monitoring agent. You had the right instinct; the vocabulary to add: name it cache-aside, name the eviction (TTL on the cheap-scan artifacts since they're snapshots that go stale), and proactively call out the stampede risk if 100 competitors' cheap-scan keys all expire on the same schedule → stagger TTLs or single-flight the rebuild.
- **Cross-shard query caching**: "cache trending posts in Redis with 5min TTL" IS cache-aside + accept eventual consistency. Same concept, two contexts — explain it once, reuse it. See [02-sharding.md](02-sharding.md).
