"""Dynamic scanner dispatch engine.

Loads scanner modules specified in config.yaml and runs them.
Each scanner implements: scan(ScannerConfig) -> ScanResult.
"""

from __future__ import annotations

import importlib
import logging

from scripts.config_loader import ScannerConfig, SignalForceConfig
from scripts.models import ScanResult, Signal

logger = logging.getLogger(__name__)


def run_all_scanners(config: SignalForceConfig) -> list[Signal]:
    """Run all enabled scanners and return a flat list of Signal objects.

    Each scanner returns a ScanResult (containing signals_found: list[Signal]).
    This runner flattens them into a single list for downstream processing.
    Failed scanners are logged and skipped.
    """
    all_signals: list[Signal] = []

    for name, scanner_config in config.scanners.items():
        if not scanner_config.enabled:
            logger.info("Scanner '%s' disabled, skipping", name)
            continue

        if not _has_keywords(scanner_config):
            logger.warning(
                "Scanner '%s' enabled but no keywords configured — will return no results",
                name,
            )

        try:
            module = importlib.import_module(scanner_config.module)
            scan_fn = getattr(module, "scan")
            result: ScanResult = scan_fn(scanner_config)
            logger.info("Scanner '%s' returned %d signals", name, len(result.signals_found))
            all_signals.extend(result.signals_found)
        except ModuleNotFoundError:
            logger.error("Scanner module '%s' not found for '%s'", scanner_config.module, name)
        except AttributeError:
            logger.error("Module '%s' has no scan() function", scanner_config.module)
        except Exception:
            logger.exception("Scanner '%s' failed, skipping", name)

    return all_signals


def _has_keywords(config: ScannerConfig) -> bool:
    """Check if a scanner config has any search terms configured."""
    return bool(
        config.keywords
        or config.topics
        or config.libraries
        or config.queries
        or config.training_tags
        or config.card_keywords
        or config.titles
        or config.skills
    )
