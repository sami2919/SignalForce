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
        scan(cfg)
    mock_scan.assert_called_once_with(7)
