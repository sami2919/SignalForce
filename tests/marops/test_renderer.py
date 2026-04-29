"""Smoke test for renderer — renders sample JSON to HTML without API call."""
import json
from pathlib import Path

import pytest

from scripts.marops.models import LifecycleBrief
from scripts.marops.renderer import render_html

_SAMPLE = Path(__file__).parent.parent.parent / "demo" / "veriforce.json"


@pytest.mark.skipif(not _SAMPLE.exists(), reason="demo/veriforce.json not yet committed")
def test_render_html_from_sample(tmp_path: Path):
    payload = json.loads(_SAMPLE.read_text())
    brief = LifecycleBrief.model_validate(payload)
    out = tmp_path / "veriforce.pdf"
    render_html(brief, out)
    html_out = out.with_suffix(".html")
    assert html_out.exists()
    content = html_out.read_text()
    assert "Veriforce" in content
    assert "Tier-2" in content
