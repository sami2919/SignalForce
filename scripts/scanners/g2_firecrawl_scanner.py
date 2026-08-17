"""G2 Review Scanner via Firecrawl — replaces cookie-based approach.

Uses Firecrawl to scrape G2 review pages and extract structured review data
(company name, rating, frustration signals, vendor mentioned). This eliminates
the need for fragile G2 session cookies that expire every ~7 days.

Signal type: "g2_review"  (same as the old g2_authenticated_scanner — drop-in replacement)
Strength:
  - STRONG:   Migration/replacing/switching language OR low rating + frustration keywords
  - MODERATE: Frustration keywords (expensive, complex, slow, etc.)
  - WEAK:     Any other review with company identifiable

Usage:
  python -m scripts.scanners.g2_firecrawl_scanner
  python -m scripts.scanners.g2_firecrawl_scanner --vendors marketo hubspot
  python -m scripts.scanners.g2_firecrawl_scanner --output /tmp/g2_signals.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import datetime, timezone

from scripts.config import get_config
from scripts.firecrawl_client import FirecrawlClient
from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_VENDORS: list[dict] = [
    {
        "slug": "adobe-marketo-engage",
        "display": "Marketo",
        "url_pattern": "g2.com/products/adobe-marketo-engage/reviews",
    },
    {
        "slug": "hubspot-marketing-hub",
        "display": "HubSpot",
        "url_pattern": "g2.com/products/hubspot-marketing-hub/reviews",
    },
    {"slug": "pardot", "display": "Pardot", "url_pattern": "g2.com/products/pardot/reviews"},
]

_STRONG_KEYWORDS: set[str] = {
    "migration",
    "migrating",
    "migrated",
    "replacing",
    "replaced",
    "switching",
    "switched",
    "evaluating",
    "replacement",
    "alternative",
    "alternatives",
    "moved off",
    "looking for",
    "searching for",
}

_MODERATE_KEYWORDS: set[str] = {
    "expensive",
    "complex",
    "slow",
    "frustrating",
    "difficult",
    "overhead",
    "bloated",
    "ceiling",
    "too much",
    "painful",
    "clunky",
    "overpriced",
    "not worth",
    "hard to use",
    "steep learning",
    "rigid",
}

# Regex: extract "at CompanyName" from reviewer title text
_AT_COMPANY_RE = re.compile(r"\bat\s+([A-Z][A-Za-z0-9][A-Za-z0-9&.,\- ]{0,50}?)(?:\s*[|,·•\n]|$)")
_NON_COMPANIES: set[str] = {
    "g2",
    "g2.com",
    "the time",
    "the company",
    "a startup",
    "my company",
    "a team",
    "our team",
    "a large",
    "a small",
    "work",
    "the university",
}

# Extraction prompt for Firecrawl's LLM extraction
_EXTRACTION_PROMPT = (
    "Extract all reviews from this G2 product review page. For each review, return: "
    "1) reviewer_company (the company the reviewer works at, from their title like 'VP Marketing at Acme Corp'), "
    "2) star_rating (1-5 number), "
    "3) review_snippet (first 200 chars of the review body), "
    "4) frustration_keywords (list of any keywords from: migration, replacing, switching, "
    "evaluating, alternative, expensive, complex, slow, frustrating, difficult, overpriced, "
    "bloated, clunky, rigid, ceiling, painful), "
    "5) vendor_name (the product being reviewed). "
    "Return as a JSON array of objects."
)

_EXTRACTION_SYSTEM_PROMPT = (
    "You are a G2 review analysis assistant. Extract structured data from G2 product "
    "review pages. Only include reviews where the reviewer's company name is identifiable. "
    "Skip reviews from G2 employees or where no company is mentioned."
)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class G2FirecrawlScanner:
    """Scrapes G2 reviews via Firecrawl, extracting structured review data."""

    def __init__(self, api_key: str | None = None) -> None:
        resolved = api_key or get_config().firecrawl_api_key
        if not resolved:
            logger.warning(
                "FIRECRAWL_API_KEY not set. G2 Firecrawl scanner cannot run. "
                "Add FIRECRAWL_API_KEY to your .env file."
            )
        self._api_key = resolved
        self._client: FirecrawlClient | None = None

    @property
    def client(self) -> FirecrawlClient:
        """Lazily initialize the Firecrawl client."""
        if self._client is None:
            if not self._api_key:
                raise ValueError("FIRECRAWL_API_KEY not configured")
            self._client = FirecrawlClient(api_key=self._api_key)
        return self._client

    def scan(
        self,
        lookback_days: int = 30,
        vendors: list[dict] | None = None,
        use_extraction: bool = True,
    ) -> ScanResult:
        """Run the G2 Firecrawl scanner.

        Args:
            lookback_days:  Retained for interface compatibility (not used in scraping).
            vendors:        List of vendor dicts with 'slug', 'display', 'url_pattern'.
                           Defaults to _DEFAULT_VENDORS.
            use_extraction: If True, use Firecrawl's LLM extraction. If False,
                           use raw markdown scraping + regex parsing.

        Returns:
            ScanResult with g2_review signals.
        """
        started_at = datetime.now(timezone.utc)

        if not self._api_key:
            return ScanResult(
                scan_type="g2_review",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                signals_found=[],
                total_raw_results=0,
                total_after_dedup=0,
                errors=["FIRECRAWL_API_KEY not configured — see .env.example"],
            )

        vendor_list = vendors or _DEFAULT_VENDORS
        signals: list[Signal] = []
        seen_companies: set[str] = set()
        total_raw = 0
        errors: list[str] = []

        for vendor in vendor_list:
            review_url = f"https://www.{vendor['url_pattern']}"

            if use_extraction:
                try:
                    vendor_signals = self._scan_with_extraction(review_url, vendor["display"])
                except Exception as exc:
                    msg = f"G2 Firecrawl extraction failed for {vendor['display']}: {exc}"
                    logger.warning(msg)
                    errors.append(msg)
                    # Fall back to markdown scraping
                    try:
                        vendor_signals = self._scan_with_markdown(review_url, vendor["display"])
                    except Exception as exc2:
                        msg = f"G2 Firecrawl markdown fallback also failed for {vendor['display']}: {exc2}"
                        logger.warning(msg)
                        errors.append(msg)
                        continue
            else:
                try:
                    vendor_signals = self._scan_with_markdown(review_url, vendor["display"])
                except Exception as exc:
                    msg = f"G2 Firecrawl scrape failed for {vendor['display']}: {exc}"
                    logger.warning(msg)
                    errors.append(msg)
                    continue

            for signal in vendor_signals:
                total_raw += 1
                key = signal.company_name.lower()
                if key not in seen_companies and key not in _NON_COMPANIES:
                    seen_companies.add(key)
                    signals.append(signal)

        return ScanResult(
            scan_type="g2_review",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            signals_found=signals,
            total_raw_results=total_raw,
            total_after_dedup=len(signals),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Extraction-based scanning (primary — uses Firecrawl LLM extraction)
    # ------------------------------------------------------------------

    def _scan_with_extraction(self, review_url: str, vendor_display: str) -> list[Signal]:
        """Use Firecrawl's structured extraction to pull reviews from a G2 page.

        Args:
            review_url:    G2 product review page URL.
            vendor_display: Human-readable vendor name for metadata.

        Returns:
            List of Signal objects extracted from the page.
        """
        resp = self.client.extract(
            url=review_url,
            prompt=_EXTRACTION_PROMPT,
            system_prompt=_EXTRACTION_SYSTEM_PROMPT,
        )

        # Extraction response may have data at top level or nested
        raw_data = resp.get("data", resp)
        reviews: list[dict] = []

        if isinstance(raw_data, dict):
            # Could be a single object with a reviews key, or the extraction itself
            if "reviews" in raw_data:
                reviews = raw_data["reviews"]
            else:
                reviews = [raw_data]
        elif isinstance(raw_data, list):
            reviews = raw_data

        signals: list[Signal] = []
        for review in reviews:
            if not isinstance(review, dict):
                continue
            company = review.get("reviewer_company", "") or review.get("company", "")
            if not company or company.lower() in _NON_COMPANIES:
                continue

            rating_raw = review.get("star_rating") or review.get("rating", 0)
            try:
                rating = float(rating_raw)
            except (ValueError, TypeError):
                rating = 0.0

            snippet = review.get("review_snippet", "") or review.get("snippet", "")
            frustration = review.get("frustration_keywords", [])
            if isinstance(frustration, str):
                frustration = [frustration]

            vendor = review.get("vendor_name", vendor_display)

            signal = self._build_signal(
                company=company,
                rating=rating,
                snippet=snippet,
                frustration_keywords=frustration,
                vendor=vendor,
                source_url=review_url,
            )
            if signal:
                signals.append(signal)

        return signals

    # ------------------------------------------------------------------
    # Markdown-based scanning (fallback — regex parsing of scraped markdown)
    # ------------------------------------------------------------------

    def _scan_with_markdown(self, review_url: str, vendor_display: str) -> list[Signal]:
        """Scrape G2 review page to markdown and parse reviews with regex.

        Fallback when LLM extraction is unavailable or fails.

        Args:
            review_url:    G2 product review page URL.
            vendor_display: Human-readable vendor name.

        Returns:
            List of Signal objects parsed from markdown.
        """
        resp = self.client.scrape(review_url)
        markdown = resp.get("data", {}).get("markdown", "") or resp.get("markdown", "")

        if not markdown:
            return []

        signals: list[Signal] = []

        # Extract company names from "at CompanyName" patterns
        company_matches = _AT_COMPANY_RE.findall(markdown)

        # Extract star ratings (G2 shows "X.X" or "X out of 5")
        rating_pattern = re.compile(
            r"(\d(?:\.\d)?)\s*(?:/?\s*5)?\s*(?:star|rating|★)", re.IGNORECASE
        )
        ratings = rating_pattern.findall(markdown)

        # Try to extract review snippets — text between "Review" headers or quotes
        snippet_pattern = re.compile(r'>\s*["\']?(.{50,300}?)["\']?\s*(?:<|\n\n)', re.DOTALL)
        snippets = snippet_pattern.findall(markdown)

        # Build signals from extracted company names
        for i, company in enumerate(company_matches):
            company = company.strip().rstrip(",.")
            if len(company) < 2 or company.lower() in _NON_COMPANIES:
                continue

            rating = 0.0
            if i < len(ratings):
                try:
                    rating = float(ratings[i])
                except (ValueError, TypeError):
                    pass

            snippet = snippets[i] if i < len(snippets) else ""
            frustration = self._find_frustration_keywords(snippet + " " + company)

            signal = self._build_signal(
                company=company,
                rating=rating,
                snippet=snippet,
                frustration_keywords=frustration,
                vendor=vendor_display,
                source_url=review_url,
            )
            if signal:
                signals.append(signal)

        return signals

    # ------------------------------------------------------------------
    # Signal building
    # ------------------------------------------------------------------

    def _build_signal(
        self,
        company: str,
        rating: float,
        snippet: str,
        frustration_keywords: list[str],
        vendor: str,
        source_url: str,
    ) -> Signal | None:
        """Build a g2_review Signal from extracted review data.

        Args:
            company:             Reviewer's company name.
            rating:              Star rating (1–5).
            snippet:             Review text snippet.
            frustration_keywords: List of detected frustration keywords.
            vendor:              Product being reviewed (Marketo, HubSpot, etc.).
            source_url:          G2 review page URL.

        Returns:
            Signal object, or None if company is not identifiable.
        """
        if not company or company.lower() in _NON_COMPANIES:
            return None

        combined_text = (snippet + " " + " ".join(frustration_keywords)).lower()
        strength = self._score(combined_text, rating)

        return Signal(
            signal_type="g2_review",
            company_name=company,
            signal_strength=strength,
            source_url=source_url,
            raw_data={
                "snippet": snippet[:500],
                "rating": rating,
                "vendor": vendor,
            },
            metadata={
                "source_type": "g2_firecrawl",
                "product_mentioned": vendor,
                "frustration_keywords": frustration_keywords,
                "star_rating": rating,
            },
        )

    def _score(self, text: str, rating: float) -> SignalStrength:
        """Score signal strength from frustration keywords and rating."""
        for kw in _STRONG_KEYWORDS:
            if kw in text:
                return SignalStrength.STRONG
        if rating <= 2.0:
            for kw in _MODERATE_KEYWORDS:
                if kw in text:
                    return SignalStrength.STRONG
        for kw in _MODERATE_KEYWORDS:
            if kw in text:
                return SignalStrength.MODERATE
        return SignalStrength.WEAK

    def _find_frustration_keywords(self, text: str) -> list[str]:
        """Find all frustration keywords present in text."""
        lower = text.lower()
        return [kw for kw in (_STRONG_KEYWORDS | _MODERATE_KEYWORDS) if kw in lower]


# ---------------------------------------------------------------------------
# Entry point for scanner_runner
# ---------------------------------------------------------------------------


def scan(config: ScannerConfig) -> ScanResult:
    """Entry point called by scanner_runner."""
    scanner = G2FirecrawlScanner()
    vendors = config.custom_params.get("vendors")
    use_extraction = config.custom_params.get("use_extraction", True)
    return scanner.scan(
        lookback_days=config.lookback_days,
        vendors=vendors,
        use_extraction=use_extraction,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape G2 reviews via Firecrawl — no session cookie required.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--vendors",
        nargs="+",
        default=None,
        help="Vendor slugs to scan (default: marketo hubspot pardot).",
    )
    parser.add_argument(
        "--no-extraction",
        action="store_true",
        help="Use markdown scraping + regex instead of LLM extraction.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to write results as JSON.",
    )
    parser.add_argument("--lookback-days", type=int, default=30)
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the G2 Firecrawl scanner."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    vendors = None
    if args.vendors:
        vendors = [
            {"slug": v, "display": v.capitalize(), "url_pattern": f"g2.com/products/{v}/reviews"}
            for v in args.vendors
        ]

    scanner = G2FirecrawlScanner()
    result = scanner.scan(
        lookback_days=args.lookback_days,
        vendors=vendors,
        use_extraction=not args.no_extraction,
    )

    print(f"\nG2 Firecrawl scan complete — {len(result.signals_found)} signals")
    print(f"  Raw results:  {result.total_raw_results}")
    print(f"  After dedup:  {result.total_after_dedup}")
    if result.errors:
        print(f"  Errors:       {len(result.errors)}")
        for e in result.errors:
            print(f"    {e}")

    for signal in sorted(result.signals_found, key=lambda s: s.signal_strength, reverse=True):
        strength = SignalStrength(signal.signal_strength).name
        stars = signal.metadata.get("star_rating", "?")
        vendor = signal.raw_data.get("vendor", "?")
        print(f"  [{strength:8s}] {signal.company_name} — {vendor} ★{stars}")
        if signal.raw_data.get("snippet"):
            print(f'    "{signal.raw_data["snippet"][:120]}"')

    if args.output:
        output_data = result.model_dump(mode="json")
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
