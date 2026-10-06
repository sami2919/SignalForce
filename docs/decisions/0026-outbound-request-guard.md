# ADR-0026: Outbound request guard and tenant-scoped scanning

Status: accepted, 2026-10-05

## Context

Invited users can add domains to a watchlist and the server fetches them, so a user can point our fetcher at internal addresses (cloud metadata at 169.254.169.254, Fly's private network, localhost), directly or through a redirect.

## Decisions

1. **One guarded client.** Every `httpx.AsyncClient` in the watch, resolve and holdout paths is created through `scripts.net.guard.guarded_client()` (`scripts/watch/runner.py`, `scripts/registry/resolver.py`, `scripts/measure/holdout.py`). A request event hook resolves the target host and refuses the request unless every address it resolves to is globally routable and not multicast. The hook runs on every request, including each redirect hop. A test (`test_no_raw_async_client_outside_the_guard`) fails if the text `httpx.AsyncClient(` appears in any Python file under `scripts/` other than `scripts/net/guard.py`.
2. **IPv6 forms that wrap an IPv4 address are unwrapped before the check.** IPv4-mapped, 6to4, NAT64 (`64:ff9b::/96`) and SIIT (`::ffff:0:0:0/96`) addresses are judged by the IPv4 address they carry, so `64:ff9b::a9fe:a9fe` is refused as 169.254.169.254. The IPv4-compatible range (`::/96`), the local-use NAT64 range (`64:ff9b:1::/48`) and site-local (`fec0::/10`) are refused outright. Scope ids (`%eth0`) are stripped before parsing.
3. **Fail closed.** A host with no addresses, a lookup failure and an unparseable address all raise `BlockedAddress`; any exception inside the check becomes `BlockedAddress`.
4. **A blocked request raises `BlockedAddress`, a subclass of `httpx.TransportError`**, so existing `except httpx.HTTPError` handlers record it as a failed fetch instead of crashing a scan.
5. **Domains are also checked at intake.** `POST /watchlist` resolves each new domain with `assert_public_host` and returns a 422 naming each refused domain (and why), so the user sees the refusal immediately instead of a silent failed resolution. A watchlist holds at most 25 domains per tenant (`MAX_WATCHLIST`); more than 25 in one submission, or a submission that would take the total past 25, is a 422. Re-adding a domain that is already on the list is ignored, not an error, and counts nothing extra toward the cap. Accepted domains are resolved to sources in a background task; the page shows "resolving..." until that finishes.
6. **The tenant comes from the signed-in invite, never from a request parameter.** This holds for the dashboard, the watchlist and the audit bridge (`/audit/from-watchlist`, which exports only that tenant's accounts and signals and audits them against CRM files the user uploads). An invite with no workspace gets a 403 on the watchlist and the bridge. The bridge keeps ADR-0025's stateless promise for the uploaded files.
7. **The daily worker scans every tenant that has an active source** when `SCAN_TENANTS=all` (`_tenant_slugs_to_scan`); without it, `TENANT_SLUG` selects a single tenant, and with neither set the run exits 1. Each tenant runs through `_scan_tenant_safely`: an exception in one tenant is logged and counted as a failure (exit code 1 for the run) and does not stop the remaining tenants.

## Residual risk

- **DNS rebinding.** The address is checked before the connection, and the connection resolves again, so a hostile DNS server can answer differently the second time. Closing this needs a connect-time address pin. Watchlists are capped at 25 domains per tenant and the audience is invite-only, which bounds exposure for now.
- **Synchronous DNS lookups at intake.** `POST /watchlist` runs `socket.getaddrinfo` in a request thread for each new domain, so a slow resolver slows that request (at most 25 lookups).
- **The cap check is not race-safe.** Two concurrent submissions can each pass the "at most 25" check and together exceed it.
- **No UI to remove an account.** Once a domain is added it stays on the watchlist; removal is an operator task in the database.

## Not done

Per-tenant holdout recall: the hourly holdout machine still measures the owner tenant only.
