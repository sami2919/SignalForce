"""Firecrawl Website Enrichment Scanner.

Given company domains (from existing signals or config seed URLs), scrapes
homepage + key pages (/about, /careers, /product) via Firecrawl, extracts
clean markdown, and produces Signal objects with structured website enrichment
metadata that feeds into the ICP scoring engine.

Signal type: "website_enrichment"
Strength:
  - STRONG:   ICP keywords found in product description or tech stack
  - MODERATE: ICP keywords found in hiring language or about page
  - WEAK:     Page scraped but no ICP keyword matches
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone

from scripts.config import get_config
from scripts.firecrawl_client import FirecrawlClient
from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)


# Key sub-pages to scrape for enrichment beyond the homepage
_KEY_PAGES: list[str] = ["/about", "/careers", "/product", "/team", "/pricing"]

# ICP keyword groups used for lightweight scoring — these are generic enough
# to work across ICPs; the real scoring happens downstream in icp_fit_scorer.py
_ICP_INDICATOR_KEYWORDS: set[str] = {
    "reinforcement learning",
    "rlhf",
    "grpo",
    "reward model",
    "policy gradient",
    "sim-to-real",
    "agent",
    "llm",
    "ai",
    "machine learning",
    "ml",
    "training",
    "fine-tuning",
    "inference",
    "gpu",
    "cuda",
    "pytorch",
    "tensorflow",
    "jax",
}


def _normalize_domain(domain: str) -> str:
    """Ensure domain has a scheme for Firecrawl."""
    domain = domain.strip().lower()
    if domain.startswith("http"):
        return domain
    return f"https://{domain}"


def _extract_domain(url: str) -> str:
    """Extract bare domain from a URL."""
    clean = url.replace("https://", "").replace("http://", "")
    return clean.split("/")[0].split(":")[0]


def _score_content(markdown: str, config_keywords: list[str]) -> SignalStrength:
    """Score signal strength based on ICP keyword presence in scraped content.

    Args:
        markdown:          Scraped page markdown content.
        config_keywords:   Keywords from scanner config for matching.

    Returns:
        SignalStrength enum.
    """
    lower = markdown.lower()

    # Check config-supplied keywords first (ICP-specific)
    config_matches = [kw for kw in config_keywords if kw.lower() in lower]

    # Also check generic ICP indicator keywords
    icp_matches = [kw for kw in _ICP_INDICATOR_KEYWORDS if kw in lower]

    total_matches = len(config_matches) + len(icp_matches)

    if total_matches >= 3:
        return SignalStrength.STRONG
    if total_matches >= 1:
        return SignalStrength.MODERATE
    return SignalStrength.WEAK


def _extract_hiring_language(markdown: str) -> list[str]:
    """Extract hiring-related phrases from careers page markdown."""
    lower = markdown.lower()
    phrases: list[str] = []

    # Look for role mentions near "hiring", "join", "careers" context
    hiring_indicators = [
        "we're hiring",
        "we are hiring",
        "join our team",
        "open roles",
        "job openings",
        "careers",
        "now hiring",
    ]
    for indicator in hiring_indicators:
        if indicator in lower:
            phrases.append(indicator)

    # Extract job-relevant snippets (lines mentioning engineer/researcher/scientist)
    for line in markdown.split("\n"):
        line_lower = line.lower()
        if any(role in line_lower for role in ("engineer", "researcher", "scientist", "manager")):
            line_clean = line.strip()
            if line_clean and len(line_clean) < 200:
                phrases.append(line_clean)

    return phrases[:10]  # cap to avoid bloating metadata


def _scrape_company(
    client: FirecrawlClient,
    domain: str,
    config_keywords: list[str],
    scrape_key_pages: bool = True,
) -> Signal | None:
    """Scrape a company website and build a Signal.

    Args:
        client:           FirecrawlClient instance.
        domain:           Company domain (with or without scheme).
        config_keywords:  Keywords from config for ICP matching.
        scrape_key_pages: If True, also scrape /about, /careers, etc.

    Returns:
        Signal object or None if scraping fails.
    """
    url = _normalize_domain(domain)
    bare_domain = _extract_domain(url)

    all_markdown: list[str] = []
    pages_scraped: list[str] = []
    hiring_language: list[str] = []

    # 1. Scrape homepage
    try:
        resp = client.scrape(url)
        home_md = resp.get("data", {}).get("markdown", "")
        if not home_md:
            # Some responses put markdown at top level
            home_md = resp.get("markdown", "")
        all_markdown.append(home_md)
        pages_scraped.append(url)
    except Exception as exc:
        logger.warning("Failed to scrape homepage for %s: %s", domain, exc)
        return None

    # 2. Scrape key sub-pages
    if scrape_key_pages:
        for page in _KEY_PAGES:
            page_url = f"{url.rstrip('/')}{page}"
            try:
                resp = client.scrape(page_url, max_age=30)
                page_md = resp.get("data", {}).get("markdown", "")
                if not page_md:
                    page_md = resp.get("markdown", "")
                if page_md:
                    all_markdown.append(page_md)
                    pages_scraped.append(page_url)
                    if page == "/careers":
                        hiring_language = _extract_hiring_language(page_md)
            except Exception as exc:
                logger.debug("Could not scrape %s: %s", page_url, exc)
                continue

    combined_markdown = "\n\n---\n\n".join(all_markdown)
    strength = _score_content(combined_markdown, config_keywords)

    # Extract tech stack hints from markdown
    tech_stack = _extract_tech_stack(combined_markdown)

    return Signal(
        signal_type="website_enrichment",
        company_name=bare_domain.split(".")[0].capitalize(),
        company_domain=bare_domain,
        signal_strength=strength,
        source_url=url,
        raw_data={
            "markdown": combined_markdown[:5000],  # cap for storage
            "pages_scraped": pages_scraped,
        },
        metadata={
            "domain": bare_domain,
            "tech_stack": tech_stack,
            "hiring_language": hiring_language,
            "product_description": _extract_product_description(combined_markdown),
            "page_count": len(pages_scraped),
            "enrichment_source": "firecrawl",
        },
    )


def _extract_tech_stack(markdown: str) -> list[str]:
    """Extract tech stack mentions from markdown content."""
    lower = markdown.lower()
    stack: list[str] = []

    tech_indicators: dict[str, str] = {
        "pytorch": "PyTorch",
        "tensorflow": "TensorFlow",
        "jax": "JAX",
        "react": "React",
        "next.js": "Next.js",
        "python": "Python",
        "rust": "Rust",
        "go ": "Go",
        "typescript": "TypeScript",
        "kubernetes": "Kubernetes",
        "docker": "Docker",
        "aws": "AWS",
        "gcp": "GCP",
        "azure": "Azure",
        "snowflake": "Snowflake",
        "databricks": "Databricks",
        "spark": "Spark",
        "kafka": "Kafka",
        "redis": "Redis",
        "postgresql": "PostgreSQL",
        "mongodb": "MongoDB",
        "cuda": "CUDA",
        "gpu": "GPU",
        "triton": "Triton",
        "vllm": "vLLM",
        "ray": "Ray",
        "slurm": "Slurm",
    }

    for needle, display in tech_indicators.items():
        if needle in lower:
            stack.append(display)

    return stack


def _extract_product_description(markdown: str) -> str:
    """Extract the first meaningful paragraph as product description."""
    for line in markdown.split("\n"):
        line = line.strip()
        # Skip headers, nav, short lines
        if line and not line.startswith("#") and not line.startswith("[") and len(line) > 50:
            return line[:300]
    return ""


def scan(config: ScannerConfig) -> ScanResult:
    """Run the Firecrawl website enrichment scanner.

    Expects either:
    - config.keywords containing domains to scrape
    - config.custom_params["domains"] containing a list of domains
    - config.queries containing domains to scrape

    Args:
        config: ScannerConfig with domains in keywords or custom_params.

    Returns:
        ScanResult with Signal objects for each successfully scraped company.
    """
    started_at = datetime.now(timezone.utc)

    app_config = get_config()
    if not app_config.firecrawl_api_key:
        return ScanResult(
            scan_type="website_enrichment",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
            errors=["FIRECRAWL_API_KEY not configured — see .env.example"],
        )

    client = FirecrawlClient(api_key=app_config.firecrawl_api_key)

    # Gather domains from config
    domains: list[str] = []
    domains.extend(config.keywords)
    domains.extend(config.custom_params.get("domains", []))
    domains.extend(config.queries)

    if not domains:
        logger.warning("Firecrawl scanner enabled but no domains configured")
        return ScanResult(
            scan_type="website_enrichment",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
        )

    # Keywords for scoring (from config.topics — ICP-specific terms)
    scoring_keywords = list(config.topics) + list(config.libraries)

    signals: list[Signal] = []
    seen_domains: set[str] = set()
    total_raw = 0
    errors: list[str] = []

    for domain in domains:
        bare = _extract_domain(_normalize_domain(domain))
        if bare in seen_domains:
            continue
        seen_domains.add(bare)
        total_raw += 1

        try:
            signal = _scrape_company(client, domain, scoring_keywords)
            if signal:
                signals.append(signal)
        except Exception as exc:
            msg = f"Failed to enrich {domain}: {exc}"
            logger.warning(msg)
            errors.append(msg)

    return ScanResult(
        scan_type="website_enrichment",
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        signals_found=signals,
        total_raw_results=total_raw,
        total_after_dedup=len(signals),
        errors=errors,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Enrich company websites via Firecrawl — scrape, extract, score.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--domains",
        nargs="+",
        required=True,
        help="Company domains to scrape (e.g. openai.com anthropic.com)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to write results as JSON.",
    )
    parser.add_argument(
        "--no-key-pages",
        action="store_true",
        help="Only scrape homepage, skip /about /careers etc.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the Firecrawl website enrichment scanner."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    from scripts.config_loader import ScannerConfig

    scanner_cfg = ScannerConfig(
        module="scripts.scanners.firecrawl_scanner",
        keywords=args.domains,
        lookback_days=7,
    )

    result = scan(scanner_cfg)

    print(f"Scan complete — {len(result.signals_found)} signals")
    print(f"  Raw results:  {result.total_raw_results}")
    print(f"  After dedup:  {result.total_after_dedup}")
    if result.errors:
        print(f"  Errors:       {len(result.errors)}")

    for signal in sorted(result.signals_found, key=lambda s: s.signal_strength, reverse=True):
        strength = SignalStrength(signal.signal_strength).name
        tech = ", ".join(signal.metadata.get("tech_stack", [])[:5])
        print(f"  [{strength:8s}] {signal.company_name} — {signal.company_domain}")
        if tech:
            print(f"    Tech: {tech}")

    if args.output:
        output_data = result.model_dump(mode="json")
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
