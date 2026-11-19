"""Assemble the demo report from the store.

Every number is computed from what the store holds, so the report is reproducible. A section
whose inputs are missing says plainly that it was not run and why; it never shows zeros or
placeholder figures. The report contains Loyalist customers detected from their own embeds, so
it is written only under the directory the caller passes (the CLI passes the gitignored
`out/magic/`).
"""

import math
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from scripts.hospitality.benchmark.compare import FAIRNESS_NOTE
from scripts.hospitality.config import HospitalityConfig
from scripts.hospitality.events.rank import meeting_list, rank_events
from scripts.hospitality.events.registry import load_events
from scripts.hospitality.labels import current_customers, with_customer_flags
from scripts.hospitality.models import (
    BenchmarkResult,
    Contact,
    CurveRecord,
    CustomerLabel,
    Draft,
    EntityLink,
    EventAppearance,
    Group,
    Judgement,
    LicenseRecord,
    ScoredAccount,
    Signal,
    StackObservation,
    Venue,
    WebsiteLookup,
    WindowEstimate,
)
from scripts.hospitality.scoring import TIE_DECIMALS, rank_prospects, tie_blocks
from scripts.hospitality.store import DocStore
from scripts.hospitality.window.survival import quantile_time

REPORT_NAME = "demo_report.md"
TOP_N = 25

SECTIONS: tuple[str, ...] = (
    "Universe and location counts",
    "Opening-timing curve",
    "Recall audit",
    "Head-to-head",
    "Backtests",
    "Stack distribution and Loyalist penetration",
    "Top 25 prospects with traces",
    "Contacts coverage and cost per verified contact",
    "Drafts with judge scores",
    "Event ranking and the top meeting list",
    "Limitations and assumptions",
    "Questions for Magic",
)

# Spec section 10.
QUESTIONS: tuple[str, ...] = (
    "What is the canonical unit of account (venue, concept, group, contract)?",
    "Which CRM, sender, scheduler and enrichment tools are in use today?",
    (
        "Of recent wins, what share started from a walk-in, dinner, event, referral or inbound, "
        "and how many involved an opening within 6 months?"
    ),
    "What does a lost deal look like (SevenRooms built-in CRM, do nothing, price)?",
    "How much revenue comes from new venues inside existing groups?",
    "Is any outbound email running now, and from which domains?",
)


def _not_run(what: str, why: str) -> list[str]:
    return [f"**Not run: {what}.** {why}", ""]


def _fmt(value: float | None, unit: str = "") -> str:
    return "n/a" if value is None else f"{value:g}{unit}"


def _esc(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _universe(
    venues: Sequence[Venue],
    groups: Sequence[Group],
    licenses: Sequence[LicenseRecord],
    links: Sequence[EntityLink],
) -> list[str]:
    if not venues:
        return _not_run(
            "universe counts",
            "The store holds no resolved venues (run ingest-sla, ingest-dohmh and resolve).",
        )
    multi = sum(len(g.venue_ids) > 1 for g in groups)
    by_source = Counter(lic.source for lic in licenses)
    by_resolution = Counter(g.resolution for g in groups)
    lines = [
        f"- Venues (locations): {len(venues)}",
        f"- Groups: {len(groups)} ({multi} with more than one venue)",
        f"- Licenses: {len(licenses)} ("
        + ", ".join(f"{k}: {v}" for k, v in sorted(by_source.items()))
        + ")",
        f"- Venues matched to a DOHMH record: {sum(v.camis is not None for v in venues)}",
        (
            f"- Venues with a first inspection date: "
            f"{sum(v.first_inspection_date is not None for v in venues)}"
        ),
        f"- Venues with a website: {sum(bool(v.website) for v in venues)}",
        f"- Possibly-same links (below the auto-merge threshold, not merged): {len(links)}",
        "- Groups by how they were formed: "
        + (", ".join(f"{k}: {v}" for k, v in sorted(by_resolution.items())) or "none"),
        "",
        (
            "Caveat: groups are formed only from a shared legal name, shared website domain, and "
            "press and job-board evidence that names a venue's group, so the multi-venue group "
            "count is a lower bound; operators with "
            "differently named entities per venue appear as separate groups. The possibly-same links "
            "are unresolved ambiguity, not counted as merges."
        ),
        "",
    ]
    return lines


def _timing(curves: Sequence[CurveRecord], cfg: HospitalityConfig) -> list[str]:
    if not curves:
        return _not_run("opening-timing curve", "No curves are stored (run the window command).")
    ordered = sorted(curves, key=lambda c: (c.stratum != "all", -c.n, c.stratum))
    lines = [
        (
            "Days from license issue to first DOHMH inspection, from a Kaplan-Meier curve that "
            "corrects for censoring: an issued license whose site is not inspected yet is "
            "censored at its age. It is dropped instead when the missing inspection is more "
            "likely a match miss than a site that has not opened: the license is possibly-same "
            "linked to an already-inspected site, or it has no DOHMH record at all and is older "
            f"than {cfg.window_unmatched_censor_max_age_days} days. Licenses issued after the "
            "site's first inspection (transfers, renewals) and durations over "
            f"{cfg.max_opening_days:g} days are dropped too; pending applications are not on "
            "the curve."
        ),
        "",
        "| Stratum | n | 25th pct (days) | Median (days) | 75th pct (days) |",
        "|---|---|---|---|---|",
    ]
    for c in ordered:
        q1, med, q3 = (quantile_time(c.steps, q) for q in (0.25, 0.5, 0.75))
        lines.append(f"| {_esc(c.stratum)} | {c.n} | {_fmt(q1)} | {_fmt(med)} | {_fmt(q3)} |")
    lines += [
        "",
        (
            "n/a means the curve never falls that far (too many still-unopened sites to estimate that "
            "quantile). Strata are shown only where the sample was large enough to fit a curve."
        ),
        "",
    ]
    return lines


def _recall(store: DocStore, cfg: HospitalityConfig, today: date) -> list[str]:
    from scripts.hospitality import cli  # lazy: cli imports this module

    if not store.load("venues", Venue) or not store.load("licenses", LicenseRecord):
        return _not_run(
            "recall audit",
            "It needs resolved venues and licenses with DOHMH first-inspection dates in the store.",
        )
    r = cli.recall(cfg.report_recall_weeks, today, store, cfg)
    lines = [
        (
            f"Window {r.start} to {r.end}. What this measures: whether our license signals fire "
            "before a venue's first DOHMH inspection, for the openings we can tie to a license. "
            "It is not market-wide recall and not the share of NYC openings found: most venues "
            "first inspected in the window never matched an on-premise license we can see, and "
            "they are outside the truth set."
        ),
        "",
        f"- Venues first inspected in the window (every DOHMH first inspection): {r.first_inspections}",
        f"- Of those, tied to at least one license record: {r.license_matched}",
        (
            f"- Of those, new on-premise openings (not a transfer or renewal), the truth set: "
            f"{r.total}"
        ),
        "",
    ]
    if not r.total:
        lines += ["No license-matched openings fell in the window, so nothing is computed.", ""]
        return lines
    over = (
        f"; {r.leads_over_cap} of the {r.caught} leads are longer than {r.lead_cap_days} days "
        f"and are excluded from this median (a signal that early is not a buying-window lead; "
        f"the median over all leads is {_fmt(r.median_lead_days, ' days')})"
        if r.leads_over_cap
        else f"; no lead is longer than {r.lead_cap_days} days"
    )
    lines += [
        (
            f"- License-signal timeliness among license-matched openings: caught before the first "
            f"inspection {r.caught} of {r.total} ({r.recall:.1%})"
        ),
        (
            f"- Of those, caught with a lead within {r.lead_cap_days} days of the first "
            f"inspection: {r.caught - r.leads_over_cap} of {r.total} "
            f"({(r.caught - r.leads_over_cap) / r.total:.1%}); an earlier signal is caught but is "
            "not a buying-window lead"
        ),
        (
            f"- Coverage of all first inspections in the window: {r.caught} of "
            f"{r.first_inspections} ({r.coverage:.1%})"
        ),
        (
            f"- Median lead before the first inspection: "
            f"{_fmt(r.median_lead_days_within_cap, ' days')}{over}."
        ),
        "",
        (
            "Caveat: the truth set exists only because a license was matched, so the first figure "
            "is close to circular (a matched license that predates the inspection is a catch by "
            "construction); misses come from licenses outside the lookback or stale caps. The "
            "replay uses the same lookback and stale caps as live scoring. Neither figure is a "
            "lift claim."
        ),
        "",
    ]
    return lines


def _head_to_head(results: Sequence[BenchmarkResult]) -> list[str]:
    note = [f"Fairness note: {FAIRNESS_NOTE}", ""]
    if not results:
        return [
            *_not_run(
                "head-to-head",
                "No benchmark result is stored; the benchmark command spends real Claude and "
                "web-search budget and needs ANTHROPIC_API_KEY and --yes.",
            ),
            *note,
        ]
    r = results[0]
    lines = [
        (
            f"Truth set: n={r.truth_total} license-matched new openings first inspected after "
            f"the cutoff; each method is scored on at most k={r.k} distinct venues."
        ),
        "",
        "| Method | Hits | Precision@k | Duplicates | Non-venues |",
        "|---|---|---|---|---|",
        f"| SignalForce | {r.sf_hits} | {r.sf_precision_at_k:.3f} | n/a | n/a |",
    ]
    for i, hits in enumerate(r.claude_hits):
        lines.append(
            f"| Plain Claude run {i} | {hits} | {r.claude_precision_at_k[i]:.3f} | "
            f"{r.claude_duplicates[i]} | {r.claude_unmatched[i]} |"
        )
    lines += [
        "",
        f"Claude run-to-run Jaccard: {r.claude_run_jaccard:.3f} ({len(r.claude_hits)} runs).",
        "",
    ]
    lines += [f"Note: {n}" for n in r.notes if n != FAIRNESS_NOTE]
    return [*lines, *note]


def _backtests(store: DocStore) -> list[str]:
    from scripts.hospitality import cli  # lazy: cli imports this module

    if not store.load("venues", Venue) or not store.load("scores", ScoredAccount):
        return _not_run(
            "backtests", "They need resolved venues and scored groups (run resolve and score)."
        )
    out = cli.backtest(store)
    replayed = [c for c in out.cases if c.status == "replayed"]
    caught = [c for c in replayed if c.lead_days is not None]
    lines = [
        "Indicative only: tiny samples, not a lift claim.",
        "",
        (
            f"Case replay: {len(out.cases)} customers with a known new venue; {len(replayed)} "
            f"could be replayed, {len(out.cases) - len(replayed)} are not evaluable (no dated "
            "anchor; the venue appears only after the anchor; or no license or application on "
            "file before the venue opened, so no license signal could have fired: a coverage gap "
            "of the source, which counts against coverage in the recall audit, not a timing "
            f"result). Of the replayed cases, {len(caught)} had an opening signal on or before "
            f"the anchor"
            + (
                f"; {len(replayed)} replayed case(s) are too few to estimate a rate."
                if len(replayed) < 10
                else "."
            )
            + f" {out.undated} customers have no public date at all."
        ),
        "",
        (
            "The anchor is an upper bound (the customer was live on or before it), so a lead is "
            "measured to that bound and may overstate the true lead."
        ),
        "",
    ]
    if out.cases:
        lines += [
            "| Customer | Anchor (on or before) | New venue | Outcome | Signals |",
            "|---|---|---|---|---|",
        ]
        for c in out.cases:
            if c.status == "not_evaluable":
                outcome = f"not evaluable: {c.reason}"
            elif c.lead_days is not None:
                outcome = f"signal {c.lead_days} days before the anchor"
            else:
                outcome = "miss: no opening signal on or before the anchor"
            anchor = f"{c.anchor_date} ({c.anchor_basis})" if c.anchor_date else "undated"
            lines.append(
                f"| {_esc(c.customer)} | {anchor} | {c.new_venue_id or 'venue not found'} "
                f"| {_esc(outcome)} | {', '.join(c.signal_types) or 'none'} |"
            )
    else:
        lines.append("No customer with a known new venue is in the store.")
    shown = "undefined" if math.isnan(out.fit_auc) else f"{out.fit_auc:.3f}"
    lines += [
        "",
        (
            f"Fit AUC: {shown} (customers n={out.n_customers} vs other scored groups "
            f"n={out.n_others}). Static fit only, no timing; indicative only."
            + (
                f" With n={out.n_customers}, too few customers for the AUC to separate signal "
                "from chance."
                if out.n_customers < 10
                else ""
            )
        ),
    ]
    if out.fit_distinct <= 1:
        lines.append("Fit is degenerate (every scored group has the same fit), so AUC is a tie.")
    lines.append("")
    return lines


def _customer_section(customers: dict[str, CustomerLabel], names: dict[str, str]) -> list[str]:
    lines = [
        "### Existing Loyalist customers (excluded from every prospect and meeting list)",
        "",
        "Shown so the detection can be checked; none of these is a target of any kind.",
        "",
    ]
    if not customers:
        return [*lines, "No customer groups were identified in the store.", ""]
    for gid, label in sorted(customers.items(), key=lambda kv: names.get(kv[0], kv[0])):
        date_note = (
            f", public on or before {label.first_public_date}" if label.first_public_date else ""
        )
        lines.append(
            f"- {names.get(gid, gid)} ({label.source}{date_note}; evidence: {label.evidence_ref})"
        )
    return [*lines, ""]


def _website_coverage(lookups: Sequence[WebsiteLookup]) -> list[str]:
    """One line on how the websites behind the stack figures were found and checked."""
    if not lookups:
        return []
    hits = [w for w in lookups if w.website]
    how = Counter(w.verified_by or w.source for w in hits)
    misses = Counter(w.miss_reason or "unspecified" for w in lookups if not w.website)
    parts = ", ".join(f"{n} {k}" for k, n in how.most_common()) or "none"
    why = ", ".join(f"{n} {k}" for k, n in misses.most_common()) or "none"
    return [
        (
            f"Website lookups: {len(lookups)} (n={len(lookups)}); found {len(hits)} ({parts}); "
            f"no site: {why}. Search finds count only when the page shows the venue's own phone "
            "or address."
        ),
        "",
    ]


def _stack(
    observations: Sequence[StackObservation],
    customers: dict[str, CustomerLabel],
    names: dict[str, str],
    lookups: Sequence[WebsiteLookup] = (),
) -> list[str]:
    lines: list[str]
    if not observations:
        lines = _not_run(
            "stack distribution and Loyalist penetration",
            "No stack crawl is stored (run websites and crawl; they need EXA_API_KEY or "
            "FIRECRAWL_API_KEY, and crawl needs FIRECRAWL_API_KEY).",
        )
    else:
        latest: dict[str, StackObservation] = {}
        for o in sorted(observations, key=lambda o: o.observed_at):
            latest[o.venue_id] = o
        n = len(latest)
        counts = Counter(p for o in latest.values() for p in set(o.platforms))
        loyalist = counts.get("loyalist", 0)
        lines = [
            f"Latest crawl of {n} venue websites (n={n}); a venue counts once per platform.",
            "",
            "| Platform | Venues | Share of crawled |",
            "|---|---|---|",
        ]
        lines += [f"| {p} | {c} | {c / n:.1%} |" for p, c in counts.most_common()]
        lines += [
            "",
            f"Loyalist penetration: {loyalist} of {n} crawled venues ({loyalist / n:.1%}; n={n}).",
            "",
            (
                "Caveat: only venues with a found website that was crawled are counted, and a platform "
                "is detected only from link, script and form attributes, so both figures are lower "
                "bounds, not the market."
            ),
            "",
        ]
    return [*lines, *_website_coverage(lookups), *_customer_section(customers, names)]


def _tie_break_line(acct: ScoredAccount, today: date) -> str:
    if acct.opening_date is not None:
        days = (acct.opening_date - today).days
        when = f"in {days} days" if days > 0 else f"{-days} days ago" if days < 0 else "today"
        opening = f"opening {acct.opening_date} ({when})"
    else:
        opening = "no dated opening"
    newest = acct.latest_signal_on or "none"
    return f"Tie-break: {opening}; newest contributing signal {newest}."


def _trace(
    acct: ScoredAccount,
    evidence: dict[str, Signal],
    names: dict[str, str],
    rank: int,
    today: date,
    tie: tuple[int, int] | None = None,
) -> list[str]:
    label = f"{rank} (tied {tie[0]}–{tie[1]})" if tie else f"{rank}"
    lines = [
        f"#### {label}. {names.get(acct.group_id, acct.group_id)}",
        "",
        (
            f"priority {acct.priority:.3f} = P(window) {acct.p_window:.3f} x (0.5 + 0.5 x fit "
            f"{acct.fit:.2f}) x relationship {acct.relationship:.2f}"
        ),
        "",
        _tie_break_line(acct, today),
        "",
        "| Signal | Precision | Weight | Contribution | Note | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    for c in sorted(acct.contributions, key=lambda c: (-c.contribution, c.signal_id)):
        sig = evidence.get(c.signal_id)
        ref = sig.evidence_ref if sig else "not found in store"
        lines.append(
            f"| {_esc(c.signal_type)} | {c.precision:.2f} | {c.weight:.2f} | "
            f"{c.contribution:.3f} | {_esc(c.note)} | {_esc(ref)} |"
        )
    return [*lines, ""]


def _prospects(
    accounts: Sequence[ScoredAccount],
    signals: Sequence[Signal],
    names: dict[str, str],
    today: date,
) -> list[str]:
    if not accounts:
        return _not_run("prospect ranking", "No scores are stored (run the score command).")
    evidence = {s.signal_id: s for s in signals}
    ranked = rank_prospects(accounts)
    lines = [
        (
            f"Cold prospects only: {len(ranked)} ranked of {len(accounts)} scored groups; "
            f"showing the top {min(TOP_N, len(ranked))}. Each trace lists the signal, its prior "
            "precision, weight, contribution and the evidence it came from."
        ),
        "",
    ]
    shown = ranked[:TOP_N]
    ties = tie_blocks(ranked)
    distinct = len({round(a.priority, TIE_DECIMALS) for a in shown})
    lines += [
        (
            f"The top {len(shown)} hold {distinct} distinct priorities. Ranks that share a "
            "priority are tied: the score cannot separate them, and they are listed by a stated "
            "tie-break (the estimated opening nearest the scoring date, then the newest "
            "contributing signal, then group id), which is an ordering rule, not evidence that "
            "one is the better prospect."
        ),
        "",
    ]
    for i, acct in enumerate(shown, 1):
        tie = ties.get(acct.group_id)
        if tie and tie[0] == i:
            first_below = len(shown) + 1
            below = ""
            if tie[1] > first_below:
                below = f"; ranks {first_below}–{tie[1]} are below the top {len(shown)}"
            elif tie[1] == first_below:
                below = f"; rank {first_below} is below the top {len(shown)}"
            lines += [
                f"**Ranks {tie[0]}–{tie[1]} share priority {acct.priority:.3f} (tied){below}.**",
                "",
            ]
        lines += _trace(acct, evidence, names, i, today, tie)
    disq = sorted(
        (a for a in accounts if a.disqualified_reason and not a.is_customer),
        key=lambda a: (a.disqualified_reason or "", names.get(a.group_id, a.group_id)),
    )
    lines += [f"### Disqualified (not ranked): {len(disq)}", ""]
    lines += [f"- {names.get(a.group_id, a.group_id)}: {a.disqualified_reason}" for a in disq]
    return [*lines, ""] if disq else [*lines, "None.", ""]


def _contacts(contacts: Sequence[Contact], accounts: Sequence[ScoredAccount]) -> list[str]:
    if not contacts:
        return _not_run(
            "contacts",
            "No contacts are stored (the contacts command needs HUNTER_API_KEY, "
            "FIRECRAWL_API_KEY and ANTHROPIC_API_KEY).",
        )
    top = {a.group_id for a in rank_prospects(accounts)[:TOP_N]}
    covered = {c.group_id for c in contacts} & top
    with_email = [c for c in contacts if c.email]
    return [
        (
            f"- Top-{TOP_N} prospect groups with at least one contact: {len(covered)} of {len(top)} "
            f"(n={len(top)})"
        ),
        f"- Contacts stored: {len(contacts)}; with an email: {len(with_email)}",
        "- By source: "
        + ", ".join(f"{k}: {v}" for k, v in sorted(Counter(c.source for c in contacts).items())),
        "",
        (
            "Cost per verified contact is not computed: the store does not record per-run vendor "
            "spend or call counts, so any figure here would be invented."
        ),
        "",
    ]


def _drafts(
    drafts: Sequence[Draft],
    judgements: Sequence[Judgement],
    customers: dict[str, CustomerLabel],
    names: dict[str, str],
) -> list[str]:
    if not drafts:
        return _not_run(
            "drafts", "No drafts are stored (the draft command needs ANTHROPIC_API_KEY)."
        )
    if len(drafts) != len(judgements):
        return _not_run(
            "drafts",
            f"The store has {len(drafts)} drafts but {len(judgements)} judgements, so scores "
            "cannot be paired reliably.",
        )
    cold = [(d, j) for d, j in zip(drafts, judgements, strict=True) if d.group_id not in customers]
    n = len(cold)
    passed = sum(j.passed for _, j in cold)
    grounded = sum(not j.grounding_violations for _, j in cold)
    lines = [
        (
            f"Drafts (never sent): n={n}; judge pass rate {passed}/{n}; "
            f"grounding check clean {grounded}/{n}."
        ),
        "",
    ]
    for d, j in cold:
        lines += [
            f"#### {names.get(d.group_id, d.group_id)} ({d.angle}): {_esc(d.subject)}",
            (
                f"judge score {j.score:.2f}; passed: {j.passed}; grounded: {j.factually_grounded}; "
                f"violations: {len(j.grounding_violations)}"
            ),
            "",
        ]
        lines += [
            f"- {_esc(s.text)} [{', '.join(s.evidence_ids) or 'no evidence cited'}]"
            for s in d.sentences
        ]
        lines.append("")
    return lines


def _events(
    store: DocStore,
    events_path: Path,
    accounts: dict[str, ScoredAccount],
    venues: Sequence[Venue],
    customers: dict[str, CustomerLabel],
    cfg: HospitalityConfig,
) -> list[str]:
    appearances = store.load("event_appearances", EventAppearance)
    if not appearances:
        return _not_run(
            "event ranking",
            "No lineup appearances are stored (the events-extract command needs "
            "FIRECRAWL_API_KEY and ANTHROPIC_API_KEY).",
        )
    events = load_events(events_path)  # unverified dates are excluded
    priors = cfg.events
    ranked = rank_events(events, appearances, accounts, venues, customers, priors=priors)
    by_id = {e.event_id: e for e in events}
    lines = [
        (
            f"Verified-date events ranked by expected meetings per dollar (n={len(events)} events, "
            f"{len(appearances)} appearances). Meeting rates and attendance are priors, not "
            "measured; unknown cost scores 0 per dollar."
        ),
        "",
        "| Event | Expected meetings | Per dollar | Matched people |",
        "|---|---|---|---|",
    ]
    for s in ranked:
        lines.append(
            f"| {_esc(by_id[s.event_id].name)} | {s.expected_meetings:.4f} | "
            f"{s.score_per_dollar:.6f} | {s.matched_people} |"
        )
    lines.append("")
    if ranked:
        top = by_id[ranked[0].event_id]
        targets = meeting_list(top, appearances, accounts, venues, customers, priors=priors)
        lines += [
            f"### Top meeting list: {top.name}",
            "",
            (
                f'"In window" means p_window >= {priors.in_window_p:.2f} (one full-weight opening '
                "signal inside its estimated window); it is a threshold on a prior-based score."
            ),
            "",
            "Prospects:",
        ]
        lines += [
            f"- {t.person} ({t.reason}); priority {t.priority:.2f}; "
            f"{'in window' if t.in_window else 'not in window'}"
            for t in targets
            if not t.is_customer
        ] or ["- none"]
        lines.append("")
    return lines


def _limitations(cfg: HospitalityConfig, estimates: Sequence[WindowEstimate]) -> list[str]:
    lines = [
        "- Priors below are starting assumptions from research, not fitted to Magic data.",
        "- Group counts are a lower bound; possibly-same links are not merged.",
        (
            "- The recall audit covers license-matched openings only (a minority of first "
            "inspections; both denominators are in section 3) and is not a lift claim."
        ),
        "- Case replay and fit AUC are indicative only (tiny samples).",
        (
            "- The head-to-head has residual biases in both directions (listed in section 4), "
            "so its result is indicative and a lower bound for neither side."
        ),
        "- The opening-timing median comes from a censoring-corrected curve.",
        "- Public data only; no Magic data, no real outbound email (drafts only).",
        "",
        "Signal priors used by scoring:",
        "",
        "| Signal | Precision | Half-life (days) | Family |",
        "|---|---|---|---|",
    ]
    for name, p in sorted(cfg.priors.items()):
        lines.append(f"| {name} | {p.precision:.2f} | {_fmt(p.half_life_days)} | {p.family} |")
    basis = Counter(e.basis.split(";")[0] for e in estimates)  # drop per-venue age detail
    lines += [
        "",
        "Fit weights: " + ", ".join(f"{k}={v:g}" for k, v in sorted(cfg.fit_weights.items())),
        (
            f"Opening window: {cfg.window_pre_days} days before to {cfg.window_post_days} days after "
            f"the estimated opening; half-life outside it {cfg.window_outside_half_life_days:g} days."
        ),
        "Opening-estimate bases in the store: "
        + (", ".join(f"{k} ({v})" for k, v in sorted(basis.items())) or "none"),
        "Event attendance priors: "
        + ", ".join(f"{k}={v}" for k, v in cfg.events.attend_prior.items()),
        "Event meeting-rate priors: "
        + ", ".join(f"{k}={v}" for k, v in cfg.events.meeting_rate_prior.items()),
        "",
    ]
    return lines


def build_report(
    store: DocStore,
    cfg: HospitalityConfig,
    out_dir: Path,
    *,
    today: date | None = None,
    events_path: Path | None = None,
) -> Path:
    """Write the 12-section demo report to `out_dir/demo_report.md` and return its path."""
    from scripts.hospitality import cli  # lazy: cli imports this module

    today = today or date.today()
    events_path = events_path or cli.EVENTS_PATH
    venues = store.load("venues", Venue)
    groups = store.load("groups", Group)
    licenses = store.load("licenses", LicenseRecord)
    customers = current_customers(store, cli.SEED_PATH, venues=venues, groups=groups)
    accounts = with_customer_flags(store.load("scores", ScoredAccount), customers)
    names = {g.group_id: g.name for g in groups}
    signals = [*store.load("license_signals", Signal), *store.load("signals", Signal)]

    body: list[list[str]] = [
        _universe(venues, groups, licenses, store.load("links", EntityLink)),
        _timing(store.load("curves", CurveRecord), cfg),
        _recall(store, cfg, today),
        _head_to_head(store.load("benchmark", BenchmarkResult)),
        _backtests(store),
        _stack(
            store.load("stack_observations", StackObservation),
            customers,
            names,
            store.load("websites", WebsiteLookup),
        ),
        _prospects(accounts, signals, names, today),
        _contacts(store.load("contacts", Contact), accounts),
        _drafts(store.load("drafts", Draft), store.load("judgements", Judgement), customers, names),
        _events(store, events_path, {a.group_id: a for a in accounts}, venues, customers, cfg),
        _limitations(cfg, store.load("estimates", WindowEstimate)),
        [f"{i}. {q}" for i, q in enumerate(QUESTIONS, 1)] + [""],
    ]
    lines = [
        "# Magic / Loyalist demo report",
        "",
        (
            f"Generated {today} from the local store. Contains detected Loyalist customers: private, "
            "written only under out/magic/ (gitignored); never commit or publish it."
        ),
        "",
    ]
    for i, (title, section) in enumerate(zip(SECTIONS, body, strict=True), 1):
        lines += [f"## {i}. {title}", "", *section]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / REPORT_NAME
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


if __name__ == "__main__":
    from scripts.hospitality import cli

    print(cli.report())
    sys.exit(0)
