"""Claude API call: YAML config → LifecycleBrief via tool_use.

Adapted from conversion-walkin/hypothesizer.py.
Uses prompt caching on the system block — pays cache-write once, reads on every
subsequent prospect. Cost in steady state: ~$0.002 per brief (Sonnet 4.6, cached).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import anthropic

from scripts.marops.models import LifecycleBrief, MarOpsCampaignConfig

MODEL = "claude-sonnet-4-6"
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
5. Pipeline projection must include a downside scenario."""

_PLATFORM_PRIORS = """## Conversion Platform Architecture (cached)

Conversion is an AI-native B2B marketing automation platform. Key architectural facts:

**Data layer:**
- Salesforce two-way sync: account/contact read + AE task write
- Warehouse (Snowflake/BigQuery) sync: product engagement traits, intent data
- Real-time segmentation with suppression rules and deduplication

**Agent model (three non-overlapping roles):**
- Execution agent: owns send timing, channel selection, personalization token injection
- QA agent: owns scoring, suppression logic, spam-gate checks, deduplication
- Optimization agent: owns A/B variant selection, bandit reallocation, cohort re-segmentation

**Touch channels:** email, in_app_banner, ae_task, sms, linkedin

**Brief shape (what the platform consumes):**
- segment: Salesforce SOQL-style filters + warehouse traits + exclusions + estimated_size
- touches: ordered sequence, each with channel/agent/timing/subject/body_brief/tokens/qa_rules/success_metric
- optimization_triggers: event → action rules (intent spike, negative signal, renewal window)
- pipeline_projection: expected_renewals, ae_efficiency, campaign_runtime, downside"""


_BRIEF_TOOL: dict[str, Any] = {
    "name": "submit_lifecycle_brief",
    "description": "Submit the complete lifecycle campaign brief in Conversion platform shape.",
    "input_schema": {
        "type": "object",
        "required": [
            "segment", "touches", "optimization_triggers", "pipeline_projection", "meta"
        ],
        "properties": {
            "segment": {
                "type": "object",
                "required": ["name", "salesforce_filters", "warehouse_traits",
                             "exclusions", "estimated_size"],
                "properties": {
                    "name": {"type": "string"},
                    "salesforce_filters": {"type": "array", "items": {"type": "string"}},
                    "warehouse_traits": {"type": "array", "items": {"type": "string"}},
                    "exclusions": {"type": "array", "items": {"type": "string"}},
                    "estimated_size": {"type": "string"},
                },
            },
            "touches": {
                "type": "array",
                "minItems": 3,
                "items": {
                    "type": "object",
                    "required": ["step", "channel", "agent", "timing", "subject",
                                 "body_brief", "personalization_tokens", "qa_rules",
                                 "success_metric"],
                    "properties": {
                        "step": {"type": "integer"},
                        "channel": {
                            "type": "string",
                            "enum": ["email", "in_app_banner", "ae_task", "sms", "linkedin"],
                        },
                        "agent": {
                            "type": "string",
                            "enum": ["execution", "qa", "optimization"],
                        },
                        "timing": {"type": "string"},
                        "subject": {"type": "string"},
                        "body_brief": {"type": "string"},
                        "personalization_tokens": {"type": "array", "items": {"type": "string"}},
                        "qa_rules": {"type": "array", "items": {"type": "string"}},
                        "success_metric": {"type": "string"},
                    },
                },
            },
            "optimization_triggers": {
                "type": "array",
                "items": {"type": "string"},
            },
            "pipeline_projection": {
                "type": "object",
                "required": ["expected_renewals", "ae_efficiency",
                             "campaign_runtime", "downside"],
                "properties": {
                    "expected_renewals": {"type": "string"},
                    "ae_efficiency": {"type": "string"},
                    "campaign_runtime": {"type": "string"},
                    "downside": {"type": "string"},
                },
            },
            "meta": {"type": "object"},
        },
    },
}


def generate_brief(config: MarOpsCampaignConfig) -> LifecycleBrief:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    user_message = f"""## Campaign Config

- **Prospect:** {config.prospect} ({config.prospect_url})
- **Vertical:** {config.vertical}
- **Campaign name:** {config.campaign_name}
- **Lifecycle stage:** {config.lifecycle_stage}
- **Objective:** {config.objective}
- **Segment description:** {config.segment_description}
- **Requested touch count:** {config.num_touches}

Produce the full lifecycle campaign brief via the submit_lifecycle_brief tool.
Every touch must include specific personalization tokens and QA rules.
Segment filters must use Salesforce SObject.Field__c conventions."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {"type": "text", "text": _SYSTEM_INSTRUCTIONS},
            {
                "type": "text",
                "text": _PLATFORM_PRIORS,
                "cache_control": {"type": "ephemeral"},
            },
        ],
        tools=[_BRIEF_TOOL],
        tool_choice={"type": "tool", "name": "submit_lifecycle_brief"},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        raise RuntimeError(
            f"Claude did not invoke the brief tool. Response content: {response.content!r}"
        )

    payload = tool_block.input
    return LifecycleBrief(
        prospect=config.prospect,
        prospect_url=config.prospect_url,
        vertical=config.vertical,
        campaign_name=config.campaign_name,
        objective=config.objective,
        lifecycle_stage=config.lifecycle_stage,
        segment=payload["segment"],
        touches=payload["touches"],
        optimization_triggers=payload["optimization_triggers"],
        pipeline_projection=payload["pipeline_projection"],
        meta={
            **payload.get("meta", {}),
            "model": MODEL,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
            "cache_creation_input_tokens": getattr(
                response.usage, "cache_creation_input_tokens", 0
            ),
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    )
