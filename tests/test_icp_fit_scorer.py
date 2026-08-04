"""Tests for the ICP fit scorer.

TDD: These tests are written FIRST. They define the expected behavior
before any implementation exists.
"""

from __future__ import annotations


from scripts.models import Signal, SignalStrength
from scripts.icp_fit_scorer import compute_icp_fit


def _make_signal(
    signal_type: str,
    raw_data: dict,
    metadata: dict | None = None,
) -> Signal:
    """Helper to create a Signal for testing."""
    return Signal(
        signal_type=signal_type,
        company_name="Acme Corp",
        signal_strength=SignalStrength.MODERATE,
        source_url="https://example.com",
        raw_data=raw_data,
        metadata=metadata or {},
    )


class TestComputeIcpFit:
    """compute_icp_fit scores 0–10 based on Conversion's Marketo-migration ICP."""

    def test_marketo_signal_scores_high(self):
        """Marketo in job skills = strong MAP pain signal → high ICP fit."""
        sig = _make_signal(
            "job_posting",
            raw_data={"postings": [{"snippet": "Experience with Marketo required"}]},
            metadata={"skills_mentioned": ["Marketo", "Salesforce"]},
        )
        score = compute_icp_fit([sig])
        assert score >= 7.0, f"Expected ≥7.0 for Marketo+Salesforce, got {score}"

    def test_hubspot_salesforce_scores_medium(self):
        """HubSpot + Salesforce = solid B-tier ICP fit."""
        sig = _make_signal(
            "job_posting",
            raw_data={"postings": [{"snippet": "HubSpot admin, Salesforce sync"}]},
            metadata={"skills_mentioned": ["HubSpot", "Salesforce"]},
        )
        score = compute_icp_fit([sig])
        assert 4.0 <= score < 8.0, f"Expected 4–8 for HubSpot+Salesforce, got {score}"

    def test_no_relevant_signals_scores_low(self):
        """No MAP or warehouse signals → low ICP fit."""
        sig = _make_signal(
            "job_posting",
            raw_data={"postings": [{"snippet": "React Native developer"}]},
            metadata={"skills_mentioned": []},
        )
        score = compute_icp_fit([sig])
        assert score <= 2.0, f"Expected ≤2.0 for irrelevant signal, got {score}"

    def test_reverse_etl_adds_points(self):
        """Hightouch/Census in skills = reverse ETL pain = extra ICP points."""
        sig = _make_signal(
            "job_posting",
            raw_data={"postings": [{"snippet": "Hightouch or Census experience helpful"}]},
            metadata={"skills_mentioned": ["Hightouch", "Marketo", "Salesforce"]},
        )
        score = compute_icp_fit([sig])
        assert score >= 8.5, f"Expected ≥8.5 for Hightouch+Marketo+Salesforce, got {score}"

    def test_score_capped_at_10(self):
        """ICP fit score must never exceed 10.0."""
        sig = _make_signal(
            "job_posting",
            raw_data={
                "postings": [{"snippet": ("Marketo Salesforce Hightouch Snowflake BigQuery dbt")}]
            },
            metadata={
                "skills_mentioned": [
                    "Marketo",
                    "Salesforce",
                    "Hightouch",
                    "Snowflake",
                    "dbt",
                ]
            },
        )
        score = compute_icp_fit([sig])
        assert score <= 10.0

    def test_empty_signals_returns_zero(self):
        """Empty signal list → 0.0 ICP fit."""
        assert compute_icp_fit([]) == 0.0

    def test_multiple_signals_combine(self):
        """Signals from multiple sources should be combined for scoring."""
        sig1 = _make_signal(
            "job_posting",
            raw_data={"postings": [{"snippet": "Marketo"}]},
            metadata={"skills_mentioned": ["Marketo"]},
        )
        sig2 = _make_signal(
            "github_repo",
            raw_data={},
            metadata={"topics": ["Salesforce"]},
        )
        score = compute_icp_fit([sig1, sig2])
        assert score > compute_icp_fit([sig1])  # Two sources should score higher than one
