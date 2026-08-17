# Worked Problem: Web Crawler

> Source: hellointerview.com problem-breakdown "web-crawler" + NoteGPT transcript "Design a Web Crawler w/ Ex-Meta Staff Engineer" (Evan).
> Distilled 2026-08-03.
>
> **SignalForce relevance:** SignalForce's scanner architecture (dumb Python collectors → signal_stacker →
> scored output) shares the crawler's 2-stage pipeline pattern: isolate the hard/variable part (network
> fetches) from the processing part (parsing/scoring). The SQS+DLQ retry pattern and the "queue holds a
> pointer, not the payload" principle apply directly to SignalForce's scanner pipeline. The meta-lessons
> (don't name-drop, do math when it informs a decision) are the interview communication discipline.

## The 6-step interview roadmap (Evan's method — applies to ANY system design question)

1. **Requirements** — functional (features) + non-functional (qualities/constraints). Non-functional must be **quantified** (ask scale: users, pages, throughput, latency SLAs, deadline).
2. **Core entities** — the tables/data central to the design (don't fully schema yet; come back as needed).
3. **API or interface** — for user-facing: API; for infra (like a crawler): the inputs/outputs boundary.
4. **Data flow** (optional, but high-value for infra/pipeline questions) — the high-level sequence of actions input→output. **This list directly informs the high-level design.**
5. **High-level design** — whiteboard a SIMPLE diagram that meets the functional requirements only. "Crucially meets functional requirements" — don't over-engineer yet.
6. **Deep dives** — go back to non-functional requirements ONE BY ONE, evolving the HLD until it satisfies each. **This is where senior/staff earn their value.**

**Level expectations in deep dives**: mid = 80% breadth / 20% depth, back-and-forth OK, interviewer leads you to pitfalls. Senior = 1–2 deep places. Staff = 3+ deep places, proactive, **practical** (not regurgitated). Key staff indicator: interviewer comes away having gained a new perspective.

## Meta-lesson 1: Don't do back-of-envelope math up front just to do it

Evan's strong opinion: candidates do scale math early, say "wow that's a lot," and keep going — interviewer learns nothing, candidate learns nothing. Instead: **do math at the critical junction where it informs a design decision** (e.g., "how many crawlers do I need to hit the 5-day deadline?"). Tell the interviewer you're deferring math until it informs direction. This is more sophisticated, more realistic, more indicative of real-job behavior. *(This is the "justify the need before the architecture" discipline from the sharding/caching references — same principle, third appearance.)*

## Meta-lesson 2: Don't name-drop a technique without justifying it (THE depth lesson)

Evan sees candidates reflexively say "I'll use a bloom filter" for dedup without justifying WHY. He reads it as a **bad sign** — regurgitating something read in a book (Alex Xu / Grokking) rather than thinking. The right move: set up the problem (am I memory-constrained? what's the size?), THEN choose. If not memory-constrained, a DynamoDB GSI or a Redis set is better than a bloom filter. **Name-dropping without justification = the exact "lacks depth" signal in the Rippling feedback.** Always: set up the constraint → justify the choice → state the trade-off.

## The problem

Design a web crawler that extracts text data from the web to train an LLM. Constraints: 10B pages, avg 2MB/page, must finish in **5 days**, "unlimited resources within reason." Scope ends at storing text — no model training/tokenization.

**Functional**: crawl from seed URLs; extract + store text.
**Non-functional (quantified)**: fault tolerance (resume without losing progress), politeness (robots.txt, don't overload servers), efficiency (under 5 days), scalability (10B pages).

**Core entities**: URL metadata (URL, depth, last-crawl time, S3 link to HTML, S3 link to text, domain, content hash), domain metadata (domain, last-crawl, robots.txt rules, crawl-delay), text data (output).

**Data flow**: seed URLs → DNS (resolve IP) → fetch HTML → extract text → store → extract URLs from page → add to frontier → repeat until frontier empty.

## High-level design (meets functional only)

Frontier queue (SQS, starts with seed URLs) → crawler worker pulls URL, hits DNS, fetches webpage, extracts text + URLs, writes text to S3, puts extracted URLs back on queue. Simple. Everything interesting happens in deep dives.

## Deep dive 1 — Fault tolerance: split the monolith into a 2-stage pipeline

The monolithic crawler does too much (fetch, extract text, extract URLs). If anything fails mid-way, progress is lost; can't scale stages independently; poor observability; fragile to changing requirements.

**Split into 2 stages**: (1) **URL fetcher** — pull URL, fetch HTML, store raw HTML in S3, update URL metadata. Isolates the HARD part (network failures, rate limits, slow servers). (2) **Parser worker** — pull from a second queue, fetch HTML from S3, extract text (store in S3) + extract URLs (back to frontier queue). Parsing can retry freely without re-fetching.

**Queue holds a pointer, not the payload**: put `{URL, S3 link}` JSON on the parsing queue, NOT the HTML. SQS default message limit ~1MB; pages avg 2MB; blobs belong in blob storage (highly optimized for large bytes), queues aren't meant for big payloads.

**Retry strategy** (fetch failures — internet is messy): bad = in-memory timer (lost if crawler dies, site probably not ready in 5s anyway). OK = Kafka separate topic for failed URLs with next-retry timestamp in the message. **Great = SQS built-in exponential backoff** via visibility timeout (30s → 2min → 5min → 15min...) using `ApproximateReceiveCount`; after 5 attempts → **dead-letter queue (DLQ)** via redrive policy. SQS chosen over Kafka for this.

**Crawler-down recovery**: Kafka = messages retained in log, crawlers commit offset only after successful processing (consumer group = read-once). SQS = message stays in queue until explicitly deleted; **visibility timeout** hides it from others while being processed; if crawler dies, timeout expires → message reappears for another crawler.

**Bonus of pipelining**: robust to changing requirements — ML team wants OCR/alt-text too? Just re-run parsing queue with new logic, no re-crawl of the web. (This is the DRY(E) "do the hard part once" idea — same shape as SignalForce's scanner→stacker split and the Rippling take-home's claims ledger.)

## Deep dive 2 — Politeness: robots.txt + rate limiting

**robots.txt** (per domain): `User-agent: *` (which crawler), `Disallow: /private/` (forbidden paths), `Crawl-delay: 10` (seconds between requests to this domain). Fetch once per domain, store in domain table. Before crawling: check path allowed (if not, ack/skip the message); check crawl-delay elapsed (if not, use `ChangeMessageVisibility` to defer). robots.txt may change — TTL + re-fetch (cache it; though we're IO-bound by the page fetch so not critical).

**Rate limiting**: industry standard = max 1 request/sec per domain even without crawl-delay. Redis sliding-window counter per domain. Add **jitter** (random delay) so 10 crawlers deferred off the same domain don't all retry simultaneously and re-trip the limiter.

**Per-domain lock**: Redis `SET NX` with TTL = crawl-delay, so two crawlers don't hit the same domain concurrently. Can't acquire → defer via visibility timeout.

**Same-domain pile-up problem** (staff-level): extracted URLs are usually same-domain → backlog of 100s of same-domain URLs in queue → all pulled, all hit crawl-delay/rate-limit, all put back = wasted cycles. **Smart scheduler**: don't put extracted URLs straight on the frontier queue; store them in URL metadata, and have a scheduler periodically pull a *mix* of domains onto the queue (or a priority queue). Avoids the pile-up.

## Deep dive 3 — Scalability + efficiency (save for LAST; system keeps evolving)

Do the math NOW because it informs a concrete decision: how many crawlers for 10B pages in 5 days?

- Transcript version: top AWS network-optimized instance ~400 Gbps → /8 bits → /2MB page = ~25K pages/sec theoretical. Can't use 100% bandwidth (DNS, rate limits, crawl-delay, retries, slow servers) → assume ~30% → ~10K pages/sec. 10B / 10K = 1M sec ≈ 10 days on ONE machine. Linear scaling → 2 machines = 5 days; add 2x leeway for errors/parsing overhead → **4 machines**.
- Webpage version: 200 Gbps → 12,500 pages/sec → 30% → 3,750 → 30.9 days/1 machine → **8 machines** for <5 days.

*(Numbers differ by bandwidth assumption — the METHOD is what matters: theoretical max → realistic utilization % → time/1 machine → divide by deadline → add leeway. Say "in reality I'd run a throughput test and multiply out.")*

Parser workers: downstream of the bottleneck, so **auto-scale on queue depth** (Lambda / Fargate / ECS) — just keep up.

**DNS bottleneck** (often overlooked; ~70% of elapsed time in early crawlers per the Mercator paper): (1) **DNS caching** in the same Redis cluster used for rate limiting — one lookup per domain, reuse. (2) **Multiple DNS providers + round-robin** — distributes load, reduces rate-limit risk, reduces single-provider failure risk. Evan loved this from a staff candidate — **practical, not academic**; "the first thing you'd suggest in a room with engineers after hitting DNS issues." This is the kind of answer that separates senior from junior.

## Deep dive 4 — Efficiency: deduplication (URL-level + content-level)

**(1) URL-level**: before adding a URL to the frontier, check URL metadata DB if it exists. Make URL the primary key; 10B rows → **shard on the PK**. Quick lookup, not the bottleneck anyway.

**(2) Content-level**: different URLs can serve identical content (mirrors, http vs www). Hash the HTML; check if hash already exists before queueing for parse.
- **Option A — GSI on content hash** (DynamoDB global secondary index): log n, fine because we're IO-bound by the page fetch and these are collocated in the VPC (tens of ms).
- **Option B — Redis set of hashes**: O(1), in-memory. 10B hashes × ~20 bytes = ~200GB → fits in one 256GB Redis instance (we're not money-constrained). Faster but extra hardware/cost/fault-tolerance concern.
- **Option C — Bloom filter**: space-efficient probabilistic; false positives possible (would skip content we haven't actually parsed → bad for "get ALL the text"), false negatives impossible. **Only justified if memory-constrained.** Evan: unless told you need a tiny Redis instance, don't reach for it — and reaching for it *unjustified* is a bad sign. *(Meta-lesson 2.)*

## Deep dive 5 — Crawler traps

Pages designed to trap crawlers indefinitely (self-referencing links, infinite same-domain link chains, no content). Fix: **max depth** field on URL (depth = link hops from seed; seed = 0). Parser increments depth for each new URL; stop crawling that branch past ~15–20.

## Additional deep dives (mention, don't fully build)

- **Dynamic content** (JS frameworks) — headless browser (Puppeteer) to render before extract; much slower/expensive/error-prone. (Clarify up front if needed.)
- **Monitoring** — Datadog/New Relic; the pipeline split helps track where URLs are in each stage.
- **Large pages** — HTTP HEAD request, check `Content-Length`, skip files > threshold (e.g. 10MB).
- **Continual updates** — for re-crawling (retrain model periodically): the smart URL scheduler uses last-crawl time + popularity to schedule re-crawls rather than dumping back on the queue.
- **Priority crawling** — multiple SQS queues / Kafka topics per priority; crawlers poll high-priority first.

## Final design (components)

Frontier queue (SQS) → URL fetcher (auto-scaled, ~4–8 machines) fetches HTML → S3 (raw HTML) + URL metadata (DynamoDB, sharded) → parsing queue (SQS, pointer only) → parser worker (auto-scaled on queue depth, Lambda/Fargate) → S3 (text) + extracted URLs back to frontier. Redis (rate limiting sliding window + DNS cache + per-domain locks + optional content-hash set). DLQ for 5x-failed URLs. DNS with caching + multiple providers round-robin.

## Trade-offs to articulate

| Decision | Trade-off |
|---|---|
| SQS vs Kafka | SQS: built-in visibility timeout + DLQ + managed scaling. Kafka: persistent log, offset-based read-once, but manual retry mechanics |
| Hash+index vs Redis set vs Bloom (dedup) | Index: simplest, no false +, log n. Redis set: O(1), extra hardware/fault-tolerance. Bloom: space-efficient, false + risk, only if memory-constrained |
| 2-stage pipeline vs monolith | Pipeline: fault isolation, independent scaling, requirement-flexibility, more components. Monolith: simpler, less infra |
| Single vs multiple DNS providers | Single: simpler. Multiple: load distribution, lower rate-limit/failure risk (practical, staff-level) |

---

**Interview anchor (why this matters for your gap):** This problem is a template for the *structured communication* the Rippling feedback said was missing. The 6-step roadmap IS the "structured and precise" frame: requirements → entities → interface → data flow → HLD → deep dives, in that order, each justified. Your John-interview failure (jumping to LangGraph/Pydantic before saying what the system IS) = skipping steps 1–4 and landing in step 6. And Meta-lesson 2 (don't name-drop bloom filter without justifying the constraint) is the literal "depth" critique — you name-dropped LangGraph/Pydantic/type-state handoffs without first establishing what the system did or why those choices fit. The fix for next time: walk the roadmap in order, justify every architectural choice against a stated constraint, and do math only when it changes a decision. Cross-link: [02-sharding.md](02-sharding.md) (URL metadata sharding), [03-caching.md](03-caching.md) (Redis rate-limit/DNS cache), [01-system-design-fundamentals.md](01-system-design-fundamentals.md) (queues, S3, load balancing).
