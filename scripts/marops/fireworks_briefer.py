"""Fireworks AI briefer — alternative to the Claude-based briefer.py.

Uses the OpenAI Agents SDK with Fireworks AI as the inference backend to
generate lifecycle campaign briefs. This provides a cheaper/faster alternative
to the Anthropic Claude path, especially useful for high-volume brief generation.

The Fireworks briefer uses a structured JSON output approach (via the agent's
instructions) instead of Claude's tool_use mechanism, then validates the result
against the same LifecycleBrief Pydantic schema.

Usage:
    export FIREWORKS_API_KEY=...
    python -m scripts.marops.cli veriforce --backend fireworks

Or directly:
    from scripts.marops.fireworks_briefer import generate_brief
    from scripts.marops.models import MarOpsCampaignConfig
    brief = generate_brief(config)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from scripts.fireworks_client import build_fireworks_agent, run_agent_sync
from scripts.marops.models import (
    LifecycleBrief,
    MarOpsCampaignConfig,
    OptimizationTrigger,
    compute_why_now,
)

logger = logging.getLogger(__name__)

MAX_TOKENS = 8192

_SYSTEM_INSTRUCTIONS = """You are a senior MarOps architect at a top-tier B2B SaaS company.
You produce lifecycle campaign briefs in the exact shape that Conversion's platform consumes:
Salesforce + warehouse segmentation → multi-touch sequence with agent assignments
(execution / QA / optimization) → optimization triggers → pipeline projection.

Quality bar:
1. Every touch must specify personalization tokens and QA rules. Vague placeholders are rejected.
2. Agent assignments must be non-overlapping: execution owns sends, QA owns scoring/suppression, optimization owns variant selection.
3. Segment filters must reference real Salesforce field conventions (SObject.Field__c syntax).
4. Optimization triggers must be actionable conditions, not observations.
5. Pipeline projection must include a downside scenario.

You MUST respond with a single valid JSON object matching this exact schema (no markdown, no commentary):

{
  "segment": {
    "name": "string",
    "salesforce_filters": ["SObject.Field__c = 'value'", ...],
    "warehouse_traits": ["trait_name:operator:value", ...],
    "exclusions": ["exclusion criteria", ...],
    "estimated_size": "string (e.g. ~450 accounts)"
  },
  "touches": [
    {
      "step": 1,
      "channel": "email|in_app_banner|ae_task|sms|linkedin",
      "agent": "execution|qa|optimization",
      "timing": "string (e.g. Day 0, 9am local)",
      "subject": "string",
      "body_brief": "string (2-3 sentences)",
      "personalization_tokens": ["{{token}}", ...],
      "qa_rules": ["rule", ...],
      "success_metric": "string"
    }
  ],
  "optimization_triggers": [
    {"condition": "string", "action": "string"}
  ],
  "pipeline_projection": {
    "expected_renewals": "string",
    "ae_efficiency": "string",
    "campaign_runtime": "string",
    "downside": "string (mandatory downside scenario)"
  },
  "meta": {}
}

Produce at least 3 touches. Each touch must have all required fields populated."""

_PLATFORM_PRIORS = """## Conversion Platform Architecture

Conversion is an AI-native B2B marketing automation platform. Key architectural facts:

**Data layer:**
- Salesforce two-way sync: account/contact read + AE task write
- Warehouse (Snowflake/BigQuery) sync: product engagement traits, intent data
- Real-time segmentation with suppression rules and deduplication

**Agent model (three non-overlapping roles):**
- Execution agent: owns send timing, channel selection, personalization token injection
- QA agent: owns scoring, suppression logic, spam-gate checks, deduplication
- Optimization agent: owns A/B variant selection, bandit reallocation, cohort re-segmentation

**Touch channels:** email, in_app_banner, ae_task, sms, linkedin"""


def generate_brief(config: MarOpsCampaignConfig) -> LifecycleBrief:
    """Generate a lifecycle campaign brief using Fireworks AI.

    This is the Fireworks alternative to scripts.marops.briefer.generate_brief.
    It uses the OpenAI Agents SDK with a Fireworks-backed model instead of
    Claude's tool_use mechanism. The agent is instructed to output structured JSON,
    which is then validated against the same LifecycleBrief schema.

    Args:
        config: MarOpsCampaignConfig loaded from YAML.

    Returns:
        LifecycleBrief validated against the Pydantic schema.

    Raises:
        RuntimeError: If the Fireworks API key is missing or the response
                      cannot be parsed as valid JSON matching the schema.
    """
    # Build the why-now context
    why_now_context = ""
    if config.why_now_signals:
        lines = ["## Why Now — Active Buying Signals\n"]
        for s in config.why_now_signals:
            days = s.get("days_ago", 0)
            lines.append(
                f"- [{s.get('signal_type', 'signal').upper()}] {s.get('description', '')} "
                f"({days}d ago, source: {s.get('source', 'unknown')})"
            )
        lines.append(
            "\nReference these signals in the objective, segment rationale, and "
            "optimization triggers. The buying window is active — the campaign must "
            "move fast. Include a 'conference_meet' optimization trigger if a "
            "conference signal is present."
        )
        why_now_context = "\n" + "\n".join(lines)

    user_message = f"""## Campaign Config

- **Prospect:** {config.prospect} ({config.prospect_url})
- **Vertical:** {config.vertical}
- **Campaign name:** {config.campaign_name}
- **Lifecycle stage:** {config.lifecycle_stage}
- **Objective:** {config.objective}
- **Segment description:** {config.segment_description}
- **Requested touch count:** {config.num_touches}
{why_now_context}
Produce the full lifecycle campaign brief as a single JSON object. Do not include
markdown code fences or any text outside the JSON object."""

    instructions = f"{_SYSTEM_INSTRUCTIONS}\n\n{_PLATFORM_PRIORS}"

    agent = build_fireworks_agent(
        name="MarOpsBriefer",
        instructions=instructions,
        tools=[],
    )

    raw_output = run_agent_sync(agent, user_message)

    # Parse the JSON output — strip any accidental markdown fences
    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        # Remove markdown code fences
        lines = cleaned.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Fireworks agent did not return valid JSON. Parse error: {exc}. "
            f"Raw output (first 500 chars): {raw_output[:500]!r}"
        ) from exc

    # Build the LifecycleBrief with the same schema as the Claude path
    return LifecycleBrief(
        prospect=config.prospect,
        prospect_url=config.prospect_url,
        vertical=config.vertical,
        campaign_name=config.campaign_name,
        objective=config.objective,
        lifecycle_stage=config.lifecycle_stage,
        segment=payload["segment"],
        touches=payload["touches"],
        optimization_triggers=[OptimizationTrigger(**t) for t in payload["optimization_triggers"]],
        pipeline_projection=payload["pipeline_projection"],
        why_now=compute_why_now(config.why_now_signals),
        meta={
            **payload.get("meta", {}),
            "model": "fireworks",
            "backend": "fireworks",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
