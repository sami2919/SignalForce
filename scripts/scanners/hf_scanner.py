"""Hugging Face Model Upload Scanner.

Detects organizations uploading trained models to the Hugging Face Hub.
Scans for models tagged with training methods, groups by organization,
scores by upload volume, and returns Signal objects.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta, UTC
from typing import Any

from scripts.api_client import BaseAPIClient
from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hugging Face API client
# ---------------------------------------------------------------------------


class HuggingFaceClient(BaseAPIClient):
    """Hugging Face Hub API client — no authentication required (public API)."""

    BASE_URL = "https://huggingface.co/api"

    def __init__(self, timeout: int = 30) -> None:
        super().__init__(base_url=self.BASE_URL, auth_headers=None, timeout=timeout)

    def list_models(
        self,
        search: str | None = None,
        sort: str = "lastModified",
        direction: int = -1,
        limit: int = 100,
        filter_tag: str | None = None,
    ) -> list[dict]:
        """List models from Hugging Face Hub.

        Args:
            search: Optional free-text search query.
            sort: Field to sort by (default "lastModified").
            direction: Sort direction — -1 for descending (newest first).
            limit: Maximum number of models to return (default 100).
            filter_tag: Filter models by a specific tag (e.g. "ppo", "rlhf").

        Returns:
            List of model dicts from the HF API.
        """
        params: dict[str, Any] = {
            "sort": sort,
            "direction": direction,
            "limit": limit,
        }
        if search:
            params["search"] = search
        if filter_tag:
            params["tags"] = filter_tag

        result = self.get("/models", params=params)
        if isinstance(result, list):
            return result
        return result.get("items", [])

    def get_model_info(self, model_id: str) -> dict:
        """Fetch detailed information for a specific model.

        Args:
            model_id: The model identifier, e.g. "meta-llama/Llama-3-RL-8B".

        Returns:
            Model detail dict from the HF API.
        """
        return self.get(f"/models/{model_id}")


# ---------------------------------------------------------------------------
# Monitor class (internal implementation)
# ---------------------------------------------------------------------------


class HuggingFaceRLMonitor:
    """Monitor that detects organizations uploading trained models to HF Hub.

    Tags and card keywords are driven by ScannerConfig rather than hardcoded constants.
    """

    # Class-level defaults — kept for test compatibility (tests use RL_TRAINING_TAGS directly)
    RL_TRAINING_TAGS: list[str] = [
        "ppo",
        "dpo",
        "grpo",
        "rlhf",
        "reinforcement-learning",
        "reward-model",
        "orpo",
        "kto",
    ]

    def __init__(self, training_tags: list[str] | None = None) -> None:
        self._client = HuggingFaceClient()
        if training_tags is not None:
            self.RL_TRAINING_TAGS = training_tags

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def scan(self, lookback_days: int = 7) -> ScanResult:
        """Run a full Hugging Face model scan.

        Steps:
        1. For each training tag, search HF Hub for models with that tag.
        2. Filter results to models modified within lookback_days.
        3. Filter to models that have a namespace (org or user prefix).
        4. Group by organization namespace.
        5. Deduplicate: same org found via multiple tag searches → one entry.
        6. Score each org by total model count.
        7. Build Signal objects and return ScanResult.

        Args:
            lookback_days: Number of days back to look for new/updated models.

        Returns:
            ScanResult with Signal objects for each qualifying organization.
        """
        started_at = datetime.now(UTC)

        org_models: dict[str, set[str]] = defaultdict(set)
        org_model_details: dict[str, list[dict]] = defaultdict(list)
        total_raw = 0
        errors: list[str] = []

        for tag in self.RL_TRAINING_TAGS:
            try:
                models = self._client.list_models(filter_tag=tag)
            except Exception as exc:
                msg = f"list_models failed for tag '{tag}': {exc}"
                logger.warning(msg)
                errors.append(msg)
                continue

            for model in models:
                model_id: str = model.get("modelId") or model.get("id", "")
                if not self._is_org_model(model_id):
                    continue
                if not self._is_recent(model, lookback_days):
                    continue

                org = model_id.split("/")[0]

                if model_id not in org_models[org]:
                    org_models[org].add(model_id)
                    org_model_details[org].append(model)
                    total_raw += 1

        signals: list[Signal] = []
        for org, model_list in org_model_details.items():
            model_count = len(model_list)
            score = self._score_org(model_count)
            signal = self._create_signal(org, model_list, score)
            signals.append(signal)

        completed_at = datetime.now(UTC)

        return ScanResult(
            scan_type="huggingface_model",
            started_at=started_at,
            completed_at=completed_at,
            signals_found=signals,
            total_raw_results=total_raw,
            total_after_dedup=len(signals),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_org_model(self, model_id: str) -> bool:
        """Return True if the model_id has an org/user namespace prefix."""
        return "/" in model_id

    def _extract_training_method(self, model_info: dict) -> str | None:
        """Extract the first matching training method tag from a model's tag list."""
        tags: list[str] = model_info.get("tags", []) or []
        for tag in tags:
            if tag in self.RL_TRAINING_TAGS:
                return tag
        return None

    def _is_recent(self, model_info: dict, lookback_days: int) -> bool:
        """Return True if the model was last modified within lookback_days."""
        last_modified_raw: str | None = model_info.get("lastModified")
        if not last_modified_raw:
            return False

        try:
            last_modified = datetime.fromisoformat(last_modified_raw.replace("Z", "+00:00"))
        except (ValueError, TypeError) as exc:
            logger.warning("Could not parse lastModified '%s': %s", last_modified_raw, exc)
            return False

        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        return last_modified > cutoff

    def _score_org(self, model_count: int) -> SignalStrength:
        """Score an organization's activity by model upload volume."""
        if model_count >= 4:
            return SignalStrength.STRONG
        if model_count >= 2:
            return SignalStrength.MODERATE
        return SignalStrength.WEAK

    def _create_signal(
        self,
        org: str,
        model_list: list[dict],
        score: SignalStrength,
    ) -> Signal:
        """Build a Signal object for a detected active organization."""
        model_ids = [m.get("modelId") or m.get("id", "") for m in model_list]
        training_methods: list[str] = list(
            filter(None, [self._extract_training_method(m) for m in model_list])
        )
        seen: set[str] = set()
        unique_methods: list[str] = []
        for method in training_methods:
            if method not in seen:
                seen.add(method)
                unique_methods.append(method)

        sorted_models = sorted(
            model_list,
            key=lambda m: m.get("lastModified", ""),
            reverse=True,
        )
        primary_model_id = sorted_models[0].get("modelId") or sorted_models[0].get("id", "")
        source_url = f"https://huggingface.co/{primary_model_id}"

        return Signal(
            signal_type="huggingface_model",
            company_name=org,
            signal_strength=score,
            source_url=source_url,
            raw_data={"models": model_list},
            metadata={
                "model_names": model_ids,
                "training_methods": unique_methods,
                "model_count": len(model_list),
                "org_url": f"https://huggingface.co/{org}",
            },
        )


# ---------------------------------------------------------------------------
# Module-level entry point
# ---------------------------------------------------------------------------


def scan(config: ScannerConfig) -> ScanResult:
    """Run a full Hugging Face Hub scan using configuration.

    Args:
        config: ScannerConfig with training_tags list and lookback_days.

    Returns:
        ScanResult with Signal objects for each qualifying organization.
    """
    monitor = HuggingFaceRLMonitor(training_tags=config.training_tags or config.keywords)
    return monitor.scan(config.lookback_days)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan Hugging Face Hub for organisations uploading trained models.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Number of days back to scan for new or updated model uploads.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to write results as JSON.",
    )
    parser.add_argument(
        "--min-strength",
        type=int,
        default=1,
        choices=[1, 2, 3],
        help="Minimum signal strength to include (1=WEAK, 2=MODERATE, 3=STRONG).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the Hugging Face model scanner."""
    from scripts.config_loader import load_config

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    sf_config = load_config()
    scanner_cfg = sf_config.scanners.get("huggingface")
    if scanner_cfg is None:
        raise SystemExit("No 'huggingface' scanner configured in config.yaml")

    if args.lookback_days != 7:
        scanner_cfg = scanner_cfg.model_copy(update={"lookback_days": args.lookback_days})

    result = scan(scanner_cfg)

    filtered_signals = [s for s in result.signals_found if s.signal_strength >= args.min_strength]

    print(f"Scan complete — {len(filtered_signals)} signals (min strength: {args.min_strength})")
    print(f"  Raw results:  {result.total_raw_results}")
    print(f"  After dedup:  {result.total_after_dedup}")
    print(f"  After filter: {len(filtered_signals)}")

    for signal in sorted(filtered_signals, key=lambda s: s.signal_strength, reverse=True):
        strength_label = SignalStrength(signal.signal_strength).name
        print(f"  [{strength_label:8s}] {signal.company_name} — {signal.source_url}")

    if args.output:
        output_data = {
            "scan_id": result.scan_id,
            "scan_type": result.scan_type,
            "started_at": result.started_at.isoformat(),
            "completed_at": result.completed_at.isoformat(),
            "total_raw_results": result.total_raw_results,
            "total_after_dedup": result.total_after_dedup,
            "signals": [
                {
                    "company_name": s.company_name,
                    "signal_strength": s.signal_strength,
                    "source_url": s.source_url,
                    "metadata": s.metadata,
                }
                for s in filtered_signals
            ],
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
