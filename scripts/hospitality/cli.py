"""Command-line entry point: python -m scripts.hospitality.cli <command>."""

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import date

from scripts.hospitality.config import load_config
from scripts.hospitality.models import (
    InspectionVenue,
    LicenseRecord,
    LicenseSource,
)
from scripts.hospitality.resolve.groups import form_groups
from scripts.hospitality.resolve.match import match_licenses
from scripts.hospitality.resolve.venues import build_venues
from scripts.hospitality.sources.dohmh import (
    fetch_first_inspections,
    fetch_never_inspected,
    merge_inspection_venues,
)
from scripts.hospitality.sources.sla import fetch_licenses
from scripts.hospitality.sources.snapshot import take_snapshot
from scripts.hospitality.sources.socrata import SocrataClient
from scripts.hospitality.store import DocStore

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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.hospitality.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest-sla", help="Ingest NY SLA licenses for NYC via Socrata")
    sub.add_parser("ingest-dohmh", help="Ingest DOHMH first-inspection venues via Socrata")
    sub.add_parser("snapshot-pending", help="Record today's SLA pending applications")
    sub.add_parser("resolve", help="Match licenses to inspections; build venues and groups")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
