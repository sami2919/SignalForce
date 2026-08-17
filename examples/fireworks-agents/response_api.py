"""Simple OpenAI Responses API call via Fireworks AI inference."""

import os

from openai import OpenAI


FIREWORKS_BASE_URL = os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
FIREWORKS_MODEL = os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/glm-5p2")
FIREWORKS_API_KEY = "ADD YOUR API KEY HERE!"


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Set {name} before running this script.")
    return value


def main() -> None:
    client = OpenAI(
        base_url=FIREWORKS_BASE_URL,
        api_key=FIREWORKS_API_KEY,
    )

    response = client.responses.create(
        model=FIREWORKS_MODEL,
        input="Write a one-sentence poem about the ocean.",
    )

    print(response.output_text)


if __name__ == "__main__":
    main()
