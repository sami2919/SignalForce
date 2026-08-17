# System Design Fundamentals

> Source: NoteGPT transcript "System Design Explained — APIs, Databases, Caching, CDNs, Load Balancing & Production Infra."
> Distilled 2026-08-03.
>
> **SignalForce relevance:** For every project (SignalForce, Circuit outbound engine, Rippling take-home),
> be able to answer: web/data tier split, which DB + why (SQL vs NoSQL decision rule), where deployed,
> how scaled (vertical vs horizontal), LB strategy, SPOFs + mitigations, auth/authz model, API style +
> protocol, and the TCP/UDP choice for any real-time piece.

## 1. From one server to scaled

- **Single server**: web app + API + DB + cache all on one box. User → DNS (maps domain→IP) → HTTP request → server → HTML/JSON response. Fine for small, struggles under load.
- **First split**: separate **web tier** (handles traffic) from **data tier** (DB), so each scales on its own load.
- **Vertical scaling (scale up)** = add RAM/CPU to one server. Simple, but hard cap + no redundancy (one box dies = everything dies).
- **Horizontal scaling (scale out)** = add more servers + a **load balancer** to distribute traffic. Fault-tolerant, scalable, but needs a LB. Prefer this for high-traffic.

## 2. Databases — when to use which

**SQL / RDBMS** (PostgreSQL, MySQL, Oracle, SQLite): tables/rows/columns, **joins**, **ACID** (Atomic=all-or-nothing, Consistent=valid→valid state, Isolation=concurrent txns don't interfere, Durable=survives crash). Use when: data well-structured with clear relationships, strong consistency/transactional integrity needed (banking, e-commerce customers+orders).

**NoSQL** types:
- **Document** (MongoDB) — JSON-like docs, complex structures in one record.
- **Wide-column** (Cassandra, Cosmos DB) — massive scale, great for many writes.
- **Graph** (Neo4j; Amazon Neptune for product recommendations) — entities + relationships as graphs.
- **Key-value** (Redis, Memcached) — RAM-backed, extremely fast R/W; simplicity + speed.

Use NoSQL when: super low latency, unstructured/semi-structured JSON, flexible scalable storage for huge volumes (e.g. recommendation engine storing user activity as KV). NoSQL can store user+orders+products in one document (no joins).

## 3. Load balancers — 7 algorithms + SPOF

1. **Round robin** — sequential rotation; servers with similar specs.
2. **Least connections** — fewest active connections; variable-length sessions.
3. **Least response time** — lowest latency + fewest connections; mixed-capability servers.
4. **IP hash** — hash client IP → same server every time; stateful servers (client sticks).
5. **Weighted** (weighted RR / weighted least-conn) — weights by capacity (16/32/64 GB RAM).
6. **Geographical** — closest server to user; global latency reduction.
7. **Consistent hashing** — hash ring; same client → same server (like IP hash, more robust to add/remove nodes).

- **Health checks**: LB pings servers, stops sending traffic to dead ones, resumes when they're back.
- **Examples**: software (Nginx, HAProxy), hardware (F5, Citrix), cloud (AWS ELB, Azure LB, GCP — auto-scaling + security + monitoring built in).

**Single point of failure (SPOF)** = one component whose failure takes the whole system down (e.g. a single DB behind many APIs). Causes reliability loss, scalability limits, security risk (attackers target it). Fix LB-as-SPOF with: **redundancy** (multiple LBs), **health checks on the LBs themselves**, **self-healing** (auto-replace a dead LB with a new instance).

## 4. API design — 3 styles + 4 principles

- **REST** — resource-based endpoints, stateless, HTTP methods (GET/POST/PUT-PATCH/DELETE), web+mobile. Multiple requests for related data, explicit versioning (/api/v1/), HTTP caching.
- **GraphQL** — single endpoint, client specifies exact shape (query/mutation/subscription), minimal round trips, complex UIs. Schema evolves without versioning (or field-level versioning), app-level caching.
- **gRPC** — high-perf RPC, **protocol buffers**, **HTTP/2**, streaming/bidirectional, microservices internal comms (browsers don't all support HTTP/2).

**4 principles**: **consistent** (naming/casing), **simple** (usable without docs), **secure** (auth + input validation + rate limiting), **performant** (caching, pagination, minimized payloads, reduced round trips).

**Design process**: requirements (use cases, scope, perf bottlenecks, security) → approach (top-down from reqs / bottom-up from existing data models / contract-first) → lifecycle (design → dev/test → deploy/monitor → maintenance → deprecation/retirement).

## 5. API protocols — choose by interaction pattern

- **HTTP** — request/response, methods, status codes (2xx success, 3xx redirect, 4xx client error, 5xx server), headers (content-type, authorization, accept, cache-control, user-agent), bearer/basic/OAuth auth. Default for REST.
- **HTTPS** = HTTP + TLS/SSL encryption. Encrypted in transit, integrity, auth, SEO. **Always use HTTPS.**
- **WebSockets** — handshake then bidirectional; server pushes to client without request. Real-time (chat, video). Replaces wasteful HTTP polling.
- **AMQP** — enterprise message queuing. Producer → broker (queue) → consumer. Async, decouples capacity (consumer pulls when free). Exchange types: direct, fanout, topic. (Order processing: producer publishes, consumer updates inventory when ready.)
- **gRPC** — Google RPC, protobufs, HTTP/2, streaming, server-to-server.

Choose by: interaction pattern (request-response→HTTP, real-time→WebSocket), performance (microservices→gRPC), client compatibility, payload size, security, DX.

## 6. Transport layer — TCP vs UDP

- **TCP** — reliable, connection-based (**3-way handshake**: SYN → SYN-ACK → ACK), ordered, resends lost packets, more overhead. Payments, auth, user data, banking, emails.
- **UDP** — fast, **no delivery guarantee**, no handshake/order, less overhead. Video calls, gaming, live streams (a dropped packet is fine, don't resend stale data).

## 7. REST design rules

- **Resources = nouns, plural**: /products (collection), /products/123 (item), /products/123/reviews (nested). Never /getProducts.
- **Filtering/sorting/pagination** via query params (?category=X&in_stock=true&sort=price&page=3&limit=10). Page+limit, or offset+limit, or cursor. Saves bandwidth, perf, flexibility.
- **Methods**: GET (safe + idempotent), POST (create, NOT idempotent), PUT (replace whole), PATCH (partial update), DELETE.
- **Status codes**: 200 OK, 201 Created, 204 No Content, 3xx redirect, 400 bad request, 401 unauthorized, 404 not found, 500 server error.
- **Best practices**: plural nouns, proper HTTP methods (DELETE /users/ID not POST /users/delete), filtering+sorting+pagination, versioning prefix (/api/v1/).

## 8. GraphQL specifics

- Schema = contract; types (User, Post), queries (read = GET), mutations (write = POST/PUT/PATCH/DELETE).
- **Error handling differs**: GraphQL always returns **200**, errors go in an `errors` field (with status code, message, path). Partial data + errors can coexist.
- Best practices: small modular schemas, **query depth limits** (~6-7 layers, avoid infinite nesting), meaningful naming, **input types** for mutations.

## 9. Authentication (who you are) vs Authorization (what you can do)

**Auth methods**:
- **Basic** — base64 user:pass per request; insecure (base64 reversible) unless HTTPS; rarely prod.
- **Digest** — MD5 hash; outdated.
- **API keys** — unique key per client, stored server-side with hash + scopes. Leaks are risky, no built-in expiry, random string (no embedded info — server must DB-lookup to know owner/permissions).
- **Session-based** — login → session store (Redis common: fast + key expiry) → session-ID cookie. **Stateful** (server remembers). Traditional web apps; doesn't scale for APIs/distributed.
- **Bearer** — "whoever has the token gets access" — a **pattern, not a method**. Most common bearer token = JWT.
- **JWT** — signed JSON object (user ID, expiry, claims/roles). **Stateless, self-contained** — verify signature locally, no DB lookup, reduces DB load, scalable.
- **Access + refresh tokens** — access token short-lived (15min–1hr, API calls); refresh token long-lived (days/weeks, renews access). **Store refresh tokens in HTTP-only cookies, NOT localStorage** (XSS).

**OAuth 2** = **authorization framework, NOT auth method**. "What can this app access on behalf of user" (e.g. grant an app read access to your Google Drive). Flow: consent screen → auth code → exchange code for access token. Token proves app can access resources, **doesn't tell the app who you are**.

**OpenID Connect** = adds authentication on top of OAuth 2. Returns **ID token** (JWT with identity: email/user ID) + access token. "Sign in with Google/GitHub" = this. Modern, secure, scalable.

**SSO** = **UX pattern, not auth method**. Login once → access multiple services (Google → Gmail, Drive, YouTube, Calendar). Uses identity protocols underneath: **SAML** (XML-based, enterprise/legacy — Salesforce, corporate dashboards) or **OpenID Connect** (modern, JWT ID token).

## 10. Authorization models

- **RBAC** (role-based) — roles → permissions (admin/editor/viewer). Most common. GitHub, Stripe, CMS.
- **ABAC** (attribute-based) — user/resource/env attributes + conditions (dept=HR AND resource=internal, time/location/device). More flexible, more complex, policy conflicts possible.
- **ACL** (access control list) — per-resource permission list (Google Doc sharing: Alice=read, Bob=read+write). User-centric, **hard to scale at millions of objects**.
- **Enforcement**: OAuth 2 = delegated authorization (Vercel gets a scoped token to your GitHub repos, not your password). JWT/bearer tokens carry identity + roles + scopes. **Tokens are mechanisms; RBAC/ABAC/ACL are the models that define what's allowed.** Real systems combine models.

## 11. API security — 7 techniques

1. **Rate limiting** — per endpoint / per user / per IP, PLUS an overall cap (DDoS: bots each get their own per-IP limit, so aggregate cap catches distributed attacks).
2. **CORS** — which origins can call your API from a browser (only your frontend domain).
3. **SQL/NoSQL injection** — parameterized queries / ORM safeguards; never interpolate user input into queries.
4. **Firewalls (WAF)** — filter malicious traffic (AWS WAF blocks suspicious SQL keywords / weird HTTP methods).
5. **VPNs** — private APIs reachable only from inside the network (internal admin dashboards).
6. **CSRF** (cross-site request forgery) — tricks a logged-in browser into unwanted requests via stolen session cookie. Use **CSRF tokens + session cookies** (banking).
7. **XSS** (cross-site scripting) — inject scripts into pages served to other users (malicious comment → executes in victim's browser, steals cookies). Sanitize input + output.

---

**Interview anchor**: for every project (SignalForce, Circuit outbound engine, AWS prospecting tool, Rippling take-home), be able to answer: web/data tier split, which DB + **why** (SQL vs NoSQL decision rule), where deployed, how scaled (vertical vs horizontal), LB strategy, SPOFs + mitigations, auth/authz model, API style + protocol, and the TCP/UDP choice for any real-time piece. See [10-circuit-outbound-engine.md](10-circuit-outbound-engine.md) for the production-hardened SignalForce-adjacent narrative that applies these fundamentals.
