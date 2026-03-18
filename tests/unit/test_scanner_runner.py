"""Tests for dynamic scanner dispatch."""

from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch
import logging

import pytest

from scripts.config_loader import load_config, ScannerConfig
from scripts.models import ScanResult, Signal, SignalStrength
from scripts.scanner_runner import run_all_scanners, _has_keywords

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_signal(signal_type: str = "github") -> Signal:
    return Signal(
        signal_type=signal_type,
        company_name="Test Co",
        signal_strength=SignalStrength.STRONG,
        source_url="https://example.com",
        raw_data={},
    )


def _make_scan_result(signals: list[Signal] | None = None) -> ScanResult:
    now = datetime.now(UTC)
    return ScanResult(
        scan_type="github",
        started_at=now,
        completed_at=now,
        signals_found=signals or [_make_signal()],
        total_raw_results=1,
        total_after_dedup=1,
    )


class TestRunAllScanners:
    def test_skips_disabled_scanner(self) -> None:
        config = load_config(_FIXTURES / "sample_config.yaml")
        with patch("scripts.scanner_runner.importlib") as mock_imp:
            run_all_scanners(config)
            mock_imp.import_module.assert_called_once()
            call_arg = mock_imp.import_module.call_args[0][0]
            assert "github" in call_arg

    def test_handles_missing_module(self, caplog: pytest.LogCaptureFixture) -> None:
        config = load_config(_FIXTURES / "sample_config.yaml")
        with caplog.at_level(logging.ERROR):
            signals = run_all_scanners(config)
        assert "not found" in caplog.text.lower() or len(signals) == 0

    def test_handles_scanner_exception(self) -> None:
        config = load_config(_FIXTURES / "sample_config.yaml")
        mock_module = MagicMock()
        mock_module.scan.side_effect = RuntimeError("boom")
        with patch("scripts.scanner_runner.importlib.import_module", return_value=mock_module):
            signals = run_all_scanners(config)
        assert signals == []

    def test_collects_signals_from_scanner(self) -> None:
        config = load_config(_FIXTURES / "sample_config.yaml")
        mock_module = MagicMock()
        mock_module.scan.return_value = _make_scan_result([_make_signal()])
        with patch("scripts.scanner_runner.importlib.import_module", return_value=mock_module):
            signals = run_all_scanners(config)
        assert len(signals) == 1
        assert signals[0].company_name == "Test Co"


class TestHasKeywords:
    def test_empty_config(self) -> None:
        config = ScannerConfig(module="test")
        assert _has_keywords(config) is False

    def test_with_keywords(self) -> None:
        config = ScannerConfig(module="test", keywords=["k1"])
        assert _has_keywords(config) is True

    def test_with_topics(self) -> None:
        config = ScannerConfig(module="test", topics=["t1"])
        assert _has_keywords(config) is True
