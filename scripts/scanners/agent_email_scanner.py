"""Agent+email repo scanner — finds GitHub repos declaring both an agent
framework and an email library in a dependency manifest.

The signal: an Organization-owned repo whose manifest (pyproject.toml,
requirements.txt, package.json) declares BOTH an agent framework
(openai-agents, langgraph, crewai, ...) AND an email library (resend,
sendgrid, ...). That is a team shipping an agent that touches email — the
exact problem AgentMail's ICP is solving right now.

See docs/decisions/0006-agent-email-repo-scanner.md for the full rationale
and live-API measurements behind every decision below. Do not re-derive them.

Key decisions (ADR-0006):
  1. Manifest-scoped combined queries (`"fw" "lib" filename:manifest`), not
     N+M query-set intersection — /search/code cannot page past 1000 results
     and individual terms match 57k-169k files, so intersection samples two
     truncated windows rather than computing a real intersection.
  2. Only `language:`, `filename:`, `path:`, `extension:`, `repo:`, `org:`,
     `user:`, `size:` are valid /search/code qualifiers. `pushed:`, `stars:`,
     `created:` etc. return `total_count: 0` with HTTP 200 — a silent
     corpus wipe, not an error.
  3. Recency is NOT read from the search payload's embedded `repository`
     object — it lacks `pushed_at`/`created_at`/`stargazers_count`. A second
     pass against GET /repos/{full_name} (core bucket, 5000/hr) enriches the
     survivors only, after filtering.
  4. Pipeline order: search -> dedup -> drop forks -> drop non-Org owners ->
     diff against the ledger -> enrich the new-to-us set -> record all new
     org candidates -> emit for new AND not archived. Ordering filters by
     selectivity/cost keeps enrichment cheap.
  5. "First seen" means first seen by us (repo_observations ledger), not
     repo creation date. A tenant with zero ledger rows is a SEEDING run:
     record everything, emit nothing — a seeding run must never look like
     "found nothing".
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

import requests
from pydantic import BaseModel, ConfigDict

from scripts.api_client import APIError, BaseAPIClient
from scripts.config import get_config
from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Decision 2 — the only qualifiers /search/code supports without silently
# zeroing the corpus. Never add to this set without re-reading ADR-0006.
# ---------------------------------------------------------------------------

ALLOWED_QUALIFIERS: frozenset[str] = frozenset(
    {"language", "filename", "path", "extension", "repo", "org", "user", "size"}
)

_QUALIFIER_RE = re.compile(r"(\w+):\S+")

# ---------------------------------------------------------------------------
# Default matrix (ADR-0006 appendix has measured counts for several pairs).
# Overridable via ScannerConfig.custom_params.
# ---------------------------------------------------------------------------

_DEFAULT_PY_FRAMEWORKS = [
    "openai-agents",
    "langgraph",
    "crewai",
    "agno",
    "autogen",
    "pydantic-ai",
]
_DEFAULT_PY_EMAIL_LIBS = ["resend", "sendgrid", "postmark", "mailgun"]
_DEFAULT_PY_MANIFESTS = ["requirements.txt", "pyproject.toml"]

_DEFAULT_JS_FRAMEWORKS = ["mastra", "@openai/agents", "@langchain/langgraph"]
_DEFAULT_JS_EMAIL_LIBS = ["resend", "nodemailer", "@sendgrid/mail", "postmark"]
_DEFAULT_JS_MANIFEST = "package.json"

_PER_PAGE = 100
_MAX_PAGES = 3  # cap, per brief — 300 results/query even though the API allows 1000
# The point WE truncate, not the API's 1000-result ceiling. A pair with
# total_count=500 already loses 200 matches to _MAX_PAGES before it ever gets
# near the API's own limit — warning only above 1000 would silently discard
# anything in [301, 1000) with no truncated_pairs entry (ADR-0006 Consequences:
# truncation must never be silent).
_TRUNCATION_CEILING = _MAX_PAGES * _PER_PAGE


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# GitHub API client
# ---------------------------------------------------------------------------


class GitHubClient(BaseAPIClient):
    """GitHub REST API v3 client for code search + repo enrichment."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None, timeout: int = 30) -> None:
        if token:
            auth_headers: dict[str, str] = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        else:
            auth_headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        super().__init__(base_url=self.BASE_URL, auth_headers=auth_headers, timeout=timeout)

    def search_code(self, query: str, page: int = 1, per_page: int = _PER_PAGE) -> dict:
        """Search GitHub code (/search/code). 10 req/min — never call inside a hot loop
        without respecting that; BaseAPIClient handles 403-quota-exhausted backoff."""
        return self.get(
            "/search/code",
            params={"q": query, "page": page, "per_page": per_page},
        )

    def get_repo(self, full_name: str) -> dict:
        """Fetch repo metadata (/repos/{full_name}) — core bucket, 5000/hr, NOT search."""
        return self.get(f"/repos/{full_name}")


# ---------------------------------------------------------------------------
# Query construction (Decision 1 + Decision 2)
# ---------------------------------------------------------------------------


def qualifiers_in_query(query: str) -> set[str]:
    """Extract every `key:value` qualifier key present in a search query string."""
    return {m.group(1) for m in _QUALIFIER_RE.finditer(query)}


def build_query(framework: str, email_lib: str, manifest: str) -> str:
    """Build a manifest-scoped combined query for one (framework, email_lib, manifest) triple.

    Raises:
        ValueError: if the constructed query would use a qualifier outside
            ALLOWED_QUALIFIERS (Decision 2 — these return total_count: 0 with
            HTTP 200, a silent corpus wipe, not an error).
    """
    query = f'"{framework}" "{email_lib}" filename:{manifest}'
    used = qualifiers_in_query(query)
    disallowed = used - ALLOWED_QUALIFIERS
    if disallowed:
        raise ValueError(f"Disallowed search qualifiers {disallowed} in query: {query}")
    return query


@dataclass(frozen=True)
class MatrixEntry:
    framework: str
    email_lib: str
    manifest: str


def build_matrix(config: ScannerConfig) -> list[MatrixEntry]:
    """Build the (framework, email_lib, manifest) triples from config.custom_params,
    falling back to the ADR-0006 starting matrix when config omits a list."""
    cp = config.custom_params

    py_frameworks = cp.get("python_frameworks", _DEFAULT_PY_FRAMEWORKS)
    py_email_libs = cp.get("python_email_libs", _DEFAULT_PY_EMAIL_LIBS)
    py_manifests = cp.get("python_manifests", _DEFAULT_PY_MANIFESTS)

    js_frameworks = cp.get("js_frameworks", _DEFAULT_JS_FRAMEWORKS)
    js_email_libs = cp.get("js_email_libs", _DEFAULT_JS_EMAIL_LIBS)
    js_manifest = cp.get("js_manifest", _DEFAULT_JS_MANIFEST)

    matrix: list[MatrixEntry] = []
    for fw in py_frameworks:
        for lib in py_email_libs:
            for manifest in py_manifests:
                matrix.append(MatrixEntry(fw, lib, manifest))
    for fw in js_frameworks:
        for lib in js_email_libs:
            matrix.append(MatrixEntry(fw, lib, js_manifest))
    return matrix


# ---------------------------------------------------------------------------
# Candidate extraction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Candidate:
    full_name: str
    html_url: str
    fork: bool
    owner_login: str
    owner_type: str


def _extract_candidate(item: dict) -> _Candidate | None:
    """Pull the fields we need out of one /search/code result item.

    The embedded `repository` object is minimal (Decision 3): it has
    full_name, html_url, fork, and owner{login,type} — NOT pushed_at,
    created_at, or stargazers_count. Those come from enrichment.
    """
    repo = item.get("repository")
    if not repo:
        return None
    full_name = repo.get("full_name")
    if not full_name:
        return None
    owner = repo.get("owner") or {}
    return _Candidate(
        full_name=full_name,
        html_url=repo.get("html_url", f"https://github.com/{full_name}"),
        fork=bool(repo.get("fork", False)),
        owner_login=owner.get("login", ""),
        owner_type=owner.get("type", ""),
    )


# ---------------------------------------------------------------------------
# Ledger port (Decision 5) — the DB-free seam scanner unit tests use.
# Concrete implementation: scripts/scanners/agent_email_ledger.py
# ---------------------------------------------------------------------------


class RepoObservationRecord(BaseModel):
    """DTO passed to LedgerPort.record(). Mirrors RepoObservation columns
    minus tenant_id/id/first_seen_at, which are the ledger's responsibility."""

    model_config = ConfigDict(frozen=True)

    full_name: str
    owner_login: str
    html_url: str
    created_at_gh: datetime | None = None
    pushed_at_gh: datetime | None = None
    stars_at_first_seen: int = 0
    archived: bool = False


class LedgerPort(Protocol):
    """The seam that keeps scan() testable without a Session (per Task 2.2 brief)."""

    def is_empty(self) -> bool:
        """True iff this tenant has zero ledger rows — a seeding run (Decision 5)."""
        ...

    def known(self, full_names: list[str]) -> set[str]:
        """Return the subset of full_names already recorded for this tenant."""
        ...

    def record(self, observations: list[RepoObservationRecord]) -> None:
        """Persist new observations. Called once per scan with the new-to-us set."""
        ...


# ---------------------------------------------------------------------------
# Run-level stats (Task 2.2 brief, Step 5: numbers, not vibes)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScanStats:
    queries_issued: int
    search_requests: int
    core_requests: int
    raw_hits: int
    after_dedup: int
    after_fork_drop: int
    after_org_filter: int
    new_to_us: int
    enriched: int
    emitted: int
    truncated_pairs: list[str] = field(default_factory=list)
    seeding_run: bool = False
    failed_queries: list[str] = field(default_factory=list)


def _build_signal(rec: RepoObservationRecord, first_seen_at: datetime) -> Signal:
    """ADR-0006 Decision 5: the payload carries created_at, pushed_at, AND
    first_seen_at so "new to us" is never misreadable as "shipped this week" —
    a repo can be new to the ledger while its pushed_at is months old."""
    return Signal(
        signal_type="agent_email_repo",
        company_name=rec.owner_login,
        source_url=rec.html_url,
        signal_strength=SignalStrength.STRONG,
        raw_data={"full_name": rec.full_name},
        metadata={
            "full_name": rec.full_name,
            "created_at": rec.created_at_gh.isoformat() if rec.created_at_gh else None,
            "pushed_at": rec.pushed_at_gh.isoformat() if rec.pushed_at_gh else None,
            "first_seen_at": first_seen_at.isoformat(),
            "stars": rec.stars_at_first_seen,
        },
    )


def _search_pair(client: GitHubClient, query: str) -> tuple[list[_Candidate], int, int, bool]:
    """Run one query, paging up to _MAX_PAGES. Returns
    (candidates, raw_hit_count, search_requests_used, truncated)."""
    candidates: list[_Candidate] = []
    raw_hits = 0
    requests_used = 0
    truncated = False

    page = 1
    while page <= _MAX_PAGES:
        response = client.search_code(query, page=page)
        requests_used += 1
        total_count = response.get("total_count", 0)
        if total_count > _TRUNCATION_CEILING:
            truncated = True
        items = response.get("items", [])
        raw_hits += len(items)
        for item in items:
            candidate = _extract_candidate(item)
            if candidate is not None:
                candidates.append(candidate)
        if len(items) < _PER_PAGE:
            break
        page += 1

    return candidates, raw_hits, requests_used, truncated


def scan_with_stats(config: ScannerConfig, ledger: LedgerPort) -> tuple[ScanResult, ScanStats]:
    """Run the full agent+email scan and return (ScanResult, ScanStats).

    ScanStats carries the per-run operational numbers (queries issued, search
    vs. core requests, funnel counts) that ScanResult's fixed shape has no
    room for — required by the Task 2.2 brief's Step 5 real-data report.
    """
    app_config = get_config()
    client = GitHubClient(token=app_config.github_token)

    started_at = _utcnow()
    matrix = build_matrix(config)

    errors: list[str] = []
    failed_queries: list[str] = []
    truncated_pairs: list[str] = []
    search_requests = 0
    core_requests = 0
    raw_hits = 0

    # full_name -> candidate, first-seen-wins across queries (dedup, Decision 4).
    candidates: dict[str, _Candidate] = {}

    for entry in matrix:
        try:
            query = build_query(entry.framework, entry.email_lib, entry.manifest)
        except ValueError as exc:
            # A config-supplied triple could contain a colon; fail that pair loudly
            # but do not abort the run (per-query isolation, cf. Task 1.3b finding).
            logger.error("Skipping invalid query for %s: %s", entry, exc)
            failed_queries.append(str(entry))
            errors.append(str(exc))
            continue

        try:
            found, hits, used, truncated = _search_pair(client, query)
        except (APIError, requests.RequestException) as exc:
            # requests.RequestException (e.g. ConnectionError, or a second
            # consecutive Timeout — BaseAPIClient only retries a timeout once,
            # outside any try, so it can propagate raw) is not an APIError and
            # was leaking past this handler, aborting the remaining ~53 queries
            # on a run that already took 6-15 minutes. Per-query isolation
            # requires catching both (cf. Task 1.3b finding).
            logger.warning("Search query failed, skipping: %s — %s", query, exc)
            failed_queries.append(query)
            errors.append(f"{query}: {exc}")
            continue

        search_requests += used
        raw_hits += hits
        if truncated:
            logger.warning(
                "Query total_count exceeds truncation ceiling (%d): %s", _TRUNCATION_CEILING, query
            )
            truncated_pairs.append(query)

        for candidate in found:
            candidates.setdefault(candidate.full_name, candidate)

    after_dedup = len(candidates)

    # GitHub rarely indexes forks in code search; 0/2320 dropped in the
    # 2026-08-04 live run. Kept as declared intent, not a load-bearing filter.
    non_fork = {fn: c for fn, c in candidates.items() if not c.fork}
    after_fork_drop = len(non_fork)

    org_owned = {fn: c for fn, c in non_fork.items() if c.owner_type == "Organization"}
    after_org_filter = len(org_owned)

    all_full_names = list(org_owned.keys())
    seeding_run = ledger.is_empty()
    known = ledger.known(all_full_names)
    new_full_names = [fn for fn in all_full_names if fn not in known]

    # Enrichment (Decision 3): core bucket only, on the new-to-us set only,
    # never inside the search loop.
    new_records: list[RepoObservationRecord] = []
    for full_name in new_full_names:
        candidate = org_owned[full_name]
        try:
            # Counted before the call resolves, not after: a failed enrichment
            # still consumes real core-bucket quota, and undercounting errs in
            # the reassuring direction during exactly the 403 storm where the
            # number matters.
            core_requests += 1
            repo_data = client.get_repo(full_name)
        except (APIError, requests.RequestException) as exc:
            logger.warning("Enrichment failed, skipping: %s — %s", full_name, exc)
            errors.append(f"enrich {full_name}: {exc}")
            if seeding_run:
                # A seeding run enriches at full width (Decision 5) and is the
                # run most exposed to this: if a partially-failed seeding run
                # does NOT record the candidate, the next run sees it as
                # "new to us" and emits a false signal for a repo that was
                # already present during seeding. The ledger's question is
                # only "have we seen this repo" — that needs nothing from
                # GET /repos, and a seeding run emits nothing regardless, so
                # the missing stars/created_at/pushed_at cost nothing.
                new_records.append(
                    RepoObservationRecord(
                        full_name=full_name,
                        owner_login=candidate.owner_login,
                        html_url=candidate.html_url,
                    )
                )
            continue

        created_at_gh = _parse_gh_datetime(repo_data.get("created_at"))
        pushed_at_gh = _parse_gh_datetime(repo_data.get("pushed_at"))

        new_records.append(
            RepoObservationRecord(
                full_name=full_name,
                owner_login=candidate.owner_login,
                html_url=candidate.html_url,
                created_at_gh=created_at_gh,
                pushed_at_gh=pushed_at_gh,
                stars_at_first_seen=repo_data.get("stargazers_count", 0),
                archived=bool(repo_data.get("archived", False)),
            )
        )

    ledger.record(new_records)

    signals: list[Signal] = []
    if not seeding_run:
        for rec in new_records:
            if rec.archived:
                continue
            signals.append(_build_signal(rec, first_seen_at=started_at))

    completed_at = _utcnow()

    result = ScanResult(
        scan_type="agent_email_repo",
        started_at=started_at,
        completed_at=completed_at,
        signals_found=signals,
        total_raw_results=raw_hits,
        total_after_dedup=after_dedup,
        errors=errors,
    )
    stats = ScanStats(
        queries_issued=len(matrix),
        search_requests=search_requests,
        core_requests=core_requests,
        raw_hits=raw_hits,
        after_dedup=after_dedup,
        after_fork_drop=after_fork_drop,
        after_org_filter=after_org_filter,
        new_to_us=len(new_full_names),
        enriched=len(new_records),
        emitted=len(signals),
        truncated_pairs=truncated_pairs,
        seeding_run=seeding_run,
        failed_queries=failed_queries,
    )

    logger.info(
        "agent_email_repo scan complete",
        extra={
            "queries_issued": stats.queries_issued,
            "search_requests": stats.search_requests,
            "core_requests": stats.core_requests,
            "raw_hits": stats.raw_hits,
            "after_dedup": stats.after_dedup,
            "after_fork_drop": stats.after_fork_drop,
            "after_org_filter": stats.after_org_filter,
            "new_to_us": stats.new_to_us,
            "enriched": stats.enriched,
            "emitted": stats.emitted,
            "seeding_run": stats.seeding_run,
        },
    )

    return result, stats


def scan(config: ScannerConfig, ledger: LedgerPort) -> ScanResult:
    """Entry point matching the Signal/ScanResult shape other scanners return.

    Note this scanner's scan() takes a required `ledger` argument, unlike
    scanner_runner's `scan(ScannerConfig) -> ScanResult` convention — this
    scanner is DB-backed (the recency filter IS the ledger, per Decision 5)
    and is not wired into scanner_runner by this task. See Task 2.2 report.
    """
    result, _stats = scan_with_stats(config, ledger)
    return result


def _parse_gh_datetime(raw: str | None) -> datetime | None:
    """Parse a GitHub API ISO-8601 timestamp ('...Z' suffix) into an aware datetime."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Could not parse GitHub timestamp: %r", raw)
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Scan GitHub for org-owned repos declaring both an agent framework and an "
            "email library. Requires a SQLite ledger DB (never point at the production DB)."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--sqlite-path",
        type=str,
        required=True,
        help="Path to a throwaway SQLite file backing the repo_observations ledger.",
    )
    parser.add_argument(
        "--tenant-slug",
        type=str,
        default="agentmail",
        help="Tenant slug to scope the ledger to.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to write results as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point. Builds its own throwaway SQLite engine — does not touch
    scripts.storage.session / DATABASE_URL, so it can never hit the production DB."""
    import json

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from scripts.config_loader import load_config
    from scripts.scanners.agent_email_ledger import SqlAlchemyRepoLedger
    from scripts.storage.models import Base, Tenant

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    engine = create_engine(f"sqlite:///{args.sqlite_path}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    tenant = session.query(Tenant).filter_by(slug=args.tenant_slug).one_or_none()
    if tenant is None:
        tenant = Tenant(slug=args.tenant_slug, name=args.tenant_slug)
        session.add(tenant)
        session.commit()

    ledger = SqlAlchemyRepoLedger(session, tenant.id)

    sf_config = load_config()
    scanner_cfg = sf_config.scanners.get("agent_email")
    if scanner_cfg is None:
        # Fall back to an all-defaults config if not present in config.yaml.
        scanner_cfg = ScannerConfig(module="scripts.scanners.agent_email_scanner")

    result, stats = scan_with_stats(scanner_cfg, ledger)

    print(f"Seeding run: {stats.seeding_run}")
    print(f"Queries issued:      {stats.queries_issued}")
    print(f"Search requests:     {stats.search_requests}")
    print(f"Core requests:       {stats.core_requests}")
    print(f"Raw hits:            {stats.raw_hits}")
    print(f"After dedup:         {stats.after_dedup}")
    print(f"After fork drop:     {stats.after_fork_drop}")
    print(f"After org filter:    {stats.after_org_filter}")
    print(f"New to us:           {stats.new_to_us}")
    print(f"Enriched:            {stats.enriched}")
    print(f"Emitted:             {stats.emitted}")
    if stats.truncated_pairs:
        print(f"TRUNCATED pairs ({len(stats.truncated_pairs)}): {stats.truncated_pairs}")
    if stats.failed_queries:
        print(f"Failed queries ({len(stats.failed_queries)}): {stats.failed_queries}")

    for signal in result.signals_found:
        print(f"  [SIGNAL] {signal.company_name} — {signal.source_url}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result.model_dump(mode="json"), f, indent=2, default=str)
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
