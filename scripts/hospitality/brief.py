"""A presentable account brief for the top hospitality groups: built on the same store as the
demo report, written for a seller rather than an engineer.

Per account: a short summary, each signal with a plain hypothesis of why it matters, the
Loyalist customer stories worth citing in a cold email (verbatim excerpts from Loyalist's own
customer-stories page, never invented outcomes), and the evidence as clickable links.
Existing customers and disqualified groups never appear. Written only under the out dir.
"""

import string
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from scripts.hospitality.config import HospitalityConfig
from scripts.hospitality.labels import current_customers, with_customer_flags
from scripts.hospitality.models import (
    Group,
    LicenseRecord,
    RegistryRecord,
    ScoredAccount,
    Signal,
    StackObservation,
    Venue,
    WindowEstimate,
)
from scripts.hospitality.resolve.normalize import borough_of_zip
from scripts.hospitality.resolve.operators import (
    cluster_operators,
    is_agent,
    operator_key,
    stored_counts,
)
from scripts.hospitality.scoring import _has_accolade, rank_prospects
from scripts.hospitality.sources.registry import RECORDS, normalize_company, registry_link
from scripts.hospitality.store import DocStore

STORIES = "https://www.eatloyalist.com/customer-stories/"
NAMED_RESOLUTIONS = frozenset({"job_board", "shared_domain", "press", "manual"})

# Why each signal matters, in a seller's words. Hypotheses, not facts: the priors behind them
# are research guesses until Magic's won deals calibrate them.
HYPOTHESES: dict[str, str] = {
    "license_pending": "A new venue is on the way. Its reservation, CRM and marketing tools "
    "haven't been chosen yet, so this is the cheapest moment to be in the conversation.",
    "license_issued": "The licence is through, so opening is close. Owners pick their guest "
    "tools in these months, before service starts and habits set in.",
    "not_yet_inspected": "No health inspection yet, so the venue hasn't opened. Tools are still "
    "being chosen.",
    "opening_soon": "Publicly listed as opening soon. The team is being hired now, and the guest "
    "list and CRM setup are being decided with it.",
    "hiring_burst": "Hiring many roles at once means staffing a whole venue, the clearest sign "
    "of an opening in hiring data.",
    "new_gm": "A new general manager often re-picks the guest tools and wants to know the "
    "regulars from day one.",
    "new_chef": "A new head of kitchen usually means a new or relaunched concept, which is a "
    "reason to rebuild how the restaurant knows and brings back its guests.",
    "guest_role_hire": "This hire owns reservations and the guest book. Loyalist is that "
    "person's daily tool, so they are the likeliest champion.",
    "events_role_hire": "Events and private dining run on knowing past guests and rebooking "
    "them, which is what a guest CRM is for.",
    "staffing_change": "Re-staffing an open venue. New teams are a natural moment to change how "
    "guests are tracked.",
    "stack_fragmented": "Booking, events and guest data sit in separate tools. That mess is "
    "what a single guest CRM replaces.",
    "private_events": "Sells private events. Repeat event bookers are high-value guests worth "
    "remembering and winning back.",
    "tripleseat_resy": "Runs events and reservations in separate systems, so no one sees the "
    "whole guest.",
    "platform_switch": "Changed booking platform recently, so it is already re-evaluating vendors.",
    "press_opening": "Press has announced an opening, so the venue and its owners are in "
    "launch mode.",
    "lookalike": "Looks like an existing Loyalist customer, so the fit is proven elsewhere.",
    "hotel_partnership": "Tied to a hotel, where guest data and VIP handling matter more.",
}
_LABELS: dict[str, str] = {
    "license_pending": "Liquor licence applied for",
    "license_issued": "Liquor licence issued",
    "not_yet_inspected": "Not yet inspected",
    "opening_soon": "Listed as opening soon",
    "hiring_burst": "Hiring many roles at once",
    "new_gm": "Hiring a general manager",
    "new_chef": "Hiring a head chef",
    "guest_role_hire": "Hiring a guest-facing lead",
    "events_role_hire": "Hiring for events",
    "staffing_change": "Re-staffing",
    "stack_fragmented": "Fragmented guest-tool stack",
    "private_events": "Sells private events",
    "tripleseat_resy": "Tripleseat alongside Resy",
    "platform_switch": "Switched booking platform",
    "press_opening": "Opening in the press",
    "lookalike": "Looks like a current customer",
    "hotel_partnership": "Hotel partnership",
}


def hypothesis(signal_type: str) -> str:
    return HYPOTHESES.get(
        signal_type, "A change at this operator that can reopen how it handles its guests."
    )


@dataclass(frozen=True)
class Story:
    customer: str
    situation: str
    excerpt: str


# Excerpts as published on Loyalist's customer-stories page (read 2026-11-20). No customer
# outcome numbers are published there, so none are quoted.
STORY_GLENDALE = Story(
    "Glendale Hospitality",
    "a small group of three restaurants that rolled Loyalist out to its third venue",
    "within two weeks the return on marketing outreach through Loyalist was so undeniably "
    "strong that there was no way we weren't going to enroll the third restaurant.",
)
STORY_MFG = Story(
    "Major Food Group",
    "a large multi-venue group using it across its properties",
    "The platform provides unparalleled insight into the lifeline of our guests...",
)
STORY_HIGH_STREET = Story(
    "High Street Hospitality Group",
    "a group using guest segments for private events",
    "...especially valuable for private events...",
)
STORY_MATTOS = Story(
    "Mattos Hospitality",
    "a group running guest relations and a VIP line through it",
    "...centralized our guest relations...",
)
STORY_NOORTWYCK = Story(
    "The Noortwyck",
    "a chef-driven restaurant that relies on knowing its guests",
    "Loyalist has become indispensable to what we do.",
)
STORY_HAPPY_COOKING = Story(
    "Happy Cooking Hospitality",
    "a neighbourhood restaurant group",
    "It's like having both a cheat code and a short cut simultaneously to doing better work "
    "faster.",
)


def pick_stories(signal_types: set[str], venue_count: int) -> list[Story]:
    """Up to two customer stories whose situation matches this account's."""
    picks: list[Story] = []
    if signal_types & {"private_events", "events_role_hire", "tripleseat_resy"}:
        picks.append(STORY_HIGH_STREET)
    if "guest_role_hire" in signal_types:
        picks.append(STORY_MATTOS)
    if venue_count >= 5:
        picks.append(STORY_MFG)
    elif venue_count >= 2 or signal_types & {"opening_soon", "license_pending", "hiring_burst"}:
        picks.append(STORY_GLENDALE)
    if "new_chef" in signal_types:
        picks.append(STORY_NOORTWYCK)
    if not picks:
        picks.append(STORY_HAPPY_COOKING)
    return list(dict.fromkeys(picks))[:2]


_LICENCE_LINKS = {
    "sla_active": "https://data.ny.gov/resource/9s3h-dpkz.json?licensepermitid=",
    "sla_pending": "https://data.ny.gov/resource/f8i8-k2gm.json?application_id=",
    "sla_inactive": "https://data.ny.gov/resource/6dg3-2z7i.json?license_permit_id=",
}


def evidence_link(ref: str) -> str:
    """A clickable link for a stored evidence reference (licence ids become state records)."""
    source, _, raw = ref.partition(":")
    if source in _LICENCE_LINKS and raw:
        return _LICENCE_LINKS[source] + raw
    return ref


@dataclass(frozen=True)
class _Stub:
    group_id: str


@dataclass
class _Account:
    label: str
    kind: str
    group_ids: list[str]
    priority: float
    operator: str = ""
    venues: list[Venue] = field(default_factory=list)


def _esc(text: str) -> str:
    return text.replace("|", "\\|").replace("*", "\\*").strip()


def _display(name: str) -> str:
    """Venue names in the public records are often all caps; show them in title case."""
    return string.capwords(name.lower()) if name.isupper() else name


def _single_operator(
    members: Sequence[Venue],
    legal: dict[str, str],
    by_key: dict[str, RegistryRecord],
    cfg: HospitalityConfig,
    counts: dict[str, int],
) -> str:
    """Who the registry says is behind a one-company account, with its link ("" if unknown;
    "agent" when the record names only an agent or law firm)."""
    for v in members:
        for lid in v.license_ids:
            rec = by_key.get(normalize_company(legal.get(lid, "")))
            if rec is None or not rec.found:
                continue
            if is_agent(rec, cfg.registry, counts):
                return "agent"
            key = operator_key(rec)
            who = rec.process_name if key and key[0] == "person" else rec.process_address
            if who:
                return f"{_esc(who)} ([registry]({registry_link(rec.dos_id or '')}))"
    return ""


def _month(d: date) -> str:
    return d.strftime("%B %Y")


def build_brief(
    store: DocStore,
    cfg: HospitalityConfig,
    out_dir: Path,
    *,
    seed_path: Path,
    top: int = 25,
    today: date | None = None,
) -> Path:
    """Write `out_dir/demo_brief.md` for the top `top` hospitality accounts; return its path."""
    today = today or date.today()
    venues = store.load("venues", Venue)
    groups = store.load("groups", Group)
    names = {g.group_id: g.name for g in groups}
    group_by_id = {g.group_id: g for g in groups}
    customers = current_customers(store, seed_path, venues=venues, groups=groups)
    ranked = rank_prospects(with_customer_flags(store.load("scores", ScoredAccount), customers))
    acct = {a.group_id: a for a in ranked}
    venues_of: dict[str, list[Venue]] = {}
    for v in venues:
        venues_of.setdefault(v.group_id, []).append(v)
    signals = {s.signal_id: s for s in [*store.load("license_signals", Signal),
                                        *store.load("signals", Signal)]}  # fmt: skip
    platforms: dict[str, set[str]] = {}
    for o in store.load("stack_observations", StackObservation):
        platforms.setdefault(o.venue_id, set()).update(o.platforms)
    opens = {e.venue_id: e.estimated_open for e in store.load("estimates", WindowEstimate)}

    # Roll prospects up to operators: registry clusters first, then each remaining group.
    accounts: list[_Account] = []
    used: set[str] = set()
    records = store.load(RECORDS, RegistryRecord)
    by_key = {r.name_key: r for r in records}
    legal = {r.record_id: r.legal_name for r in store.load("licenses", LicenseRecord)}
    counts = stored_counts(records, store)
    if records:
        pool = ranked[:300]
        recs_by_group = {
            a.group_id: [
                by_key[k]
                for v in venues_of.get(a.group_id, [])
                for lid in v.license_ids
                if lid in legal and (k := normalize_company(legal[lid])) in by_key
            ]
            for a in [*pool, *(_Stub(g) for g in customers)]
        }
        named = frozenset(
            g for g in recs_by_group if group_by_id.get(g) and
            group_by_id[g].resolution in NAMED_RESOLUTIONS
        )  # fmt: skip
        for c in cluster_operators(
            recs_by_group, names, named, cfg.registry, counts, require_counts=True
        ):
            gids = [g for g in c.group_ids if g in acct]
            if len(gids) < 2 or any(g in customers for g in c.group_ids):
                continue
            first = c.members[0]
            accounts.append(_Account(
                c.label, c.kind, gids, max(acct[g].priority for g in gids),
                operator=f"{_esc(first.process_name or first.process_address or '')} "
                         f"([registry]({registry_link(first.dos_id or '')}))",
            ))  # fmt: skip
            used.update(gids)
    for a in ranked:
        if a.group_id not in used:
            g = group_by_id.get(a.group_id)
            kind = "named_group" if g and g.resolution in NAMED_RESOLUTIONS else "licence_company"
            label = names.get(a.group_id, a.group_id)
            members = venues_of.get(a.group_id, [])
            if kind == "licence_company" and members:
                shown = _display(members[0].name)
                if normalize_company(shown) != normalize_company(label):
                    label = f"{shown} ({label})"
                else:
                    label = shown
            account = _Account(label, kind, [a.group_id], a.priority)
            account.operator = _single_operator(members, legal, by_key, cfg, counts)
            accounts.append(account)
    accounts.sort(key=lambda x: (-x.priority, x.label))
    accounts = accounts[:top]

    lines = [
        "# Magic / Loyalist: top hospitality accounts",
        "",
        (
            f"Prepared {today} from public records (NY liquor licences, NYC health inspections, the "
            "NY company registry, venue websites and job postings). Existing Loyalist customers are "
            "excluded. Private: written only under out/magic/."
        ),
        "",
        (
            'Signals are evidence; the "why it matters" lines are hypotheses to test, not facts. '
            "Customer excerpts are quoted from Loyalist's customer-stories page, which publishes no "
            "outcome numbers."
        ),
        "",
        "| # | Account | Venues | Strongest signal | Priority |",
        "|---|---|---|---|---|",
    ]
    blocks: list[str] = []
    for i, account in enumerate(accounts, 1):
        members = [v for g in account.group_ids for v in venues_of.get(g, [])]
        contribs = sorted(
            (c for g in account.group_ids for c in acct[g].contributions if c.contribution > 0),
            key=lambda c: -c.contribution,
        )
        types = {c.signal_type for c in contribs}
        strongest = (
            _LABELS.get(contribs[0].signal_type, contribs[0].signal_type) if contribs else "—"
        )
        lines.append(f"| {i} | {_esc(account.label)} | {len(members)} | {strongest} | "
                     f"{account.priority:.2f} |")  # fmt: skip

        # Summary
        boroughs = sorted({b for v in members if (b := borough_of_zip(v.zip_code))})
        venue_list = ", ".join(_esc(v.name) for v in members[:6]) + (
            f" and {len(members) - 6} more" if len(members) > 6 else ""
        )
        where = f" in {', '.join(b.title() for b in boroughs)}" if boroughs else ""
        what = {
            "named_group": "A hospitality group",
            "person": "An operator found through the NY company registry",
            "office": "An operator found through the NY company registry",
            "licence_company": "A licence company (its parent group isn't resolved yet)",
        }[account.kind]
        summary = [(f"{what} with {len(members)} venue{'s' if len(members) != 1 else ''}"
                   f"{where}: {venue_list}.")]  # fmt: skip
        if account.operator.startswith("agent"):
            summary.append("Its registry record names only a law firm or registered agent, so "
                           "the operator behind it is still unresolved.")  # fmt: skip
        elif account.operator:
            summary.append(f"The NY company registry lists {account.operator} as receiving its "
                           "legal papers.")  # fmt: skip
        ahead = sorted(d for v in members if (d := opens.get(v.venue_id)) and d >= today)
        recent = sorted(d for v in members if (d := opens.get(v.venue_id))
                        and 0 <= (today - d).days <= 365)  # fmt: skip
        if "opening_soon" in types:
            summary.append("At least one venue is publicly listed as opening soon.")
        elif ahead:
            summary.append(f"A venue is expected to open around {_month(ahead[0])} "
                           "(estimated from its licence).")  # fmt: skip
        elif recent:
            summary.append(f"A venue opened recently (estimated {_month(recent[-1])}).")
        seen = sorted({p for v in members for p in platforms.get(v.venue_id, ())} - {"loyalist"})
        if seen:
            summary.append(f"Its websites show {', '.join(seen)}.")
        if "sevenrooms" in seen:
            summary.append("It uses SevenRooms, which has its own guest CRM, so this would be "
                           "a displacement sale rather than a first CRM.")  # fmt: skip
        if any(
            _has_accolade(group_by_id[g], venues_of.get(g, []), cfg.accolades)
            for g in account.group_ids
            if g in group_by_id
        ):
            summary.append("It holds a Michelin star.")

        block = [f"## {i}. {_esc(account.label)}", "", "**Summary**", "", " ".join(summary), "",
                 "**Signals and why they matter**", ""]  # fmt: skip
        evidence: list[str] = []
        for c in contribs[:6]:
            sig = signals.get(c.signal_id)
            label = _LABELS.get(c.signal_type, c.signal_type)
            detail = f" ({_esc(sig.detail)})" if sig and sig.detail else ""
            block.append(f"- **{label}**{detail}: {hypothesis(c.signal_type)}")
            if sig:
                evidence.append(f"- {label}: {evidence_link(sig.evidence_ref)}")
        if not contribs:
            block.append("- No signal contributed to this score.")
        block += ["", "**Case studies to cite**", ""]
        for story in pick_stories(types, len(members)):
            block.append(f"- **{story.customer}**, {story.situation}: \"{story.excerpt}\" "
                         f"([source]({STORIES}))")  # fmt: skip
        block += ["", "**Evidence**", ""]
        evidence += [f"- Website: {v.website}" for v in members if v.website]
        block += list(dict.fromkeys(evidence)) or ["- None stored."]
        blocks += [*block, ""]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "demo_brief.md"
    path.write_text("\n".join([*lines, "", *blocks]), encoding="utf-8")
    return path
