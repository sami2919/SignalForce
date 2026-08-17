"""SignalForce x Fireworks ICP Demo.

A single-command demo that uses Fireworks AI as the inference layer to turn
raw GTM signals into structured account intelligence for companies that look
like strong Fireworks-fit customers.

SignalForce uses Fireworks to convert raw GTM signals into structured account
intelligence for AI companies with inference-heavy workloads.

Usage:
    export FIREWORKS_API_KEY=your_key_here
    python scripts/demo_fireworks_icp.py

Output:
    - Polished terminal display of ranked Fireworks-fit accounts
    - Structured JSON saved to outputs/fireworks_icp_demo.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from scripts.fireworks_client import fireworks_completion
from scripts.marops.fireworks_icp_schema import FireworksICPBrief

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
ICP_PATH = ROOT / "configs" / "icps" / "fireworks_ai.yaml"
ACCOUNTS_PATH = ROOT / "examples" / "fireworks-demo" / "accounts.json"
OUTPUT_PATH = ROOT / "outputs" / "fireworks_icp_demo.json"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_json(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_prompt(account: dict[str, Any], icp: dict[str, Any]) -> str:
    """Build the prompt that asks Fireworks to produce a FireworksICPBrief."""
    schema_json = json.dumps(FireworksICPBrief.model_json_schema(), indent=2)
    icp_json = json.dumps(icp, indent=2)
    account_json = json.dumps(account, indent=2)

    return f"""You are running inside SignalForce, an open-source GTM intelligence workflow.

SignalForce has been configured around the Fireworks AI ICP.

Your task:
Analyze this account and return a structured Fireworks ICP brief.

Fireworks ICP:
{icp_json}

Account:
{account_json}

Return JSON only matching this schema:
{schema_json}

Rules:
- Be specific to the account signals.
- Focus on inference speed, cost, scale, open-source model flexibility, fine-tuning, and production AI.
- Do not make unsupported claims.
- Keep the LinkedIn message under 500 characters.
- Make the tone casual, technical, and builder-oriented.
- Return ONLY the JSON object, no markdown, no commentary."""


# ---------------------------------------------------------------------------
# Account analysis
# ---------------------------------------------------------------------------


def analyze_account(account: dict[str, Any], icp: dict[str, Any]) -> FireworksICPBrief:
    """Analyze a single account against the Fireworks ICP using Fireworks inference.

    Calls fireworks_completion() to get raw JSON text from the model, then
    validates it against the FireworksICPBrief schema.
    """
    prompt = build_prompt(account, icp)

    result = fireworks_completion(
        prompt=prompt,
        max_tokens=4096,
        temperature=0.2,
    )

    # fireworks_completion returns a string — parse and validate
    cleaned = result.strip()
    if cleaned.startswith("```"):
        # Strip markdown code fences if present
        lines = cleaned.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Fireworks did not return valid JSON for account "
            f"'{account.get('account_name', '?')}'. Parse error: {exc}. "
            f"Raw output (first 500 chars): {result[:500]!r}"
        ) from exc

    return FireworksICPBrief.model_validate(parsed)


# ---------------------------------------------------------------------------
# Terminal output
# ---------------------------------------------------------------------------


def print_brief(index: int, brief: FireworksICPBrief) -> None:
    """Print a polished brief to the terminal."""
    print(f"  {index}. {brief.account_name} — {brief.fit_score}/100")
    print(f"     Intent:           {brief.intent_level}")
    print(f"     Why now:           {brief.why_now}")
    print(f"     Fireworks fit:     {brief.fireworks_relevance}")
    print(f"     Persona:           {brief.recommended_persona}")
    print(f"     Outbound angle:    {brief.outbound_angle}")
    print(f"     LinkedIn message:  {brief.linkedin_message}")
    print(f"     Cold email:        {brief.cold_email_subject}")
    print()


# ---------------------------------------------------------------------------
# Main demo entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the Fireworks ICP demo: load config + accounts, analyze, print, save."""
    icp = load_yaml(ICP_PATH)
    accounts = load_json(ACCOUNTS_PATH)

    print()
    print("  \U0001f525 SignalForce x Fireworks ICP Demo")
    print()
    print("  Using Fireworks as the inference layer to turn raw GTM signals")
    print("  into structured account intelligence.")
    print()
    print(f"  Loaded ICP:          {icp['name']}")
    print(f"  Loaded demo accounts: {len(accounts)}")
    print()
    print("  Analyzing accounts with Fireworks AI...")
    print()

    briefs: list[FireworksICPBrief] = []
    for account in accounts:
        try:
            brief = analyze_account(account, icp)
            briefs.append(brief)
        except (RuntimeError, Exception) as exc:
            print(f"  [error] Failed to analyze '{account.get('account_name', '?')}': {exc}")
            print()

    # Sort by fit score, descending
    briefs.sort(key=lambda b: b.fit_score, reverse=True)

    print("  Top Fireworks-fit accounts:")
    print()

    for index, brief in enumerate(briefs, start=1):
        print_brief(index, brief)

    # Save structured output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps([brief.model_dump() for brief in briefs], indent=2),
        encoding="utf-8",
    )

    print(f"  Saved structured output to {OUTPUT_PATH}")
    print()
    print("  ---")
    print("  SignalForce uses Fireworks to convert raw signals into predictable JSON fields:")
    print("  fit_score, intent_level, matched_signals, why_now, fireworks_relevance,")
    print("  recommended_persona, outbound_angle, linkedin_message")
    print()
    print("  This demonstrates Fireworks powering a real business workflow, not just a chatbot.")
    print()


if __name__ == "__main__":
    main()
