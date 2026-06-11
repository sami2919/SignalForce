"""G2 Manual Seed Scanner.

Reads company names + review snippets you collected manually from G2 and
emits them as g2_review signals. Bypasses DataDome entirely — you do the
browser session, paste what you find here.

Seed file: config/g2_seeds.yaml
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)

_SEED_FILE = Path(__file__).parent.parent.parent / "config" / "g2_seeds.yaml"

_STRONG_KEYWORDS = {
    "migration", "replacing", "switching", "evaluating", "replacement",
    "alternative", "alternatives", "migrating", "moved off",
}
_MODERATE_KEYWORDS = {
    "expensive", "complex", "slow", "frustrating", "difficult",
    "overhead", "bloated", "ceiling", "too much", "painful", "clunky",
}


def _score(snippet: str, star_rating: int) -> SignalStrength:
    lower = snippet.lower()
    for kw in _STRONG_KEYWORDS:
        if kw in lower:
            return SignalStrength.STRONG
    if star_rating <= 2:
        for kw in _MODERATE_KEYWORDS:
            if kw in lower:
                return SignalStrength.STRONG
    for kw in _MODERATE_KEYWORDS:
        if kw in lower:
            return SignalStrength.MODERATE
    return SignalStrength.WEAK


def scan(config: ScannerConfig) -> ScanResult:
    started_at = datetime.now(timezone.utc)

    if not _SEED_FILE.exists():
        return ScanResult(
            scan_type="g2_review",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
            errors=[f"Seed file not found: {_SEED_FILE}"],
        )

    with open(_SEED_FILE) as f:
        data = yaml.safe_load(f)

    reviews = data.get("reviews", []) if data else []
    signals: list[Signal] = []

    for review in reviews:
        company = review.get("company", "").strip()
        # Skip the placeholder example entry
        if not company or company == "Example Corp":
            continue

        snippet = review.get("snippet", "")
        vendor = review.get("vendor", "Unknown MAP")
        star_rating = int(review.get("star_rating", 2))
        review_url = review.get("review_url", "")

        signals.append(Signal(
            signal_type="g2_review",
            company_name=company,
            signal_strength=_score(snippet, star_rating),
            source_url=review_url,
            raw_data={
                "snippet": snippet,
                "rating": star_rating,
                "vendor": vendor,
            },
            metadata={
                "source_type": "g2_manual_seed",
                "product_mentioned": vendor,
                "star_rating": star_rating,
            },
        ))

    logger.info("G2 seed scanner: %d signals loaded from %s", len(signals), _SEED_FILE)

    return ScanResult(
        scan_type="g2_review",
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        signals_found=signals,
        total_raw_results=len(reviews),
        total_after_dedup=len(signals),
        errors=[],
    )
