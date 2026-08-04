"""Tests for renderer — renders sample JSON to HTML without API call."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.marops.models import LifecycleBrief
from scripts.marops.renderer import render_html

_SAMPLE = Path(__file__).parent.parent.parent / "demo" / "veriforce.json"


@pytest.mark.skipif(not _SAMPLE.exists(), reason="demo/veriforce.json not yet committed")
def test_render_html_from_sample(tmp_path: Path):
    payload = json.loads(_SAMPLE.read_text())
    brief = LifecycleBrief.model_validate(payload)
    out = tmp_path / "veriforce.html"
    render_html(brief, out)
    assert out.exists()
    content = out.read_text()
    assert "Veriforce" in content
    assert "Tier-2" in content


@pytest.mark.skipif(not _SAMPLE.exists(), reason="demo/veriforce.json not yet committed")
def test_render_html_weasyprint_oserror_is_nonfatal(tmp_path: Path):
    payload = json.loads(_SAMPLE.read_text())
    brief = LifecycleBrief.model_validate(payload)
    out = tmp_path / "veriforce.html"

    mock_wp = MagicMock()
    mock_wp.HTML.side_effect = OSError("no font")
    with patch.dict(sys.modules, {"weasyprint": mock_wp}):
        render_html(brief, out)

    assert out.exists(), "HTML must be written even when WeasyPrint raises OSError"
