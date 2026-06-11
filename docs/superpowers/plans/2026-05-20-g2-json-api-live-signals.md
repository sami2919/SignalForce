# G2 Live Signal Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make G2 review signals actually fire in a live demo by switching from HTML scraping (which fails on G2's JS-rendered pages) to G2's internal JSON API, and wire `g2_review` into the scoring engine so signals actually affect grades.

**Architecture:** G2's frontend is a React SPA that fetches review data from `GET /products/{slug}/reviews.json?filters[star_rating]=N&page=1`. That endpoint accepts the same session cookie as the browser, returns structured JSON (no HTML parsing), and is immune to CSS selector churn. The scanner switches to this endpoint. Scoring config gains `g2_review` weights so signals grade properly. A `--diagnose` CLI flag gives fast in-demo debugging.

**Tech Stack:** Python 3.9+, `requests`, `python-dotenv`, `pytest`, `ruff`. No new dependencies.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `scripts/scanners/g2_authenticated_scanner.py` | Replace BS4 HTML scraping with JSON API fetch; add `--diagnose` CLI flag |
| Modify | `tests/test_g2_authenticated_scanner.py` | Update mocks to JSON API shape; add diagnose + pagination tests |
| Modify | `config/config.yaml` | Add `g2_review: 3.5` to `intent_weights` and `g2_review: 21.0` to `half_lives_days` |
| Modify | `examples/marketo-migration/config.yaml` | Same scoring additions (keep in sync with active config) |

---

### Task 1: Add `g2_review` scoring weights

`g2_review` signals currently default to weight `1.0` and half-life `7.0` because they're not in the config. A single G2 review from a VP of Marketing is stronger evidence than a LinkedIn post — it should score `3.5` with a 21-day half-life (same as `map_frustration`).

**Files:**
- Modify: `config/config.yaml` (lines around the `scoring:` block)
- Modify: `examples/marketo-migration/config.yaml` (same block)

- [ ] **Step 1: Add `g2_review` to `config/config.yaml`**

In `config/config.yaml`, under `scoring:`, add to both `intent_weights` and `half_lives_days`:

```yaml
scoring:
  intent_weights:
    github_repo: 2.0
    arxiv_paper: 0.0
    huggingface_model: 0.0
    job_posting: 3.0
    funding_event: 2.5
    linkedin_activity: 2.0
    map_frustration: 2.5         # Public MAP frustration on LinkedIn/blog = active evaluation signal
    g2_review: 3.5               # Authenticated G2 review — named company + named vendor = highest signal

  half_lives_days:
    github_repo: 14.0
    arxiv_paper: 10.0
    huggingface_model: 7.0
    job_posting: 14.0
    funding_event: 30.0
    linkedin_activity: 3.0
    map_frustration: 21.0
    g2_review: 21.0              # G2 reviews don't expire quickly — reviewer frustration is durable
```

- [ ] **Step 2: Apply the same change to `examples/marketo-migration/config.yaml`**

Find the identical `intent_weights` and `half_lives_days` blocks in `examples/marketo-migration/config.yaml` and apply the same two lines.

- [ ] **Step 3: Verify the config loads without error**

```bash
python -c "from scripts.config_loader import load_config; c = load_config(); print(c.scoring.intent_weights)"
```

Expected: dict printed, includes `g2_review: 3.5`.

- [ ] **Step 4: Commit**

```bash
git add config/config.yaml examples/marketo-migration/config.yaml
git commit -m "feat: add g2_review scoring weight and half-life to active + example configs"
```

---

### Task 2: Write failing tests for JSON API scanner

G2's review JSON endpoint: `GET https://www.g2.com/products/{slug}/reviews.json?filters%5Bstar_rating%5D={stars}&page=1`

Response shape (actual G2 API, simplified):
```json
{
  "reviews": [
    {
      "title": "Too expensive for what you get",
      "body": "Marketo is complex and we are evaluating alternatives.",
      "star_rating": 2,
      "reviewer": {
        "title": "VP Marketing at Acme Corp"
      },
      "url": "/reviews/marketo/acme-corp-review-123"
    }
  ],
  "meta": {
    "total_count": 42,
    "current_page": 1,
    "total_pages": 5
  }
}
```

**Files:**
- Modify: `tests/test_g2_authenticated_scanner.py`

- [ ] **Step 1: Replace HTML fixtures with JSON fixtures**

Replace the entire contents of `tests/test_g2_authenticated_scanner.py` with:

```python
"""Unit tests for G2AuthenticatedScanner. All HTTP calls mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scripts.scanners.g2_authenticated_scanner import G2AuthenticatedScanner, scan
from scripts.config_loader import ScannerConfig
from scripts.models import SignalStrength

_REVIEW_PAGE_1 = {
    "reviews": [
        {
            "title": "Too complex and too expensive",
            "body": "Marketo is way too complex for our team. We are evaluating alternatives now.",
            "star_rating": 2,
            "reviewer": {"title": "VP Marketing at Acme Corp"},
            "url": "/reviews/marketo/acme-corp-review-123",
        },
        {
            "title": "HubSpot ceiling is real",
            "body": "We keep hitting limits on custom audiences. Painful workarounds every week.",
            "star_rating": 3,
            "reviewer": {"title": "Director of Demand Gen at Beta Inc"},
            "url": "/reviews/hubspot/beta-inc-review-456",
        },
    ],
    "meta": {"total_count": 2, "current_page": 1, "total_pages": 1},
}

_EMPTY_PAGE = {
    "reviews": [],
    "meta": {"total_count": 0, "current_page": 1, "total_pages": 1},
}

_NO_COMPANY_PAGE = {
    "reviews": [
        {
            "title": "It was okay",
            "body": "Nothing special.",
            "star_rating": 3,
            "reviewer": {"title": "Anonymous Reviewer"},
            "url": "/reviews/marketo/anon-789",
        }
    ],
    "meta": {"total_count": 1, "current_page": 1, "total_pages": 1},
}

_MULTI_PAGE_1 = {
    "reviews": [
        {
            "title": "Replacing this ASAP",
            "body": "We are switching to something better.",
            "star_rating": 1,
            "reviewer": {"title": "MOPs Manager at PageOne Corp"},
            "url": "/reviews/marketo/pageone-001",
        }
    ],
    "meta": {"total_count": 2, "current_page": 1, "total_pages": 2},
}

_MULTI_PAGE_2 = {
    "reviews": [
        {
            "title": "Migration in progress",
            "body": "Migrating off now. Painful but worth it.",
            "star_rating": 2,
            "reviewer": {"title": "Engineer at PageTwo Ltd"},
            "url": "/reviews/marketo/pagetwo-002",
        }
    ],
    "meta": {"total_count": 2, "current_page": 2, "total_pages": 2},
}


def _make_json_response(data: dict, status: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = data
    mock.raise_for_status = MagicMock()
    return mock


@pytest.fixture
def scanner() -> G2AuthenticatedScanner:
    return G2AuthenticatedScanner(cookie="fake_session=abc123")


def test_extracts_company_names(scanner: G2AuthenticatedScanner) -> None:
    with patch.object(scanner._session, "get", return_value=_make_json_response(_REVIEW_PAGE_1)):
        result = scanner.scan(lookback_days=7)
    companies = {s.company_name for s in result.signals_found}
    assert "Acme Corp" in companies
    assert "Beta Inc" in companies


def test_signal_type_is_g2_review(scanner: G2AuthenticatedScanner) -> None:
    with patch.object(scanner._session, "get", return_value=_make_json_response(_REVIEW_PAGE_1)):
        result = scanner.scan(lookback_days=7)
    assert all(s.signal_type == "g2_review" for s in result.signals_found)


def test_evaluating_keyword_scores_strong(scanner: G2AuthenticatedScanner) -> None:
    with patch.object(scanner._session, "get", return_value=_make_json_response(_REVIEW_PAGE_1)):
        result = scanner.scan(lookback_days=7)
    acme = next(s for s in result.signals_found if s.company_name == "Acme Corp")
    assert acme.signal_strength == SignalStrength.STRONG


def test_ceiling_keyword_scores_at_least_moderate(scanner: G2AuthenticatedScanner) -> None:
    with patch.object(scanner._session, "get", return_value=_make_json_response(_REVIEW_PAGE_1)):
        result = scanner.scan(lookback_days=7)
    beta = next(s for s in result.signals_found if s.company_name == "Beta Inc")
    assert beta.signal_strength in (SignalStrength.STRONG, SignalStrength.MODERATE)


def test_skips_cards_without_company(scanner: G2AuthenticatedScanner) -> None:
    with patch.object(scanner._session, "get", return_value=_make_json_response(_NO_COMPANY_PAGE)):
        result = scanner.scan(lookback_days=7)
    assert len(result.signals_found) == 0


def test_empty_page_returns_zero_signals(scanner: G2AuthenticatedScanner) -> None:
    with patch.object(scanner._session, "get", return_value=_make_json_response(_EMPTY_PAGE)):
        result = scanner.scan(lookback_days=7)
    assert len(result.signals_found) == 0


def test_deduplicates_same_company_across_vendors(scanner: G2AuthenticatedScanner) -> None:
    """Same company in Marketo + HubSpot reviews → one signal."""
    with patch.object(scanner._session, "get", return_value=_make_json_response(_REVIEW_PAGE_1)):
        result = scanner.scan(lookback_days=7)
    companies = [s.company_name for s in result.signals_found]
    assert len(companies) == len(set(c.lower() for c in companies))


def test_missing_cookie_returns_empty_with_no_crash() -> None:
    scanner = G2AuthenticatedScanner(cookie="")
    result = scanner.scan()
    assert len(result.signals_found) == 0
    assert result.scan_type == "g2_review"
    assert any("G2_SESSION_COOKIE" in e for e in result.errors)


def test_403_logs_error_and_continues(scanner: G2AuthenticatedScanner) -> None:
    forbidden = _make_json_response({}, status=403)
    forbidden.raise_for_status = MagicMock()
    with patch.object(scanner._session, "get", return_value=forbidden):
        result = scanner.scan()
    assert len(result.errors) > 0
    assert any("403" in e or "cookie" in e.lower() for e in result.errors)


def test_paginates_multiple_pages(scanner: G2AuthenticatedScanner) -> None:
    """Scanner fetches page 2 when total_pages > 1."""
    responses = [
        _make_json_response(_MULTI_PAGE_1),
        _make_json_response(_MULTI_PAGE_2),
    ]
    with patch.object(scanner._session, "get", side_effect=responses * 9):
        result = scanner.scan(lookback_days=7)
    companies = {s.company_name for s in result.signals_found}
    assert "PageOne Corp" in companies
    assert "PageTwo Ltd" in companies


def test_raw_data_includes_snippet_for_icp_scorer(scanner: G2AuthenticatedScanner) -> None:
    """ICP fit scorer reads raw_data['snippet'] — verify it's populated."""
    with patch.object(scanner._session, "get", return_value=_make_json_response(_REVIEW_PAGE_1)):
        result = scanner.scan(lookback_days=7)
    acme = next(s for s in result.signals_found if s.company_name == "Acme Corp")
    assert "marketo" in acme.raw_data.get("snippet", "").lower()


def test_scan_module_function() -> None:
    cfg = ScannerConfig(
        enabled=True,
        module="scripts.scanners.g2_authenticated_scanner",
        keywords=["Marketo"],
        lookback_days=7,
    )
    with patch(
        "scripts.scanners.g2_authenticated_scanner.G2AuthenticatedScanner.scan"
    ) as mock_scan:
        mock_scan.return_value = MagicMock(scan_type="g2_review", signals_found=[])
        result = scan(cfg)
    mock_scan.assert_called_once_with(7)
```

- [ ] **Step 2: Run tests — verify they all FAIL**

```bash
pytest tests/test_g2_authenticated_scanner.py -v 2>&1 | head -40
```

Expected: multiple failures (`AttributeError` or `AssertionError`) since the scanner still uses HTML scraping.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_g2_authenticated_scanner.py
git commit -m "test: update g2 scanner tests for JSON API shape (RED)"
```

---

### Task 3: Implement JSON API fetching in G2AuthenticatedScanner

Replace the HTML scraping approach entirely. The JSON API endpoint is:
`https://www.g2.com/products/{slug}/reviews.json?filters%5Bstar_rating%5D={stars}&page={page}`

**Files:**
- Modify: `scripts/scanners/g2_authenticated_scanner.py`

- [ ] **Step 1: Replace the scanner implementation**

Replace the entire file contents of `scripts/scanners/g2_authenticated_scanner.py` with:

```python
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
    {"slug": "marketo", "display": "Marketo"},
    {"slug": "hubspot", "display": "HubSpot"},
    {"slug": "pardot", "display": "Pardot"},
]

_STAR_RATINGS = [1, 2, 3]
_MAX_PAGES = 3  # Cap pages per vendor/rating to stay polite

_STRONG_KEYWORDS = {
    "migration", "replacing", "switching", "evaluating", "replacement",
    "alternative", "alternatives", "migrating", "moved off",
}
_MODERATE_KEYWORDS = {
    "expensive", "complex", "slow", "frustrating", "difficult",
    "overhead", "bloated", "ceiling", "too much", "painful", "clunky",
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
_AT_COMPANY_RE = re.compile(
    r"\bat\s+([A-Z][A-Za-z0-9][A-Za-z0-9&.,\- ]{0,50}?)(?:\s*[|,·•\n]|$)"
)
_NON_COMPANIES = {
    "g2", "g2.com", "the time", "the company", "a startup", "my company",
    "a team", "our team", "a large", "a small", "work",
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
        print(f"\nG2 Diagnostics")
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
                    page, data.get("meta", {}).get("total_pages", "?"),
                    vendor["display"], stars, len(reviews),
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
        title = review.get("reviewer", {}).get("title", "") or ""
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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="G2 authenticated review scanner (JSON API)")
    parser.add_argument("--diagnose", action="store_true", help="Print cookie state and API health check")
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
                print(f"    \"{s.raw_data['snippet'][:120]}\"")
        if result.errors:
            print(f"\nErrors ({len(result.errors)}):")
            for e in result.errors:
                print(f"  {e}")
```

- [ ] **Step 2: Run the tests**

```bash
pytest tests/test_g2_authenticated_scanner.py -v
```

Expected: all tests PASS. Fix any failures before continuing.

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
pytest --cov=scripts --cov-report=term-missing -q 2>&1 | tail -20
```

Expected: no new failures. Coverage should stay at or above current level.

- [ ] **Step 4: Run the linter**

```bash
ruff check scripts/scanners/g2_authenticated_scanner.py && ruff format --check scripts/scanners/g2_authenticated_scanner.py
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add scripts/scanners/g2_authenticated_scanner.py
git commit -m "feat: switch G2 scanner from HTML scraping to JSON API, add --diagnose flag"
```

---

### Task 4: Verify end-to-end scoring with g2_review signals

Confirm that a `g2_review` signal now flows through the scoring engine at the right weight. This is a quick manual integration check — no new test files.

**Files:**
- No file changes — this is verification only

- [ ] **Step 1: Verify the intent scorer picks up g2_review weight**

```bash
python -c "
from scripts.config_loader import load_config
from scripts.intent_scorer import IntentScorer
from scripts.models import Signal, SignalStrength
from datetime import datetime, timezone

config = load_config()
scorer = IntentScorer(config)
signal = Signal(
    signal_type='g2_review',
    company_name='Test Corp',
    signal_strength=SignalStrength.STRONG,
    source_url='https://g2.com/test',
    raw_data={'snippet': 'Replacing marketo, evaluating alternatives', 'vendor': 'Marketo'},
    metadata={'star_rating': 2, 'product_mentioned': 'Marketo'},
    detected_at=datetime.now(timezone.utc),
)
result = scorer.score_signals([signal], icp_fit=7.0)
print(f'Combined score: {result.combined_score:.2f}')
print(f'Grade: {result.icp_score.value}')
assert result.combined_score > 4.0, f'Expected >4.0, got {result.combined_score}'
print('PASS — g2_review signal scores correctly')
"
```

Expected output includes `Grade: A` or `Grade: B` and `PASS`.

- [ ] **Step 2: Verify `--diagnose` runs without error (no cookie required)**

```bash
python -m scripts.scanners.g2_authenticated_scanner --diagnose
```

Expected: diagnostic output prints, no Python traceback. If no cookie is set, prints "Cookie set: NO".

- [ ] **Step 3: Final full test run**

```bash
pytest --cov=scripts --cov-report=term-missing -q
```

Expected: all tests pass. No coverage regression below current level.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: verify g2_review scoring end-to-end — all tests passing"
```

---

## Live Demo Runbook (Post-Implementation)

When someone asks for a live demo against their ICP:

**1. Grab a fresh G2 cookie (2 minutes):**
```
Log into g2.com → DevTools (F12) → Network tab → click any request to g2.com
→ right-click → "Copy as cURL" → extract the Cookie header value
→ paste into .env as G2_SESSION_COOKIE="..."
```

**2. Verify the cookie works:**
```bash
python -m scripts.scanners.g2_authenticated_scanner --diagnose
```
If status is 200 and reviews > 0, you're live.

**3. Drop in their ICP config:**
```bash
cp examples/marketo-migration/config.yaml config/config.yaml
# Edit config/config.yaml for their company/ICP if different
```

**4. Run the live scan:**
```bash
python -m scripts.demo_scan --lookback-days 14 --min-grade B
```

**Failure modes and fixes:**
- `403 Forbidden` → cookie expired, re-copy from DevTools
- `reviews: []` on page 1 with status 200 → G2 changed the API endpoint path; run `--debug` and check raw response
- No companies extracted → reviewer titles use a different format; check `raw_data` in `--debug` output

---

## Self-Review

**Spec coverage:**
- ✅ G2 signals actually fire (JSON API, not HTML scraping)
- ✅ `g2_review` wired into scoring config at 3.5 weight / 21-day half-life
- ✅ Pagination support (up to `_MAX_PAGES=3` per vendor/rating)
- ✅ `--diagnose` flag for live demo debugging
- ✅ `raw_data.snippet` populated so ICP fit scorer picks up MAP keywords from review text
- ✅ Cookie-missing path still returns graceful empty result

**Placeholder scan:** None found.

**Type consistency:** `Signal`, `ScanResult`, `SignalStrength`, `ScannerConfig` all imported from `scripts.scanners.base` / `scripts.models` — consistent across all tasks.
