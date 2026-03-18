"""LinkedIn activity signal scanner.

Detects prospects active on LinkedIn posting about RL/ML topics.
The 48-hour activity filter alone doubles response rates (Gojiberry AI).

Works in data-input mode: accepts pre-collected activity data as JSON/dicts.
Data can come from Sales Navigator export, Phantom Buster, or manual research.
Keywords driving relevance filtering are configurable via ScannerConfig.keywords.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, UTC

from scripts.scanners.base import ScannerConfig, ScanResult, Signal, SignalStrength

logger = logging.getLogger(__name__)

# Default keywords indicating relevance in activity topics
_DEFAULT_KEYWORDS: list[str] = [
    "reinforcement learning",
    "rlhf",
    "grpo",
    "reward model",
    "rl environment",
    "gymnasium",
    "stable-baselines",
    "policy optimization",
    "ppo",
    "dpo",
    "machine learning",
    "deep learning",
    "ai agent",
    "llm training",
    "model training",
    "neural network",
    "transformer",
    "fine-tuning",
    "artificial intelligence",
    "ml infrastructure",
    "mlops",
]

# Module-level alias kept for backward compatibility with tests that patch RL_KEYWORDS directly
RL_KEYWORDS = _DEFAULT_KEYWORDS


class LinkedInActivityScanner:
    """Scans LinkedIn activity data for engagement signals."""

    def __init__(self, max_age_hours: int = 48, keywords: list[str] | None = None) -> None:
        self.max_age_hours = max_age_hours
        self._keywords = keywords if keywords is not None else _DEFAULT_KEYWORDS

    def scan_from_data(
        self,
        activity_data: list[dict],
        now: datetime | None = None,
    ) -> ScanResult:
        """Process pre-collected LinkedIn activity data into signals.

        Each activity dict should have:
            - name: str (contact name)
            - company: str (company name)
            - activity_type: str ("posted", "commented", "liked", "shared")
            - topic: str (content of the post/comment)
            - timestamp: str (ISO format datetime)

        Returns ScanResult with signals grouped by company.
        """
        if now is None:
            now = datetime.now(UTC)

        started_at = now
        cutoff = now - timedelta(hours=self.max_age_hours)

        relevant: list[dict] = []
        total_raw = len(activity_data)
        for activity in activity_data:
            ts = self._parse_timestamp(activity.get("timestamp", ""))
            if ts is None or ts < cutoff:
                continue
            topic = activity.get("topic", "").lower()
            if not self._is_relevant(topic):
                continue
            relevant.append(activity)

        company_activities: dict[str, list[dict]] = defaultdict(list)
        for activity in relevant:
            company = activity.get("company", "").strip()
            if company:
                company_activities[company].append(activity)

        signals: list[Signal] = []
        for company, activities in company_activities.items():
            strength = self._score_activities(activities)
            signal = self._create_signal(company, activities, strength)
            signals.append(signal)

        return ScanResult(
            scan_type="linkedin_activity",
            started_at=started_at,
            completed_at=datetime.now(UTC),
            signals_found=signals,
            total_raw_results=total_raw,
            total_after_dedup=len(signals),
        )

    def _is_relevant(self, topic: str) -> bool:
        """Return True if topic contains any configured keyword."""
        return any(kw in topic for kw in self._keywords)

    def _score_activities(self, activities: list[dict]) -> SignalStrength:
        """Score based on activity type and volume.

        - Posted about topic: STRONG (highest intent)
        - Commented on content: MODERATE
        - Liked/shared: WEAK
        Multiple activities from same company → highest type wins.
        """
        has_posted = any(a.get("activity_type") == "posted" for a in activities)
        has_commented = any(a.get("activity_type") == "commented" for a in activities)

        if has_posted:
            return SignalStrength.STRONG
        if has_commented:
            return SignalStrength.MODERATE
        return SignalStrength.WEAK

    def _create_signal(
        self, company: str, activities: list[dict], strength: SignalStrength
    ) -> Signal:
        activity_types = list({a.get("activity_type", "unknown") for a in activities})
        topics = list({a.get("topic", "") for a in activities if a.get("topic")})
        contacts = list({a.get("name", "") for a in activities if a.get("name")})

        return Signal(
            signal_type="linkedin_activity",
            company_name=company,
            signal_strength=strength,
            source_url=f"https://linkedin.com/company/{company.lower().replace(' ', '-')}",
            raw_data={"activities": activities},
            metadata={
                "activity_types": activity_types,
                "topics": topics,
                "active_contacts": contacts,
                "activity_count": len(activities),
            },
        )

    def _parse_timestamp(self, ts_str: str) -> datetime | None:
        if not ts_str:
            return None
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except (ValueError, TypeError):
            return None


# ---------------------------------------------------------------------------
# Module-level entry point
# ---------------------------------------------------------------------------


def scan(config: ScannerConfig) -> ScanResult:
    """Run a LinkedIn activity scan using configuration.

    Because LinkedIn activity data must be pre-collected externally (from
    Sales Navigator, Phantom Buster, etc.), this entry point returns an empty
    ScanResult when called without external data. Use scan_from_data() directly
    when you have activity data to process.

    Args:
        config: ScannerConfig with keywords list and lookback_days.

    Returns:
        ScanResult (empty unless data is injected via scan_from_data).
    """
    keywords = config.keywords or None
    scanner = LinkedInActivityScanner(
        max_age_hours=config.lookback_days * 24,
        keywords=keywords,
    )
    return scanner.scan_from_data([])


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    print("LinkedInActivityScanner — data-input mode demo")
    print()
    print("Usage: pipe JSON array of activity dicts to stdin")
    print()
    print("Example activity dict:")
    print(
        json.dumps(
            {
                "name": "Jane Smith",
                "company": "Acme AI",
                "activity_type": "posted",
                "topic": "reinforcement learning environments for robotics",
                "timestamp": "2024-01-15T10:30:00Z",
            },
            indent=2,
        )
    )
    sys.exit(0)
