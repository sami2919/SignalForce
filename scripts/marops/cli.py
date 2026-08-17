"""MarOps brief generator CLI.

Usage:
    # Claude backend (default):
    export ANTHROPIC_API_KEY=...
    python -m scripts.marops.cli hubspot-ceiling

    # Fireworks backend:
    export FIREWORKS_API_KEY=...
    python -m scripts.marops.cli veriforce --backend fireworks

    # Fireworks ICP demo:
    export FIREWORKS_API_KEY=...
    python -m scripts.marops.cli fireworks-demo

Reads: examples/marops/<slug>.yaml
Writes: out/<slug>.json, out/<slug>.html
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import anthropic
import yaml

from scripts.marops.models import MarOpsCampaignConfig
from scripts.marops.renderer import render_html

ROOT = Path(__file__).parent.parent.parent
EXAMPLES = ROOT / "examples" / "marops"
OUT = ROOT / "out"


def run(slug: str, backend: str = "claude") -> Path:
    config_path = EXAMPLES / f"{slug}.yaml"
    if not config_path.exists():
        print(f"[error] config not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    raw = yaml.safe_load(config_path.read_text())
    config = MarOpsCampaignConfig.model_validate(raw)

    t0 = time.time()

    if backend == "fireworks":
        from scripts.marops.fireworks_briefer import generate_brief

        backend_label = "Fireworks AI"
    else:
        from scripts.marops.briefer import generate_brief

        backend_label = "Claude API"

    print(f"[1/2] generating brief for {config.prospect} ({backend_label}) ...", flush=True)
    try:
        brief = generate_brief(config)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
    except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
        print(
            f"[error] API failed ({type(exc).__name__}) — open demo/veriforce.html instead",
            file=sys.stderr,
        )
        sys.exit(1)
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
    t1 = time.time()

    token_info = ""
    if "input_tokens" in brief.meta:
        token_info = (
            f"tokens: in={brief.meta['input_tokens']} out={brief.meta['output_tokens']} "
            f"cache_read={brief.meta.get('cache_read_input_tokens', 0)}  "
        )
    print(f"      {token_info}[{t1 - t0:.1f}s]")

    OUT.mkdir(exist_ok=True)
    json_path = OUT / f"{slug}.json"
    json_path.write_text(json.dumps(brief.model_dump(), indent=2))

    html_path = OUT / f"{slug}.html"
    print(f"[2/2] rendering {slug}.html ...", flush=True)
    render_html(brief, html_path)

    t2 = time.time()
    print(f"\nDone. Open: {html_path}  (total: {t2 - t0:.1f}s)")
    return html_path


def run_fireworks_demo() -> None:
    """Run the Fireworks ICP demo workflow."""
    from scripts.demo_fireworks_icp import main as demo_main

    demo_main()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a MarOps lifecycle campaign brief.")
    parser.add_argument("slug", help="Config slug (e.g. veriforce) or 'fireworks-demo'")
    parser.add_argument(
        "--backend",
        choices=["claude", "fireworks"],
        default="claude",
        help="LLM backend to use (default: claude)",
    )
    args = parser.parse_args()

    if args.slug == "fireworks-demo":
        run_fireworks_demo()
    else:
        run(args.slug, backend=args.backend)


if __name__ == "__main__":
    main()
