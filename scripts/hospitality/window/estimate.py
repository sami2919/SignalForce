"""Per-venue opening-window estimates from Kaplan-Meier curves."""

from collections.abc import Sequence
from datetime import date, timedelta

from scripts.hospitality.config import HospitalityConfig
from scripts.hospitality.models import LicenseRecord, Venue, WindowEstimate
from scripts.hospitality.window.survival import Curve, quantile_time, stratum_of, survival_at


def _p_open(curve: Curve, age: float, horizon: float) -> float:
    """P(opens within `horizon` days | not open at `age`); age may be negative (future issue)."""
    s_now = survival_at(curve, max(age, 0.0))
    if s_now <= 0.0:
        return 1.0
    return min(1.0, max(0.0, 1.0 - survival_at(curve, age + horizon) / s_now))


def _conditional_remaining_median(curve: Curve, age: float) -> float | None:
    """Median remaining days for a venue still unopened at `age`."""
    s_now = survival_at(curve, age)
    for t, s in curve[1:]:
        if t > age and s <= s_now / 2 + 1e-9:
            return t - age
    return None


def estimate_window(
    venue: Venue,
    license: LicenseRecord,
    curves: dict[str, Curve],
    cfg: HospitalityConfig,
    today: date,
) -> WindowEstimate | None:
    """Estimate opening date and 90/180-day open probabilities; None if not estimable."""
    if venue.first_inspection_date is not None:
        return None  # already opened
    stratum = stratum_of(license)
    curve = curves.get(stratum)
    used = stratum
    if curve is None:
        curve, used = curves.get("all"), "all"
    if curve is None:
        return None

    prior = ""
    if license.source == "sla_pending":
        if license.received_date is None:
            return None
        issue = license.received_date + timedelta(days=cfg.pending_to_issue_prior_days)
        issue = max(issue, today)  # an overdue application cannot issue in the past
        prior = f"prior:pending_to_issue={cfg.pending_to_issue_prior_days}d;"
    elif license.source == "sla_active":
        if license.original_issue_date is None:
            return None
        issue = license.original_issue_date
    else:
        return None

    age = float((today - issue).days)
    median = quantile_time(curve, 0.5)
    if median is None:
        return None
    est = issue + timedelta(days=round(median))
    if est < today:
        remaining = _conditional_remaining_median(curve, age)
        est = today + timedelta(days=round(remaining)) if remaining is not None else today
    return WindowEstimate(
        venue_id=venue.venue_id,
        estimated_open=est,
        p_open_90d=_p_open(curve, age, 90),
        p_open_180d=_p_open(curve, age, 180),
        basis=f"{prior}km:{used};median={round(median)}d;age={int(age)}d",
    )


def estimate_all(
    venues: Sequence[Venue],
    licenses: Sequence[LicenseRecord],
    curves: dict[str, Curve],
    cfg: HospitalityConfig,
    today: date,
) -> list[WindowEstimate]:
    """Estimate every unopened venue from its best license (issued preferred over pending)."""
    by_id = {lic.record_id: lic for lic in licenses}
    out: list[WindowEstimate] = []
    for venue in venues:
        if venue.first_inspection_date is not None:
            continue
        lics = [lic for lid in venue.license_ids if (lic := by_id.get(lid)) is not None]
        active = [lic for lic in lics if lic.source == "sla_active" and lic.original_issue_date]
        pending = [lic for lic in lics if lic.source == "sla_pending" and lic.received_date]
        if active:
            chosen = max(active, key=lambda x: x.original_issue_date)  # type: ignore[arg-type,return-value]
        elif pending:
            chosen = max(pending, key=lambda x: x.received_date)  # type: ignore[arg-type,return-value]
        else:
            continue
        est = estimate_window(venue, chosen, curves, cfg, today)
        if est is not None:
            out.append(est)
    return out
