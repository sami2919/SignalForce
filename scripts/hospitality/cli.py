"""Command-line entry point: python -m scripts.hospitality.cli <command>."""

import argparse
import asyncio
import os
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from scripts.firecrawl_client import FirecrawlClient
from scripts.hospitality.budget import CallBudget
from scripts.hospitality.config import load_config
from scripts.hospitality.labels import (
    customer_groups,
    labels_from_embeds,
    load_seed_labels,
)
from scripts.hospitality.measure.recall import ground_truth_openings, recall_audit
from scripts.hospitality.models import (
    CurveRecord,
    CustomerLabel,
    EntityLink,
    Group,
    InspectionVenue,
    LicenseRecord,
    LicenseSource,
    ScoredAccount,
    Signal,
    StackObservation,
    Venue,
    WindowEstimate,
)
from scripts.hospitality.resolve.groups import form_groups
from scripts.hospitality.resolve.match import match_licenses
from scripts.hospitality.resolve.venues import build_venues
from scripts.hospitality.scoring import (
    contract_operator_reason,
    operator_names,
    rank_prospects,
    score_group,
)
from scripts.hospitality.signals import license_signals
from scripts.hospitality.sources.dohmh import (
    fetch_first_inspections,
    fetch_never_inspected,
    merge_inspection_venues,
)
from scripts.hospitality.sources.sla import fetch_licenses
from scripts.hospitality.sources.snapshot import first_seen_pending, take_snapshot
from scripts.hospitality.sources.socrata import SocrataClient
from scripts.hospitality.stack.crawl import crawl_stacks
from scripts.hospitality.stack.signals import (
    disqualified_venues,
    loyalist_venues,
    stack_signals,
)
from scripts.hospitality.stack.websites import PlacesClient, attach_websites
from scripts.hospitality.store import DocStore
from scripts.hospitality.window.estimate import estimate_all
from scripts.hospitality.window.survival import (
    build_curves,
    linked_to_inspected,
    opening_durations,
    quantile_time,
)

SEED_PATH = Path(__file__).resolve().parents[2] / "examples/magic-loyalist/customers_seed.yaml"
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


def resolve() -> dict[str, int]:
    """Match licenses to inspections, build venues, form groups; save venues/groups/links."""
    cfg = load_config()
    store = DocStore()
    licenses = store.load("licenses", LicenseRecord)
    inspections = store.load("inspections", InspectionVenue)
    match = match_licenses(licenses, inspections, cfg)
    venues, groups = form_groups(build_venues(licenses, inspections, match), licenses)
    for kind in ("venues", "groups", "links"):
        store.clear(kind)  # resolve is a full recompute; drop rows from earlier runs
    store.save("venues", venues, key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    store.save("groups", groups, key=lambda g: g.group_id)  # type: ignore[attr-defined]
    store.save(
        "links",
        match.links,
        key=lambda link: f"{link.left_id}|{link.right_id}",  # type: ignore[attr-defined]
    )
    return {
        "venues": len(venues),
        "groups": len(groups),
        "multi_venue_groups": sum(len(g.venue_ids) > 1 for g in groups),
        "possibly_same_links": len(match.links),
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
    durations = opening_durations(venues, licenses, today, links, max_unmatched_age_days=cap)
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


def websites(limit: int = 400) -> dict[str, int]:
    """Look up websites via Google Places for venues with a window estimate; save venues."""
    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not key:  # fail fast, before touching the store or the network
        raise SystemExit("GOOGLE_PLACES_API_KEY is not set; the websites command needs it")
    cfg = load_config()
    store = DocStore()
    venues = store.load("venues", Venue)
    estimates = store.load("estimates", WindowEstimate)
    by_id = {v.venue_id: v for v in venues}
    # Prioritized: venues with an estimate, soonest-opening first, without a website yet.
    ranked = sorted(estimates, key=lambda e: e.estimated_open)
    # Seed customers first: they are always looked up (to label them and seed lookalikes).
    seed_groups = customer_groups(load_seed_labels(SEED_PATH), venues, store.load("groups", Group))
    customer_ids = [v.venue_id for v in venues if v.group_id in seed_groups and not v.website]
    ordered = [*customer_ids, *(e.venue_id for e in ranked)]
    priority = list(
        dict.fromkeys(vid for vid in ordered if vid in by_id and not by_id[vid].website)
    )[:limit]
    budget = CallBudget("places", min(limit, cfg.budgets["places"]))
    updated = attach_websites(venues, PlacesClient(key, budget), priority)
    changed = [u for u, v in zip(updated, venues, strict=True) if u != v]
    store.save("venues", changed, key=lambda v: v.venue_id)  # type: ignore[attr-defined]
    return {"prioritized": len(priority), "lookups": budget.used, "websites_found": len(changed)}


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
    """Label customer groups from the seed list and detected embeds; save labels; count by source."""
    store = DocStore()
    venues = store.load("venues", Venue)
    groups = store.load("groups", Group)
    observations = store.load("stack_observations", StackObservation)
    first_seen: dict[str, date] = {}
    for o in sorted(observations, key=lambda o: o.observed_at):
        if "loyalist" in o.platforms:
            first_seen.setdefault(o.venue_id, o.observed_at.date())
    embeds = labels_from_embeds(loyalist_venues(observations), venues, first_seen)
    all_labels = [*load_seed_labels(SEED_PATH), *embeds]
    customers = customer_groups(all_labels, venues, groups)
    store.clear("customer_labels")
    store.save(
        "customer_labels",
        all_labels,
        key=lambda c: f"{c.source}|{c.name}|{c.website_domain}",  # type: ignore[attr-defined]
    )
    counts = Counter(label.source for label in customers.values())
    return {"public_list": counts["public_list"], "embed": counts["embed"]}


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
    )
    store.clear("license_signals")  # recomputed in full each run, so stale ones never linger
    store.save("license_signals", lic_signals, key=lambda s: s.signal_id)  # type: ignore[attr-defined]
    signals: list[Signal] = [*lic_signals, *store.load("signals", Signal)]

    labels = store.load("customer_labels", CustomerLabel) or load_seed_labels(SEED_PATH)
    customers = customer_groups(labels, venues, list(groups.values()))
    disqualified = disqualified_venues(observations)
    licenses_by_id = {lic.record_id: lic for lic in licenses}

    # Index once; scoring 47k groups must not rescan all venues/signals per group.
    group_of = {v.venue_id: v.group_id for v in venues}
    venues_by_group: dict[str, list[Venue]] = {}
    for v in venues:
        venues_by_group.setdefault(v.group_id, []).append(v)
    signals_by_group: dict[str, list[Signal]] = {}
    for sig in signals:
        gid = group_of.get(sig.entity_id, sig.entity_id)
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
        operator = contract_operator_reason(operator_names(group, members, licenses_by_id), cfg)
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


def recall(weeks: int = 12, today: date | None = None) -> dict[str, object]:
    """Replay license signals for venues first inspected in the last `weeks`; report recall.

    Each opening is replayed as of the day before its first inspection (no inspection yet, no
    match-miss filter), so only signals that could have existed beforehand are counted.
    """
    cfg = load_config()
    today = today or date.today()
    start = today - timedelta(weeks=weeks)
    store = DocStore()
    licenses = store.load("licenses", LicenseRecord)
    openings = ground_truth_openings(store.load("venues", Venue), start, today, cfg, licenses)
    replayed: list[Signal] = []
    for v in openings:
        as_of = v.first_inspection_date - timedelta(days=1)  # type: ignore[operator]
        pre = v.model_copy(update={"first_inspection_date": None})
        replayed.extend(license_signals([pre], licenses, {}, as_of))
    report = recall_audit(openings, replayed, start, today)
    return {**report.model_dump(mode="json"), "misses_sample": list(report.misses[:10])}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.hospitality.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest-sla", help="Ingest NY SLA licenses for NYC via Socrata")
    sub.add_parser("ingest-dohmh", help="Ingest DOHMH first-inspection venues via Socrata")
    sub.add_parser("snapshot-pending", help="Record today's SLA pending applications")
    sub.add_parser("resolve", help="Match licenses to inspections; build venues and groups")
    sub.add_parser("window", help="Fit opening-timing curves; estimate venue opening windows")
    p_web = sub.add_parser("websites", help="Find websites for prioritized venues (Google Places)")
    p_web.add_argument("--limit", type=int, default=400, help="Max venues to look up")
    sub.add_parser("crawl", help="Crawl venue websites; detect stacks and emit stack signals")
    sub.add_parser("labels", help="Label customer groups (seed list + Loyalist embeds)")
    sub.add_parser("score", help="Score groups (noisy-OR) and print the top 25 prospects")
    p_recall = sub.add_parser("recall", help="Recall of license signals vs DOHMH first inspections")
    p_recall.add_argument("--weeks", type=int, default=12, help="Look-back window in weeks")
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
        for name, n in websites(args.limit).items():
            print(f"{name}: {n}")
    elif args.command == "crawl":
        out = crawl()
        for name, value in out.items():
            print(f"{name}: {value}")
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
        out = recall(args.weeks)
        print(f"window: {out['start']} to {out['end']}")
        print(f"openings: {out['total']}, caught before first inspection: {out['caught']}")
        print(f"recall: {out['recall']:.3f}")
        print(f"median lead days: {out['median_lead_days']}")
        print(f"sample misses: {out['misses_sample']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
