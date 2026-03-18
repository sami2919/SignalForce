"""Signal stacking and composite scoring engine.

Combines outputs from all scanners, groups signals by company, calculates
composite scores, and produces ranked CompanyProfile objects.

Usage:
    # As a module
    from scripts.signal_stacker import SignalStacker, stack_from_files

    stacker = SignalStacker(config=load_config())
    profiles = stacker.stack_signals(scan_results)

    # As a CLI
    python -m scripts.signal_stacker --inputs scan1.json scan2.json --output ranked.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from scripts.config_loader import SignalForceConfig, load_config
from scripts.intent_scorer import IntentScorer
from scripts.models import (
    CompanyProfile,
    ICPScore,
    ScanResult,
    Signal,
)

logger = logging.getLogger(__name__)

# Suffixes to strip during name normalization (order matters — strip longest first
# to avoid partial matches, e.g. "technologies" before "tech").
_STRIP_SUFFIXES: tuple[str, ...] = (
    "technologies",
    "research",
    "labs",
    "corp",
    "inc",
    "ltd",
    "llc",
    "ai",
)

# Multiplier table keyed by number of unique source types.
_MULTIPLIER: dict[int, float] = {1: 1.0, 2: 1.5, 3: 2.0}
_MULTIPLIER_FALLBACK = 3.0  # 4+ unique source types


class SignalStacker:
    """Groups signals by company and calculates composite scores.

    Args:
        known_domains: Optional mapping of normalized company name → domain.
            Improves matching when signals lack a ``company_domain`` field.
            E.g. ``{"deepmind": "deepmind.com", "google deepmind": "deepmind.com"}``
        use_intent_scoring: When True, use IntentScorer (intent-weighted, recency-decayed)
            to calculate composite scores. When False (default), use the legacy formula
            (sum of strengths × breadth multiplier) for backward compatibility.
    """

    def __init__(
        self,
        known_domains: dict[str, str] | None = None,
        use_intent_scoring: bool = False,
        config: SignalForceConfig | None = None,
    ) -> None:
        self._known_domains: dict[str, str] = known_domains or {}
        self.use_intent_scoring: bool = use_intent_scoring
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stack_signals(self, scan_results: list[ScanResult]) -> list[CompanyProfile]:
        """Combine scanner outputs into ranked, deduplicated CompanyProfiles.

        Steps:
        1. Flatten all signals from every ScanResult.
        2. Group by company using domain/name matching.
        3. Build a CompanyProfile per group with composite score + ICP grade.
        4. Return list sorted by composite_signal_score descending.
        """
        if not scan_results:
            return []

        all_signals: list[Signal] = [
            signal for scan in scan_results for signal in scan.signals_found
        ]

        groups: dict[str, list[Signal]] = self._group_signals_by_company(all_signals)

        profiles: list[CompanyProfile] = []
        for group_key, signals in groups.items():
            if self.use_intent_scoring and self._config is not None:
                scoring_result = IntentScorer(self._config).score_signals(signals, icp_fit=0.0)
                composite = scoring_result.combined_score
                icp = scoring_result.icp_score
            else:
                composite = self._calculate_composite_score(signals)
                icp = self._determine_icp_score(composite)

            # Prefer the first domain found among the group's signals; fall back
            # to the group key (which is either a domain or a normalized name).
            domain = self._resolve_domain(group_key, signals)

            # Use the most-specific company name in the group (longest after trim).
            company_name = max((s.company_name for s in signals), key=len)

            profiles.append(
                CompanyProfile(
                    company_name=company_name,
                    domain=domain,
                    icp_score=icp,
                    composite_signal_score=composite,
                    signals=list(signals),
                )
            )

        profiles.sort(key=lambda p: p.composite_signal_score, reverse=True)
        return profiles

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _calculate_composite_score(self, signals: list[Signal]) -> float:
        """Return composite score = sum(strengths) × breadth multiplier.

        Breadth multiplier rewards diversity of signal sources:
            1 unique type  → ×1.0
            2 unique types → ×1.5
            3 unique types → ×2.0
            4+ unique types → ×3.0
        """
        base = sum(int(s.signal_strength) for s in signals)
        unique_types = len({s.signal_type for s in signals})
        multiplier = _MULTIPLIER.get(unique_types, _MULTIPLIER_FALLBACK)
        return base * multiplier

    def _determine_icp_score(self, composite: float) -> ICPScore:
        """Map composite score to ICP grade A/B/C/D."""
        if composite >= 9.0:
            return ICPScore.A
        if composite >= 5.0:
            return ICPScore.B
        if composite >= 2.0:
            return ICPScore.C
        return ICPScore.D

    # ------------------------------------------------------------------
    # Company matching / grouping
    # ------------------------------------------------------------------

    def _normalize_name(self, name: str) -> str:
        """Lowercase, strip common legal/type suffixes, strip punctuation/whitespace."""
        # Remove punctuation (commas, periods, etc.) but keep word characters and spaces.
        cleaned = re.sub(r"[^\w\s]", " ", name.lower())

        # Iteratively strip known suffixes from the end of the token sequence.
        words = cleaned.split()
        changed = True
        while changed:
            changed = False
            if words and words[-1] in _STRIP_SUFFIXES:
                words.pop()
                changed = True

        return " ".join(words).strip()

    def _match_company(
        self,
        name1: str,
        domain1: str | None,
        name2: str,
        domain2: str | None,
    ) -> bool:
        """Return True if two company references refer to the same entity.

        Priority 1 — both have domains: match iff domains are equal (definitive).
        Priority 2 — name-based: exact normalized match OR one name is a
                      substring of the other (handles "DeepMind" ↔ "Google DeepMind").
        """
        if domain1 and domain2:
            return domain1.lower() == domain2.lower()

        n1 = self._normalize_name(name1)
        n2 = self._normalize_name(name2)

        if n1 == n2:
            return True
        if n1 in n2 or n2 in n1:
            return True

        return False

    def _group_signals_by_company(self, signals: list[Signal]) -> dict[str, list[Signal]]:
        """Partition signals into groups, one per distinct company.

        Group keys are domains (preferred) or normalized names (fallback).
        For each signal we enrich its domain via ``known_domains`` before grouping.
        """
        # group_key → list[Signal]
        groups: dict[str, list[Signal]] = {}
        # group_key → (canonical_name, canonical_domain)
        group_meta: dict[str, tuple[str, str | None]] = {}

        for signal in signals:
            domain = signal.company_domain or self._lookup_known_domain(signal.company_name)
            matched_key: str | None = None

            for key, (meta_name, meta_domain) in group_meta.items():
                if self._match_company(signal.company_name, domain, meta_name, meta_domain):
                    matched_key = key
                    break

            if matched_key is not None:
                groups[matched_key].append(signal)
                # Promote to a real domain key if we now have one.
                if domain and not group_meta[matched_key][1]:
                    new_key = domain
                    if new_key != matched_key:
                        groups[new_key] = groups.pop(matched_key)
                        group_meta[new_key] = (signal.company_name, domain)
                        del group_meta[matched_key]
            else:
                key = domain if domain else self._normalize_name(signal.company_name)
                groups[key] = [signal]
                group_meta[key] = (signal.company_name, domain)

        return groups

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------

    def _lookup_known_domain(self, name: str) -> str | None:
        """Check whether this company name appears in the known_domains map."""
        normalized = self._normalize_name(name)
        # Try exact normalized key first.
        if normalized in self._known_domains:
            return self._known_domains[normalized]
        # Try original lowercase key.
        lower = name.lower().strip()
        return self._known_domains.get(lower)

    def _resolve_domain(self, group_key: str, signals: list[Signal]) -> str:
        """Return the best domain string for a CompanyProfile.

        Prefers a real domain from the signals, then the group key itself.
        """
        for signal in signals:
            if signal.company_domain:
                return signal.company_domain
        return group_key


# ---------------------------------------------------------------------------
# Standalone function
# ---------------------------------------------------------------------------


def stack_from_files(
    file_paths: list[str],
    use_intent_scoring: bool = False,
    config: SignalForceConfig | None = None,
) -> list[CompanyProfile]:
    """Load ScanResult JSON files, deserialize, and run the stacking pipeline.

    Args:
        file_paths: Paths to JSON files each containing a serialized ScanResult.
        use_intent_scoring: When True, use intent-weighted scoring. Defaults to False
            for backward compatibility.
        config: Optional SignalForceConfig for intent scoring weights and thresholds.

    Returns:
        Ranked list of CompanyProfile objects.
    """
    if not file_paths:
        return []

    scan_results: list[ScanResult] = []
    for path in file_paths:
        try:
            raw = Path(path).read_text(encoding="utf-8")
            scan_results.append(ScanResult.model_validate_json(raw))
        except Exception:
            logger.exception("Failed to load ScanResult from %s", path)
            raise

    return SignalStacker(use_intent_scoring=use_intent_scoring, config=config).stack_signals(
        scan_results
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="signal_stacker",
        description="Stack scanner outputs into ranked company profiles.",
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        metavar="FILE",
        help="One or more ScanResult JSON files to stack.",
    )
    parser.add_argument(
        "--output",
        required=True,
        metavar="FILE",
        help="Path to write the ranked CompanyProfile list as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    config = load_config()
    logger.info("Loading %d scan result file(s)…", len(args.inputs))
    profiles = stack_from_files(args.inputs, config=config)
    logger.info("Stacked into %d company profiles.", len(profiles))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([json.loads(p.model_dump_json()) for p in profiles], indent=2),
        encoding="utf-8",
    )
    logger.info("Wrote ranked profiles to %s", output_path)


if __name__ == "__main__":
    main(sys.argv[1:])
