"""Render a LifecycleBrief to HTML via Jinja2.

HTML is the load-bearing artifact —
Chrome Save-as-PDF renders better than WeasyPrint on macOS.
WeasyPrint is attempted as best-effort if installed.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from scripts.marops.models import LifecycleBrief

_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "renderer" / "marops"


def render_html(brief: LifecycleBrief, html_path: Path) -> None:
    """Render brief to HTML at html_path. Attempts WeasyPrint PDF as best-effort."""
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
        why_now=payload.get("why_now"),
    )

    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html)
    print(f"[ok] wrote {html_path}")

    pdf_path = html_path.with_suffix(".pdf")
    try:
        from weasyprint import HTML  # type: ignore

        HTML(string=html, base_url=str(_TEMPLATE_DIR)).write_pdf(str(pdf_path))
        print(f"[ok] wrote {pdf_path}")
    except (ImportError, OSError) as exc:
        print(f"[skip pdf] {type(exc).__name__}: open {html_path} in Chrome → ⌘P → Save as PDF")
