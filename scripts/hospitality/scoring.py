"""Noisy-OR P(in buying window) per group, with an explainable contribution trace."""

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from scripts.hospitality.config import HospitalityConfig, SignalPrior
from scripts.hospitality.models import (
    Contribution,
    Group,
    LicenseRecord,
    ScoredAccount,
    Signal,
    StackObservation,
    Venue,
    WindowEstimate,
)
from scripts.hospitality.resolve.normalize import normalize_name
from scripts.hospitality.stack.fingerprints import EVENTS, RESERVATION

_SECONDS_PER_DAY = 86400.0


class ScoreInputs(BaseModel):
    """Frozen bundle of `score_group`'s arguments, so replays use identical inputs."""

    model_config = ConfigDict(frozen=True)

    group: Group
    signals: tuple[Signal, ...]
    estimates: dict[str, WindowEstimate]
    venues: tuple[Venue, ...]
    observations: tuple[StackObservation, ...]
    cfg: HospitalityConfig
    now: datetime
    is_customer: bool
    disqualified_reason: str | None

    def kwargs(self) -> dict[str, Any]:
        """Shallow field dict (keeps nested models), ready for `score_group(**...)`."""
        return {name: getattr(self, name) for name in type(self).model_fields}


def noisy_or(ps: Sequence[float]) -> float:
    """P(at least one independent cause fires); 0.0 for no causes."""
    return 1.0 - math.prod(1.0 - p for p in ps)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def window_weight(
    signal: Signal,
    prior: SignalPrior,
    estimate: WindowEstimate | None,
    now: datetime,
    cfg: HospitalityConfig,
) -> float:
    """Weight in [0, 1]: 1 inside the opening window, decaying outside it or with signal age."""
    if prior.family == "opening" and estimate is not None:
        rel = (now.date() - estimate.estimated_open).days  # negative = before opening
        if -cfg.window_pre_days <= rel <= cfg.window_post_days:
            return 1.0
        outside = -cfg.window_pre_days - rel if rel < 0 else rel - cfg.window_post_days
        return 0.5 ** (outside / cfg.window_outside_half_life_days)
    if prior.half_life_days is None:
        return 1.0  # state signal, valid while last observed
    age_days = max(0.0, (_aware(now) - _aware(signal.observed_at)).total_seconds())
    return 0.5 ** (age_days / _SECONDS_PER_DAY / prior.half_life_days)


def _latest_by_venue(observations: Sequence[StackObservation]) -> dict[str, StackObservation]:
    out: dict[str, StackObservation] = {}
    for o in sorted(observations, key=lambda o: o.observed_at):
        out[o.venue_id] = o
    return out


def fit_score(
    group: Group,
    venues: Sequence[Venue],
    observations: Sequence[StackObservation],
    cfg: HospitalityConfig,
) -> float:
    """Sum of configured fit weights for the criteria the group satisfies (0..1)."""
    members = [v for v in venues if v.group_id == group.group_id]
    latest = _latest_by_venue(observations)
    platforms = {p for v in members if (o := latest.get(v.venue_id)) for p in o.platforms}
    checks = {
        "multi_venue": len(members) >= 2 or len(group.venue_ids) >= 2,
        "reservation_platform": bool(RESERVATION & platforms),
        "events_program": bool(EVENTS & platforms),
        "accolade": group.group_id in cfg.accolades
        or group.name.casefold() in {a.casefold() for a in cfg.accolades},
        "full_service_class": any(v.license_description == "Restaurant" for v in members),
    }
    return min(1.0, sum(w for k, w in cfg.fit_weights.items() if checks.get(k, False)))


def _opening_dedupe(
    rows: Sequence[tuple[Signal, SignalPrior, float, float]], cfg: HospitalityConfig
) -> tuple[set[str], dict[str, str]]:
    """Which signals count toward p_window, and why the rest were zeroed.

    Opening evidence (pending / issued / not-yet-inspected) is one fact per venue: only the
    strongest counts. Then only the strongest `max_opening_venues_per_group` venues count.
    Every other signal counts independently.
    """
    evidence = set(cfg.opening_evidence_signals)
    counted = {sig.signal_id for sig, *_ in rows if sig.signal_type not in evidence}
    notes: dict[str, str] = {}
    by_venue: dict[str, list[tuple[Signal, float]]] = {}
    for sig, _prior, _weight, raw in rows:
        if sig.signal_type in evidence:
            by_venue.setdefault(sig.entity_id, []).append((sig, raw))
    best: dict[str, tuple[Signal, float]] = {}
    for venue_id, items in by_venue.items():
        ordered = sorted(items, key=lambda x: (-x[1], x[0].signal_id))
        best[venue_id] = ordered[0]
        for sig, _ in ordered[1:]:
            notes[sig.signal_id] = (
                f"folded into strongest opening signal {ordered[0][0].signal_id} for this venue"
            )
    ranked = sorted(best.items(), key=lambda kv: (-kv[1][1], kv[0]))
    for rank, (venue_id, (sig, _raw)) in enumerate(ranked):
        if rank < cfg.max_opening_venues_per_group:
            counted.add(sig.signal_id)
        else:
            notes[sig.signal_id] = (
                f"beyond venue cap: only the strongest {cfg.max_opening_venues_per_group} "
                f"venues' opening terms count (venue {venue_id})"
            )
    return counted, notes


def operator_names(
    group: Group, venues: Sequence[Venue], licenses_by_id: Mapping[str, LicenseRecord]
) -> list[str]:
    """Group, venue and licensee (legal / DBA) names to screen for contract operators."""
    names = [group.name]
    for venue in venues:
        names.append(venue.name)
        for lic_id in venue.license_ids:
            if (lic := licenses_by_id.get(lic_id)) is not None:
                names.extend((lic.legal_name, lic.dba))
    return [n for n in names if n]


def contract_operator_reason(names: Iterable[str], cfg: HospitalityConfig) -> str | None:
    """`cfg.disqualify_reason` if any name matches a contract-operator pattern, else None.

    Names are normalized (lowercase, punctuation and corp suffixes dropped) before matching.
    """
    patterns = [re.compile(p, re.IGNORECASE) for p in cfg.disqualify_name_patterns]
    for name in names:
        norm = normalize_name(name)
        if norm and any(p.search(norm) for p in patterns):
            return cfg.disqualify_reason
    return None


def score_group(
    group: Group,
    signals: Sequence[Signal],
    estimates: dict[str, WindowEstimate],
    venues: Sequence[Venue],
    observations: Sequence[StackObservation],
    cfg: HospitalityConfig,
    now: datetime,
    *,
    is_customer: bool,
    disqualified_reason: str | None,
) -> ScoredAccount:
    """Score one group: priority = p_window * (0.5 + 0.5 * fit) * relationship."""
    own = {group.group_id, *group.venue_ids}
    rows: list[tuple[Signal, SignalPrior, float, float]] = []
    for sig in sorted((s for s in signals if s.entity_id in own), key=lambda s: s.signal_id):
        prior = cfg.priors[sig.signal_type]
        weight = window_weight(sig, prior, estimates.get(sig.entity_id), now, cfg)
        rows.append((sig, prior, weight, prior.precision * weight))
    counted, notes = _opening_dedupe(rows, cfg)

    contributions: list[Contribution] = []
    window_ps: list[float] = []
    alumni = False
    for sig, prior, weight, raw in rows:
        contribution = raw if sig.signal_id in counted else 0.0
        contributions.append(
            Contribution(
                signal_id=sig.signal_id,
                signal_type=sig.signal_type,
                precision=prior.precision,
                weight=weight,
                contribution=contribution,
                note=notes.get(sig.signal_id, ""),
            )
        )
        if prior.family == "relationship":
            alumni = alumni or sig.signal_type == "alumni_edge"
        else:
            window_ps.append(contribution)
    p_window = noisy_or(window_ps)
    fit = fit_score(group, venues, observations, cfg)
    relationship = 1.0 + cfg.relationship_boost if alumni else 1.0
    priority = 0.0 if disqualified_reason else p_window * (0.5 + 0.5 * fit) * relationship
    return ScoredAccount(
        group_id=group.group_id,
        p_window=p_window,
        fit=fit,
        relationship=relationship,
        priority=priority,
        contributions=tuple(contributions),
        disqualified_reason=disqualified_reason,
        is_customer=is_customer,
    )


def zero_out(account_inputs: ScoreInputs, signal_type: str) -> ScoredAccount:
    """Rescore with every signal of `signal_type` removed (same other inputs)."""
    kept = tuple(s for s in account_inputs.signals if s.signal_type != signal_type)
    return score_group(**account_inputs.model_copy(update={"signals": kept}).kwargs())


def rank_prospects(accounts: Sequence[ScoredAccount]) -> list[ScoredAccount]:
    """Cold prospects only (no customers, no disqualified), by priority desc then group_id."""
    eligible = [a for a in accounts if not a.is_customer and a.disqualified_reason is None]
    return sorted(eligible, key=lambda a: (-a.priority, a.group_id))
