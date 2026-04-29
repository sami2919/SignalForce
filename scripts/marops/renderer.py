"""Render a LifecycleBrief to HTML via Jinja2.

Adapted from conversion-walkin/render.py. HTML is the load-bearing artifact —
Chrome Save-as-PDF renders better than WeasyPrint on macOS.
WeasyPrint is attempted as best-effort if installed.
"""
from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from scripts.marops.models import LifecycleBrief

_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "renderer" / "marops"


def render_html(brief: LifecycleBrief, out_path: Path) -> None:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml", "j2"]),
    )
    template = env.get_template("lifecycle_brief.html.j2")

    payload = brief.model_dump()
    html = template.render(
        prospect={"name": brief.prospect, "url": brief.prospect_url},
        vertical=brief.vertical,
        campaign_name=brief.campaign_name,
        objective=brief.objective,
        lifecycle_stage=brief.lifecycle_stage,
        segment=payload["segment"],
        touches=payload["touches"],
        optimization_triggers=payload["optimization_triggers"],
        pipeline_projection=payload["pipeline_projection"],
        generated_at=brief.meta.get("generated_at", ""),
        meta=brief.meta,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    html_out = out_path.with_suffix(".html")
    html_out.write_text(html)
    print(f"[ok] wrote {html_out}")

    try:
        from weasyprint import HTML  # type: ignore

        HTML(string=html, base_url=str(_TEMPLATE_DIR)).write_pdf(str(out_path))
        print(f"[ok] wrote {out_path}")
    except (ImportError, OSError) as exc:
        print(f"[skip pdf] {type(exc).__name__}: open {html_out} in Chrome → ⌘P → Save as PDF")
