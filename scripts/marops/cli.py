"""MarOps brief generator CLI.

Usage:
    export ANTHROPIC_API_KEY=...
    python -m scripts.marops.cli hubspot-ceiling

Reads: examples/marops/<slug>.yaml
Writes: out/<slug>.json, out/<slug>.html
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import anthropic
import yaml

from scripts.marops.briefer import generate_brief
from scripts.marops.models import MarOpsCampaignConfig
from scripts.marops.renderer import render_html

ROOT = Path(__file__).parent.parent.parent
EXAMPLES = ROOT / "examples" / "marops"
OUT = ROOT / "out"


def run(slug: str) -> Path:
    config_path = EXAMPLES / f"{slug}.yaml"
    if not config_path.exists():
        print(f"[error] config not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    raw = yaml.safe_load(config_path.read_text())
    config = MarOpsCampaignConfig.model_validate(raw)

    t0 = time.time()
    print(f"[1/2] generating brief for {config.prospect} (Claude API) ...", flush=True)
    try:
        brief = generate_brief(config)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
    except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
        print(
            f"[error] Claude API failed ({type(exc).__name__}) — open demo/hubspot-ceiling.html instead",
            file=sys.stderr,
        )
        sys.exit(1)
    t1 = time.time()
    print(
        f"      tokens: in={brief.meta['input_tokens']} out={brief.meta['output_tokens']} "
        f"cache_read={brief.meta['cache_read_input_tokens']}  [{t1 - t0:.1f}s]"
    )

    OUT.mkdir(exist_ok=True)
    json_path = OUT / f"{slug}.json"
    json_path.write_text(json.dumps(brief.model_dump(), indent=2))

    html_path = OUT / f"{slug}.html"
    print(f"[2/2] rendering {slug}.html ...", flush=True)
    render_html(brief, html_path)

    t2 = time.time()
    print(f"\nDone. Open: {html_path}  (total: {t2 - t0:.1f}s)")
    return html_path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m scripts.marops.cli <slug>", file=sys.stderr)
        print("example: python -m scripts.marops.cli hubspot-ceiling", file=sys.stderr)
        sys.exit(1)

    run(sys.argv[1])
