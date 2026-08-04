from unittest.mock import patch
from scripts.models import Signal, SignalStrength, ICPScore
from scripts.demo_scan import run_demo_scan, format_grade_table
from scripts.signal_aggregator import ScoredCompany
from scripts.intent_scorer import ScoringResult


def _make_signal(
    company: str, skills: list[str], strength: SignalStrength = SignalStrength.STRONG
) -> Signal:
    return Signal(
        signal_type="job_posting",
        company_name=company,
        signal_strength=strength,
        source_url="https://example.com",
        raw_data={"postings": [{"snippet": " ".join(skills)}]},
        metadata={"skills_mentioned": skills},
    )


def test_run_demo_scan_returns_scored_companies():
    """run_demo_scan should return a non-empty sorted list of ScoredCompany."""
    fake_signals = [
        _make_signal("Acme Corp", ["Marketo", "Salesforce", "Hightouch"]),
        _make_signal("Beta Inc", ["HubSpot", "Salesforce"]),
    ]
    with patch("scripts.demo_scan.run_all_scanners", return_value=fake_signals):
        results = run_demo_scan()
    assert len(results) == 2
    scores = [r.scoring_result.combined_score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_run_demo_scan_empty_signals_returns_empty():
    """run_demo_scan with no scanner output should return empty list."""
    with patch("scripts.demo_scan.run_all_scanners", return_value=[]):
        results = run_demo_scan()
    assert results == []


def test_format_grade_table_contains_company_name():
    """format_grade_table should include company names in output."""
    fake_signals = [_make_signal("Acme Corp", ["Marketo", "Salesforce"])]
    with patch("scripts.demo_scan.run_all_scanners", return_value=fake_signals):
        results = run_demo_scan()
    table = format_grade_table(results)
    assert "Acme Corp" in table


def test_format_grade_table_contains_grade_letter():
    """format_grade_table should show A, B, C, or D grade."""
    fake_signals = [_make_signal("Acme Corp", ["Marketo", "Salesforce", "Hightouch"])]
    with patch("scripts.demo_scan.run_all_scanners", return_value=fake_signals):
        results = run_demo_scan()
    table = format_grade_table(results)
    assert any(f"[{g}]" in table for g in ["A", "B", "C", "D"])


def test_format_grade_table_empty_shows_no_signals_message():
    """format_grade_table with empty results should show helpful message."""
    table = format_grade_table([])
    assert "No signals" in table or "no signals" in table.lower()


def _make_scored_company(company: str, signal_types: list[str]) -> ScoredCompany:
    signals = [
        Signal(
            signal_type=st,
            company_name=company,
            signal_strength=SignalStrength.MODERATE,
            source_url="https://example.com",
            raw_data={},
        )
        for st in signal_types
    ]
    scoring_result = ScoringResult(
        intent_score=5.0,
        combined_score=5.5,
        icp_score=ICPScore.B,
        signal_count=len(signals),
        source_types=len(set(signal_types)),
    )
    return ScoredCompany(
        company_name=company,
        signals=signals,
        icp_fit=3.0,
        scoring_result=scoring_result,
    )


def test_format_grade_table_shows_signal_type_abbreviations():
    """Table must show signal type abbreviations so stacking is visible in the demo."""
    results = [_make_scored_company("Vanta", ["job_posting", "g2_review", "funding_event"])]
    table = format_grade_table(results)
    assert "job" in table
    assert "g2" in table
    assert "$" in table


def test_format_grade_table_empty_returns_no_signals_message():
    """Empty results should return a helpful message."""
    table = format_grade_table([])
    assert "No signals found" in table
