"""Kaplan-Meier opening-timing curves from license-issue -> first-inspection history."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from scripts.hospitality.models import LicenseRecord, Venue

Curve = tuple[tuple[float, float], ...]

MAX_DAYS = 730.0
_EPS = 1e-9


def kaplan_meier(durations: Sequence[float], observed: Sequence[bool]) -> Curve:
    """Product-limit estimator; events precede censorings at tied times.

    Returns (t_days, survival) steps starting at (0.0, 1.0), one step per event time.
    """
    if len(durations) != len(observed):
        raise ValueError("durations and observed must have the same length")
    events: dict[float, int] = defaultdict(int)
    total: dict[float, int] = defaultdict(int)
    for t, o in zip(durations, observed, strict=True):
        total[float(t)] += 1
        if o:
            events[float(t)] += 1
    at_risk = len(durations)
    surv = 1.0
    steps: list[tuple[float, float]] = [(0.0, 1.0)]
    for t in sorted(total):
        d = events.get(t, 0)
        if d:
            surv *= 1.0 - d / at_risk
            steps.append((t, surv))
        at_risk -= total[t]
    return tuple(steps)


def survival_at(curve: Curve, t: float) -> float:
    """S(t): the survival of the last step at or before t (1.0 before the first event)."""
    s = 1.0
    for ti, si in curve:
        if ti > t:
            break
        s = si
    return s


def quantile_time(curve: Curve, q: float) -> float | None:
    """First t where S(t) <= 1 - q; None when the curve never gets that low."""
    for t, s in curve[1:]:
        if s <= 1.0 - q + _EPS:
            return t
    return None


def opening_durations(
    venues: Sequence[Venue], licenses: Sequence[LicenseRecord], today: date
) -> list[tuple[str, float, bool]]:
    """One (stratum, days, observed) per venue with an issued (active/inactive) license.

    Inspected venues use the latest license issued on or before the first inspection; a venue
    whose only licenses were issued AFTER its first inspection is a transfer/renewal, not a new
    opening, and is excluded, as is anything over 730 days (data noise). Venues with no
    inspection yet are censored at today - issue (same 730-day cap).
    """
    by_id = {lic.record_id: lic for lic in licenses}
    out: list[tuple[str, float, bool]] = []
    for venue in venues:
        issued = [
            lic
            for lid in venue.license_ids
            if (lic := by_id.get(lid)) is not None
            and lic.source in ("sla_active", "sla_inactive")
            and lic.original_issue_date is not None
        ]
        if not issued:
            continue
        first = venue.first_inspection_date
        if first is not None:
            prior = [lic for lic in issued if lic.original_issue_date <= first]  # type: ignore[operator]
            if not prior:
                continue  # inspected before every license: renewal/transfer, not an opening
            lic = max(prior, key=lambda x: x.original_issue_date)  # type: ignore[arg-type,return-value]
            days = float((first - lic.original_issue_date).days)  # type: ignore[operator]
            observed = True
        else:
            lic = max(issued, key=lambda x: x.original_issue_date)  # type: ignore[arg-type,return-value]
            days = float((today - lic.original_issue_date).days)  # type: ignore[operator]
            observed = False
        if days < 0 or days > MAX_DAYS:
            continue
        out.append((stratum_of(lic), days, observed))
    return out


def stratum_of(lic: LicenseRecord) -> str:
    """Curve stratum key for a license: 'description|county', or 'all' if either is missing."""
    if lic.description and lic.county:
        return f"{lic.description}|{lic.county}"
    return "all"


def build_curves(durations: Sequence[tuple[str, float, bool]], min_n: int = 30) -> dict[str, Curve]:
    """Pooled 'all' curve plus one per stratum with at least min_n venues."""
    groups: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    for stratum, days, observed in durations:
        groups[stratum].append((days, observed))
    curves: dict[str, Curve] = {
        "all": kaplan_meier([d for _, d, _ in durations], [o for _, _, o in durations])
    }
    for stratum, rows in groups.items():
        if stratum != "all" and len(rows) >= min_n:
            curves[stratum] = kaplan_meier([d for d, _ in rows], [o for _, o in rows])
    return curves
