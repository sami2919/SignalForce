"""ICP fit scorer for configurable GTM ICPs.

Converts raw Signal objects into a 0–10 numeric ICP fit score.
Passed to IntentScorer.score_signals(icp_fit=...) to compute the combined
Gojiberry score: COMBINED = (ICP_Fit × 0.45) + (Intent × 0.55).

The scorer still supports the Conversion Marketo-migration branch, but it also
includes a lighter set of AI-first demand-gen keywords so Kana-style growth,
SEO, experimentation, and stack-plumbing signals contribute to fit as well.
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

_GROWTH_ENGINE_KEYWORDS: dict[str, float] = {
    "growth engineer": 2.0,
    "demand generation": 1.8,
    "lifecycle marketing": 2.0,
    "growth marketing": 1.5,
    "revenue operations": 1.5,
    "lead routing": 1.5,
    "personalization": 1.5,
    "experimentation": 1.5,
}

_AI_NATIVE_MARKETING_KEYWORDS: dict[str, float] = {
    "ai-first marketing": 2.0,
    "ai marketing": 1.8,
    "agentic": 1.8,
    "automation": 1.2,
    "openai": 1.0,
    "claude": 1.0,
}

_CONTENT_SEO_KEYWORDS: dict[str, float] = {
    "seo": 1.5,
    "semrush": 1.5,
    "content strategy": 1.2,
    "content operations": 1.5,
    "answer engine optimization": 1.8,
    "aeo": 1.8,
}

_STACK_PLUMBING_KEYWORDS: dict[str, float] = {
    "clay": 1.5,
    "sales navigator": 1.5,
    "instantly": 1.2,
    "hubspot": 2.0,
    "linkedin": 1.0,
    "wiza": 1.2,
}

# Keywords extracted from Firecrawl website enrichment signals
_WEBSITE_ENRICHMENT_KEYWORDS: dict[str, float] = {
    "reinforcement learning": 2.5,
    "rlhf": 3.0,
    "grpo": 3.0,
    "reward model": 2.5,
    "reward modeling": 2.5,
    "policy gradient": 2.0,
    "sim-to-real": 2.5,
    "post-training": 2.5,
    "fine-tuning": 1.5,
    "inference": 1.0,
    "gpu": 1.0,
    "cuda": 1.0,
    "pytorch": 0.8,
    "tensorflow": 0.8,
    "jax": 0.8,
    "agent": 1.5,
    "llm": 1.5,
    "machine learning": 1.0,
    "ai infrastructure": 2.0,
    "training cluster": 2.0,
    "training platform": 2.0,
}

_ALL_TABLES: list[dict[str, float]] = [
    _MAP_PAIN_KEYWORDS,
    _SALESFORCE_KEYWORDS,
    _REVERSE_ETL_KEYWORDS,
    _WAREHOUSE_KEYWORDS,
    _PLG_KEYWORDS,
    _MOPS_ROLE_KEYWORDS,
    _GROWTH_ENGINE_KEYWORDS,
    _AI_NATIVE_MARKETING_KEYWORDS,
    _CONTENT_SEO_KEYWORDS,
    _STACK_PLUMBING_KEYWORDS,
    _WEBSITE_ENRICHMENT_KEYWORDS,
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
    for key in ("snippet", "title", "body", "markdown"):
        val = signal.raw_data.get(key)
        if isinstance(val, str):
            parts.append(val)

    # Firecrawl website enrichment signals store structured data in metadata
    if signal.signal_type == "website_enrichment":
        meta = signal.metadata
        desc = meta.get("product_description", "")
        if isinstance(desc, str):
            parts.append(desc)
        tech = meta.get("tech_stack", [])
        if isinstance(tech, list):
            parts.extend(str(t) for t in tech)
        hiring = meta.get("hiring_language", [])
        if isinstance(hiring, list):
            parts.extend(str(h) for h in hiring)

    # Firecrawl search signals store content in raw_data markdown + description
    if signal.signal_type == "firecrawl_search":
        desc = signal.raw_data.get("description", "")
        if isinstance(desc, str):
            parts.append(desc)

    # G2 Firecrawl signals store frustration keywords and vendor in metadata
    if signal.signal_type == "g2_review":
        vendor = signal.metadata.get("product_mentioned", "")
        if isinstance(vendor, str):
            parts.append(vendor)

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
