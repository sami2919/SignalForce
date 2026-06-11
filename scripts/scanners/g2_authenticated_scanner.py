"""G2 Authenticated Review Scanner — JSON API approach.

G2's frontend fetches review data from a JSON endpoint that accepts the same
session cookie as the browser. This is more reliable than HTML scraping because
it returns structured data and doesn't require CSS selector maintenance.

Setup (one-time):
  1. Log into g2.com in your browser
  2. Open DevTools → Network → filter for 'reviews.json' → copy the Cookie header
  3. Add to .env:  G2_SESSION_COOKIE="<paste full cookie string>"

Usage:
  python -m scripts.scanners.g2_authenticated_scanner
  python -m scripts.scanners.g2_authenticated_scanner --diagnose
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Iterator

import requests

from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)

_COOKIE_ENV_VAR = "G2_SESSION_COOKIE"

_MAP_VENDORS: list[dict] = [
    {"slug": "adobe-marketo-engage", "display": "Marketo"},
    {"slug": "hubspot", "display": "HubSpot"},
    {"slug": "pardot", "display": "Pardot"},
]

_STAR_RATINGS = [1, 2, 3]
_MAX_PAGES = 3  # Cap pages per vendor/rating to stay polite

_STRONG_KEYWORDS = {
    "migration",
    "replacing",
    "switching",
    "evaluating",
    "replacement",
    "alternative",
    "alternatives",
    "migrating",
    "moved off",
}
_MODERATE_KEYWORDS = {
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
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.5",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.g2.com/",
}

# Regex: extract "at CompanyName" from reviewer title text
_AT_COMPANY_RE = re.compile(r"\bat\s+([A-Z][A-Za-z0-9][A-Za-z0-9&.,\- ]{0,50}?)(?:\s*[|,·•\n]|$)")
_NON_COMPANIES = {
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
}


class G2AuthenticatedScanner:
    """Fetches G2 reviews via the internal JSON API using the user's session cookie."""

    def __init__(self, cookie: str | None = None, debug: bool = False) -> None:
        resolved = cookie or os.environ.get(_COOKIE_ENV_VAR, "")
        if not resolved:
            logger.warning(
                "G2_SESSION_COOKIE not set. Log into g2.com → DevTools → Network → "
                "filter for 'reviews.json' → copy the Cookie header → add to .env."
            )
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        if resolved:
            self._session.headers["Cookie"] = resolved
        self._debug = debug

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def scan(self, lookback_days: int = 30) -> ScanResult:
        started_at = datetime.now(timezone.utc)

        if not self._session.headers.get("Cookie"):
            return ScanResult(
                scan_type="g2_review",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                signals_found=[],
                total_raw_results=0,
                total_after_dedup=0,
                errors=["G2_SESSION_COOKIE not configured — see .env.example"],
            )

        signals: list[Signal] = []
        seen: set[str] = set()
        total_raw = 0
        errors: list[str] = []

        for vendor in _MAP_VENDORS:
            for stars in _STAR_RATINGS:
                try:
                    for review in self._fetch_reviews(vendor, stars):
                        total_raw += 1
                        company = review.get("company", "")
                        key = company.lower()
                        if not company or key in seen or key in _NON_COMPANIES:
                            continue
                        seen.add(key)
                        signals.append(self._to_signal(review, vendor["display"]))
                    time.sleep(1.0)
                except Exception as exc:
                    msg = f"G2 fetch failed ({vendor['display']} ★{stars}): {exc}"
                    logger.warning(msg)
                    errors.append(msg)

        return ScanResult(
            scan_type="g2_review",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            signals_found=signals,
            total_raw_results=total_raw,
            total_after_dedup=len(signals),
            errors=errors,
        )

    def diagnose(self) -> None:
        """Print diagnostic info about cookie state and first API response. Use --diagnose."""
        cookie = self._session.headers.get("Cookie", "")
        print("\nG2 Diagnostics")
        print(f"  Cookie set: {'yes' if cookie else 'NO — set G2_SESSION_COOKIE in .env'}")
        if cookie:
            print(f"  Cookie preview: {cookie[:60]}...")

        vendor = _MAP_VENDORS[0]
        stars = 2
        url = self._api_url(vendor["slug"], stars, page=1)
        print(f"\n  Testing: GET {url}")
        try:
            resp = self._session.get(url, timeout=10)
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                reviews = data.get("reviews", [])
                meta = data.get("meta", {})
                print(f"  Reviews on page 1: {len(reviews)}")
                print(f"  Total reviews: {meta.get('total_count', '?')}")
                print(f"  Total pages: {meta.get('total_pages', '?')}")
                if reviews:
                    r = reviews[0]
                    print(f"  First reviewer title: {r.get('reviewer', {}).get('title', '(none)')}")
                    print(f"  First review body (first 120 chars): {str(r.get('body', ''))[:120]}")
            elif resp.status_code == 403:
                print("  403 Forbidden — cookie is expired. Re-copy from DevTools.")
            elif resp.status_code == 401:
                print("  401 Unauthorized — cookie is missing or invalid.")
            else:
                print(f"  Unexpected status. Response text: {resp.text[:200]}")
        except Exception as exc:
            print(f"  Error: {exc}")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _api_url(self, slug: str, stars: int, page: int) -> str:
        return (
            f"https://www.g2.com/products/{slug}/reviews.json"
            f"?filters%5Bstar_rating%5D={stars}"
            f"&filters%5Bsort%5D=recent"
            f"&page={page}"
        )

    def _fetch_reviews(self, vendor: dict, stars: int) -> Iterator[dict]:
        slug = vendor["slug"]
        page = 1

        while page <= _MAX_PAGES:
            url = self._api_url(slug, stars, page)
            resp = self._session.get(url, timeout=15)

            if resp.status_code == 403:
                raise RuntimeError(
                    "403 Forbidden — cookie may be expired. "
                    "Re-copy from DevTools and update G2_SESSION_COOKIE in .env. "
                    "Run --diagnose for details."
                )
            resp.raise_for_status()

            data = resp.json()
            reviews = data.get("reviews", [])

            if self._debug:
                logger.info(
                    "G2 JSON page %d/%d for %s ★%d — %d reviews",
                    page,
                    data.get("meta", {}).get("total_pages", "?"),
                    vendor["display"],
                    stars,
                    len(reviews),
                )

            if not reviews:
                break

            for raw in reviews:
                company = self._extract_company(raw)
                snippet = self._extract_snippet(raw)
                rating = raw.get("star_rating") or stars
                review_url = raw.get("url", "")
                if review_url and not review_url.startswith("http"):
                    review_url = f"https://www.g2.com{review_url}"
                if company:
                    yield {
                        "company": company,
                        "snippet": snippet,
                        "rating": rating,
                        "review_url": review_url,
                    }

            total_pages = data.get("meta", {}).get("total_pages", 1)
            if page >= total_pages:
                break
            page += 1
            time.sleep(0.5)

    def _extract_company(self, review: dict) -> str | None:
        reviewer = review.get("reviewer") or {}
        title = reviewer.get("title") or ""
        m = _AT_COMPANY_RE.search(title)
        if m:
            name = m.group(1).strip().rstrip(".,")
            if len(name) >= 2 and name.lower() not in _NON_COMPANIES:
                return name
        return None

    def _extract_snippet(self, review: dict) -> str:
        body = review.get("body") or review.get("title") or ""
        return str(body)[:500]

    def _to_signal(self, review: dict, vendor_display: str) -> Signal:
        snippet = review.get("snippet", "")
        rating = review.get("rating")
        return Signal(
            signal_type="g2_review",
            company_name=review["company"],
            signal_strength=self._score(snippet, rating),
            source_url=review.get("review_url", ""),
            raw_data={
                "snippet": snippet,
                "rating": rating,
                "vendor": vendor_display,
            },
            metadata={
                "source_type": "g2_authenticated",
                "product_mentioned": vendor_display,
                "frustration_keywords": self._found_keywords(snippet),
                "star_rating": rating,
            },
        )

    def _score(self, text: str, rating: int | None) -> SignalStrength:
        lower = text.lower()
        for kw in _STRONG_KEYWORDS:
            if kw in lower:
                return SignalStrength.STRONG
        if rating is not None and rating <= 2:
            for kw in _MODERATE_KEYWORDS:
                if kw in lower:
                    return SignalStrength.STRONG
        for kw in _MODERATE_KEYWORDS:
            if kw in lower:
                return SignalStrength.MODERATE
        return SignalStrength.WEAK

    def _found_keywords(self, text: str) -> list[str]:
        lower = text.lower()
        return [kw for kw in (_STRONG_KEYWORDS | _MODERATE_KEYWORDS) if kw in lower]


def scan(config: ScannerConfig) -> ScanResult:
    """Entry point called by scanner_runner."""
    return G2AuthenticatedScanner().scan(config.lookback_days)


if __name__ == "__main__":
    import argparse

    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="G2 authenticated review scanner (JSON API)")
    parser.add_argument(
        "--diagnose", action="store_true", help="Print cookie state and API health check"
    )
    parser.add_argument("--debug", action="store_true", help="Log page counts during scan")
    parser.add_argument("--lookback-days", type=int, default=30)
    args = parser.parse_args()

    scanner = G2AuthenticatedScanner(debug=args.debug)
    if args.diagnose:
        scanner.diagnose()
    else:
        result = scanner.scan(args.lookback_days)
        print(f"\nG2 signals found: {len(result.signals_found)}")
        for s in result.signals_found:
            stars = s.metadata.get("star_rating", "?")
            vendor = s.raw_data.get("vendor", "?")
            print(f"  [{s.signal_strength.value}] {s.company_name} — {vendor} ★{stars}")
            if s.raw_data.get("snippet"):
                print(f'    "{s.raw_data["snippet"][:120]}"')
        if result.errors:
            print(f"\nErrors ({len(result.errors)}):")
            for e in result.errors:
                print(f"  {e}")
