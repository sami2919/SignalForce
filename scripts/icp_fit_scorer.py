"""ICP fit scorer for the Marketo-migration ICP (warehouse-native MAP vendor example).

Converts raw Signal objects into a 0–10 numeric ICP fit score.
Passed to IntentScorer.score_signals(icp_fit=...) to compute the combined
Gojiberry score: COMBINED = (ICP_Fit × 0.45) + (Intent × 0.55).

Scoring table (additive, capped at 10.0):
  Marketo in skills/snippet   +3.0   (explicit MAP pain = highest value)
  Salesforce in signals       +2.0   (vendor is Salesforce-native)
  HubSpot Enterprise signal   +2.0   (hitting ceiling)
  Pardot/Eloqua signal        +2.0   (enterprise MAP = large ACV)
  Reverse ETL (Hightouch/     +2.5   (papering over MAP with middleware)
    Census)
  Data warehouse tech         +1.5   (Snowflake/BigQuery/Databricks/dbt)
  PLG tools (Mixpanel etc.)   +1.0   (product-led + MAP gap)
"""

from __future__ import annotations

from scripts.models import Signal

_MAP_PAIN_KEYWORDS: dict[str, float] = {
    "marketo": 4.0,
    "hubspot enterprise": 2.5,
    "hubspot": 2.0,
    "pardot": 2.5,
    "eloqua": 2.5,
    "salesforce marketing cloud": 2.0,
    "map replacement": 2.5,
    "legacy map": 2.5,
}

_SALESFORCE_KEYWORDS: dict[str, float] = {
    "salesforce": 3.0,
    "sfdc": 3.0,
}

_REVERSE_ETL_KEYWORDS: dict[str, float] = {
    "hightouch": 2.5,
    "census": 2.5,
    "reverse etl": 2.5,
    "mparticle": 1.5,
}

_WAREHOUSE_KEYWORDS: dict[str, float] = {
    "snowflake": 1.5,
    "bigquery": 1.5,
    "databricks": 1.5,
    "dbt": 1.0,
    "data warehouse": 1.0,
    "warehouse-native": 2.0,
}

_PLG_KEYWORDS: dict[str, float] = {
    "mixpanel": 1.0,
    "amplitude": 1.0,
    "posthog": 1.0,
    "product analytics": 0.8,
    "product-led growth": 0.8,
    "plg": 0.8,
}

_MOPS_ROLE_KEYWORDS: dict[str, float] = {
    # A company hiring for these roles has an active MOPs function and a MAP dependency.
    "marketing operations": 3.0,
    "marketing automation": 3.0,  # explicitly MAP
    "marketing technology": 2.5,
    "demand generation": 2.0,
    "lifecycle marketing": 2.0,
    "revenue operations": 1.5,
    "marketing data engineer": 2.5,  # data + MOPs = warehouse-native gap
    "marketing analytics": 1.5,
    "martech": 2.5,
    "mops": 3.0,
}

_ALL_TABLES: list[dict[str, float]] = [
    _MAP_PAIN_KEYWORDS,
    _SALESFORCE_KEYWORDS,
    _REVERSE_ETL_KEYWORDS,
    _WAREHOUSE_KEYWORDS,
    _PLG_KEYWORDS,
    _MOPS_ROLE_KEYWORDS,
]

_MAX_SCORE = 10.0


def _extract_text(signal: Signal) -> str:
    """Collect all searchable text from a signal into one lowercase string."""
    parts: list[str] = []

    for key in ("skills_mentioned", "job_titles", "topics", "keywords"):
        value = signal.metadata.get(key)
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif isinstance(value, str):
            parts.append(value)

    postings = signal.raw_data.get("postings", [])
    for posting in postings:
        if isinstance(posting, dict):
            parts.append(posting.get("snippet", ""))
            parts.append(posting.get("title", ""))

    activities = signal.raw_data.get("activities", [])
    for activity in activities:
        if isinstance(activity, dict):
            parts.append(activity.get("topic", ""))

    # MAP frustration / blog signals store content directly on raw_data
    for key in ("snippet", "title", "body"):
        val = signal.raw_data.get(key)
        if isinstance(val, str):
            parts.append(val)

    return " ".join(parts).lower()


def compute_icp_fit(signals: list[Signal]) -> float:
    """Compute a 0–10 ICP fit score from a list of signals.

    Scans all signal text for MAP pain, Salesforce, warehouse, and PLG
    keywords. Each keyword contributes additively; result capped at 10.0.
    Keywords are de-duplicated — finding "marketo" in three signals only
    adds the 3.0 points once.
    """
    if not signals:
        return 0.0

    combined_text = " ".join(_extract_text(s) for s in signals)
    total = 0.0
    awarded: set[str] = set()

    for table in _ALL_TABLES:
        for keyword, points in table.items():
            if keyword not in awarded and keyword in combined_text:
                total += points
                awarded.add(keyword)

    return min(total, _MAX_SCORE)
