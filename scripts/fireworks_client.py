"""Fireworks AI client — OpenAI-compatible inference via the OpenAI Agents SDK.

This module provides the building blocks for using Fireworks AI as an
alternative LLM backend in SignalForce, following the pattern from the
`openai-agents-sdk-with-fireworks` reference (examples/fireworks-agents/).

Key insight from the reference repo:
    Fireworks model IDs contain slashes (e.g. "accounts/fireworks/models/glm-5p2").
    Passing that directly as an Agents SDK model name triggers:
        agents.exceptions.UserError: Unknown prefix: accounts
    The workaround is to construct an explicit OpenAIChatCompletionsModel with
    an AsyncOpenAI client pointed at the Fireworks base URL.

Usage (async):
    from scripts.fireworks_client import build_fireworks_agent, run_agent

    agent = build_fireworks_agent(
        name="SignalAnalyzer",
        instructions="You analyze sales signals and rank accounts.",
        tools=[my_function_tool],
    )
    result = await run_agent(agent, "Rank the top 5 accounts by intent score.")

Usage (sync convenience):
    from scripts.fireworks_client import run_fireworks_agent_sync

    result = run_fireworks_agent_sync(
        instructions="You are a helpful assistant.",
        prompt="Summarize these signals.",
        tools=[],
    )
"""

from __future__ import annotations

import logging
import os
from typing import Any

from openai import AsyncOpenAI

from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    Runner,
    function_tool,
    set_tracing_disabled,
)

from scripts.config import get_config

logger = logging.getLogger(__name__)

# Tracing posts to OpenAI's servers; disable it since we're using Fireworks.
set_tracing_disabled(True)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api.fireworks.ai/inference/v1"
DEFAULT_MODEL = "accounts/fireworks/models/glm-5p2"


def _get_fireworks_api_key() -> str:
    """Resolve the Fireworks API key from env or config.

    Priority:
        1. FIREWORKS_API_KEY env var
        2. config.fireworks_api_key (from .env via AppConfig)

    Raises:
        RuntimeError: If no key is found.
    """
    key = os.getenv("FIREWORKS_API_KEY")
    if key:
        return key

    cfg = get_config()
    if cfg.fireworks_api_key:
        return cfg.fireworks_api_key

    raise RuntimeError(
        "No Fireworks API key found. Set FIREWORKS_API_KEY in your environment or .env file."
    )


def _get_base_url() -> str:
    return os.getenv("FIREWORKS_BASE_URL", DEFAULT_BASE_URL)


def _get_model() -> str:
    return os.getenv("FIREWORKS_MODEL", DEFAULT_MODEL)


# ---------------------------------------------------------------------------
# Client / model construction
# ---------------------------------------------------------------------------


def build_openai_client() -> AsyncOpenAI:
    """Create an AsyncOpenAI client pointed at the Fireworks inference endpoint."""
    return AsyncOpenAI(
        base_url=_get_base_url(),
        api_key=_get_fireworks_api_key(),
    )


def build_chat_model(
    model: str | None = None,
    client: AsyncOpenAI | None = None,
) -> OpenAIChatCompletionsModel:
    """Construct an OpenAIChatCompletionsModel backed by Fireworks.

    This is the critical pattern: instead of passing "accounts/fireworks/models/glm-5p2"
    as a string model name (which the Agents SDK misinterprets as a provider prefix),
    we wrap it in an explicit OpenAIChatCompletionsModel with our Fireworks client.
    """
    return OpenAIChatCompletionsModel(
        model=model or _get_model(),
        openai_client=client or build_openai_client(),
    )


def build_fireworks_agent(
    name: str,
    instructions: str,
    tools: list[Any] | None = None,
    model: str | None = None,
    client: AsyncOpenAI | None = None,
) -> Agent:
    """Create an OpenAI Agents SDK Agent backed by Fireworks AI inference.

    Args:
        name: Agent name (e.g. "SignalAnalyzer", "BrieferAgent").
        instructions: System prompt / instructions for the agent.
        tools: List of @function_tool-decorated functions or Tool objects.
        model: Override the Fireworks model (default: accounts/fireworks/models/glm-5p2).
        client: Override the AsyncOpenAI client (useful for testing).

    Returns:
        Agent configured to use Fireworks for inference.
    """
    return Agent(
        name=name,
        instructions=instructions,
        model=build_chat_model(model=model, client=client),
        tools=tools or [],
    )


# ---------------------------------------------------------------------------
# Runner helpers
# ---------------------------------------------------------------------------


async def run_agent(agent: Agent, prompt: str) -> str:
    """Run an agent asynchronously and return the final output text."""
    result = await Runner.run(agent, prompt)
    return result.final_output


def run_agent_sync(agent: Agent, prompt: str) -> str:
    """Run an agent synchronously and return the final output text."""
    result = Runner.run_sync(agent, prompt)
    return result.final_output


def run_fireworks_agent_sync(
    name: str,
    instructions: str,
    prompt: str,
    tools: list[Any] | None = None,
    model: str | None = None,
) -> str:
    """One-shot convenience: build + run an agent synchronously via Fireworks.

    Args:
        name: Agent name.
        instructions: System prompt for the agent.
        prompt: The user message / task to run.
        tools: Optional list of function tools.
        model: Optional model override.

    Returns:
        The agent's final output as a string.
    """
    agent = build_fireworks_agent(
        name=name,
        instructions=instructions,
        tools=tools,
        model=model,
    )
    return run_agent_sync(agent, prompt)


# ---------------------------------------------------------------------------
# Simple Responses API call (sync, no agents SDK)
# ---------------------------------------------------------------------------


def fireworks_completion(
    prompt: str,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """Make a simple text completion via Fireworks using the OpenAI SDK.

    Uses the synchronous OpenAI client (not the Agents SDK) for cases where
    you just need a raw completion without tool-calling or agent orchestration.

    Args:
        prompt: The user message.
        model: Model override (default: accounts/fireworks/models/glm-5p2).
        max_tokens: Max tokens to generate.
        temperature: Sampling temperature.

    Returns:
        The generated text.
    """
    from openai import OpenAI  # sync client

    client = OpenAI(
        base_url=_get_base_url(),
        api_key=_get_fireworks_api_key(),
    )
    response = client.chat.completions.create(
        model=model or _get_model(),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Example function tool (from the reference repo)
# ---------------------------------------------------------------------------


@function_tool
def list_files(path: str = ".") -> str:
    """List the files in the given directory path."""
    try:
        entries = sorted(os.listdir(path))
    except OSError as exc:
        return f"Error reading directory '{path}': {exc}"
    return "\n".join(entries)
