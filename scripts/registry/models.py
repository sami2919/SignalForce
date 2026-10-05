"""Types for source resolution."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

SourceType = Literal["careers", "docs", "changelog", "pricing", "blog"]

# Why a candidate was accepted or rejected. Diagnostic, not cosmetic: a rise in
# blocked_by_robots or soft_404 tells you something changed upstream, and
# Phase 3's source health needs to tell "no source exists" apart from "source broke".
ResolutionOutcome = Literal[
    "resolved",
    "not_found",  # no path returned 200
    "soft_404",  # 200, but the body is an error page or the homepage
    "low_content",  # 200 and real, but too little text to hash meaningfully
    "blocked_by_robots",  # robots.txt disallows every candidate path
    "fetch_error",  # network/timeout on every candidate
]


class ResolvedSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_type: SourceType
    url: str  # FINAL url after redirects, not the probed one
    method: str  # "heuristic" for now; sitemap/llm are later ladder rungs
    confidence: float


class SourceAttempt(BaseModel):
    """Per-source-type result. Present even on failure — absence is not a signal."""

    model_config = ConfigDict(frozen=True)

    source_type: SourceType
    outcome: ResolutionOutcome
    url: str | None = None
    detail: str = ""


class ResolutionReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain: str
    sources: list[ResolvedSource]
    attempts: list[SourceAttempt]
    homepage_reachable: bool

    @property
    def resolved_types(self) -> set[str]:
        return {s.source_type for s in self.sources}
