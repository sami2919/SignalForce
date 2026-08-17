"""Kana demo CLI — Customer Zero GTM engine + supporting activation brief.

Usage:
    python -m scripts.kana_demo
    python -m scripts.kana_demo --sample
    python -m scripts.kana_demo --brief-only
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from scripts.config_loader import SignalForceConfig, load_config
from scripts.demo_scan import format_grade_table
from scripts.models import ICPScore, Signal
from scripts.scanner_runner import run_all_scanners
from scripts.signal_aggregator import ScoredCompany, aggregate_and_score

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_DIR = ROOT / "examples" / "kana-ai-first"
CONFIG_PATH = EXAMPLE_DIR / "config.yaml"
BRIEF_PATH = EXAMPLE_DIR / "customer-zero-brief.yaml"
SAMPLE_SIGNALS_PATH = EXAMPLE_DIR / "sample_signals.json"
OUT_DIR = ROOT / "out"
DEMO_DIR = ROOT / "demo"
TEMPLATE_DIR = ROOT / "renderer" / "kana"

_PRIMARY_SIGNAL_ORDER = {
    "job_posting": 0,
    "linkedin_activity": 1,
    "funding_event": 2,
    "github_repo": 3,
    "map_frustration": 4,
    "g2_review": 5,
}

_SIGNAL_LABELS = {
    "job_posting": "active hiring signal",
    "linkedin_activity": "leadership activity signal",
    "funding_event": "budget window signal",
    "github_repo": "stack/integration signal",
    "map_frustration": "stack-friction signal",
    "g2_review": "buyer-pain signal",
}


class KanaQueueEntry(BaseModel):
    """Structured queue entry for Kana's Customer Zero operating queue."""

    model_config = ConfigDict(frozen=True)

    company: str
    grade: ICPScore
    combined_score: float
    icp_fit: float
    signal_count: int
    signal_types: list[str]
    why_now: str
    recommended_titles: list[str]
    outbound_route: str
    message_angle: str
    experiment_tag: str
    hubspot_sync: str
    next_action: str
    source_urls: list[str] = Field(default_factory=list)


class BriefAgent(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    responsibility: str
    output: str


class BriefStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    day: str
    channel: str
    goal: str
    owner: str


class KanaCustomerZeroBrief(BaseModel):
    """Supporting artifact that shows how Kana would use its own platform."""

    model_config = ConfigDict(frozen=True)

    title: str
    audience: str
    objective: str
    why_now: list[str]
    agents: list[BriefAgent]
    channel_plan: list[BriefStep]
    experiments: list[str]
    hubspot_writeback: list[str]
    aeo_signals: list[str]
    success_metrics: list[str]
    next_48_hours: list[str]


def run_kana_scan(
    *,
    lookback_days: int | None = None,
    sample: bool = False,
) -> tuple[SignalForceConfig, list[ScoredCompany]]:
    """Run Kana scan from live scanners or sample signals."""
    config = load_config(CONFIG_PATH)

    if lookback_days is not None:
        updated_scanners = {
            name: sc.model_copy(update={"lookback_days": lookback_days})
            for name, sc in config.scanners.items()
        }
        config = config.model_copy(update={"scanners": updated_scanners})

    if sample:
        raw_signals = json.loads(SAMPLE_SIGNALS_PATH.read_text(encoding="utf-8"))
        signals = [Signal.model_validate(item) for item in raw_signals]
    else:
        signals = run_all_scanners(config)

    return config, aggregate_and_score(signals, config)


def build_queue_entries(
    results: list[ScoredCompany],
    config: SignalForceConfig,
) -> list[KanaQueueEntry]:
    """Convert scored companies into an operator-friendly GTM queue."""
    entries: list[KanaQueueEntry] = []
    default_titles = config.icp.target_titles[:3]

    for result in results:
        signal_types = sorted({s.signal_type for s in result.signals}, key=_signal_order)
        primary_type = signal_types[0] if signal_types else "job_posting"
        route = _pick_route(signal_types)
        angle = _pick_angle(result.signals, signal_types)
        entries.append(
            KanaQueueEntry(
                company=result.company_name,
                grade=result.scoring_result.icp_score,
                combined_score=result.scoring_result.combined_score,
                icp_fit=result.icp_fit,
                signal_count=result.scoring_result.signal_count,
                signal_types=signal_types,
                why_now=_summarize_why_now(result.signals, signal_types),
                recommended_titles=_pick_titles(result.signals, signal_types, default_titles),
                outbound_route=route,
                message_angle=angle,
                experiment_tag=_build_experiment_tag(primary_type, route),
                hubspot_sync=_build_hubspot_sync(route),
                next_action=_build_next_action(route),
                source_urls=_unique_urls(result.signals),
            )
        )

    return entries


def format_queue_table(entries: list[KanaQueueEntry]) -> str:
    """Render queue entries as a compact table for walk-in use."""
    if not entries:
        return "  No queue entries generated.\n"

    lines = [
        "",
        "  KANA CUSTOMER ZERO OPERATING QUEUE",
        "",
        f"  {'COMPANY':<24} {'GRADE':<7} {'ROUTE':<18} {'EXPERIMENT':<20} NEXT ACTION",
        "  " + "─" * 108,
    ]
    for entry in entries:
        lines.append(
            f"  {entry.company:<24} "
            f"{entry.grade.value:<7} "
            f"{entry.outbound_route:<18} "
            f"{entry.experiment_tag:<20} "
            f"{entry.next_action}"
        )
    lines.append("  " + "─" * 108)
    return "\n".join(lines)


def load_customer_zero_brief() -> KanaCustomerZeroBrief:
    """Load the deterministic Kana supporting brief from YAML."""
    raw = yaml.safe_load(BRIEF_PATH.read_text(encoding="utf-8"))
    return KanaCustomerZeroBrief.model_validate(raw)


def render_queue_html(entries: list[KanaQueueEntry], company_name: str) -> str:
    """Render HTML for the queue artifact."""
    env = _template_env()
    template = env.get_template("customer_zero_queue.html.j2")
    return template.render(company_name=company_name, entries=entries)


def render_brief_html(brief: KanaCustomerZeroBrief) -> str:
    """Render HTML for the supporting brief."""
    env = _template_env()
    template = env.get_template("customer_zero_brief.html.j2")
    return template.render(brief=brief)


def _template_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )


def _signal_order(signal_type: str) -> int:
    return _PRIMARY_SIGNAL_ORDER.get(signal_type, 99)


def _pick_titles(
    signals: list[Signal],
    signal_types: list[str],
    default_titles: list[str],
) -> list[str]:
    if "job_posting" in signal_types:
        text = " ".join(_signal_text(signal) for signal in signals)
        if "marketing operations" in text or "lifecycle" in text:
            return [
                "VP Marketing Operations",
                "Director of Lifecycle Marketing",
                "Head of Growth",
            ]
        if "seo" in text or "content" in text:
            return ["VP Growth", "Head of Demand Generation", "Director of Content"]
    if "linkedin_activity" in signal_types:
        return ["VP Marketing", "Head of Demand Generation", "CMO"]
    if "funding_event" in signal_types:
        return ["CMO", "VP Growth", "Head of Revenue Operations"]
    return default_titles


def _pick_route(signal_types: list[str]) -> str:
    if "job_posting" in signal_types and "linkedin_activity" in signal_types:
        return "Clay -> Instantly + Valley"
    if "linkedin_activity" in signal_types:
        return "Valley-first LinkedIn"
    if "funding_event" in signal_types:
        return "Clay -> Instantly"
    return "Clay research -> Instantly"


def _pick_angle(signals: list[Signal], signal_types: list[str]) -> str:
    text = " ".join(_signal_text(signal) for signal in signals)
    if "seo" in text or "semrush" in text or "content" in text:
        return "Close the content + AEO gap without adding manual campaign work"
    if "marketing operations" in text or "lifecycle" in text or "automation" in text:
        return "Remove the MOPs bottleneck while keeping the existing stack intact"
    if "linkedin_activity" in signal_types and "ai" in text:
        return "AI-first personalization that augments marketers instead of replacing them"
    if "funding_event" in signal_types:
        return "New budget window: increase at-bats before headcount scales linearly"
    return "Treat demand generation like code: faster experiments, cleaner routing, more at-bats"


def _build_experiment_tag(primary_type: str, route: str) -> str:
    route_token = "linkedin" if "Valley" in route else "email"
    base = {
        "job_posting": "ops-bottleneck",
        "linkedin_activity": "ai-story",
        "funding_event": "budget-window",
        "github_repo": "stack-friction",
        "map_frustration": "migration-pain",
        "g2_review": "buyer-pain",
    }.get(primary_type, "customer-zero")
    return f"{base}-{route_token}-v1"


def _build_hubspot_sync(route: str) -> str:
    if "Valley" in route:
        return (
            "Create company + lead, attach signal summary, set experiment tag, "
            "assign owner, and open LinkedIn follow-up task in HubSpot"
        )
    return (
        "Create company + lead, attach signal summary, set experiment tag, "
        "assign owner, and enroll in outbound sequence from HubSpot source of truth"
    )


def _build_next_action(route: str) -> str:
    if "Valley" in route:
        return "Research champion in Clay, launch LinkedIn touch today, email follow-up within 24h."
    return "Research champion in Clay, verify contact path, launch outbound test within 24h."


def _summarize_why_now(signals: list[Signal], signal_types: list[str]) -> str:
    labels = [_SIGNAL_LABELS.get(signal_type, signal_type) for signal_type in signal_types[:3]]
    snippets: list[str] = []
    for signal in signals[:2]:
        text = _signal_text(signal).strip()
        if text:
            snippets.append(text[:90].rstrip())
    detail = f" Signals observed: {', '.join(labels)}." if labels else ""
    if snippets:
        return f"{' '.join(snippets)}.{detail}"
    return f"Multiple fresh signals indicate a live GTM change window.{detail}"


def _signal_text(signal: Signal) -> str:
    raw = signal.raw_data
    metadata = signal.metadata
    parts: list[str] = []
    for key in ("title", "snippet", "body"):
        value = raw.get(key)
        if isinstance(value, str):
            parts.append(value)
    postings = raw.get("postings", [])
    for posting in postings:
        if isinstance(posting, dict):
            parts.extend(
                str(posting.get(key, "")) for key in ("title", "snippet") if posting.get(key)
            )
    activities = raw.get("activities", [])
    for activity in activities:
        if isinstance(activity, dict):
            parts.extend(
                str(activity.get(key, "")) for key in ("topic", "text") if activity.get(key)
            )
    for key in ("skills_mentioned", "keywords", "job_titles"):
        value = metadata.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return " ".join(part for part in parts if part).strip()


def _unique_urls(signals: list[Signal]) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for signal in signals:
        if signal.source_url not in seen:
            seen.add(signal.source_url)
            urls.append(signal.source_url)
    return urls


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Kana Customer Zero demo — GTM queue + supporting brief",
    )
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--min-grade", choices=["A", "B", "C", "D"], default="B")
    parser.add_argument("--sample", action="store_true", help="Use committed sample signals")
    parser.add_argument(
        "--brief-only", action="store_true", help="Render only the supporting brief"
    )
    args = parser.parse_args(argv)

    brief = load_customer_zero_brief()

    if not args.brief_only:
        config, results = run_kana_scan(lookback_days=args.lookback_days, sample=args.sample)
        grade_order = [ICPScore.A, ICPScore.B, ICPScore.C, ICPScore.D]
        min_idx = grade_order.index(ICPScore(args.min_grade))
        filtered_results = [
            result
            for result in results
            if grade_order.index(result.scoring_result.icp_score) <= min_idx
        ]
        entries = build_queue_entries(filtered_results, config)

        print(f"\nSignalForce — {config.company.name} Customer Zero GTM Engine")
        print("Scanning for AI-first demand generation signals...\n")
        print(format_grade_table(filtered_results))
        print(format_queue_table(entries))

        queue_json = [entry.model_dump(mode="json") for entry in entries]
        queue_html = render_queue_html(entries, config.company.name)
        _write_json(OUT_DIR / "kana-customer-zero.json", queue_json)
        _write_text(OUT_DIR / "kana-customer-zero.html", queue_html)
        print("\n  Queue artifact:")
        print("    out/kana-customer-zero.html")

    brief_json = brief.model_dump(mode="json")
    brief_html = render_brief_html(brief)
    _write_json(OUT_DIR / "kana-agent-brief.json", brief_json)
    _write_text(OUT_DIR / "kana-agent-brief.html", brief_html)
    print("\n  Supporting artifact:")
    print("    out/kana-agent-brief.html")


if __name__ == "__main__":
    _main()
