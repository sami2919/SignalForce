"""Single structured-output LLM helper: model choice, thinking, fallbacks, cost logging.

Verified against anthropic 2.8.0: ``client.beta.messages.parse`` accepts ``fallbacks`` and
``betas``, so server-side fallbacks are used.
"""

import logging
from typing import TypeVar

from anthropic import Anthropic
from pydantic import BaseModel

from scripts.hospitality.budget import CallBudget
from scripts.hospitality.config import HospitalityConfig, load_config

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_CALL_BUDGET: CallBudget | None = None


class LLMRefusal(RuntimeError):
    """Raised when the model refuses to answer."""


def _budget(cfg: HospitalityConfig) -> CallBudget:
    global _CALL_BUDGET
    if _CALL_BUDGET is None:
        _CALL_BUDGET = CallBudget("claude_calls", cfg.budgets["claude_calls"])
    return _CALL_BUDGET


def reset_budget() -> None:
    """Reset the per-run Claude call budget (tests, new run)."""
    global _CALL_BUDGET
    _CALL_BUDGET = None


def spend_call(n: int = 1) -> None:
    """Spend from the shared Claude call budget (for the one non-parse call path: web search)."""
    _budget(load_config()).spend(n)


def structured(
    model_cls: type[T],
    *,
    system: str,
    user: str,
    role: str = "extract",
    effort: str = "low",
    client: Anthropic | None = None,
) -> T:
    """Call Claude and return a validated instance of model_cls."""
    cfg = load_config()
    _budget(cfg).spend()
    client = client or Anthropic()
    msg = client.beta.messages.parse(
        model=cfg.models[role],
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=model_cls,
    )
    usage = getattr(msg, "usage", None)
    logger.info(
        "claude call role=%s model=%s input=%s output=%s cache_read=%s",
        role,
        cfg.models[role],
        getattr(usage, "input_tokens", None),
        getattr(usage, "output_tokens", None),
        getattr(usage, "cache_read_input_tokens", None),
    )
    if getattr(msg, "stop_reason", None) == "refusal":
        raise LLMRefusal(f"model refused (role={role})")
    return msg.parsed_output
