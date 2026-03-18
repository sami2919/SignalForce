"""Tests for LinkedIn activity signal scanner."""

from __future__ import annotations

from datetime import datetime, timedelta, UTC

from scripts.linkedin_activity import LinkedInActivityScanner
from scripts.models import SignalType, SignalStrength


def _make_activity(
    name: str = "John Smith",
    company: str = "Acme AI",
    activity_type: str = "posted",
    topic: str = "reinforcement learning",
    hours_ago: float = 1,
) -> dict:
    ts = (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()
    return {
        "name": name,
        "company": company,
        "activity_type": activity_type,
        "topic": topic,
        "timestamp": ts,
    }


class TestLinkedInActivityScanner:
    def test_scan_returns_scan_result(self):
        data = [_make_activity()]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert result.scan_type == SignalType.LINKEDIN_ACTIVITY
        assert len(result.signals_found) == 1

    def test_filters_non_rl_activity(self):
        data = [_make_activity(topic="cooking recipes")]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert len(result.signals_found) == 0

    def test_48_hour_filter(self):
        data = [_make_activity(hours_ago=72)]  # 3 days old
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert len(result.signals_found) == 0

    def test_within_48_hours_included(self):
        data = [_make_activity(hours_ago=24)]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert len(result.signals_found) == 1

    def test_posted_about_rl_is_strong(self):
        data = [_make_activity(activity_type="posted", topic="reinforcement learning environments")]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert result.signals_found[0].signal_strength == SignalStrength.STRONG

    def test_commented_is_moderate(self):
        data = [_make_activity(activity_type="commented", topic="RL environment platform")]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert result.signals_found[0].signal_strength == SignalStrength.MODERATE

    def test_liked_is_weak(self):
        data = [_make_activity(activity_type="liked", topic="machine learning infrastructure")]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert result.signals_found[0].signal_strength == SignalStrength.WEAK

    def test_groups_by_company(self):
        data = [
            _make_activity(name="Person A", company="SameCo", topic="reinforcement learning"),
            _make_activity(name="Person B", company="SameCo", topic="rl training"),
        ]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert len(result.signals_found) == 1
        assert result.signals_found[0].company_name == "SameCo"

    def test_different_companies_separate(self):
        data = [
            _make_activity(company="CompanyA", topic="reinforcement learning"),
            _make_activity(company="CompanyB", topic="machine learning"),
        ]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert len(result.signals_found) == 2

    def test_metadata_includes_activity_details(self):
        data = [_make_activity()]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        meta = result.signals_found[0].metadata
        assert "activity_types" in meta
        assert "topics" in meta
        assert "active_contacts" in meta
        assert "activity_count" in meta

    def test_empty_data_returns_empty(self):
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data([])
        assert len(result.signals_found) == 0

    def test_invalid_timestamp_skipped(self):
        data = [
            {
                "name": "X",
                "company": "Y",
                "activity_type": "posted",
                "topic": "reinforcement learning",
                "timestamp": "not-a-date",
            }
        ]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert len(result.signals_found) == 0

    def test_posted_wins_over_liked_in_same_company(self):
        """If one person posted and another liked, company gets STRONG."""
        data = [
            _make_activity(name="A", company="Co", activity_type="liked", topic="machine learning"),
            _make_activity(
                name="B", company="Co", activity_type="posted", topic="reinforcement learning"
            ),
        ]
        scanner = LinkedInActivityScanner()
        result = scanner.scan_from_data(data)
        assert result.signals_found[0].signal_strength == SignalStrength.STRONG
