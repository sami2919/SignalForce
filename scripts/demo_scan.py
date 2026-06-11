"""End-to-end demo scan CLI.

Runs all enabled scanners, groups signals by company, computes ICP fit,
scores with the Gojiberry formula, and prints a ranked A/B/C/D grade table.

Usage:
    python -m scripts.demo_scan
    python -m scripts.demo_scan --lookback-days 14 --min-grade B
    python -m scripts.demo_scan --json-output
"""

from __future__ import annotations

import argparse
import json
import logging

from scripts.config_loader import load_config
from scripts.models import ICPScore
from scripts.scanner_runner import run_all_scanners
from scripts.signal_aggregator import ScoredCompany, aggregate_and_score

logger = logging.getLogger(__name__)

_GRADE_STARS = {
    ICPScore.A: "★★★★",
    ICPScore.B: "★★★ ",
    ICPScore.C: "★★  ",
    ICPScore.D: "★   ",
}
_GRADE_ORDER = [ICPScore.A, ICPScore.B, ICPScore.C, ICPScore.D]

_TYPE_ABBREV: dict[str, str] = {
    "job_posting": "job",
    "g2_review": "g2",
    "funding_event": "$",
    "github_repo": "gh",
    "linkedin_activity": "li",
    "map_frustration": "map",
    "huggingface_model": "hf",
    "arxiv_paper": "arxiv",
}


def run_demo_scan(lookback_days: int | None = None) -> list[ScoredCompany]:
    """Run all enabled scanners and return sorted ScoredCompany list."""
    config = load_config()

    if lookback_days is not None:
        updated_scanners = {
            name: sc.model_copy(update={"lookback_days": lookback_days})
            for name, sc in config.scanners.items()
        }
        config = config.model_copy(update={"scanners": updated_scanners})

    print(f"\nSignalForce — {config.company.name} ICP Scanner")
    print("Scanning for Marketo/HubSpot migration signals...\n")

    signals = run_all_scanners(config)
    return aggregate_and_score(signals, config)


def format_grade_table(results: list[ScoredCompany]) -> str:
    """Format ranked results as a printable grade table string."""
    if not results:
        return "  No signals found. Check API keys and scanner config.\n"

    lines = [
        "",
        f"  {'GRADE':<8} {'COMPANY':<28} {'ICP FIT':>8} {'SIGNALS':>8} {'SCORE':>7}  TYPES",
        "  " + "─" * 75,
    ]
    for r in results:
        grade = r.scoring_result.icp_score.value
        stars = _GRADE_STARS.get(r.scoring_result.icp_score, "    ")
        unique_types = sorted({s.signal_type for s in r.signals})
        type_str = " ".join(_TYPE_ABBREV.get(t, t[:4]) for t in unique_types)
        lines.append(
            f"  [{grade}] {stars}  {r.company_name:<24} "
            f"{r.icp_fit:>7.1f}  {r.scoring_result.signal_count:>6}  "
            f"{r.scoring_result.combined_score:>6.1f}  {type_str}"
        )
    lines.append("  " + "─" * 75)
    return "\n".join(lines)


def _main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="SignalForce demo scan — find and grade MAP migration prospects",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Override lookback window in days for all scanners",
    )
    parser.add_argument(
        "--min-grade",
        choices=["A", "B", "C", "D"],
        default="C",
        help="Minimum grade to display (default: C)",
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Output results as JSON instead of a table",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    results = run_demo_scan(lookback_days=args.lookback_days)

    min_idx = _GRADE_ORDER.index(ICPScore(args.min_grade))
    filtered = [r for r in results if _GRADE_ORDER.index(r.scoring_result.icp_score) <= min_idx]

    if args.json_output:
        output = [
            {
                "company": r.company_name,
                "grade": r.scoring_result.icp_score.value,
                "icp_fit": r.icp_fit,
                "combined_score": r.scoring_result.combined_score,
                "signal_count": r.scoring_result.signal_count,
                "signal_types": sorted({s.signal_type for s in r.signals}),
            }
            for r in filtered
        ]
        print(json.dumps(output, indent=2))
    else:
        print(format_grade_table(filtered))

        if filtered:
            top = filtered[0]
            print(
                f"\n  Top prospect: {top.company_name} "
                f"[Grade {top.scoring_result.icp_score.value}] "
                f"— score {top.scoring_result.combined_score:.1f}, "
                f"ICP fit {top.icp_fit:.1f}"
            )
            print("\n  Generate a lifecycle brief:")
            print("    python -m scripts.marops.cli hubspot-ceiling\n")


if __name__ == "__main__":
    _main()
