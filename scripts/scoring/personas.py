"""Job title -> persona subcategory classification.

Sajwal (Rippling, 28:49): job titles map to persona subcategories. ADR-0017
Decision 3 is the spec -- the plan named this file and its purpose but gave
no implementation; everything here is designed from scratch, matching the
eventual `personas` table shape (`id, tenant_id, name, title_patterns JSONB,
seniority_min`) 1:1 so a future wiring task can convert DB rows into
`PersonaDefinition` with a direct field copy, the same pattern
`ScoreComponent`/`DetectedChange`/`ProbeOutcome` already established.

No `contacts` table exists yet (Phase 5 scope), so this module classifies a
bare title string, not a `Contact` row -- pure, no DB coupling, same scoping
`score_account` had before its own wiring task.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

# Keyword -> seniority tier, highest match wins when a title matches
# keywords at multiple tiers. A starting point, not a calibrated model --
# same footing as _SOURCE_PRIORITY (ADR-0009) and the signal_type weight
# table (ADR-0016) -- extend the keyword lists as real title data is seen.
_SENIORITY_KEYWORDS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (5, ("chief", "ceo", "cto", "cfo", "coo", "cmo", "cro", "president")),
    (4, ("vp", "vice president", "svp", "evp")),
    (3, ("director", "head of")),
    (2, ("manager", "lead", "principal")),
)
_DEFAULT_SENIORITY = 1


class PersonaDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    # Case-insensitive WHOLE-WORD(S) matched against a title; ANY match
    # qualifies. Not a bare substring match -- see _contains_keyword.
    title_patterns: tuple[str, ...]
    seniority_min: int


def _contains_keyword(text: str, keyword: str) -> bool:
    """Word-boundary match, not a bare substring check.

    A bare `keyword in text` check is a real bug, not a theoretical one --
    reproduced directly: "cto" is a substring of "director" (di-REC-TO-r),
    and "coo" is a substring of "coordinator" (COO-rdinator), so a naive
    substring match classifies a Director or a Coordinator as C-suite. Same
    class of defect as extractor.py's numeric-id substring bug (a digit run
    matched anywhere in a URL instead of a whole path segment) -- anchoring
    to word boundaries is the fix there and the fix here.
    """
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def seniority_level(title: str) -> int:
    """Infer a seniority tier (1-5, higher = more senior) from keywords in
    a job title. Case-insensitive whole-word match; the HIGHEST matching
    tier wins when a title matches keywords at multiple tiers -- a title
    naming multiple roles is at least as senior as its most senior-sounding
    component. Defaults to tier 1 (individual contributor) when nothing
    matches."""
    lowered = title.lower()
    best = _DEFAULT_SENIORITY
    for tier, keywords in _SENIORITY_KEYWORDS:
        if tier <= best:
            continue
        if any(_contains_keyword(lowered, keyword) for keyword in keywords):
            best = tier
    return best


def classify_persona(title: str, personas: list[PersonaDefinition]) -> PersonaDefinition | None:
    """Return the first persona (by input list order) whose title_patterns
    match `title` and whose seniority_min is satisfied. `None` if nothing
    matches -- a title matching no configured persona is a real, expected
    outcome, not an error.

    First-match-by-input-order, not "best match": no specificity signal
    exists in the input to rank matches by (title_patterns are unordered,
    unweighted strings), so ranking is entirely the caller's responsibility
    via how it orders `personas` (ADR-0017 Decision 3).
    """
    lowered = title.lower()
    title_seniority = seniority_level(title)

    for persona in personas:
        if title_seniority < persona.seniority_min:
            continue
        if any(_contains_keyword(lowered, pattern.lower()) for pattern in persona.title_patterns):
            return persona

    return None
