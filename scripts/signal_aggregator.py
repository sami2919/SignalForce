"""Signal aggregator — groups scanner output by company and produces grades.

Pipeline:
    list[Signal]
        → group by company_name
        → compute ICP fit via icp_fit_scorer
        → compute intent + combined score via IntentScorer
        → sort by combined_score descending
        → return list[ScoredCompany]
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from scripts.config_loader import SignalForceConfig
from scripts.icp_fit_scorer import compute_icp_fit
from scripts.intent_scorer import IntentScorer, ScoringResult
from scripts.models import Signal


@dataclass(frozen=True)
class ScoredCompany:
    """A company with aggregated signals and a computed grade."""

    company_name: str
    signals: list[Signal]
    icp_fit: float
    scoring_result: ScoringResult


def aggregate_and_score(
    signals: list[Signal],
    config: SignalForceConfig,
) -> list[ScoredCompany]:
    """Group signals by company, compute ICP fit, score, and return sorted results.

    Args:
        signals:  Flat list of Signal objects from one or more scanners.
        config:   Loaded SignalForceConfig (supplies scoring weights/thresholds).

    Returns:
        List of ScoredCompany objects sorted by combined_score descending.
    """
    if not signals:
        return []

    blocklist = {name.lower() for name in config.filters.company_blocklist}

    by_company: dict[str, list[Signal]] = defaultdict(list)
    for signal in signals:
        if signal.company_name.lower() not in blocklist:
            by_company[signal.company_name].append(signal)

    scorer = IntentScorer(config)
    results: list[ScoredCompany] = []

    for company_name, company_signals in by_company.items():
        icp_fit = compute_icp_fit(company_signals)
        scoring_result = scorer.score_signals(company_signals, icp_fit=icp_fit)
        results.append(
            ScoredCompany(
                company_name=company_name,
                signals=company_signals,
                icp_fit=icp_fit,
                scoring_result=scoring_result,
            )
        )

    return sorted(results, key=lambda r: r.scoring_result.combined_score, reverse=True)
