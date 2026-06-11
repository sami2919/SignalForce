"""MAP Frustration Signal Scanner.

G2 reviews are paginated listing pages — Google indexes the aggregate page,
not individual review cards. Company names live inside the card, not in the
Google snippet, so G2-via-search can't extract them.

This scanner instead targets LinkedIn posts and public blog content where
MOPs practitioners name their company and describe MAP frustration. LinkedIn
URLs include the company slug; blog posts name the company in context.

Signal type: "map_frustration" (formerly "g2_review_frustration")
Strength:
  - Contains migration/replacing/switching/evaluating → STRONG
  - Contains expensive/complex/slow/frustrating       → MODERATE
  - Any other MAP frustration language                → WEAK
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)

_STRONG_KEYWORDS = {"migration", "replacing", "switching", "evaluating", "replacement", "alternative"}
_MODERATE_KEYWORDS = {"expensive", "complex", "slow", "frustrating", "difficult", "overhead", "bloated", "ceiling"}

# LinkedIn posts from MOPs practitioners discussing MAP pain — company name
# appears in the poster's profile URL and often in the post body.
_LINKEDIN_QUERIES: list[str] = [
    'site:linkedin.com/posts "marketo" "replacing" OR "migrating" OR "alternative" "marketing operations"',
    'site:linkedin.com/posts "hubspot enterprise" "expensive" OR "ceiling" OR "warehouse" "marketing"',
    'site:linkedin.com/posts "pardot" "replacing" OR "migrating" OR "salesforce marketing cloud" "martech"',
    'site:linkedin.com/posts "marketing automation" "replacing marketo" OR "left marketo" OR "off marketo"',
    'site:linkedin.com/posts "marketo" "too complex" OR "too expensive" OR "adobe acquisition" "operations"',
    'site:linkedin.com/posts "hubspot" "data warehouse" OR "snowflake" "marketing operations" "pain"',
]

# Public blog / case study content where companies name themselves and describe their MAP situation.
_BLOG_QUERIES: list[str] = [
    '"replaced marketo" OR "migrated from marketo" "marketing operations" -site:g2.com -site:capterra.com',
    '"left hubspot" OR "outgrew hubspot" "marketing" "warehouse" OR "salesforce" -site:g2.com',
    '"marketo alternative" "we chose" OR "we switched" "marketing team" -site:g2.com -site:getapp.com',
]

_ALL_QUERIES = _LINKEDIN_QUERIES + _BLOG_QUERIES

_LINKEDIN_COMPANY_RE = re.compile(
    r"linkedin\.com/(?:in|company)/([a-z0-9\-]+)", re.IGNORECASE
)

# Words that look like company names in regex matches but aren't
_NON_COMPANY_WORDS = {
    "if", "why", "how", "what", "when", "we", "i", "you", "they", "he", "she",
    "adobe", "summit", "conference", "forum", "highlights", "marketo", "hubspot",
    "pardot", "salesforce", "forrester", "gartner", "linkedin", "google",
    "episode", "last", "this", "that", "just", "here", "there",
}


class MAPFrustrationScanner:
    """Finds companies publicly expressing MAP frustration on LinkedIn and blogs."""

    def __init__(self, api_key: str | None = None) -> None:
        from scripts.config import get_config
        from scripts.scanners.job_scanner import JobPostingClient

        resolved_key = api_key if api_key is not None else get_config().serpapi_key
        self._client = JobPostingClient(api_key=resolved_key)

    def scan(self, lookback_days: int = 30) -> ScanResult:
        started_at = datetime.now(timezone.utc)
        signals: list[Signal] = []
        total_raw = 0
        errors: list[str] = []
        seen_urls: set[str] = set()

        for query in _ALL_QUERIES:
            try:
                results = self._client.search_jobs(query, num_results=10)
            except Exception as exc:
                msg = f"MAP frustration search failed for '{query[:60]}': {exc}"
                logger.warning(msg)
                errors.append(msg)
                continue

            total_raw += len(results)
            for result in results:
                url = result.get("url", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                signal = self._result_to_signal(result)
                if signal is not None:
                    signals.append(signal)

        return ScanResult(
            scan_type="map_frustration",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            signals_found=signals,
            total_raw_results=total_raw,
            total_after_dedup=len(signals),
            errors=errors,
        )

    def _result_to_signal(self, result: dict) -> Signal | None:
        title = result.get("title", "")
        snippet = result.get("snippet", "")
        url = result.get("url", "")
        combined = (title + " " + snippet).lower()

        company = self._extract_company(url, title, snippet)
        if not company:
            return None

        product = self._extract_product(combined)
        strength = self._score_frustration(combined)

        return Signal(
            signal_type="map_frustration",
            company_name=company,
            signal_strength=strength,
            source_url=url,
            raw_data={"title": title, "snippet": snippet, "url": url},
            metadata={
                "source_type": "linkedin" if "linkedin.com" in url else "blog",
                "product_mentioned": product,
                "frustration_keywords": self._found_keywords(combined),
            },
        )

    def _extract_company(self, url: str, title: str, snippet: str) -> str | None:
        # 1. linkedin.com/company/slug → convert slug to display name
        m = _LINKEDIN_COMPANY_RE.search(url)
        if m:
            slug = m.group(1)
            return " ".join(w.capitalize() for w in slug.split("-"))

        # 2. Title: "CompanyName Replaces/Left/Migrated Marketo/HubSpot" (present or past tense)
        title_m = re.search(
            r'^([A-Z][A-Za-z0-9&]{1,}(?:\s+[A-Z]?[A-Za-z0-9&]{1,}){0,4}?)\s+'
            r'(?:replaces?|migrates?|migrated|switched?|left|drops?|ditches?|moves?)\s+'
            r'(?:marketo|hubspot|pardot|salesforce marketing cloud)',
            title,
            re.IGNORECASE,
        )
        if title_m:
            name = title_m.group(1).strip().rstrip(",.")
            first_word = name.split()[0].lower()
            if first_word not in _NON_COMPANY_WORDS and len(name) >= 2:
                return name

        # 3. "at CompanyName" in title or snippet — company is a proper noun
        text = title + " " + snippet
        at_m = re.search(
            r'\bat\s+([A-Z][A-Za-z0-9]{1,}(?:\s+[A-Z][A-Za-z0-9]{1,}){0,2})',
            text,
        )
        if at_m:
            name = at_m.group(1).strip().rstrip(",.")
            first_word = name.split()[0].lower()
            # Reject event names, products, known non-companies
            bad_suffixes = {"summit", "conference", "forum", "hub", "engage"}
            last_word = name.split()[-1].lower()
            if (first_word not in _NON_COMPANY_WORDS
                    and last_word not in bad_suffixes
                    and len(name) >= 2):
                return name

        return None

    def _extract_product(self, text: str) -> str:
        if "marketo" in text:
            return "Marketo"
        if "hubspot" in text:
            return "HubSpot"
        if "pardot" in text:
            return "Pardot"
        return "Unknown MAP"

    def _score_frustration(self, text: str) -> SignalStrength:
        for kw in _STRONG_KEYWORDS:
            if kw in text:
                return SignalStrength.STRONG
        for kw in _MODERATE_KEYWORDS:
            if kw in text:
                return SignalStrength.MODERATE
        return SignalStrength.WEAK

    def _found_keywords(self, text: str) -> list[str]:
        return [kw for kw in (_STRONG_KEYWORDS | _MODERATE_KEYWORDS) if kw in text]


# Keep old class name as alias for backwards compat with existing tests
G2ReviewScanner = MAPFrustrationScanner


def scan(config: ScannerConfig) -> ScanResult:
    scanner = MAPFrustrationScanner()
    return scanner.scan(config.lookback_days)
