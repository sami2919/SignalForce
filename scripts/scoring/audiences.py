"""Composable signal predicates.

Sajwal (Rippling, 29:26): "every single signal can be stacked to build an
audience... whatever is your money-making combo."

A recursive JSON predicate rather than a fixed score threshold, because the
useful query is "hiring field marketers AND raised in 30d" — a shape no single
scalar can express.

ADR-0017 Decisions 1-2 correct two real gaps in the plan's reference
`evaluate`: a predicate with more than one recognized key (e.g.
`{"and": [...], "min_score": 50}`, plausible from a caller merging predicate
fragments) silently evaluated only whichever key an if-chain reached first and
dropped the rest with no error -- exactly the "structurally valid, silently
wrong" shape this project keeps finding elsewhere (soft-404, accounts_probed,
the differ's silent-scalar-skip). Fixed by requiring exactly one recognized
key per predicate dict. A non-dict predicate now raises TypeError at the
recursion level that actually received it, not several frames downstream.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

_RECOGNIZED_KEYS = ("and", "or", "not", "has_signal", "min_score")


class AccountFacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: int
    signals: list[str]
    score: float


def evaluate(predicate: dict, facts: AccountFacts) -> bool:
    """Recursively evaluate a predicate against an account's facts.

    Exactly one of `and`/`or`/`not`/`has_signal`/`min_score` must be present
    (ADR-0017 Decision 1) -- zero or more than one raises `ValueError`.
    """
    if not isinstance(predicate, dict):
        raise TypeError(f"predicate must be a dict, got {type(predicate).__name__}: {predicate!r}")

    present = [key for key in _RECOGNIZED_KEYS if key in predicate]
    if len(present) == 0:
        raise ValueError(f"Unknown predicate: {predicate!r} (no recognized key present)")
    if len(present) > 1:
        raise ValueError(
            f"Ambiguous predicate: {predicate!r} has more than one recognized key {present} "
            "-- wrap separate conditions in their own 'and'/'or' list instead of merging keys "
            "into one dict"
        )

    key = present[0]
    if key == "and":
        return all(evaluate(p, facts) for p in predicate["and"])
    if key == "or":
        return any(evaluate(p, facts) for p in predicate["or"])
    if key == "not":
        return not evaluate(predicate["not"], facts)
    if key == "has_signal":
        return predicate["has_signal"] in facts.signals
    # key == "min_score"
    return facts.score >= predicate["min_score"]
