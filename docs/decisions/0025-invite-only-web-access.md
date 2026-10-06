# ADR-0025: Invite-only web access and a stateless hosted audit

Status: accepted, 2026-10-05

## Context

The Fly app served an unauthenticated read-only dashboard for one tenant. We want a few GTM engineers to use Signal Audit and, later, a watchlist.

## Decisions

1. **Invite codes, not accounts.** 128-bit random codes, stored only as sha256, checked by indexed lookup. A signed `sf_session` cookie (SameSite=Lax, Secure in production) carries the invite id. Revoking an invite ends access on the next request because every request reloads the invite.
2. **The hosted audit is stateless.** Uploaded files are held only for the one request, in memory and in short-lived temporary files (including the framework's own upload spooling), and are deleted before the response is sent. Nothing is stored or logged; only sizes and invite ids are logged.
3. **The report is served from our origin, so it is treated as hostile output.** Jinja autoescape is on and a Content-Security-Policy allows nothing but inline styles.
4. **The existing dashboard moves behind login.** It was public.
5. **Uploads are guarded before parsing.** `UploadGuardMiddleware` (`scripts/web/upload_guard.py`) answers anonymous callers with a 303 to `/login` without reading the body, and rejects bodies over `MAX_TOTAL_BYTES` + 1 MiB (by Content-Length or while streaming) with a 413. It checks only that the signed session carries an invite id, so a revoked invite can upload up to that cap before the dependency rejects it.

## Rejected

- Public signup: needs abuse protection and a privacy policy before there is any evidence of demand.
- Stored reports with accounts: needs retention and deletion handling that the "nothing stored" promise avoids.
- HubSpot OAuth: app review and token storage, for a convenience CSVs already cover.

## Consequences

Users cannot re-open a past report; they save the page or re-run. Capacity is two concurrent audits per machine; a third gets a 429.
