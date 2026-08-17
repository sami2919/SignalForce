"""CLI report generator for SignalForce analytics.

Usage:
    python -m scripts.analytics_report --last-days 30 --format markdown
    python -m scripts.analytics_report --last-days 7 --format json --out out/analytics.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from scripts.analytics import (
    get_breakdown,
    get_funnel_metrics,
    get_recommendations,
    get_stale_signals,
)
from scripts.db import create_db_engine, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SignalForce analytics reports.")
    parser.add_argument("--db-url", default=None, help="SQLAlchemy DB URL. Defaults to local DB.")
    parser.add_argument("--last-days", type=int, default=30, help="Lookback window in days.")
    parser.add_argument("--campaign-id", type=int, default=None, help="Optional campaign filter.")
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Report output format.",
    )
    parser.add_argument("--out", default=None, help="Optional output path.")
    args = parser.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.last_days)
    date_range = (start, end)

    engine = create_db_engine(args.db_url)
    init_db(engine)

    payload = build_report_payload(
        engine,
        campaign_id=args.campaign_id,
        date_range=date_range,
        last_days=args.last_days,
    )
    rendered = (
        json.dumps(payload, indent=2, sort_keys=True)
        if args.format == "json"
        else render_markdown(payload)
    )

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


def build_report_payload(
    engine: Any,
    *,
    campaign_id: int | None,
    date_range: tuple[datetime, datetime],
    last_days: int,
) -> dict[str, Any]:
    """Collect all analytics needed by both Markdown and JSON reports."""
    return {
        "window": {
            "last_days": last_days,
            "start": date_range[0].isoformat(),
            "end": date_range[1].isoformat(),
            "campaign_id": campaign_id,
        },
        "funnel": get_funnel_metrics(
            engine,
            campaign_id=campaign_id,
            date_range=date_range,
        ),
        "breakdowns": {
            "signal_type": get_breakdown(
                engine,
                group_by="signal_type",
                campaign_id=campaign_id,
                date_range=date_range,
            ),
            "icp_grade": get_breakdown(
                engine,
                group_by="icp_grade",
                campaign_id=campaign_id,
                date_range=date_range,
            ),
            "template": get_breakdown(
                engine,
                group_by="template_used",
                campaign_id=campaign_id,
                date_range=date_range,
            ),
            "experiment": get_breakdown(
                engine,
                group_by="experiment_tag",
                campaign_id=campaign_id,
                date_range=date_range,
            ),
        },
        "stale_signals": get_stale_signals(engine, campaign_id=campaign_id),
        "recommendations": get_recommendations(
            engine,
            campaign_id=campaign_id,
            date_range=date_range,
        ),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a compact Markdown analytics report."""
    funnel = payload["funnel"]
    totals = funnel["totals"]
    rates = funnel["rates"]
    window = payload["window"]

    lines = [
        f"# SignalForce Analytics Report - Last {window['last_days']} Days",
        "",
        "## Funnel",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key in [
        "signals",
        "outreach",
        "delivered",
        "opened",
        "clicked",
        "replies",
        "positive_replies",
        "meetings",
        "deals",
        "bounced",
        "unsubscribed",
    ]:
        lines.append(f"| {_label(key)} | {totals[key]} |")

    lines.extend(["", "## Rates", "", "| Rate | Value |", "|---|---:|"])
    for key, value in rates.items():
        lines.append(f"| {_label(key)} | {value:.1%} |")

    for title, rows in [
        ("Signal Type", payload["breakdowns"]["signal_type"]),
        ("ICP Grade", payload["breakdowns"]["icp_grade"]),
        ("Template", payload["breakdowns"]["template"]),
        ("Experiment", payload["breakdowns"]["experiment"]),
    ]:
        lines.extend(["", f"## By {title}", ""])
        lines.extend(_render_breakdown_table(rows))

    lines.extend(["", "## Recommendations", ""])
    if payload["recommendations"]:
        for item in payload["recommendations"]:
            lines.append(f"- **{item['severity']} / {item['category']}**: {item['message']}")
    else:
        lines.append("- No recommendations yet. Add more outcome data or lower sample thresholds.")

    lines.extend(["", "## Stale Signals", ""])
    stale = payload["stale_signals"]
    if stale:
        lines.extend(["| Company | Signal | Grade | Age Hours |", "|---|---|---:|---:|"])
        for item in stale[:20]:
            lines.append(
                "| {company_name} | {signal_type} | {icp_grade} | {age_hours} |".format(
                    company_name=item["company_name"],
                    signal_type=item["signal_type"],
                    icp_grade=item["icp_grade"] or "",
                    age_hours=item["age_hours"],
                )
            )
    else:
        lines.append("- No stale unworked signals.")

    return "\n".join(lines)


def _render_breakdown_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["No data."]

    lines = [
        "| Value | Signals | Outreach | Replies | Positive Outcomes | Meetings | Meeting Rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows[:10]:
        lines.append(
            "| {value} | {signals} | {outreach} | {replies} | {positive_outcomes} | "
            "{meetings} | {meeting_rate:.1%} |".format(**row)
        )
    return lines


def _label(value: str) -> str:
    return value.replace("_", " ").title()


if __name__ == "__main__":
    main()
