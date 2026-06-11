"""Tests for funding_seed_scanner — TDD RED phase."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.scanners.base import ScannerConfig, SignalStrength


def _make_config(seed_file_path: str) -> ScannerConfig:
    return ScannerConfig(
        enabled=True,
        module="scripts.scanners.funding_seed_scanner",
        lookback_days=30,
        keywords=["B2B SaaS"],
        custom_params={"seed_file": seed_file_path},
    )


def _write_seeds(tmp_path: Path, content: dict) -> Path:
    seed_file = tmp_path / "funding_seeds.yaml"
    seed_file.write_text(yaml.dump(content))
    return seed_file


class TestFundingSeedScanner:
    def test_loads_signals_from_seed_file(self, tmp_path):
        """Scanner reads funding_seeds.yaml and emits funding_event signals."""
        from scripts.scanners.funding_seed_scanner import scan

        seed_file = _write_seeds(tmp_path, {
            "events": [
                {
                    "company": "Vanta",
                    "amount_usd": 150_000_000,
                    "stage": "Series D",
                    "snippet": "Vanta raises $150M Series D to expand enterprise security compliance.",
                    "source_url": "https://techcrunch.com/vanta-series-d",
                }
            ]
        })
        config = _make_config(str(seed_file))
        result = scan(config)
        assert len(result.signals_found) == 1
        sig = result.signals_found[0]
        assert sig.company_name == "Vanta"
        assert sig.signal_type == "funding_event"

    def test_empty_seed_file_returns_no_signals(self, tmp_path):
        """Empty events list returns a ScanResult with zero signals."""
        from scripts.scanners.funding_seed_scanner import scan

        seed_file = _write_seeds(tmp_path, {"events": []})
        config = _make_config(str(seed_file))
        result = scan(config)
        assert result.signals_found == []
        assert result.errors == []

    def test_missing_seed_file_returns_error(self, tmp_path):
        """Missing seed file returns a ScanResult with an error, no exception raised."""
        from scripts.scanners.funding_seed_scanner import scan

        config = _make_config(str(tmp_path / "nonexistent.yaml"))
        result = scan(config)
        assert result.signals_found == []
        assert len(result.errors) == 1

    def test_large_funding_round_scores_strong(self, tmp_path):
        """Funding >= $50M should score STRONG signal strength."""
        from scripts.scanners.funding_seed_scanner import scan

        seed_file = _write_seeds(tmp_path, {
            "events": [
                {
                    "company": "BigCo",
                    "amount_usd": 100_000_000,
                    "stage": "Series C",
                    "snippet": "Raised $100M.",
                    "source_url": "https://example.com",
                }
            ]
        })
        config = _make_config(str(seed_file))
        result = scan(config)
        assert result.signals_found[0].signal_strength == SignalStrength.STRONG

    def test_small_funding_round_scores_weak(self, tmp_path):
        """Funding < $10M should score WEAK signal strength."""
        from scripts.scanners.funding_seed_scanner import scan

        seed_file = _write_seeds(tmp_path, {
            "events": [
                {
                    "company": "SmallCo",
                    "amount_usd": 5_000_000,
                    "stage": "Seed",
                    "snippet": "Raised $5M seed round.",
                    "source_url": "https://example.com",
                }
            ]
        })
        config = _make_config(str(seed_file))
        result = scan(config)
        assert result.signals_found[0].signal_strength == SignalStrength.WEAK

    def test_medium_funding_round_scores_moderate(self, tmp_path):
        """Funding >= $10M and < $50M should score MODERATE signal strength."""
        from scripts.scanners.funding_seed_scanner import scan

        seed_file = _write_seeds(tmp_path, {
            "events": [
                {
                    "company": "MidCo",
                    "amount_usd": 25_000_000,
                    "stage": "Series B",
                    "snippet": "Raised $25M Series B.",
                    "source_url": "https://example.com",
                }
            ]
        })
        config = _make_config(str(seed_file))
        result = scan(config)
        assert result.signals_found[0].signal_strength == SignalStrength.MODERATE
