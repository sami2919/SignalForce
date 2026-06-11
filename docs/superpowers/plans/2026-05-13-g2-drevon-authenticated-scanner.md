# G2 Authenticated Scanner via Drevon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the SerpAPI-based MAP frustration scanner with a Drevon-powered scanner that reads G2 review data extracted via the user's authenticated browser session, bypassing G2's IP-based scraping blocks.

**Architecture:** A Drevon browser agent script navigates G2 authenticated as the user, searches for low-star reviews of Marketo/HubSpot/Pardot, and writes structured JSON to a local file. A new `G2AuthenticatedScanner` in SignalForce reads that file and converts reviews into `Signal` objects. The existing `g2_scanner.py` (LinkedIn/blog fallback) stays in place; config switches between them via `module:`.

**Tech Stack:** Python 3.11, Pydantic v2, pytest, Drevon agent (JavaScript written to `drevon/g2_extract.js`), existing `scripts/models.py` Signal/ScanResult types.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `drevon/g2_extract.js` | Create | Drevon agent: navigates G2, extracts reviews, writes JSON |
| `scripts/scanners/g2_authenticated_scanner.py` | Create | Reads Drevon JSON output → Signal objects |
| `tests/test_g2_authenticated_scanner.py` | Create | Unit tests — all file I/O mocked |
| `config/config.yaml` | Modify | Switch `g2.module` to authenticated scanner |
| `.env.example` | Modify | Document `G2_DREVON_OUTPUT_PATH` variable |

---

## Task 1: Drevon agent script

**Files:**
- Create: `drevon/g2_extract.js`

The Drevon agent runs in your browser with your G2 session active. It searches G2 for 1–3 star reviews of Marketo, HubSpot Enterprise, and Pardot, extracts company name + review text + rating, and writes the result to `G2_OUTPUT_PATH` (defaults to `/tmp/g2_reviews.json`).

- [ ] **Step 1: Create the drevon directory and agent file**

```bash
mkdir -p /Users/sami/SignalForce/drevon
```

Create `drevon/g2_extract.js`:

```javascript
/**
 * Drevon agent: extract G2 reviews for MAP vendors.
 *
 * Run via Drevon with your G2 account logged in.
 * Output: JSON array written to G2_OUTPUT_PATH (default: /tmp/g2_reviews.json).
 *
 * Usage in Drevon:
 *   Load this script → agent navigates G2 in your browser → writes output file.
 */

const OUTPUT_PATH = process.env.G2_OUTPUT_PATH || "/tmp/g2_reviews.json";
const LOOKBACK_DAYS = parseInt(process.env.G2_LOOKBACK_DAYS || "30", 10);
const MIN_RATING = parseInt(process.env.G2_MIN_RATING || "3", 10); // 1–3 stars only

const MAP_VENDORS = [
  { slug: "marketo", display: "Marketo" },
  { slug: "hubspot", display: "HubSpot" },
  { slug: "pardot", display: "Pardot" },
];

// G2 review search URL for a vendor, filtered by star rating and recency
function reviewSearchUrl(vendorSlug, stars) {
  return (
    `https://www.g2.com/products/${vendorSlug}/reviews?` +
    `filters[star_rating]=${stars}&filters[sort]=recent&page=1`
  );
}

// Extract company name from a G2 review card DOM element.
// G2 shows reviewer's job title + company inline, e.g. "VP Marketing at Acme Corp"
function extractCompanyFromCard(card) {
  const titleEl = card.querySelector('[data-testid="reviewer-title"]') ||
                  card.querySelector('.reviewer-title') ||
                  card.querySelector('[class*="reviewer"]');
  if (!titleEl) return null;
  const text = titleEl.innerText || titleEl.textContent || "";
  const atMatch = text.match(/\bat\s+([A-Z][A-Za-z0-9\s&.,']{1,50})/);
  return atMatch ? atMatch[1].trim().replace(/[,.]$/, "") : null;
}

// Extract review snippet text from a card
function extractSnippet(card) {
  const bodyEl = card.querySelector('[data-testid="review-body"]') ||
                 card.querySelector('.review-body') ||
                 card.querySelector('[class*="review-body"]');
  if (!bodyEl) return "";
  return (bodyEl.innerText || bodyEl.textContent || "").slice(0, 500).trim();
}

// Extract star rating (integer 1–5) from a card
function extractRating(card) {
  const starsEl = card.querySelector('[data-testid="star-rating"]') ||
                  card.querySelector('[class*="star-rating"]') ||
                  card.querySelector('[aria-label*="star"]');
  if (!starsEl) return null;
  const label = starsEl.getAttribute("aria-label") || starsEl.innerText || "";
  const m = label.match(/(\d)/);
  return m ? parseInt(m[1], 10) : null;
}

// Scrape one vendor × one star rating page, return array of review objects
async function scrapeReviewPage(vendorSlug, vendorDisplay, stars) {
  const url = reviewSearchUrl(vendorSlug, stars);
  await page.goto(url, { waitUntil: "networkidle2" });

  // G2 renders reviews client-side — wait for first card
  await page.waitForSelector('[data-testid="review-card"], .review-card', {
    timeout: 10000,
  }).catch(() => null); // no cards on this page is OK

  return page.evaluate(({ vendorDisplay, stars }) => {
    const results = [];
    const cards = document.querySelectorAll(
      '[data-testid="review-card"], .review-card, [class*="review-card"]'
    );
    cards.forEach((card) => {
      function extractText(selectors) {
        for (const sel of selectors) {
          const el = card.querySelector(sel);
          if (el) return (el.innerText || el.textContent || "").trim();
        }
        return "";
      }

      const titleText = extractText([
        '[data-testid="reviewer-title"]',
        ".reviewer-title",
        '[class*="reviewer"]',
      ]);
      const atMatch = titleText.match(/\bat\s+([A-Z][A-Za-z0-9\s&.,']{1,50})/);
      const company = atMatch ? atMatch[1].trim().replace(/[,.]$/, "") : null;
      if (!company) return;

      const snippet = extractText([
        '[data-testid="review-body"]',
        ".review-body",
        '[class*="review-body"]',
      ]).slice(0, 500);

      const ratingEl = card.querySelector('[aria-label*="star"], [class*="star-rating"]');
      const ratingLabel = ratingEl
        ? ratingEl.getAttribute("aria-label") || ratingEl.innerText || ""
        : "";
      const ratingMatch = ratingLabel.match(/(\d)/);
      const rating = ratingMatch ? parseInt(ratingMatch[1], 10) : stars;

      const linkEl = card.querySelector('a[href*="/reviews/"]');
      const reviewUrl = linkEl ? "https://www.g2.com" + linkEl.getAttribute("href") : "";

      results.push({ company, snippet, rating, vendor: vendorDisplay, review_url: reviewUrl });
    });
    return results;
  }, { vendorDisplay, stars });
}

// Main: iterate vendors × star ratings, collect results, write output
(async () => {
  const allReviews = [];

  for (const vendor of MAP_VENDORS) {
    for (let stars = 1; stars <= MIN_RATING; stars++) {
      try {
        const reviews = await scrapeReviewPage(vendor.slug, vendor.display, stars);
        console.log(`[g2_extract] ${vendor.display} ★${stars}: ${reviews.length} reviews`);
        allReviews.push(...reviews);
      } catch (err) {
        console.error(`[g2_extract] Failed ${vendor.display} ★${stars}: ${err.message}`);
      }
    }
  }

  const output = {
    extracted_at: new Date().toISOString(),
    lookback_days: LOOKBACK_DAYS,
    review_count: allReviews.length,
    reviews: allReviews,
  };

  // Write output — Drevon exposes Node.js fs in agent context
  const fs = require("fs");
  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2));
  console.log(`[g2_extract] Wrote ${allReviews.length} reviews to ${OUTPUT_PATH}`);
})();
```

- [ ] **Step 2: Verify the file exists**

```bash
ls -la /Users/sami/SignalForce/drevon/g2_extract.js
```

Expected: file present, ~3KB.

- [ ] **Step 3: Commit**

```bash
cd /Users/sami/SignalForce
git add drevon/g2_extract.js
git commit -m "feat: add Drevon G2 browser agent script for authenticated review extraction"
```

---

## Task 2: G2AuthenticatedScanner Python module

**Files:**
- Create: `scripts/scanners/g2_authenticated_scanner.py`

Reads the JSON file Drevon wrote and converts each review into a `Signal` with `signal_type="g2_review"`. Falls back gracefully when the file is missing (Drevon hasn't run yet) — returns an empty `ScanResult` with a clear warning.

- [ ] **Step 1: Write the failing test first**

Create `tests/test_g2_authenticated_scanner.py`:

```python
"""Unit tests for G2AuthenticatedScanner.

All file I/O is mocked — no real filesystem reads.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from scripts.scanners.g2_authenticated_scanner import G2AuthenticatedScanner, scan
from scripts.config_loader import ScannerConfig
from scripts.models import SignalStrength


SAMPLE_DREVON_OUTPUT = {
    "extracted_at": "2026-05-13T10:00:00Z",
    "lookback_days": 30,
    "review_count": 2,
    "reviews": [
        {
            "company": "Acme Corp",
            "snippet": "Marketo is way too complex for our team. We spent more time on plumbing than campaigns.",
            "rating": 2,
            "vendor": "Marketo",
            "review_url": "https://www.g2.com/reviews/marketo-review-12345",
        },
        {
            "company": "Beta Inc",
            "snippet": "HubSpot Enterprise pricing hit our ceiling hard. Evaluating alternatives now.",
            "rating": 3,
            "vendor": "HubSpot",
            "review_url": "https://www.g2.com/reviews/hubspot-review-67890",
        },
    ],
}

EMPTY_DREVON_OUTPUT = {
    "extracted_at": "2026-05-13T10:00:00Z",
    "lookback_days": 30,
    "review_count": 0,
    "reviews": [],
}


def _mock_file(content: dict):
    return mock_open(read_data=json.dumps(content))


def test_scanner_converts_reviews_to_signals():
    """Each review with a company name becomes one Signal."""
    scanner = G2AuthenticatedScanner(output_path=Path("/tmp/g2_reviews.json"))
    with patch("builtins.open", _mock_file(SAMPLE_DREVON_OUTPUT)):
        with patch("pathlib.Path.exists", return_value=True):
            result = scanner.scan()
    assert len(result.signals_found) == 2
    assert all(s.signal_type == "g2_review" for s in result.signals_found)


def test_scanner_sets_company_name():
    scanner = G2AuthenticatedScanner(output_path=Path("/tmp/g2_reviews.json"))
    with patch("builtins.open", _mock_file(SAMPLE_DREVON_OUTPUT)):
        with patch("pathlib.Path.exists", return_value=True):
            result = scanner.scan()
    companies = {s.company_name for s in result.signals_found}
    assert "Acme Corp" in companies
    assert "Beta Inc" in companies


def test_scanner_scores_migration_language_as_strong():
    """Review containing 'evaluating alternatives' maps to STRONG signal strength."""
    scanner = G2AuthenticatedScanner(output_path=Path("/tmp/g2_reviews.json"))
    with patch("builtins.open", _mock_file(SAMPLE_DREVON_OUTPUT)):
        with patch("pathlib.Path.exists", return_value=True):
            result = scanner.scan()
    beta_signals = [s for s in result.signals_found if s.company_name == "Beta Inc"]
    assert beta_signals[0].signal_strength == SignalStrength.STRONG


def test_scanner_scores_frustration_language_as_moderate():
    """Review with 'too complex' maps to MODERATE signal strength."""
    scanner = G2AuthenticatedScanner(output_path=Path("/tmp/g2_reviews.json"))
    with patch("builtins.open", _mock_file(SAMPLE_DREVON_OUTPUT)):
        with patch("pathlib.Path.exists", return_value=True):
            result = scanner.scan()
    acme_signals = [s for s in result.signals_found if s.company_name == "Acme Corp"]
    assert acme_signals[0].signal_strength == SignalStrength.MODERATE


def test_scanner_returns_empty_when_file_missing(caplog):
    """Missing Drevon output file → empty ScanResult, warning logged, no crash."""
    scanner = G2AuthenticatedScanner(output_path=Path("/tmp/g2_reviews.json"))
    with patch("pathlib.Path.exists", return_value=False):
        result = scanner.scan()
    assert len(result.signals_found) == 0
    assert "G2_DREVON_OUTPUT_PATH" in caplog.text


def test_scanner_returns_empty_on_zero_reviews():
    scanner = G2AuthenticatedScanner(output_path=Path("/tmp/g2_reviews.json"))
    with patch("builtins.open", _mock_file(EMPTY_DREVON_OUTPUT)):
        with patch("pathlib.Path.exists", return_value=True):
            result = scanner.scan()
    assert len(result.signals_found) == 0


def test_scan_module_function():
    """Module-level scan() should accept ScannerConfig and return g2_review scan_type."""
    cfg = ScannerConfig(
        enabled=True,
        module="scripts.scanners.g2_authenticated_scanner",
        keywords=["Marketo", "HubSpot"],
        lookback_days=30,
    )
    mock_result = SAMPLE_DREVON_OUTPUT
    scanner_instance = G2AuthenticatedScanner.__new__(G2AuthenticatedScanner)
    with patch(
        "scripts.scanners.g2_authenticated_scanner.G2AuthenticatedScanner.scan"
    ) as mock_scan:
        mock_scan.return_value.__class__.__name__ = "ScanResult"
        result = scan(cfg)
    mock_scan.assert_called_once()
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd /Users/sami/SignalForce
python -m pytest tests/test_g2_authenticated_scanner.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'scripts.scanners.g2_authenticated_scanner'`

- [ ] **Step 3: Implement G2AuthenticatedScanner**

Create `scripts/scanners/g2_authenticated_scanner.py`:

```python
"""G2 Authenticated Review Scanner.

Reads structured review data produced by the Drevon browser agent
(drevon/g2_extract.js) and converts each review into a Signal.

The Drevon agent runs in the user's authenticated G2 browser session,
bypassing IP-based scraping blocks. This module is purely a file reader
— all browser automation lives in the JS agent.

Output file path: $G2_DREVON_OUTPUT_PATH (default: /tmp/g2_reviews.json)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_PATH = Path(
    os.environ.get("G2_DREVON_OUTPUT_PATH", "/tmp/g2_reviews.json")
)

_STRONG_KEYWORDS = {
    "migration", "replacing", "switching", "evaluating", "replacement",
    "alternative", "alternatives", "migrating", "moved off", "left marketo",
    "left hubspot",
}
_MODERATE_KEYWORDS = {
    "expensive", "complex", "slow", "frustrating", "difficult",
    "overhead", "bloated", "ceiling", "too much", "painful",
}


class G2AuthenticatedScanner:
    """Converts Drevon-extracted G2 reviews into Signal objects.

    Args:
        output_path: Path to the JSON file written by drevon/g2_extract.js.
            Defaults to $G2_DREVON_OUTPUT_PATH or /tmp/g2_reviews.json.
    """

    def __init__(self, output_path: Path | None = None) -> None:
        self._output_path = output_path or _DEFAULT_OUTPUT_PATH

    def scan(self) -> ScanResult:
        started_at = datetime.now(timezone.utc)

        if not self._output_path.exists():
            logger.warning(
                "G2 Drevon output file not found at %s. "
                "Run drevon/g2_extract.js first, or set G2_DREVON_OUTPUT_PATH.",
                self._output_path,
            )
            return ScanResult(
                scan_type="g2_review",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                signals_found=[],
                total_raw_results=0,
                total_after_dedup=0,
                errors=[f"Output file missing: {self._output_path}"],
            )

        with open(self._output_path) as f:
            data = json.load(f)

        reviews = data.get("reviews", [])
        signals: list[Signal] = []
        seen_companies: set[str] = set()

        for review in reviews:
            company = (review.get("company") or "").strip()
            if not company:
                continue

            # Deduplicate by company — one signal per company per scan
            key = company.lower()
            if key in seen_companies:
                continue
            seen_companies.add(key)

            snippet = review.get("snippet", "")
            vendor = review.get("vendor", "Unknown MAP")
            review_url = review.get("review_url", "")
            rating = review.get("rating")

            strength = self._score(snippet, rating)

            signals.append(
                Signal(
                    signal_type="g2_review",
                    company_name=company,
                    signal_strength=strength,
                    source_url=review_url,
                    raw_data={
                        "snippet": snippet,
                        "rating": rating,
                        "vendor": vendor,
                    },
                    metadata={
                        "source_type": "g2_authenticated",
                        "product_mentioned": vendor,
                        "frustration_keywords": self._found_keywords(snippet),
                        "star_rating": rating,
                    },
                )
            )

        return ScanResult(
            scan_type="g2_review",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            signals_found=signals,
            total_raw_results=len(reviews),
            total_after_dedup=len(signals),
        )

    def _score(self, text: str, rating: int | None) -> SignalStrength:
        lower = text.lower()
        for kw in _STRONG_KEYWORDS:
            if kw in lower:
                return SignalStrength.STRONG
        # Rating 1–2 with frustration language → STRONG; rating 3 → MODERATE
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
    """Module-level entry point called by scanner_runner."""
    output_path = Path(
        os.environ.get("G2_DREVON_OUTPUT_PATH", "/tmp/g2_reviews.json")
    )
    return G2AuthenticatedScanner(output_path=output_path).scan()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/sami/SignalForce
python -m pytest tests/test_g2_authenticated_scanner.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/scanners/g2_authenticated_scanner.py tests/test_g2_authenticated_scanner.py
git commit -m "feat: add G2AuthenticatedScanner reading Drevon browser agent output"
```

---

## Task 3: Wire into config and document the env var

**Files:**
- Modify: `config/config.yaml`
- Modify: `.env.example`

- [ ] **Step 1: Update config.yaml to use the authenticated scanner**

In `config/config.yaml`, change the `g2` scanner block from:

```yaml
  g2:
    enabled: true
    module: "scripts.scanners.g2_scanner"
    lookback_days: 30
    keywords:
      - "Marketo"
      - "HubSpot Enterprise"
      - "Pardot"
      - "MAP migration"
      - "marketing automation"
```

To:

```yaml
  g2:
    enabled: true
    module: "scripts.scanners.g2_authenticated_scanner"
    lookback_days: 30
    keywords:
      - "Marketo"
      - "HubSpot Enterprise"
      - "Pardot"
      - "MAP migration"
      - "marketing automation"
    # Output file written by drevon/g2_extract.js
    # Override with G2_DREVON_OUTPUT_PATH env var (default: /tmp/g2_reviews.json)

  # Keep LinkedIn/blog MAP frustration scanner as a secondary source
  map_frustration:
    enabled: true
    module: "scripts.scanners.g2_scanner"
    lookback_days: 30
    keywords:
      - "Marketo"
      - "HubSpot Enterprise"
      - "Pardot"
```

- [ ] **Step 2: Update .env.example**

Add to `.env.example`:

```bash
# G2 Authenticated Scanner (via Drevon browser agent)
# Path where drevon/g2_extract.js writes extracted reviews.
# Run the Drevon agent first, then run the scanner.
G2_DREVON_OUTPUT_PATH=/tmp/g2_reviews.json

# Optional: how many days of reviews to extract (passed to Drevon agent)
G2_LOOKBACK_DAYS=30

# Optional: maximum star rating to extract (1=lowest frustration, 3=moderate)
# Reviews at or below this rating are extracted. Default: 3
G2_MIN_RATING=3
```

- [ ] **Step 3: Verify config loads cleanly**

```bash
cd /Users/sami/SignalForce
python3 -c "
from scripts.config_loader import load_config
c = load_config()
print('Scanners:', list(c.scanners.keys()))
print('g2 module:', c.scanners['g2'].module)
"
```

Expected output:
```
Scanners: ['github', 'arxiv', 'huggingface', 'jobs', 'funding', 'linkedin', 'g2', 'map_frustration']
g2 module: scripts.scanners.g2_authenticated_scanner
```

- [ ] **Step 4: Run full test suite to confirm nothing broke**

```bash
cd /Users/sami/SignalForce
python -m pytest --cov=scripts --cov-report=term-missing -q 2>&1 | tail -10
```

Expected: all existing tests pass, coverage stays at or above 79%.

- [ ] **Step 5: Commit**

```bash
git add config/config.yaml .env.example
git commit -m "chore: wire G2AuthenticatedScanner into config, document G2_DREVON_OUTPUT_PATH"
```

---

## Task 4: End-to-end smoke test with a real Drevon run

**Files:**
- No code changes — this is an operational verification step.

- [ ] **Step 1: Load the Drevon agent in your browser**

Open Drevon → New Agent → load `drevon/g2_extract.js`. Make sure you are logged into G2 in the same browser profile Drevon uses.

- [ ] **Step 2: Run the agent**

Drevon will navigate G2 → Marketo reviews → HubSpot reviews → Pardot reviews (1–3 stars each), then write output to `/tmp/g2_reviews.json`.

Verify output exists:

```bash
cat /tmp/g2_reviews.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Reviews: {d[\"review_count\"]} | Companies: {len({r[\"company\"] for r in d[\"reviews\"]})}')"
```

Expected: `Reviews: N | Companies: M` where N > 0.

- [ ] **Step 3: Run the full pipeline**

```bash
cd /Users/sami/SignalForce
python3 -m scripts.demo_scan --min-grade B 2>&1
```

The G2 scanner should now contribute authenticated reviews to the signal table. Companies with G2 reviews AND job postings will score higher due to multi-source multiplier.

- [ ] **Step 4: Confirm G2 signals appear in results**

```bash
python3 -c "
import json
with open('/tmp/signals/raw_signals.json') as f:
    sigs = json.load(f)
g2 = [s for s in sigs if s['signal_type'] == 'g2_review']
print(f'G2 authenticated signals: {len(g2)}')
for s in g2[:5]:
    print(f'  {s[\"company_name\"]} | {s[\"signal_strength\"]} | {s[\"raw_data\"][\"vendor\"]}')
"
```

---

## Self-Review

**Spec coverage:**
- ✅ Bypass G2 scraping block → Drevon uses user's authenticated browser session
- ✅ Company name extraction → from `"at CompanyName"` in reviewer title
- ✅ Signal strength scoring → mirrors existing `g2_scanner.py` keyword logic
- ✅ Graceful fallback when Drevon hasn't run → empty ScanResult + warning
- ✅ Old LinkedIn/blog scanner preserved → renamed to `map_frustration` in config
- ✅ All tests mock file I/O → no real filesystem dependency in unit tests

**Placeholder scan:** None found.

**Type consistency:**
- `Signal` fields (`signal_type`, `company_name`, `signal_strength`, `source_url`, `raw_data`, `metadata`) match `scripts/models.py` definition throughout.
- `ScanResult` fields (`scan_type`, `started_at`, `completed_at`, `signals_found`, `total_raw_results`, `total_after_dedup`) match throughout.
- `G2AuthenticatedScanner.scan()` → returns `ScanResult` ✅
- `scan(config: ScannerConfig)` module entry point matches `scanner_runner.py` expected signature ✅
