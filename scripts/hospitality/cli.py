"""Command-line entry point: python -m scripts.hospitality.cli <command>."""

import argparse
import asyncio
import csv
import logging
import math
import os
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import requests
from anthropic import Anthropic

from scripts.api_client import APIError
from scripts.firecrawl_client import FirecrawlClient
from scripts.hospitality.benchmark.baseline import run_baseline
from scripts.hospitality.benchmark.compare import compare
from scripts.hospitality.budget import BudgetExceeded, CallBudget
from scripts.hospitality.config import HospitalityConfig, WebsitesConfig, load_config
from scripts.hospitality.contacts.clay import (
    clay_rows,
    import_clay_csv,
    merge_contact,
    push_to_clay,
)
from scripts.hospitality.contacts.waterfall import HunterClient, find_contacts, role_priority
from scripts.hospitality.discover.exa import ExaClient
from scripts.hospitality.discover.lookalikes import lookalike_signals, seed_url
from scripts.hospitality.discover.press import PRESS_QUERIES, extract_press, press_to_records
from scripts.hospitality.events.extract import extract_appearances
from scripts.hospitality.events.rank import meeting_list, rank_events
from scripts.hospitality.events.registry import load_events
from scripts.hospitality.labels import (
    current_customers,
    customer_evidence,
    customer_groups,
    load_seed_labels,
    with_customer_flags,
)
from scripts.hospitality.llm import LLMRefusal
from scripts.hospitality.measure.backtest import case_replay, fit_auc
from scripts.hospitality.measure.recall import (
    first_inspections_in,
    ground_truth_openings,
    recall_audit,
)
from scripts.hospitality.messages.drafter import choose_angles, draft
from scripts.hospitality.messages.judge import judge
from scripts.hospitality.models import (
    BacktestResult,
    BenchmarkResult,
    CACompany,
    CAJob,
    CASeen,
    CaseReplay,
    Contact,
    CurveRecord,
    CustomerLabel,
    Draft,
    EntityLink,
    EventAppearance,
    Group,
    GroupEvidence,
    InspectionVenue,
    Judgement,
    LicenseRecord,
    LicenseSource,
    RecallReport,
    RegistryRecord,
    ScoredAccount,
    Signal,
    StackObservation,
    Venue,
    VenueAlias,
    WebsiteLookup,
    WindowEstimate,
)
from scripts.hospitality.report import build_report
from scripts.hospitality.resolve.carry import (
    apply_websites,
    canonical_entity,
    canonical_group_id,
    carried_job_board_venues,
    carried_press_venues,
    chain_moves,
    merge_lookups,
    remap_evidence,
    remap_lookups,
    venue_moves,
)
from scripts.hospitality.resolve.groups import regroup
from scripts.hospitality.resolve.match import match_licenses
from scripts.hospitality.resolve.operators import (
    cluster_operators,
    is_agent,
    operator_key,
    stored_counts,
)
from scripts.hospitality.resolve.venues import build_venues
from scripts.hospitality.scoring import (
    contract_operator_reason,
    non_restaurant_name_reason,
    operator_names,
    premises_reason,
    rank_prospects,
    score_group,
)
from scripts.hospitality.signals import license_signals
from scripts.hospitality.sources.culinary_agents import (
    COOKIE_ENV,
    SESSION_EXPIRED,
    Fetch,
    Pacer,
    PoliteFetcher,
    SessionFetch,
    article_signals,
    article_text,
    article_urls,
    company_key,
    fetch_nyc,
    is_job_board_venue,
    job_board_venues,
    job_key,
    read_page,
    redact,
    to_signals,
    walk_nyc,
)
from scripts.hospitality.sources.culinary_agents import (
    SOURCE as CA_SOURCE,
)
from scripts.hospitality.sources.dohmh import (
    fetch_first_inspections,
    fetch_never_inspected,
    merge_inspection_venues,
)
from scripts.hospitality.sources.registry import (
    count_companies_at,
    count_companies_named,
    lookup_companies,
    normalize_company,
)
from scripts.hospitality.sources.sla import fetch_licenses
from scripts.hospitality.sources.snapshot import first_seen_pending, take_snapshot
from scripts.hospitality.sources.socrata import SocrataClient
from scripts.hospitality.stack.crawl import crawl_stacks
from scripts.hospitality.stack.signals import (
    disqualified_venues,
    lapsed_loyalist_venues,
    loyalist_venues,
    stack_signals,
)
from scripts.hospitality.stack.website_import import plan_import
from scripts.hospitality.stack.website_search import (
    WebsiteFinder,
    fetch_pages,
    iter_search_lookups,
)
from scripts.hospitality.stack.websites import PlacesClient, iter_website_lookups
from scripts.hospitality.store import DocStore
from scripts.hospitality.window.estimate import estimate_all
from scripts.hospitality.window.survival import (
    build_curves,
    linked_to_inspected,
    opening_durations,
    quantile_time,
)

logger = logging.getLogger(__name__)

SEED_PATH = Path(__file__).resolve().parents[2] / "examples/magic-loyalist/customers_seed.yaml"
EVENTS_PATH = Path(__file__).resolve().parents[2] / "examples/magic-loyalist/events.yaml"
OUT_DIR = Path(__file__).resolve().parents[2] / "out/magic"
SLA_SOURCES: tuple[LicenseSource, ...] = ("sla_pending", "sla_active", "sla_inactive")


def ingest_sla() -> dict[str, int]:
    """Fetch all three SLA datasets for NYC and save them to the `licenses` kind."""
    cfg = load_config()
    client = SocrataClient("data.ny.gov", app_token=os.environ.get("SOCRATA_APP_TOKEN") or None)
    store = DocStore()
    counts: dict[str, int] = {}
    for source in SLA_SOURCES:
        records = fetch_licenses(client, cfg, source)
        store.save("licenses", records, key=lambda r: r.record_id)  # type: ignore[attr-defined]
        counts[source] = len(records)
    return counts


def ingest_dohmh() -> dict[str, int]:
    """Fetch DOHMH first-inspection venues (dated and never-inspected) into `inspections`."""
    client = SocrataClient(
        "data.cityofnewyork.us", app_token=os.environ.get("SOCRATA_APP_TOKEN") or None
    )
    first = fetch_first_inspections(client)
    never = fetch_never_inspected(client)
    venues = merge_inspection_venues(first, never)
    DocStore().save("inspections", venues, key=lambda v: v.camis)  # type: ignore[attr-defined]
    return {
        "venues": len(venues),
        "dated": sum(v.first_inspection_date is not None for v in venues),
        "never_inspected": sum(v.first_inspection_date is None for v in venues),
    }


def snapshot_pending() -> int:
    """Fetch current SLA pending applications and record today's snapshot."""
    cfg = load_config()
    client = SocrataClient("data.ny.gov", app_token=os.environ.get("SOCRATA_APP_TOKEN") or None)
    records = fetch_licenses(client, cfg, "sla_pending")
    return take_snapshot(DocStore(), records, date.today())


def _label_key(c: CustomerLabel) -> str:
    return f"{c.source}|{c.name}|{c.website_domain}|{c.venue_id}"


def _evidence_key(e: GroupEvidence) -> str:
    return f"{e.evidence_ref}|{e.name}"


def _regroup(
    store: DocStore,
    cfg: HospitalityConfig,
    venues: Sequence[Venue],
    licenses: Sequence[LicenseRecord],
    moves: dict[str, str] | None = None,
) -> tuple[list[Venue], list[Group]]:
    """Regroup from scratch (names, domains, every stored evidence merge); save; re-key records.

    The one grouping path for resolve, websites, press and culinary-agents. Records keyed to a
    venue that moved (`moves`) or to a group that merged follow it (M3), so contacts, drafts,
    observations, embed labels and group-level signals never strand on an old id.
    """
    aliases = chain_moves(
        {a.old_venue_id: a.new_venue_id for a in store.load("venue_aliases", VenueAlias)},
        moves or {},
    )
    evidence = remap_evidence(store.load("group_evidence", GroupEvidence), aliases)
    grouped, groups = regroup(
        venues, licenses, evidence, ignore_domains=frozenset(cfg.shared_host_domains)
    )
    group_of = {v.venue_id: v.group_id for v in grouped}

    def entity(eid: str) -> str:
        return canonical_entity(eid, group_of, aliases)

    def group(gid: str) -> str:
        return canonical_group_id(gid, group_of, aliases) or gid

    store.replace("venues", grouped, key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    store.replace("groups", groups, key=lambda g: g.group_id)  # type: ignore[attr-defined]
    store.replace("group_evidence", evidence, key=_evidence_key)  # type: ignore[arg-type]
    store.replace(
        "venue_aliases",
        [VenueAlias(old_venue_id=o, new_venue_id=n) for o, n in sorted(aliases.items())],
        key=lambda a: a.old_venue_id,  # type: ignore[attr-defined]
    )
    store.replace(
        "stack_observations",
        [
            o.model_copy(update={"venue_id": entity(o.venue_id)})
            for o in store.load("stack_observations", StackObservation)
        ],
        key=lambda o: f"{o.venue_id}|{o.observed_at.isoformat()}",  # type: ignore[attr-defined]
    )
    store.replace(
        "signals",
        [
            s.model_copy(update={"entity_id": entity(s.entity_id)})
            for s in store.load("signals", Signal)
        ],
        key=lambda s: s.signal_id,  # type: ignore[attr-defined]
    )
    store.replace(
        "customer_labels",
        [
            c.model_copy(update={"venue_id": entity(c.venue_id)}) if c.venue_id else c
            for c in store.load("customer_labels", CustomerLabel)
        ],
        key=_label_key,  # type: ignore[arg-type]
    )
    store.replace(
        "contacts",
        [
            c.model_copy(update={"group_id": group(c.group_id)})
            for c in store.load("contacts", Contact)
        ],
        key=lambda c: c.contact_id,  # type: ignore[attr-defined]
    )
    store.replace(
        "drafts",
        [d.model_copy(update={"group_id": group(d.group_id)}) for d in store.load("drafts", Draft)],
        key=lambda d: d.draft_id,  # type: ignore[attr-defined]
    )
    return grouped, groups


def resolve() -> dict[str, int]:
    """Match licenses to inspections, build venues, form groups; save venues/groups/links.

    A recompute of what public data says that keeps everything public data cannot rebuild:
    paid website lookups, press-only venues and group evidence (merges) are re-applied, and
    records keyed to a venue that moved or a group that merged follow it.
    """
    cfg = load_config()
    store = DocStore()
    today = date.today()
    licenses = store.load("licenses", LicenseRecord)
    inspections = store.load("inspections", InspectionVenue)
    old = store.load("venues", Venue)
    match = match_licenses(licenses, inspections, cfg)
    built = build_venues(licenses, inspections, match)
    moves = venue_moves(old, built)
    press_venues = carried_press_venues(old, (v.venue_id for v in built))
    board_venues = carried_job_board_venues(old, (v.venue_id for v in built))
    lookups = remap_lookups(merge_lookups(store.load("websites", WebsiteLookup), old, today), moves)
    store.replace("websites", lookups, key=lambda w: w.venue_id)  # type: ignore[attr-defined]
    venues, groups = _regroup(
        store, cfg, apply_websites([*built, *press_venues, *board_venues], lookups), licenses, moves
    )
    store.replace(
        "links",
        match.links,
        key=lambda link: f"{link.left_id}|{link.right_id}",  # type: ignore[attr-defined]
    )
    return {
        "venues": len(venues),
        "groups": len(groups),
        "multi_venue_groups": sum(len(g.venue_ids) > 1 for g in groups),
        "possibly_same_links": len(match.links),
        "websites_kept": sum(v.website is not None for v in venues),
        "press_venues_kept": len(press_venues),
        "job_board_venues_kept": len(board_venues),
        "venues_moved": len(moves),
    }


def window(today: date | None = None) -> dict[str, object]:
    """Build opening-timing curves and per-venue window estimates; save both."""
    cfg = load_config()
    today = today or date.today()
    store = DocStore()
    venues = store.load("venues", Venue)
    licenses = store.load("licenses", LicenseRecord)
    links = store.load("links", EntityLink)
    cap = cfg.window_unmatched_censor_max_age_days
    durations = opening_durations(
        venues, licenses, today, links, max_unmatched_age_days=cap, max_days=cfg.max_opening_days
    )
    curves = build_curves(durations)
    counts: dict[str, int] = {"all": len(durations)}
    for stratum, _, _ in durations:
        counts[stratum] = counts.get(stratum, 0) + 1
    estimates = estimate_all(venues, licenses, curves, cfg, today, links)
    for kind in ("curves", "estimates"):
        store.clear(kind)
    store.save(
        "curves",
        [CurveRecord(stratum=k, n=counts.get(k, 0), steps=c) for k, c in curves.items()],
        key=lambda r: r.stratum,  # type: ignore[attr-defined]
    )
    store.save("estimates", estimates, key=lambda e: e.venue_id)  # type: ignore[attr-defined]
    summary: list[tuple[str, int, float | None, float | None, float | None]] = []
    top = sorted((k for k in curves if k != "all"), key=lambda k: -counts[k])[:3]
    for k in ("all", *top):
        c = curves[k]
        summary.append(
            (k, counts[k], quantile_time(c, 0.25), quantile_time(c, 0.5), quantile_time(c, 0.75))
        )
    observed = sum(o for _, _, o in durations)
    return {
        "durations": len(durations),
        "observed": observed,
        "censored": len(durations) - observed,
        "estimates": len(estimates),
        "strata": summary,
    }


def _spreadsheet_safe(value: str) -> str:
    """Neutralize a cell a spreadsheet would run as a formula."""
    return f"'{value}" if value[:1] in ("=", "+", "-", "@") else value


def _website_priority(
    store: DocStore, venues: Sequence[Venue], estimates: Sequence[WindowEstimate]
) -> list[str]:
    """Venue ids worth a website, in order.

    Seed-customer venues first (for embed detection), then every venue of the ranked cold
    prospects, best priority first (soonest opening within a group), then the remaining
    venues with a window estimate, soonest opening first. Disqualified groups are skipped.
    """
    by_id = {v.venue_id for v in venues}
    seed_groups = current_customers(store, SEED_PATH, venues=venues)
    customer_ids = [v.venue_id for v in venues if v.group_id in seed_groups]
    opens = {e.venue_id: e.estimated_open for e in estimates}
    scores = store.load("scores", ScoredAccount)
    dropped = {s.group_id for s in scores if s.disqualified_reason}
    # The report's own order (ties broken by its stated rule), so "top N" means the same here.
    rank = {
        s.group_id: i
        for i, s in enumerate(a for a in rank_prospects(scores) if a.group_id not in seed_groups)
    }
    far = date.max
    ranked_prospects = sorted(
        (v for v in venues if v.group_id in rank),
        key=lambda v: (rank[v.group_id], opens.get(v.venue_id, far), v.venue_id),
    )
    by_open = sorted(estimates, key=lambda e: e.estimated_open)
    group_of = {v.venue_id: v.group_id for v in venues}
    ordered = [
        *customer_ids,
        *(v.venue_id for v in ranked_prospects),
        *(e.venue_id for e in by_open if group_of.get(e.venue_id) not in dropped),
    ]
    return list(dict.fromkeys(vid for vid in ordered if vid in by_id))


def p0_required_keys(cfg: WebsitesConfig) -> tuple[str, ...]:
    """Keys the paid P0 steps need, checked before step one.

    crawl always needs Firecrawl, which also satisfies the search provider (Exa is optional);
    the `places` provider adds GOOGLE_PLACES_API_KEY.
    """
    places = ("GOOGLE_PLACES_API_KEY",) if cfg.provider == "places" else ()
    return (*places, "FIRECRAWL_API_KEY")


def websites(
    limit: int = 400, today: date | None = None, provider: str | None = None
) -> dict[str, int | str]:
    """Look up websites for venues with a window estimate (and seed customers); regroup.

    `search` (default): Exa, Firecrawl search as the fallback, then each site is accepted only
    when its pages show the venue's own phone or street address. `places`: Google Places.
    Every lookup (hit or miss) is saved to the `websites` kind as it is made, so a re-resolve
    keeps it and no venue is looked up twice for a website already found. A miss is retried
    after `website_miss_retry_days`. Venues sharing a website domain then merge.
    """
    cfg = load_config()
    provider = provider or cfg.websites.provider
    exa_key = os.environ.get("EXA_API_KEY")
    fc_key = os.environ.get("FIRECRAWL_API_KEY")
    places_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if provider == "places":
        if not places_key:  # fail fast, before touching the store or the network
            raise SystemExit("GOOGLE_PLACES_API_KEY is not set; websites with provider places")
    elif not (exa_key or fc_key):
        raise SystemExit(
            "EXA_API_KEY and FIRECRAWL_API_KEY are both unset; the websites search provider "
            "needs at least one (or pass --provider places with GOOGLE_PLACES_API_KEY)"
        )
    today = today or date.today()
    store = DocStore()
    venues = store.load("venues", Venue)
    estimates = store.load("estimates", WindowEstimate)
    known = {w.venue_id: w for w in store.load("websites", WebsiteLookup)}

    def due(v: Venue) -> bool:
        if v.website:
            return False
        w = known.get(v.venue_id)
        return w is None or (
            w.website is None and (today - w.looked_up_on).days >= cfg.website_miss_retry_days
        )

    by_id = {v.venue_id: v for v in venues}
    priority = [vid for vid in _website_priority(store, venues, estimates) if due(by_id[vid])][
        :limit
    ]
    summary: dict[str, int | str] = {"provider": provider}
    found: list[WebsiteLookup] = []
    if provider == "places":
        budget = CallBudget("places", min(limit, cfg.budgets["places"]))
        stream = iter_website_lookups(
            venues,
            PlacesClient(places_key or "", budget),
            priority,
            today,
            cfg.website_match_max_distance_m,
            cfg.website_match_min_name_similarity,
        )
        calls = {"calls_places": lambda: budget.used}
        summary["engines"] = "google_places"
    else:
        exa = (
            ExaClient(exa_key, CallBudget("exa", min(limit, cfg.budgets["exa"])))
            if exa_key
            else None
        )
        fc_budget = CallBudget("firecrawl", min(limit, cfg.budgets["firecrawl"]))
        phones = {i.camis: i.phone for i in store.load("inspections", InspectionVenue) if i.phone}
        finder = WebsiteFinder(
            cfg.websites,
            exa=exa,
            firecrawl=FirecrawlClient(fc_key) if fc_key else None,
            firecrawl_budget=fc_budget if fc_key else None,
            fetch=fetch_pages,
            phones=phones,
        )
        stream = iter_search_lookups(venues, finder, priority, today)
        calls = {
            "calls_exa": lambda: finder.exa_calls,
            "calls_firecrawl": lambda: finder.firecrawl_calls,
        }
        summary["engines"] = "+".join(
            name for name, key in (("exa", exa_key), ("firecrawl", fc_key)) if key
        )
        in_use = (
            "Exa primary, Firecrawl search fallback"
            if exa_key and fc_key
            else "Exa only"
            if exa_key
            else "Firecrawl only"
        )
        print(f"websites: search provider, {in_use}")
    try:
        for lookup in stream:
            found.append(lookup)  # noqa: PERF402 (kept one by one: partial on error)
    finally:  # paid for: keep every lookup made, even if an error ends the run
        store.save("websites", found, key=lambda w: w.venue_id)  # type: ignore[attr-defined]
    updated = apply_websites(venues, found)
    _, groups = _regroup(store, cfg, updated, store.load("licenses", LicenseRecord))
    venue_of = {v.venue_id: v for v in venues}
    phone_on_record = {i.camis for i in store.load("inspections", InspectionVenue) if i.phone}
    misses = Counter(w.miss_reason or "unspecified" for w in found if w.website is None)
    summary.update(
        {
            "prioritized": len(priority),
            "lookups": len(found),
            "websites_found": sum(w.website is not None for w in found),
            "verified_phone": sum(w.verified_by == "phone" for w in found),
            "verified_address": sum(w.verified_by == "address" for w in found),
            "verified_address_no_phone_record": sum(
                w.verified_by == "address" and venue_of[w.venue_id].camis not in phone_on_record
                for w in found
            ),
            **{f"misses_{reason}": n for reason, n in sorted(misses.items())},
            **{name: read() for name, read in calls.items()},
            "multi_venue_groups": sum(len(g.venue_ids) > 1 for g in groups),
        }
    )
    return summary


def websites_import(
    path: Path, overwrite: bool = False, today: date | None = None
) -> dict[str, int]:
    """Import hand-filled websites from a CSV (`venue_id` or `camis`, `website`); regroup."""
    cfg = load_config()
    store = DocStore()
    venues = store.load("venues", Venue)
    existing = store.load("websites", WebsiteLookup)
    lookups, counts = plan_import(
        path,
        venues,
        existing,
        cfg.websites.excluded_domains,
        overwrite=overwrite,
        today=today or date.today(),
    )
    if lookups:
        store.save("websites", lookups, key=lambda w: w.venue_id)  # type: ignore[attr-defined]
        _regroup(store, cfg, apply_websites(venues, lookups), store.load("licenses", LicenseRecord))
    return counts.model_dump()


def websites_export_misses(today: date | None = None) -> Path:
    """Write the prioritized venues still lacking a website to a CSV to fill in by hand."""
    store = DocStore()
    venues = store.load("venues", Venue)
    estimates = {e.venue_id: e for e in store.load("estimates", WindowEstimate)}
    lookups = {w.venue_id: w for w in store.load("websites", WebsiteLookup)}
    by_id = {v.venue_id: v for v in venues}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "website_misses.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        out = csv.writer(fh)
        out.writerow(
            ["venue_id", "camis", "name", "address", "zip_code", "estimated_open", "miss_reason",
             "website"]
        )  # fmt: skip
        for vid in _website_priority(store, venues, list(estimates.values())):
            v, lookup = by_id[vid], lookups.get(vid)
            if v.website or (lookup and lookup.website):
                continue
            est = estimates.get(vid)
            out.writerow(
                [
                    v.venue_id,
                    v.camis or "",
                    _spreadsheet_safe(v.name),
                    _spreadsheet_safe(v.address),
                    v.zip_code,
                    est.estimated_open.isoformat() if est else "",
                    (lookup.miss_reason or "") if lookup else "not_looked_up",
                    "",
                ]
            )
    return path


def crawl(now: datetime | None = None) -> dict[str, object]:
    """Crawl venue websites, store stack observations (appending) and stack signals."""
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:  # fail fast, before touching the store or the network
        raise SystemExit("FIRECRAWL_API_KEY is not set; the crawl command needs it")
    cfg = load_config()
    now = now or datetime.now(UTC)
    store = DocStore()
    venues = store.load("venues", Venue)
    previous = store.load("stack_observations", StackObservation)
    budget = CallBudget("firecrawl", cfg.budgets["firecrawl"])
    observations = asyncio.run(
        crawl_stacks(venues, now, firecrawl=FirecrawlClient(key), firecrawl_budget=budget)
    )
    signals = stack_signals(observations, venues, previous, now)
    # History accumulates: each crawl time is its own row; a rerun at the same time overwrites.
    store.save(
        "stack_observations",
        observations,
        key=lambda o: f"{o.venue_id}|{o.observed_at.isoformat()}",  # type: ignore[attr-defined]
    )
    store.save("signals", signals, key=lambda s: s.signal_id)  # type: ignore[attr-defined]
    return {
        "observations": len(observations),
        "platforms": dict(Counter(p for o in observations for p in o.platforms)),
        "loyalist_embeds": len(loyalist_venues(observations)),
        "disqualified": len(disqualified_venues(observations)),
        "signals": len(signals),
        "firecrawl_calls": budget.used,
    }


def labels() -> dict[str, int]:
    """Snapshot the customer evidence (seed + every embed ever seen); count groups by source.

    Not required for the gate: every consumer computes `current_customers` itself. Embeds once
    seen stay labels; one missing from its venue's latest crawl is logged for review.
    """
    store = DocStore()
    venues = store.load("venues", Venue)
    groups = store.load("groups", Group)
    observations = store.load("stack_observations", StackObservation)
    stored = store.load("customer_labels", CustomerLabel)
    evidence = customer_evidence(SEED_PATH, venues, observations, stored)
    customers = customer_groups(evidence, venues, groups)
    store.replace("customer_labels", evidence, key=_label_key)  # type: ignore[arg-type]
    lapsed = lapsed_loyalist_venues(observations)
    for venue_id in lapsed:
        logger.warning("Loyalist embed missing from the latest crawl of %s: review", venue_id)
    counts = Counter(label.source for label in customers.values())
    return {
        "public_list": counts["public_list"],
        "embed": counts["embed"],
        "embeds_lapsed": len(lapsed),
    }


def _aliases(store: DocStore) -> dict[str, str]:
    return {a.old_venue_id: a.new_venue_id for a in store.load("venue_aliases", VenueAlias)}


NAMED_GROUP_RESOLUTIONS = frozenset({"job_board", "shared_domain", "press", "manual"})


def _top_prospect_companies(
    store: DocStore, top: int
) -> tuple[list[ScoredAccount], dict[str, list[str]]]:
    """The top cold prospects and, per group, the legal names of its venues' licences. Customer
    groups' companies are included too, so a cluster sharing an operator with a customer can be
    recognised as the customer's and dropped."""
    accounts = rank_prospects(_gated_scores(store))[:top]
    wanted = {a.group_id for a in accounts} | set(current_customers(store, SEED_PATH))
    legal = {r.record_id: r.legal_name for r in store.load("licenses", LicenseRecord)}
    by_group: dict[str, list[str]] = {}
    for v in store.load("venues", Venue):
        if v.group_id in wanted:
            for lid in v.license_ids:
                if lid in legal:
                    by_group.setdefault(v.group_id, []).append(legal[lid])
    return accounts, {g: list(dict.fromkeys(n)) for g, n in by_group.items()}


def registry(top: int = 300, *, client=None, budget: int | None = None) -> dict[str, int | str]:
    """Look up who receives legal papers for the licence companies of the top cold prospects.

    Free public data (data.ny.gov, no key), cached and budgeted. Display-only: scores and the
    stored groups are untouched; `report` shows the operator clusters it implies.
    """
    cfg = load_config()
    store = DocStore()
    accounts, companies = _top_prospect_companies(store, top)
    names = list(dict.fromkeys(n for ns in companies.values() for n in ns))
    calls = CallBudget(
        "registry", budget if budget is not None else cfg.budgets.get("registry", 600)
    )
    client = client or SocrataClient(
        "data.ny.gov", app_token=os.environ.get("SOCRATA_APP_TOKEN") or None
    )
    stopped = ""
    try:
        records = lookup_companies(names, client, calls, store)
        for r in records:
            line = r.process_address_1 or r.process_address
            if r.found and line and r.process_zip and not is_agent(r, cfg.registry, {}):
                count_companies_at(line, r.process_zip, client, calls, store)
                key = operator_key(r)
                if key and key[0] == "person" and r.process_name:
                    count_companies_named(r.process_name, client, calls, store)
    except BudgetExceeded as exc:
        stopped = f"budget: {exc}"
    except APIError as exc:
        stopped = f"api error: {exc}"
    except requests.exceptions.RequestException as exc:  # dropped connection, proxy reset
        stopped = f"network error: {type(exc).__name__}"
    cached = {r.name_key: r for r in store.load("registry_records", RegistryRecord)}
    by_group = {
        g: [cached[k] for k in (normalize_company(n) for n in ns) if k in cached]
        for g, ns in companies.items()
    }
    records = [r for rs in by_group.values() for r in rs]
    counts = stored_counts(records, store)
    groups = store.load("groups", Group)
    named = frozenset(g.group_id for g in groups if g.resolution in NAMED_GROUP_RESOLUTIONS)
    clusters = cluster_operators(
        by_group,
        {g.group_id: g.name for g in groups},
        named,
        cfg.registry,
        counts,
        require_counts=True,
    )
    found = [r for r in records if r.found]
    return {
        "prospect_groups": len(accounts),
        "companies": len(names),
        "looked_up": len(records),
        "found": len(found),
        "not_found": len(records) - len(found),
        "agents": sum(is_agent(r, cfg.registry, counts) for r in found),
        "clusters": len(clusters),
        "requests": calls.used,
        "stopped": stopped,
    }


def _gated_scores(store: DocStore) -> list[ScoredAccount]:
    """Stored scores with `is_customer` recomputed now: a stored flag can be stale."""
    return with_customer_flags(
        store.load("scores", ScoredAccount), current_customers(store, SEED_PATH)
    )


def _score_accounts(
    store: DocStore,
    cfg: HospitalityConfig,
    now: datetime,
    *,
    venues: Sequence[Venue],
    groups: dict[str, Group],
    licenses: Sequence[LicenseRecord],
    estimates: dict[str, WindowEstimate],
    observations: Sequence[StackObservation],
    signals: Sequence[Signal],
) -> list[ScoredAccount]:
    """Score every group that has signals; reads the store, writes nothing."""
    customers = current_customers(
        store, SEED_PATH, venues=venues, groups=list(groups.values()), observations=observations
    )
    disqualified = disqualified_venues(observations)
    licenses_by_id = {lic.record_id: lic for lic in licenses}

    # Index once; scoring 47k groups must not rescan all venues/signals per group.
    group_of = {v.venue_id: v.group_id for v in venues}
    venues_by_group: dict[str, list[Venue]] = {}
    for v in venues:
        venues_by_group.setdefault(v.group_id, []).append(v)
    signals_by_group: dict[str, list[Signal]] = {}
    aliases = _aliases(store)
    for sig in signals:  # a group-level signal keyed by a since-merged group still counts (M3)
        gid = canonical_group_id(sig.entity_id, group_of, aliases) or sig.entity_id
        signals_by_group.setdefault(gid, []).append(sig)
    obs_by_group: dict[str, list[StackObservation]] = {}
    for o in observations:
        if o.venue_id in group_of:
            obs_by_group.setdefault(group_of[o.venue_id], []).append(o)

    accounts: list[ScoredAccount] = []
    for gid, sigs in signals_by_group.items():
        group = groups.get(gid)
        if group is None:
            continue
        members = venues_by_group.get(gid, [])
        reasons = sorted(r for v in members if (r := disqualified.get(v.venue_id)))
        names = operator_names(group, members, licenses_by_id)
        operator = (
            contract_operator_reason(names, cfg)
            or non_restaurant_name_reason(names, cfg)
            or premises_reason(members, licenses_by_id, cfg)
        )
        accounts.append(
            score_group(
                group,
                sigs,
                estimates,
                members,
                obs_by_group.get(gid, []),
                cfg,
                now,
                is_customer=gid in customers,
                disqualified_reason=operator or (reasons[0] if reasons else None),
            )
        )
    return accounts


def score(now: datetime | None = None) -> dict[str, object]:
    """Build license signals, score every group with signals; save `scores`; rank prospects."""
    cfg = load_config()
    now = now or datetime.now(UTC)
    store = DocStore()
    venues = store.load("venues", Venue)
    groups = {g.group_id: g for g in store.load("groups", Group)}
    licenses = store.load("licenses", LicenseRecord)
    links = store.load("links", EntityLink)
    estimates = {e.venue_id: e for e in store.load("estimates", WindowEstimate)}
    observations = store.load("stack_observations", StackObservation)
    lic_signals = license_signals(
        venues,
        licenses,
        first_seen_pending(store),
        now.date(),
        linked=linked_to_inspected(venues, links),
        max_unmatched_age_days=cfg.window_unmatched_censor_max_age_days,
        issued_lookback_days=cfg.issued_lookback_days,
        not_yet_inspected_max_age_days=cfg.not_yet_inspected_max_age_days,
    )
    store.clear("license_signals")  # recomputed in full each run, so stale ones never linger
    store.save("license_signals", lic_signals, key=lambda s: s.signal_id)  # type: ignore[attr-defined]
    signals: list[Signal] = [*lic_signals, *store.load("signals", Signal)]

    accounts = _score_accounts(
        store,
        cfg,
        now,
        venues=venues,
        groups=groups,
        licenses=licenses,
        estimates=estimates,
        observations=observations,
        signals=signals,
    )
    store.clear("scores")
    store.save("scores", accounts, key=lambda a: a.group_id)  # type: ignore[attr-defined]
    ranked = rank_prospects(accounts)
    return {
        "license_signals": dict(Counter(s.signal_type for s in lic_signals)),
        "scored_groups": len(accounts),
        "customers": sum(a.is_customer for a in accounts),
        "disqualified": sum(a.disqualified_reason is not None for a in accounts),
        "prospects": len(ranked),
        "top": [(a, groups[a.group_id].name) for a in ranked[:25]],
    }


def contacts(top: int = 25) -> dict[str, object]:
    """Find named contacts for the top prospect groups (team page, then Hunter); save them."""
    for var in ("HUNTER_API_KEY", "FIRECRAWL_API_KEY", "ANTHROPIC_API_KEY"):
        if not os.environ.get(var):  # fail fast, before touching the store or the network
            raise SystemExit(f"{var} is not set; the contacts command needs it")
    cfg = load_config()
    store = DocStore()
    venues = store.load("venues", Venue)
    groups = {g.group_id: g for g in store.load("groups", Group)}
    ranked = rank_prospects(_gated_scores(store))[:top]
    budgets = {
        "firecrawl": CallBudget("firecrawl", cfg.budgets["firecrawl"]),
        "hunter": CallBudget("hunter", cfg.budgets["hunter"]),
    }
    firecrawl = FirecrawlClient(os.environ["FIRECRAWL_API_KEY"])
    hunter = HunterClient(os.environ["HUNTER_API_KEY"], budgets["hunter"])
    found: list[Contact] = []
    try:
        for acct in ranked:
            found.extend(
                find_contacts(
                    acct,
                    venues,
                    firecrawl=firecrawl,
                    hunter=hunter,
                    budgets=budgets,
                    min_email_confidence=cfg.min_email_confidence,
                    max_email_lookups=cfg.max_email_lookups_per_group,
                )
            )
    finally:  # an unexpected error (Hunter 401, Firecrawl APIError) keeps what was paid for
        store.save("contacts", found, key=lambda c: c.contact_id)  # type: ignore[attr-defined]
    return {
        "groups": len(ranked),
        "groups_with_contacts": len({c.group_id for c in found}),
        "contacts": len(found),
        "with_email": sum(c.email is not None for c in found),
        "firecrawl_calls": budgets["firecrawl"].used,
        "hunter_calls": budgets["hunter"].used,
        "names": [groups[a.group_id].name for a in ranked if a.group_id in groups][:5],
    }


def events_extract(path: Path = EVENTS_PATH) -> dict[str, object]:
    """Extract appearances from the lineup pages of verified-date registry events; save them."""
    for var in ("FIRECRAWL_API_KEY", "ANTHROPIC_API_KEY"):
        if not os.environ.get(var):  # fail fast, before touching the store or the network
            raise SystemExit(f"{var} is not set; the events-extract command needs it")
    cfg = load_config()
    events = load_events(path)  # unverified dates are excluded
    budget = CallBudget("firecrawl", cfg.budgets["firecrawl"])
    firecrawl = FirecrawlClient(os.environ["FIRECRAWL_API_KEY"])
    found: list[EventAppearance] = []
    stopped = ""
    store = DocStore()
    try:
        for event in events:
            found.extend(extract_appearances(event, firecrawl, budget))
    except BudgetExceeded as exc:
        stopped = str(exc)
        logger.warning("events-extract stopped: %s", exc)
    finally:  # an unexpected error (APIError, LLMRefusal) keeps the events already extracted
        store.save(
            "event_appearances",
            found,
            key=lambda a: f"{a.event_id}|{a.person}|{a.restaurant}|{a.role}|{a.source_url}",  # type: ignore[attr-defined]
        )
    out: dict[str, object] = {
        "events": len(events),
        "appearances": len(found),
        "firecrawl_calls": budget.used,
    }
    if stopped:
        out["stopped"] = stopped
    return out


def events_rank(path: Path = EVENTS_PATH) -> dict[str, object]:
    """Rank verified-date events by expected meetings per dollar; write meeting lists."""
    store = DocStore()
    events = load_events(path)  # unverified dates are excluded
    appearances = store.load("event_appearances", EventAppearance)
    venues = store.load("venues", Venue)
    groups = store.load("groups", Group)
    customers = current_customers(store, SEED_PATH, venues=venues, groups=groups)
    scores = with_customer_flags(store.load("scores", ScoredAccount), customers)
    accounts = {a.group_id: a for a in scores}
    priors = load_config().events
    ranked = rank_events(events, appearances, accounts, venues, customers, priors=priors)
    by_id = {e.event_id: e for e in events}
    lines = ["# Event ranking and meeting lists", ""]
    total = 0
    for s in ranked:
        ev = by_id[s.event_id]
        targets = meeting_list(ev, appearances, accounts, venues, customers, priors=priors)
        total += len(targets)
        cost = f"${ev.cost_usd:,.0f}" if ev.cost_usd > 0 else "cost unknown"
        lines += [
            f"## {ev.name} ({ev.event_type}, {cost})",
            (
                f"expected meetings {s.expected_meetings:.4f}, "
                f"per dollar {s.score_per_dollar:.6f}, matched people {s.matched_people}"
            ),
            "",
            "### Prospects",
        ]
        lines += [
            f"- {t.person} ({t.reason}); priority {t.priority:.2f}; "
            f"{'in window' if t.in_window else 'not in window'}"
            for t in targets
            if not t.is_customer
        ] or ["- none"]
        lines.append("")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "meeting_lists.md").write_text("\n".join(lines), encoding="utf-8")
    return {
        "events": len(ranked),
        "appearances": len(appearances),
        "targets": total,
        "top": [(by_id[s.event_id].name, round(s.expected_meetings, 4)) for s in ranked[:5]],
    }


def _contact_text(contact: Contact | None) -> tuple[str, ...]:
    return (contact.name, contact.role) if contact else ()


def draft_command(top: int = 10) -> dict[str, object]:
    """Draft (never send) up to `draft_angles_per_group` angles per top cold prospect; judge and
    save them."""
    if not os.environ.get("ANTHROPIC_API_KEY"):  # fail fast, before touching the store
        raise SystemExit("ANTHROPIC_API_KEY is not set; the draft command needs it")
    cfg = load_config()
    store = DocStore()
    venues = store.load("venues", Venue)
    group_of = {v.venue_id: v.group_id for v in venues}
    aliases = _aliases(store)

    def group(eid: str) -> str:
        return canonical_group_id(eid, group_of, aliases) or eid

    # What the grounding check may trace a name in a draft to, besides the cited evidence.
    own_names: dict[str, list[str]] = {g.group_id: [g.name] for g in store.load("groups", Group)}
    for v in venues:
        own_names.setdefault(v.group_id, []).extend((v.name, v.address))

    signals_by_group: dict[str, list[Signal]] = {}
    for sig in [*store.load("license_signals", Signal), *store.load("signals", Signal)]:
        signals_by_group.setdefault(group(sig.entity_id), []).append(sig)
    contacts_by_group: dict[str, list[Contact]] = {}
    for c in store.load("contacts", Contact):
        contacts_by_group.setdefault(group(c.group_id), []).append(c)
    ranked = rank_prospects(_gated_scores(store))[:top]
    drafts: list[Draft] = []
    judgements: dict[str, Judgement] = {}
    try:
        for acct in ranked:
            evidence = signals_by_group.get(acct.group_id, [])
            people = sorted(
                contacts_by_group.get(acct.group_id, []), key=lambda c: role_priority(c.role)
            )
            contact = people[0] if people else None
            for angle in choose_angles(evidence)[: cfg.draft_angles_per_group]:
                d = draft(acct, evidence, contact, angle)
                account_text = [*own_names.get(acct.group_id, []), *_contact_text(contact)]
                judgements[d.draft_id] = judge(
                    d, evidence, account_text=account_text, pass_score=cfg.judge_pass_score
                )
                drafts.append(d)  # only once judged: a stored draft always has its judgement
    finally:  # an unexpected error (LLMRefusal, APIError) keeps the drafts already judged
        store.save("drafts", drafts, key=lambda d: d.draft_id)  # type: ignore[attr-defined]
        ids = {id(j): k for k, j in judgements.items()}
        store.save("judgements", list(judgements.values()), key=lambda j: ids[id(j)])
    passed = sum(j.passed for j in judgements.values())
    grounded = sum(not j.grounding_violations for j in judgements.values())
    return {
        "groups": len(ranked),
        "drafts": len(drafts),
        "passed": passed,
        "grounded": grounded,
        "pass rate": f"{passed / len(drafts):.0%}" if drafts else "n/a",
        "grounding rate": f"{grounded / len(drafts):.0%}" if drafts else "n/a",
    }


def clay_push(top: int = 25) -> dict[str, object]:
    """Push the top cold prospects to the Clay table by webhook (customers never pushed)."""
    url = os.environ.get("CLAY_WEBHOOK_URL")
    if not url:  # fail fast, before touching the store or the network
        raise SystemExit("CLAY_WEBHOOK_URL is not set; the clay-push command needs it")
    cfg = load_config()
    store = DocStore()
    ranked = rank_prospects(_gated_scores(store))[:top]
    rows = clay_rows(ranked, store.load("venues", Venue), store.load("contacts", Contact))
    budget = CallBudget("clay", cfg.budgets["clay"])
    pushed = push_to_clay(url, rows, budget)
    return {"rows": len(rows), "pushed": pushed, "clay_calls": budget.used}


def clay_import(path: Path) -> dict[str, object]:
    """Import Clay's enriched CSV as contacts for known prospect groups; never downgrade."""
    store = DocStore()
    known = {a.group_id for a in rank_prospects(_gated_scores(store))}
    group_of = {v.venue_id: v.group_id for v in store.load("venues", Venue)}
    aliases = _aliases(store)
    parsed = [  # a row exported before a merge carries the old group id (M3)
        c.model_copy(update={"group_id": canonical_group_id(c.group_id, group_of, aliases)})
        if canonical_group_id(c.group_id, group_of, aliases)
        else c
        for c in import_clay_csv(path)
    ]
    kept = [c for c in parsed if c.group_id in known]
    for c in parsed:
        if c.group_id not in known:
            logger.warning("clay import skipped: group %s is not a known prospect", c.group_id)
    existing = {c.contact_id: c for c in store.load("contacts", Contact)}
    merged = [
        merge_contact(existing[c.contact_id], c) if c.contact_id in existing else c for c in kept
    ]
    store.save("contacts", merged, key=lambda c: c.contact_id)  # type: ignore[attr-defined]
    return {
        "imported": len(merged),
        "skipped": len(parsed) - len(kept),
        "with_email": sum(c.email is not None for c in merged),
    }


def press(days: int = 120, today: date | None = None) -> dict[str, object]:
    """Search press for openings, extract facts, save signals/venues/evidence, merge, rescore."""
    if not os.environ.get("EXA_API_KEY"):  # fail fast, before touching the store or the network
        raise SystemExit("EXA_API_KEY is not set; the press command needs it")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set; the press command needs it")
    cfg = load_config()
    today = today or date.today()
    store = DocStore()
    venues = store.load("venues", Venue)
    groups = store.load("groups", Group)
    exa_budget = CallBudget("exa", cfg.budgets["exa"])
    exa = ExaClient.from_env(exa_budget)
    alumni = frozenset(cfg.alumni_employers)
    signals: dict[str, Signal] = {}
    new_venues: dict[str, Venue] = {}
    evidence: list[GroupEvidence] = []
    seen: set[str] = set()
    stopped = ""
    refused = 0
    try:
        for query in PRESS_QUERIES:
            results = exa.search(query, start_published_date=today - timedelta(days=days))
            for res in results:
                if res.url in seen or not res.text:
                    continue
                seen.add(res.url)
                try:
                    facts = extract_press(res.text, res.url)
                except LLMRefusal:
                    refused += 1
                    continue
                sigs, created, ev = press_to_records(
                    facts,
                    res.url,
                    res.published_date,
                    [*venues, *new_venues.values()],
                    groups,
                    alumni,
                )
                signals.update({s.signal_id: s for s in sigs})
                new_venues.update({v.venue_id: v for v in created})
                evidence.extend(ev)
    except BudgetExceeded as exc:  # keep what was found; report the stop, never hide it
        stopped = str(exc)
    finally:  # any other error (Exa 5xx, Claude APIError) still keeps the paid extractions
        store.save("signals", list(signals.values()), key=lambda s: s.signal_id)  # type: ignore[attr-defined]
        store.save("group_evidence", evidence, key=_evidence_key)  # type: ignore[arg-type]
        _regroup(store, cfg, [*venues, *new_venues.values()], store.load("licenses", LicenseRecord))
    scored = score()
    return {
        "articles": len(seen),
        "refused": refused,
        "signals": len(signals),
        "new_venues": len(new_venues),
        "evidence": len(evidence),
        "exa_calls": exa_budget.used,
        "stopped": stopped,
        "scored_groups": scored["scored_groups"],
    }


CA_LOGGED_IN_REFUSAL = (
    "Logged-in Culinary Agents mode is off. The Culinary Agents user agreement (§7) bans robots "
    "and scrapers for any purpose without written permission and limits accounts to personal "
    "use; running this risks a banned account or a legal letter, a risk only the operator can "
    "accept. To run it: set culinary_agents.enabled and culinary_agents.authenticated to true "
    "in your local hospitality config and put a fresh session cookie in the "
    "CULINARY_AGENTS_COOKIE environment variable (never in a file you commit or in chat)."
)


def culinary_agents(
    fetch: Fetch | None = None,
    today: date | None = None,
    sleep: Callable[[float], None] = time.sleep,
    *,
    session_fetch: SessionFetch | None = None,
    backfill: bool = False,
    max_pages: int | None = None,
    articles: bool = False,
) -> dict[str, object]:
    """Culinary Agents hiring / opening-soon signals and group evidence; merge groups, rescore.

    Public mode reads page 1 of each search. Logged-in mode (`culinary_agents.authenticated`,
    or `--backfill` / `--max-pages`) walks the paginated XHR search with the operator's session.
    `--articles` reads the public /resources articles as opening news (no login).
    """
    cfg = load_config()
    if not cfg.culinary_agents.enabled:  # fail fast, before touching the store or the network
        raise SystemExit(
            "The Culinary Agents source is disabled. Its user agreement appears to restrict "
            "automated data collection: review https://culinaryagents.com/agreement, then set "
            "culinary_agents.enabled: true in the hospitality config to run it."
        )
    if articles:
        return _culinary_agents_articles(cfg, fetch or PoliteFetcher(), today, sleep)
    if cfg.culinary_agents.authenticated or backfill or max_pages is not None:
        cookie = os.environ.get(COOKIE_ENV, "").strip()
        if not cfg.culinary_agents.authenticated or not cookie:
            raise SystemExit(CA_LOGGED_IN_REFUSAL)
        return _culinary_agents_logged_in(
            cfg,
            session_fetch or PoliteFetcher(cookie=cookie).page,
            today,
            sleep,
            backfill,
            max_pages,
            cookie,
        )
    today = today or date.today()
    store = DocStore()
    venues = store.load("venues", Venue)
    groups = store.load("groups", Group)
    budget = CallBudget("culinary_agents", cfg.budgets.get("culinary_agents", 40))
    jobs, companies = fetch_nyc(cfg.culinary_agents, budget, fetch or PoliteFetcher(), today, sleep)
    board = job_board_venues(companies, venues)  # unmatched opening-soon companies (added)
    venues = [*venues, *board.venues]
    signals, evidence = to_signals(jobs, companies, venues, groups, today, cfg.culinary_agents)
    store.save("signals", signals, key=lambda s: s.signal_id)  # type: ignore[attr-defined]
    store.save("group_evidence", evidence, key=_evidence_key)  # type: ignore[arg-type]
    _regroup(store, cfg, venues, store.load("licenses", LicenseRecord))
    scored = score()
    spent = budget.used >= budget.limit
    return {
        "pages": budget.used,
        "jobs": len(jobs),
        "companies": len(companies),
        "job_board_venues": len(board.venues),
        "job_board_out_of_area": len(board.out_of_area),
        "signals": len(signals),
        "evidence": len(evidence),
        "stopped": f"culinary_agents page budget spent ({budget.limit}); results may be partial"
        if spent
        else "",
        "scored_groups": scored["scored_groups"],
    }


def _culinary_agents_articles(
    cfg: HospitalityConfig, fetch: Fetch, today: date | None, sleep: Callable[[float], None]
) -> dict[str, object]:
    """Public /resources articles through the press extractor as `press_opening` signals.

    Without ANTHROPIC_API_KEY only the index is read and the article URLs are listed.
    """
    today = today or date.today()
    budget = CallBudget("culinary_agents", cfg.budgets.get("culinary_agents", 40))
    pace = Pacer(cfg.culinary_agents.delay_seconds, sleep)
    urls: list[str] = []
    stopped = ""
    try:
        urls = article_urls(cfg.culinary_agents, budget, fetch, pace)
    except BudgetExceeded as exc:
        stopped = str(exc)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {
            "articles": len(urls),
            "extracted": 0,
            "urls": urls,
            "note": "ANTHROPIC_API_KEY is not set: listing article URLs only",
            "stopped": stopped,
        }
    store = DocStore()
    venues = store.load("venues", Venue)
    groups = store.load("groups", Group)
    signals: dict[str, Signal] = {}
    new_venues: dict[str, Venue] = {}
    evidence: list[GroupEvidence] = []
    extracted = refused = 0
    try:
        for url in urls:
            html = read_page(url, budget, fetch, pace)
            if not html:
                continue
            try:
                sigs, created, ev = article_signals(
                    url,
                    article_text(html),
                    extract_press,
                    [*venues, *new_venues.values()],
                    groups,
                    today,
                )
            except LLMRefusal:
                refused += 1
                continue
            extracted += 1
            signals.update({s.signal_id: s for s in sigs})
            new_venues.update({v.venue_id: v for v in created})
            evidence.extend(ev)
    except BudgetExceeded as exc:
        stopped = str(exc)
    finally:  # keep the paid extractions whatever stopped the loop
        store.save("signals", list(signals.values()), key=lambda s: s.signal_id)  # type: ignore[attr-defined]
        store.save("group_evidence", evidence, key=_evidence_key)  # type: ignore[arg-type]
        _regroup(store, cfg, [*venues, *new_venues.values()], store.load("licenses", LicenseRecord))
    scored = score()
    return {
        "articles": len(urls),
        "extracted": extracted,
        "refused": refused,
        "signals": len(signals),
        "new_venues": len(new_venues),
        "stopped": stopped,
        "scored_groups": scored["scored_groups"],
    }


STOPPED_PAGE = "culinary_agents_stopped_page.txt"


def _save_stopped_page(reason: str, url: str, body: str, cookie: str) -> str:
    """Save the body of the page a logged-in walk stopped on, cookie redacted, under OUT_DIR
    (gitignored) for inspection; "" when the walk did not stop on a page. Overwritten per stop.
    """
    if not body:
        return ""
    parts = urlsplit(url)
    target = f"{parts.path}?{parts.query}" if parts.query else parts.path
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / STOPPED_PAGE
    path.write_text(
        redact(f"# stopped on {target}: {reason}\n{body}", cookie or None), encoding="utf-8"
    )
    return str(path)


def _culinary_agents_logged_in(
    cfg: HospitalityConfig,
    fetch: SessionFetch,
    today: date | None,
    sleep: Callable[[float], None],
    backfill: bool,
    max_pages: int | None,
    cookie: str = "",
) -> dict[str, object]:
    """Backfill once (`--backfill`), then a daily delta that stops at already-seen items.

    Seen items (`ca_seen`), jobs (`ca_jobs`) and companies (`ca_companies`) are stored so the
    next run skips what it knows, `first_seen` dates signals and hiring bursts span runs.
    """
    today = today or date.today()
    store = DocStore()
    venues = store.load("venues", Venue)
    groups = store.load("groups", Group)
    name = "culinary_agents_backfill" if backfill else "culinary_agents"
    limit = cfg.budgets.get(name, 150 if backfill else 40)
    if max_pages is not None:
        limit = min(limit, max_pages)
    budget = CallBudget(name, limit)
    seen = {s.key: s for s in store.load("ca_seen", CASeen)}
    stored_jobs = {job_key(j): j for j in store.load("ca_jobs", CAJob)}
    stored_companies = {company_key(c): c for c in store.load("ca_companies", CACompany)}
    walk = walk_nyc(
        cfg.culinary_agents,
        budget,
        fetch,
        seen,
        today,
        backfill=backfill,
        sleep=sleep,
        known_companies=stored_companies,
    )
    store.save("ca_seen", list(walk.seen), key=lambda s: s.key)  # type: ignore[attr-defined]
    store.save("ca_jobs", list(walk.jobs), key=job_key)  # type: ignore[arg-type]
    store.save("ca_companies", list(walk.companies), key=company_key)  # type: ignore[arg-type]
    all_jobs = list({**stored_jobs, **{job_key(j): j for j in walk.jobs}}.values())
    all_companies = list(
        {**stored_companies, **{company_key(c): c for c in walk.companies}}.values()
    )
    first_seen = {**{k: s.first_seen for k, s in seen.items()}}
    first_seen |= {s.key: s.first_seen for s in walk.seen}
    # Job-board venues are derived from every stored company, so they are rebuilt each run:
    # one the rules now reject is deleted, not kept.
    base = [v for v in venues if not is_job_board_venue(v.venue_id)]
    board = job_board_venues(all_companies, base)  # unmatched opening-soon companies
    venues = [*base, *board.venues]
    signals, evidence = to_signals(
        all_jobs, all_companies, venues, groups, today, cfg.culinary_agents, first_seen
    )
    # Recomputed in full from every stored job and company, so this run's signals and job-board
    # evidence replace the earlier ones: a signal whose type or venue changed never lingers.
    kept = [s for s in store.load("signals", Signal) if s.source != CA_SOURCE]
    store.replace("signals", [*kept, *signals], key=lambda s: s.signal_id)  # type: ignore[attr-defined]
    other = [e for e in store.load("group_evidence", GroupEvidence) if e.resolution != "job_board"]
    store.replace("group_evidence", [*other, *evidence], key=_evidence_key)  # type: ignore[arg-type]
    _regroup(store, cfg, venues, store.load("licenses", LicenseRecord))
    scored = score()
    stopped = walk.stopped
    if max_pages is not None and "budget exhausted" in stopped:
        stopped = f"page cap reached (--max-pages {max_pages})"
    if walk.auth_failure:
        stopped = f"{stopped}; {SESSION_EXPIRED}"
    stopped_page = _save_stopped_page(walk.stopped, walk.stopped_url, walk.stopped_body, cookie)
    return {
        "mode": "backfill" if backfill else "daily",
        "budget": limit,
        "pages": walk.pages,
        "new_jobs": walk.new_jobs,
        "new_opening_soon_companies": walk.new_companies,
        "private_listings_skipped": walk.private_skipped,
        "early_exit": ", ".join(walk.early_exit),
        "stopped": stopped,
        "stopped_page": stopped_page,
        "job_board_venues": len(board.venues),
        "job_board_out_of_area": len(board.out_of_area),
        "signals": len(signals),
        "evidence": len(evidence),
        "scored_groups": scored["scored_groups"],
    }


def lookalikes(now: datetime | None = None) -> dict[str, object]:
    """Find venues similar to customer sites via Exa, save `lookalike` signals, rescore."""
    if not os.environ.get("EXA_API_KEY"):  # fail fast, before touching the store or the network
        raise SystemExit("EXA_API_KEY is not set; the lookalikes command needs it")
    cfg = load_config()
    now = now or datetime.now(UTC)
    store = DocStore()
    venues = store.load("venues", Venue)
    groups = store.load("groups", Group)
    seeds = customer_evidence(
        SEED_PATH,
        venues,
        store.load("stack_observations", StackObservation),
        store.load("customer_labels", CustomerLabel),
    )
    exa_budget = CallBudget("exa", cfg.budgets["exa"])
    exa = ExaClient.from_env(exa_budget)
    signals = lookalike_signals(exa, seeds, venues, now, groups=groups)
    store.save("signals", signals, key=lambda s: s.signal_id)  # type: ignore[attr-defined]
    scored = score()
    return {
        "seeds": sum(seed_url(s) is not None for s in seeds),
        "signals": len(signals),
        "exa_calls": exa_budget.used,
        "scored_groups": scored["scored_groups"],
    }


def recall(
    weeks: int = 12,
    today: date | None = None,
    store: DocStore | None = None,
    cfg: HospitalityConfig | None = None,
) -> RecallReport:
    """Replay license signals for venues first inspected in the last `weeks`; report recall.

    Each opening is replayed as of the day before its first inspection (no inspection yet, no
    match-miss filter), so only signals that could have existed beforehand are counted. As-of
    replay is `historical`: now-inactive licenses count at their issue date, as they did then.
    The live lookback and stale caps apply as in `score`, so the replay never counts a signal
    live scoring would not emit. Recall is reported with its coverage denominator (every first
    inspection in the window), because the truth set is license-matched openings only.
    """
    cfg = cfg or load_config()
    today = today or date.today()
    start = today - timedelta(weeks=weeks)
    store = store or DocStore()
    licenses = store.load("licenses", LicenseRecord)
    venues = store.load("venues", Venue)
    inspected = first_inspections_in(venues, start, today)
    openings = ground_truth_openings(venues, start, today, cfg, licenses)
    replayed: list[Signal] = []
    for v in openings:
        as_of = v.first_inspection_date - timedelta(days=1)  # type: ignore[operator]
        pre = v.model_copy(update={"first_inspection_date": None})
        replayed.extend(_replay_signals([pre], licenses, {}, as_of, cfg))
    return recall_audit(
        openings,
        replayed,
        start,
        today,
        first_inspections=len(inspected),
        license_matched=sum(bool(v.license_ids) for v in inspected),
        lead_cap_days=cfg.recall_lead_cap_days,
    )


def _replay_signals(
    venues: Sequence[Venue],
    licenses: Sequence[LicenseRecord],
    first_seen: dict[str, date],
    as_of: date,
    cfg: HospitalityConfig,
    **kw: object,
) -> list[Signal]:
    """As-of license signals with the same lookback and stale caps as live `score`."""
    return license_signals(
        venues,
        licenses,
        first_seen,
        as_of,
        historical=True,
        issued_lookback_days=cfg.issued_lookback_days,
        not_yet_inspected_max_age_days=cfg.not_yet_inspected_max_age_days,
        **kw,  # type: ignore[arg-type]
    )


# Customer label name -> the new venue the research ties to it (docs/research/magic/02).
CASE_HINTS: dict[str, str] = {
    "The Noortwyck": "Oriana",
    "Dinex Group": "La Tête d'Or",
    "Momofuku": "Bar Kabawa",
    "Rezdôra": "Massara",
}


def backtest(store: DocStore | None = None) -> BacktestResult:
    """Case replay on customers with a known new venue, plus fit AUC. Indicative only.

    Each case is anchored on the venue's own seed date when it has one, else on the customer's
    date for a venue that already existed by then (`case_anchor`); other cases are reported as
    not evaluable, never as misses. The replay is as of the anchor: an inspection after the
    anchor is forgotten (one before it is kept, so a later renewal is no opening signal), and
    the live lookback and stale caps apply (`historical=True`).
    """
    cfg = load_config()
    store = store or DocStore()
    venues = store.load("venues", Venue)
    groups = store.load("groups", Group)
    licenses = store.load("licenses", LicenseRecord)
    customers = current_customers(store, SEED_PATH, venues=venues, groups=groups)
    pending_seen = first_seen_pending(store)
    stored = store.load("signals", Signal)

    def signals_for(venue: Venue, anchor: date) -> list[Signal]:
        inspected = venue.first_inspection_date
        pre = venue.model_copy(
            update={
                "first_inspection_date": inspected if inspected and inspected <= anchor else None
            }
        )
        return [
            *_replay_signals([pre], licenses, pending_seen, anchor, cfg),
            *(s for s in stored if s.entity_id == venue.venue_id),
        ]

    cases = case_replay(
        customers,
        venues,
        signals_for,
        CASE_HINTS,
        seeds=load_seed_labels(SEED_PATH),
        licenses=licenses,
    )
    accounts = with_customer_flags(store.load("scores", ScoredAccount), customers)
    return BacktestResult(
        cases=tuple(cases),
        undated=sum(1 for c in customers.values() if c.first_public_date is None),
        fit_auc=fit_auc(accounts),
        fit_distinct=len({a.fit for a in accounts}),
        n_customers=sum(a.is_customer for a in accounts),
        n_others=sum(not a.is_customer for a in accounts),
    )


def _case_line(c: CaseReplay) -> str:
    venue = c.new_venue_id or "venue not found"
    if c.status == "not_evaluable":
        return f"  {c.customer[:28]:<28} {venue}: not evaluable ({c.reason})"
    lead = f"{c.lead_days}d" if c.lead_days is not None else "no prior signal (miss)"
    return (
        f"  {c.customer[:28]:<28} anchor<={c.anchor_date} ({c.anchor_basis}) {venue}: "
        f"lead={lead} [{', '.join(c.signal_types)}]"
    )


def _print_backtest(out: BacktestResult) -> None:
    replayed = sum(c.status == "replayed" for c in out.cases)
    print("INDICATIVE ONLY: tiny samples, not a lift claim.")
    print(
        f"Case replay (n={len(out.cases)} customers with a known new venue; {replayed} replayed, "
        f"{len(out.cases) - replayed} not evaluable):"
    )
    for c in out.cases:
        print(_case_line(c))
    print(f"Customers with no public date: {out.undated}")
    shown = "undefined" if math.isnan(out.fit_auc) else f"{out.fit_auc:.3f}"
    print(
        f"Fit AUC: {shown} (customers n={out.n_customers} vs others n={out.n_others}); "
        "static fit only, no timing."
    )
    if out.fit_distinct <= 1:
        print("Fit is degenerate: every scored group has the same fit, so AUC is 0.5 by tie.")


P0_STEPS: tuple[str, ...] = (
    "ingest-sla",
    "snapshot-pending",
    "ingest-dohmh",
    "resolve",
    "window",
    "websites",
    "crawl",
    "labels",
    "score",
    "recall",
    "backtest",
)


def benchmark(cutoff_weeks: int = 8, today: date | None = None) -> BenchmarkResult:
    """Head-to-head: SignalForce ranking as of the cutoff vs plain Claude + web search.

    The SignalForce side uses only data recorded on or before the cutoff (licenses received or
    issued, signals observed, inspections and the DOHMH records themselves, window estimates
    all as of `cutoff`); the truth set is venues first inspected after the cutoff. Both sides
    are scored on at most k distinct venues (`compare`). Residual biases (grouping and matching
    built with today's data, Claude's hindsight) are stated in `FAIRNESS_NOTE`. Nothing here
    overwrites the live scores.
    """
    cfg = load_config()
    today = today or date.today()
    cutoff = today - timedelta(weeks=cutoff_weeks)
    store = DocStore()
    all_venues = store.load("venues", Venue)
    groups = {g.group_id: g for g in store.load("groups", Group)}
    all_licenses = store.load("licenses", LicenseRecord)
    links = store.load("links", EntityLink)
    truth = ground_truth_openings(all_venues, cutoff + timedelta(days=1), today, cfg, all_licenses)

    # As-of inputs: forget everything recorded after the cutoff. A venue first inspected later
    # had no DOHMH record yet, so it loses its camis as well as its inspection: as of the cutoff
    # it was a license-only site, and the match-miss rule treats it as one (I7a).
    venues = [
        v.model_copy(update={"first_inspection_date": None, "camis": None})
        if v.first_inspection_date is not None and v.first_inspection_date > cutoff
        else v
        for v in all_venues
    ]
    later = {v.camis for v in all_venues if v.camis} - {v.camis for v in venues if v.camis}
    links = [link for link in links if link.right_id not in later]
    licenses = [
        lic
        for lic in all_licenses
        if not (lic.source == "sla_pending" and (lic.received_date or cutoff) > cutoff)
        and not (lic.source != "sla_pending" and (lic.original_issue_date or cutoff) > cutoff)
    ]
    first_seen = {k: d for k, d in first_seen_pending(store).items() if d <= cutoff}
    now = datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=UTC)
    cap = cfg.window_unmatched_censor_max_age_days
    curves = build_curves(
        opening_durations(venues, licenses, cutoff, links, max_unmatched_age_days=cap)
    )
    estimates = {e.venue_id: e for e in estimate_all(venues, licenses, curves, cfg, cutoff, links)}
    observations = [
        o for o in store.load("stack_observations", StackObservation) if o.observed_at <= now
    ]
    lic_signals = _replay_signals(  # historical: a now-lapsed license was live at the cutoff
        venues,
        licenses,
        first_seen,
        cutoff,
        cfg,
        linked=linked_to_inspected(venues, links),
        max_unmatched_age_days=cap,
    )
    stack = [s for s in store.load("signals", Signal) if s.observed_at <= now]
    customer_ids = current_customers(
        store, SEED_PATH, venues=venues, groups=list(groups.values()), observations=observations
    )
    accounts = [
        a.model_copy(update={"is_customer": a.group_id in customer_ids})
        for a in _score_accounts(
            store,
            cfg,
            now,
            venues=venues,
            groups=groups,
            licenses=licenses,
            estimates=estimates,
            observations=observations,
            signals=[*lic_signals, *stack],
        )
    ]
    ranked = rank_prospects(accounts)
    venue_ids = {v.venue_id for v in venues}
    venue_of_signal = {
        s.signal_id: s.entity_id for s in [*lic_signals, *stack] if s.entity_id in venue_ids
    }
    bench = cfg.benchmark
    runs = run_baseline(Anthropic(), cutoff, runs=bench.runs, max_searches=bench.max_searches)
    result = compare(ranked, venue_of_signal, runs, truth, all_venues, k=bench.k)
    store.clear("benchmark")
    store.save("benchmark", [result], key=lambda r: f"cutoff:{cutoff.isoformat()}")
    return result


def _print_benchmark(r: BenchmarkResult) -> None:
    print(f"truth openings after cutoff: {r.truth_total}  (k={r.k})")
    print(f"SignalForce: hits={r.sf_hits} precision@k={r.sf_precision_at_k:.3f}")
    for i, hit in enumerate(r.claude_hits):
        print(
            f"Claude run {i}: hits={hit} precision={r.claude_precision_at_k[i]:.3f} "
            f"duplicates={r.claude_duplicates[i]} non-venues={r.claude_unmatched[i]}"
        )
    print(f"Claude run-to-run Jaccard: {r.claude_run_jaccard:.3f}")
    for note in r.notes:
        print(f"note: {note}")


def report() -> Path:
    """Assemble the demo report from the store; written only under `OUT_DIR` (gitignored)."""
    return build_report(DocStore(), load_config(), OUT_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.hospitality.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest-sla", help="Ingest NY SLA licenses for NYC via Socrata")
    sub.add_parser("ingest-dohmh", help="Ingest DOHMH first-inspection venues via Socrata")
    sub.add_parser("snapshot-pending", help="Record today's SLA pending applications")
    sub.add_parser("resolve", help="Match licenses to inspections; build venues and groups")
    sub.add_parser("window", help="Fit opening-timing curves; estimate venue opening windows")
    p_web = sub.add_parser(
        "websites", help="Find and verify websites for prioritized venues (Exa / Firecrawl search)"
    )
    p_web.add_argument("--limit", type=int, default=400, help="Max venues to look up")
    p_web.add_argument(
        "--provider", choices=("search", "places"), help="Override websites.provider in the config"
    )
    p_wimp = sub.add_parser("websites-import", help="Import hand-filled websites from a CSV")
    p_wimp.add_argument("csv", type=Path, help="CSV with venue_id (or camis) and website columns")
    p_wimp.add_argument(
        "--overwrite", action="store_true", help="Replace sites found by search or Places"
    )
    sub.add_parser(
        "websites-export-misses", help="Write venues still lacking a website to out/magic/ as CSV"
    )
    sub.add_parser("crawl", help="Crawl venue websites; detect stacks and emit stack signals")
    sub.add_parser("labels", help="Label customer groups (seed list + Loyalist embeds)")
    p_registry = sub.add_parser(
        "registry", help="Who is behind the top prospects' licence companies (NY registry)"
    )
    p_registry.add_argument("--top", type=int, default=300)
    p_brief = sub.add_parser(
        "brief", help="Presentable brief of the top hospitality accounts (out/magic/demo_brief.md)"
    )
    p_brief.add_argument("--top", type=int, default=25)
    sub.add_parser("score", help="Score groups (noisy-OR) and print the top 25 prospects")
    p_recall = sub.add_parser("recall", help="Recall of license signals vs DOHMH first inspections")
    p_recall.add_argument("--weeks", type=int, default=12, help="Look-back window in weeks")
    p_press = sub.add_parser("press", help="Press discovery: openings, people, group evidence")
    p_press.add_argument(
        "--days", type=int, default=120, help="Search articles from the last N days"
    )
    p_ca = sub.add_parser(
        "culinary-agents",
        help="Culinary Agents hiring / opening-soon signals (disabled unless configured)",
    )
    p_ca.add_argument(
        "--backfill",
        action="store_true",
        help="Logged-in: walk every page once (budgets.culinary_agents_backfill)",
    )
    p_ca.add_argument(
        "--articles",
        action="store_true",
        help="Public /resources articles as opening news (lists URLs without ANTHROPIC_API_KEY)",
    )
    p_ca.add_argument(
        "--max-pages", type=int, help="Logged-in: fetch at most this many pages in this run"
    )
    p_contacts = sub.add_parser("contacts", help="Contacts for top prospects (team page, Hunter)")
    p_contacts.add_argument("--top", type=int, default=25, help="Top N ranked prospects")
    sub.add_parser("events-extract", help="Lineup appearances for registry events (public pages)")
    sub.add_parser("events-rank", help="Rank events by expected meetings per dollar; meeting lists")
    p_clay_push = sub.add_parser("clay-push", help="Push top prospects to Clay (webhook)")
    p_clay_push.add_argument("--top", type=int, default=25, help="Top N ranked prospects")
    p_clay_import = sub.add_parser("clay-import", help="Import Clay's enriched CSV as contacts")
    p_clay_import.add_argument("csv", type=Path, help="Clay CSV export")
    p_draft = sub.add_parser("draft", help="Evidence-linked drafts for top prospects (no sending)")
    p_draft.add_argument("--top", type=int, default=10, help="Top N ranked prospects")
    sub.add_parser("lookalikes", help="Exa lookalikes of customer sites, matched to known venues")
    sub.add_parser("backtest", help="Case replay on known customers + fit AUC (indicative)")
    sub.add_parser("report", help="Assemble the demo report from the store (out/magic/)")
    sub.add_parser("run-p0", help="Run the whole P0 chain, ingest through backtest")
    p_bench = sub.add_parser(
        "benchmark", help="Head-to-head vs plain Claude + web search (spends real money)"
    )
    p_bench.add_argument("--cutoff-weeks", type=int, default=8, help="Cutoff = today minus weeks")
    p_bench.add_argument("--yes", action="store_true", help="Confirm the Claude spend")
    args = parser.parse_args(argv)
    if args.command == "ingest-sla":
        for source, n in ingest_sla().items():
            print(f"{source}: {n}")
    elif args.command == "ingest-dohmh":
        for name, n in ingest_dohmh().items():
            print(f"{name}: {n}")
    elif args.command == "snapshot-pending":
        print(f"sla_pending snapshot rows: {snapshot_pending()}")
    elif args.command == "resolve":
        for name, n in resolve().items():
            print(f"{name}: {n}")
    elif args.command == "window":
        out = window()
        print(
            f"durations: {out['durations']} ({out['observed']} observed, {out['censored']} censored)"
        )
        print(f"estimates: {out['estimates']}")
        for k, n, q1, med, q3 in out["strata"]:  # type: ignore[attr-defined]
            print(f"{k}: n={n} median={med}d IQR={q1}-{q3}d")
    elif args.command == "websites":
        for name, n in websites(args.limit, provider=args.provider).items():
            print(f"{name}: {n}")
    elif args.command == "websites-import":
        for name, n in websites_import(args.csv, overwrite=args.overwrite).items():
            print(f"{name}: {n}")
    elif args.command == "websites-export-misses":
        print(f"misses written to: {websites_export_misses()}")
    elif args.command == "crawl":
        out = crawl()
        for name, value in out.items():
            print(f"{name}: {value}")
    elif args.command == "brief":
        from scripts.hospitality.brief import build_brief

        path = build_brief(DocStore(), load_config(), OUT_DIR, seed_path=SEED_PATH, top=args.top)
        print(f"brief: {path}")
    elif args.command == "registry":
        for name, n in registry(args.top).items():
            print(f"{name}: {n}")
    elif args.command == "labels":
        for name, n in labels().items():
            print(f"{name}: {n}")
    elif args.command == "score":
        out = score()
        for name in ("license_signals", "scored_groups", "customers", "disqualified", "prospects"):
            print(f"{name}: {out[name]}")
        for rank, (acct, name) in enumerate(out["top"], 1):  # type: ignore[arg-type,misc]
            top3 = sorted(acct.contributions, key=lambda c: -c.contribution)[:3]
            why = ", ".join(f"{c.signal_type}={c.contribution:.2f}" for c in top3)
            print(
                f"{rank:>2}. {name[:40]:<40} priority={acct.priority:.3f} "
                f"p={acct.p_window:.2f} fit={acct.fit:.2f} [{why}]"
            )
    elif args.command == "recall":
        r = recall(args.weeks)
        print(f"window: {r.start} to {r.end}")
        print(
            f"first inspections in window: {r.first_inspections} (license-matched {r.license_matched})"
        )
        print(f"license-matched new openings (truth set): {r.total}")
        print(f"caught before first inspection: {r.caught} of {r.total} ({r.recall:.3f})")
        print(
            f"coverage of all first inspections: {r.caught} of {r.first_inspections} ({r.coverage:.3f})"
        )
        print(
            f"median lead days: {r.median_lead_days_within_cap} (leads <= {r.lead_cap_days} d; "
            f"{r.leads_over_cap} longer excluded; all leads: {r.median_lead_days})"
        )
        print(f"sample misses: {list(r.misses[:10])}")
    elif args.command == "press":
        for name, value in press(args.days).items():
            print(f"{name}: {value}")
    elif args.command == "culinary-agents":
        for name, value in culinary_agents(
            backfill=args.backfill, max_pages=args.max_pages
        ).items():
            print(f"{name}: {value}")
    elif args.command == "contacts":
        for name, value in contacts(args.top).items():
            print(f"{name}: {value}")
    elif args.command == "events-extract":
        for name, value in events_extract().items():
            print(f"{name}: {value}")
    elif args.command == "events-rank":
        for name, value in events_rank().items():
            print(f"{name}: {value}")
    elif args.command == "clay-push":
        for name, value in clay_push(args.top).items():
            print(f"{name}: {value}")
    elif args.command == "clay-import":
        for name, value in clay_import(args.csv).items():
            print(f"{name}: {value}")
    elif args.command == "draft":
        for name, value in draft_command(args.top).items():
            print(f"{name}: {value}")
    elif args.command == "lookalikes":
        for name, value in lookalikes().items():
            print(f"{name}: {value}")
    elif args.command == "backtest":
        _print_backtest(backtest())
    elif args.command == "report":
        print(f"report: {report()}")
    elif args.command == "run-p0":
        missing = [
            var for var in p0_required_keys(load_config().websites) if not os.environ.get(var)
        ]
        if missing:  # fail fast, before ingest or resolve touch the store (M6)
            raise SystemExit(f"run-p0 needs {', '.join(missing)}; set it before running the chain")
        for step in P0_STEPS:
            print(f"== {step} ==")
            if main([step]):
                raise SystemExit(f"run-p0 stopped: {step} failed")
    elif args.command == "benchmark":
        if not os.environ.get("ANTHROPIC_API_KEY"):  # fail fast, before any store or network use
            raise SystemExit("ANTHROPIC_API_KEY is not set; the benchmark command needs it")
        bench_cfg = load_config()
        bench = bench_cfg.benchmark
        searches = bench.runs * bench.max_searches
        print(
            f"Maximum spend: {bench.runs} runs x {bench.max_searches} searches = "
            f"{searches} web searches (~${searches * bench.web_search_usd_each:.2f} at list "
            f"price, re-check it) plus tokens (up to 16000 output tokens per call, "
            f"{bench_cfg.budgets['claude_calls']} calls hard cap)."
        )
        if not args.yes:
            raise SystemExit("Re-run with --yes to spend this on the Claude API")
        _print_benchmark(benchmark(args.cutoff_weeks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
