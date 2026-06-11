"""Funding Event Manual Seed Scanner.

Reads pre-seeded funding events from config/funding_seeds.yaml and emits
them as funding_event signals. Use to inject real funding rounds for
the demo without needing a live Crunchbase API key.

Seed file path can be overridden via scanner custom_params:
    custom_params:
      seed_file: config/funding_seeds.yaml  # default
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)

_DEFAULT_SEED_FILE = Path(__file__).parent.parent.parent / "config" / "funding_seeds.yaml"

_STRONG_THRESHOLD_USD = 50_000_000  # >= $50M → STRONG
_MODERATE_THRESHOLD_USD = 10_000_000  # >= $10M → MODERATE
# < $10M → WEAK


def _score(amount_usd: int) -> SignalStrength:
    if amount_usd >= _STRONG_THRESHOLD_USD:
        return SignalStrength.STRONG
    if amount_usd >= _MODERATE_THRESHOLD_USD:
        return SignalStrength.MODERATE
    return SignalStrength.WEAK


def scan(config: ScannerConfig) -> ScanResult:
    started_at = datetime.now(timezone.utc)

    seed_file_override = config.custom_params.get("seed_file")
    seed_file = Path(seed_file_override) if seed_file_override else _DEFAULT_SEED_FILE

    if not seed_file.exists():
        return ScanResult(
            scan_type="funding_event",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
            errors=[f"Seed file not found: {seed_file}"],
        )

    with open(seed_file) as f:
        data = yaml.safe_load(f)

    events = data.get("events", []) if data else []
    signals: list[Signal] = []

    for event in events:
        company = event.get("company", "").strip()
        if not company:
            continue

        amount_usd = int(event.get("amount_usd", 0))
        stage = event.get("stage", "Unknown")
        snippet = event.get("snippet", "")
        source_url = event.get("source_url", "")

        signals.append(
            Signal(
                signal_type="funding_event",
                company_name=company,
                signal_strength=_score(amount_usd),
                source_url=source_url,
                raw_data={
                    "amount_usd": amount_usd,
                    "stage": stage,
                    "snippet": snippet,
                },
                metadata={
                    "source_type": "funding_manual_seed",
                    "funding_stage": stage,
                    "amount_usd": amount_usd,
                },
            )
        )

    logger.info("Funding seed scanner: %d signals loaded from %s", len(signals), seed_file)

    return ScanResult(
        scan_type="funding_event",
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        signals_found=signals,
        total_raw_results=len(events),
        total_after_dedup=len(signals),
        errors=[],
    )
