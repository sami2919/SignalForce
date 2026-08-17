"""OpenAI Agents SDK example using Fireworks AI inference.

Lists files in the repository directory by giving the agent a function tool.
"""

import os

from openai import AsyncOpenAI

from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    Runner,
    function_tool,
    set_tracing_disabled,
)


FIREWORKS_BASE_URL = os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
FIREWORKS_MODEL = os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/glm-5p2")
FIREWORKS_API_KEY = "ADD YOUR API KEY HERE!"


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Set {name} before running this script.")
    return value


# Tracing posts to OpenAI's servers; disable it since we're using Fireworks.
set_tracing_disabled(True)


@function_tool
def list_files(path: str = ".") -> str:
    """List the files in the given directory path."""
    try:
        entries = sorted(os.listdir(path))
    except OSError as exc:
        return f"Error reading directory '{path}': {exc}"
    return "\n".join(entries)


def build_agent() -> Agent:
    client = AsyncOpenAI(
        base_url=FIREWORKS_BASE_URL,
        api_key=FIREWORKS_API_KEY,
    )

    return Agent(
        name="FileLister",
        instructions=(
            "You are a helpful agent that lists files in directories. "
            "Use the list_files tool whenever the user asks about files."
        ),
        model=OpenAIChatCompletionsModel(
            model=FIREWORKS_MODEL,
            openai_client=client,
        ),
        tools=[list_files],
    )


def main() -> None:
    result = Runner.run_sync(
        build_agent(),
        "List the files in the current repository directory.",
    )
    print(result.final_output)


if __name__ == "__main__":
    main()
