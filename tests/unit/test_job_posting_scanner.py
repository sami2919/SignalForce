"""Unit tests for JobPostingScanner — written FIRST (TDD RED phase).

All HTTP calls are mocked at the JobPostingClient method level.
No real API calls are made.
"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch


from scripts.models import SignalType, SignalStrength, ScanResult, Signal

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "job_posting_responses.json"


def load_fixture() -> dict:
    with open(FIXTURES_PATH) as f:
        return json.load(f)


def make_search_result(
    title: str,
    url: str,
    snippet: str = "",
    company: str | None = None,
) -> dict:
    """Build a minimal search result dict."""
    return {"title": title, "url": url, "snippet": snippet, "company": company}


_LEVER_COUNTER: dict[str, int] = {}
_GREENHOUSE_COUNTER: dict[str, int] = {}
_ASHBY_COUNTER: dict[str, int] = {}


def make_lever_result(company_slug: str, role: str) -> dict:
    _LEVER_COUNTER[company_slug] = _LEVER_COUNTER.get(company_slug, 0) + 1
    uid = _LEVER_COUNTER[company_slug]
    return make_search_result(
        title=f"{role} at {company_slug}",
        url=f"https://jobs.lever.co/{company_slug}/abc{uid:03d}",
        snippet=f"{company_slug} is hiring a {role}. Experience with pytorch required.",
        company=None,  # company must be extracted from URL
    )


def make_greenhouse_result(company_slug: str, role: str) -> dict:
    _GREENHOUSE_COUNTER[company_slug] = _GREENHOUSE_COUNTER.get(company_slug, 0) + 1
    uid = _GREENHOUSE_COUNTER[company_slug]
    return make_search_result(
        title=f"{role} at {company_slug}",
        url=f"https://boards.greenhouse.io/{company_slug}/jobs/def{uid:03d}",
        snippet=f"{company_slug} is hiring. gymnasium and reward design experience needed.",
        company=None,
    )


def make_ashby_result(company_slug: str, role: str) -> dict:
    _ASHBY_COUNTER[company_slug] = _ASHBY_COUNTER.get(company_slug, 0) + 1
    uid = _ASHBY_COUNTER[company_slug]
    return make_search_result(
        title=f"{role} at {company_slug}",
        url=f"https://app.ashbyhq.com/jobs/{company_slug}/abc{uid:03d}",
        snippet="Join our RL team. Experience with simulation and pytorch preferred.",
        company=None,
    )


# ---------------------------------------------------------------------------
# JobPostingClient tests
# ---------------------------------------------------------------------------


class TestJobPostingClient:
    def test_client_initializes_with_base_url(self):
        from scripts.job_posting_scanner import JobPostingClient

        client = JobPostingClient(base_url="https://serpapi.com")
        assert client.base_url == "https://serpapi.com"

    def test_search_jobs_returns_list(self):
        from scripts.job_posting_scanner import JobPostingClient

        client = JobPostingClient(base_url="https://serpapi.com")
        with patch.object(
            client,
            "get",
            return_value={
                "organic_results": [{"title": "RL Engineer", "link": "https://lever.co/x"}]
            },
        ):
            results = client.search_jobs("reinforcement learning engineer")
        assert isinstance(results, list)

    def test_search_jobs_empty_response(self):
        from scripts.job_posting_scanner import JobPostingClient

        client = JobPostingClient(base_url="https://serpapi.com")
        with patch.object(client, "get", return_value={}):
            results = client.search_jobs("reinforcement learning engineer")
        assert results == []


# ---------------------------------------------------------------------------
# test_scan_returns_scan_result
# ---------------------------------------------------------------------------


class TestScanReturnsScanResult:
    def test_scan_returns_scan_result_type(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        scanner._client = MagicMock()
        scanner._client.search_jobs.return_value = []

        result = scanner.scan(lookback_days=7)

        assert isinstance(result, ScanResult)
        assert result.scan_type == SignalType.JOB_POSTING

    def test_scan_has_started_and_completed_at(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        scanner._client = MagicMock()
        scanner._client.search_jobs.return_value = []

        result = scanner.scan(lookback_days=7)

        assert isinstance(result.started_at, datetime)
        assert isinstance(result.completed_at, datetime)
        assert result.completed_at >= result.started_at


# ---------------------------------------------------------------------------
# test_extracts_company_from_lever_url
# ---------------------------------------------------------------------------


class TestExtractsCompanyFromLeverUrl:
    def test_extracts_company_from_lever_url(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        result = make_lever_result("acme-ai", "RL Engineer")
        company = scanner._extract_company_from_result(result)
        assert company == "acme-ai"

    def test_extracts_company_from_lever_url_with_different_slug(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        result = make_lever_result("deepmind", "Senior RL Researcher")
        company = scanner._extract_company_from_result(result)
        assert company == "deepmind"

    def test_lever_url_with_trailing_path(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        result = make_search_result(
            title="RL Engineer",
            url="https://jobs.lever.co/openai/abc-def-ghi/apply",
            snippet="",
        )
        company = scanner._extract_company_from_result(result)
        assert company == "openai"


# ---------------------------------------------------------------------------
# test_extracts_company_from_greenhouse_url
# ---------------------------------------------------------------------------


class TestExtractsCompanyFromGreenhouseUrl:
    def test_extracts_company_from_greenhouse_url(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        result = make_greenhouse_result("anthropic", "RL Engineer")
        company = scanner._extract_company_from_result(result)
        assert company == "anthropic"

    def test_extracts_company_from_greenhouse_boards_url(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        result = make_search_result(
            title="Policy Optimization Engineer at google-deepmind",
            url="https://boards.greenhouse.io/google-deepmind/jobs/12345",
            snippet="",
        )
        company = scanner._extract_company_from_result(result)
        assert company == "google-deepmind"


# ---------------------------------------------------------------------------
# test_extracts_company_from_title_pattern
# ---------------------------------------------------------------------------


class TestExtractsCompanyFromTitlePattern:
    def test_extracts_company_from_title_at_pattern(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        result = make_search_result(
            title="Reinforcement Learning Engineer at AcmeCorp",
            url="https://www.acmecorp.com/careers/rl-engineer",
            snippet="",
        )
        company = scanner._extract_company_from_result(result)
        assert company == "AcmeCorp"

    def test_extracts_company_field_if_present(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        result = make_search_result(
            title="RL Engineer at SomeCompany",
            url="https://example.com/jobs/123",
            snippet="",
            company="ExplicitCompany",
        )
        company = scanner._extract_company_from_result(result)
        assert company == "ExplicitCompany"

    def test_returns_none_for_personal_blog(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        result = make_search_result(
            title="How I became an RLHF engineer - Personal Blog",
            url="https://medium.com/@user/how-i-became-rlhf-engineer",
            snippet="Personal blog post.",
            company=None,
        )
        company = scanner._extract_company_from_result(result)
        assert company is None

    def test_returns_none_when_no_company_extractable(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        result = make_search_result(
            title="Jobs in ML",
            url="https://randomsite.com/jobs-list",
            snippet="",
        )
        company = scanner._extract_company_from_result(result)
        assert company is None


# ---------------------------------------------------------------------------
# test_extracts_company_from_ashby_url
# ---------------------------------------------------------------------------


class TestExtractsCompanyFromAshbyUrl:
    def test_extracts_company_from_ashbyhq_url(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        result = make_ashby_result("cohere", "RLHF Engineer")
        company = scanner._extract_company_from_result(result)
        assert company == "cohere"


# ---------------------------------------------------------------------------
# test_scoring_by_posting_count
# ---------------------------------------------------------------------------


class TestScoringByPostingCount:
    def test_score_one_posting_is_weak(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        score = scanner._score_company(posting_count=1)
        assert score == SignalStrength.WEAK

    def test_score_two_postings_is_moderate(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        score = scanner._score_company(posting_count=2)
        assert score == SignalStrength.MODERATE

    def test_score_three_postings_is_moderate(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        score = scanner._score_company(posting_count=3)
        assert score == SignalStrength.MODERATE

    def test_score_four_postings_is_strong(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        score = scanner._score_company(posting_count=4)
        assert score == SignalStrength.STRONG

    def test_score_ten_postings_is_strong(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        score = scanner._score_company(posting_count=10)
        assert score == SignalStrength.STRONG


# ---------------------------------------------------------------------------
# test_deduplicates_same_company_different_titles
# ---------------------------------------------------------------------------


class TestDeduplicatesSameCompanyDifferentTitles:
    def test_deduplicates_same_company_from_multiple_job_title_searches(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        scanner._client = MagicMock()

        # Two different title searches both return DeepMind
        scanner._client.search_jobs.side_effect = [
            [make_lever_result("deepmind", "RL Engineer")],
            [make_greenhouse_result("deepmind", "RL Researcher")],
        ]

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=["reinforcement learning engineer", "RL researcher"],
        ):
            result = scanner.scan(lookback_days=7)

        # Should deduplicate to a single signal for deepmind
        company_names = [s.company_name for s in result.signals_found]
        assert company_names.count("deepmind") == 1

    def test_dedup_accumulates_posting_count(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        scanner._client = MagicMock()

        # 3 searches for deepmind across different titles → STRONG (combined = 4)
        scanner._client.search_jobs.side_effect = [
            [make_lever_result("deepmind", "RL Engineer")],
            [make_lever_result("deepmind", "RL Researcher")],
            [make_greenhouse_result("deepmind", "Simulation Engineer")],
            [make_greenhouse_result("deepmind", "RLHF Engineer")],
        ]

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=[
                "reinforcement learning engineer",
                "RL researcher",
                "simulation engineer",
                "RLHF engineer",
            ],
        ):
            result = scanner.scan(lookback_days=7)

        deepmind_signals = [s for s in result.signals_found if s.company_name == "deepmind"]
        assert len(deepmind_signals) == 1
        assert deepmind_signals[0].signal_strength == SignalStrength.STRONG


# ---------------------------------------------------------------------------
# test_handles_empty_results
# ---------------------------------------------------------------------------


class TestHandlesEmptyResults:
    def test_handles_empty_results(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        scanner._client = MagicMock()
        scanner._client.search_jobs.return_value = []

        result = scanner.scan(lookback_days=7)

        assert result.total_after_dedup == 0
        assert result.signals_found == []

    def test_handles_results_with_no_extractable_company(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        scanner._client = MagicMock()

        # Personal blog result — no company extractable
        scanner._client.search_jobs.return_value = [
            make_search_result(
                title="My journey into RL engineering",
                url="https://medium.com/@user/rl-journey",
                snippet="Personal blog",
                company=None,
            )
        ]

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=["reinforcement learning engineer"],
        ):
            result = scanner.scan(lookback_days=7)

        assert result.total_after_dedup == 0
        assert result.signals_found == []

    def test_handles_client_exception_gracefully(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        scanner._client = MagicMock()
        scanner._client.search_jobs.side_effect = Exception("Network error")

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=["reinforcement learning engineer"],
        ):
            result = scanner.scan(lookback_days=7)

        # Should not raise; errors are captured
        assert isinstance(result, ScanResult)
        assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# test_metadata_includes_job_titles
# ---------------------------------------------------------------------------


class TestMetadataIncludesJobTitles:
    def test_metadata_includes_job_titles(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        scanner._client = MagicMock()

        scanner._client.search_jobs.side_effect = [
            [make_lever_result("acme-ai", "Reinforcement Learning Engineer")],
            [make_greenhouse_result("acme-ai", "RL Researcher")],
        ]

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=["reinforcement learning engineer", "RL researcher"],
        ):
            result = scanner.scan(lookback_days=7)

        assert len(result.signals_found) == 1
        signal = result.signals_found[0]
        assert "job_titles" in signal.metadata
        assert isinstance(signal.metadata["job_titles"], list)
        assert len(signal.metadata["job_titles"]) > 0

    def test_metadata_includes_posting_urls(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        scanner._client = MagicMock()

        scanner._client.search_jobs.return_value = [make_lever_result("acme-ai", "RL Engineer")]

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=["reinforcement learning engineer"],
        ):
            result = scanner.scan(lookback_days=7)

        signal = result.signals_found[0]
        assert "posting_urls" in signal.metadata
        assert isinstance(signal.metadata["posting_urls"], list)
        assert len(signal.metadata["posting_urls"]) > 0

    def test_metadata_includes_posting_count(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        scanner._client = MagicMock()

        scanner._client.search_jobs.return_value = [make_lever_result("acme-ai", "RL Engineer")]

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=["reinforcement learning engineer"],
        ):
            result = scanner.scan(lookback_days=7)

        signal = result.signals_found[0]
        assert "posting_count" in signal.metadata
        assert signal.metadata["posting_count"] == 1

    def test_metadata_includes_skills_mentioned(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        scanner._client = MagicMock()

        scanner._client.search_jobs.return_value = [make_lever_result("acme-ai", "RL Engineer")]

        with patch.object(
            scanner,
            "_build_search_queries",
            return_value=["reinforcement learning engineer"],
        ):
            result = scanner.scan(lookback_days=7)

        signal = result.signals_found[0]
        assert "skills_mentioned" in signal.metadata
        assert isinstance(signal.metadata["skills_mentioned"], list)


# ---------------------------------------------------------------------------
# test_extracts_rl_skills
# ---------------------------------------------------------------------------


class TestExtractsRLSkills:
    def test_extracts_pytorch_from_description(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        skills = scanner._extract_skills("Experience with pytorch and gymnasium required.")
        assert "pytorch" in skills

    def test_extracts_gymnasium_from_description(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        skills = scanner._extract_skills(
            "Build environments using gymnasium and simulation frameworks."
        )
        assert "gymnasium" in skills

    def test_extracts_tensorflow_from_description(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        skills = scanner._extract_skills("We use tensorflow for our training pipelines.")
        assert "tensorflow" in skills

    def test_extracts_reward_design_from_description(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        skills = scanner._extract_skills("Experience with reward design and reward shaping.")
        assert "reward design" in skills

    def test_extracts_simulation_from_description(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        skills = scanner._extract_skills("Build physics simulation environments for RL training.")
        assert "simulation" in skills

    def test_extracts_multiple_skills(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        description = "Experience with pytorch, gymnasium, and reward design. Knowledge of simulation helpful."
        skills = scanner._extract_skills(description)
        assert "pytorch" in skills
        assert "gymnasium" in skills
        assert "reward design" in skills
        assert "simulation" in skills

    def test_returns_empty_list_for_no_skills(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        skills = scanner._extract_skills("Looking for a software engineer.")
        assert skills == []

    def test_case_insensitive_extraction(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        skills = scanner._extract_skills("Experience with PyTorch and Gymnasium.")
        assert "pytorch" in skills
        assert "gymnasium" in skills


# ---------------------------------------------------------------------------
# test_create_signal
# ---------------------------------------------------------------------------


class TestCreateSignal:
    def test_create_signal_has_correct_type(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        postings = [make_lever_result("acme-ai", "RL Engineer")]
        signal = scanner._create_signal("acme-ai", postings, SignalStrength.WEAK)
        assert signal.signal_type == SignalType.JOB_POSTING

    def test_create_signal_has_correct_company(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        postings = [make_lever_result("acme-ai", "RL Engineer")]
        signal = scanner._create_signal("acme-ai", postings, SignalStrength.WEAK)
        assert signal.company_name == "acme-ai"

    def test_create_signal_has_correct_strength(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        postings = [
            make_lever_result("acme-ai", "RL Engineer"),
            make_greenhouse_result("acme-ai", "RL Researcher"),
            make_ashby_result("acme-ai", "Simulation Engineer"),
            make_lever_result("acme-ai", "RLHF Engineer"),
        ]
        signal = scanner._create_signal("acme-ai", postings, SignalStrength.STRONG)
        assert signal.signal_strength == SignalStrength.STRONG

    def test_create_signal_source_url_is_first_posting_url(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        postings = [make_lever_result("acme-ai", "RL Engineer")]
        signal = scanner._create_signal("acme-ai", postings, SignalStrength.WEAK)
        assert signal.source_url == postings[0]["url"]

    def test_create_signal_metadata_has_required_keys(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        postings = [make_lever_result("acme-ai", "RL Engineer")]
        signal = scanner._create_signal("acme-ai", postings, SignalStrength.WEAK)
        assert "job_titles" in signal.metadata
        assert "posting_urls" in signal.metadata
        assert "posting_count" in signal.metadata
        assert "skills_mentioned" in signal.metadata


# ---------------------------------------------------------------------------
# test_build_search_queries
# ---------------------------------------------------------------------------


class TestBuildSearchQueries:
    def test_build_search_queries_returns_list(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        queries = scanner._build_search_queries(lookback_days=7)
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_queries_include_rl_job_titles(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        queries = scanner._build_search_queries(lookback_days=7)
        all_queries = " ".join(queries).lower()
        assert any(
            term in all_queries
            for term in ["reinforcement learning", "rlhf", "simulation engineer", "reward modeling"]
        )

    def test_queries_include_job_board_domains(self):
        from scripts.job_posting_scanner import JobPostingScanner

        scanner = JobPostingScanner.__new__(JobPostingScanner)
        queries = scanner._build_search_queries(lookback_days=7)
        all_queries = " ".join(queries)
        assert any(
            domain in all_queries
            for domain in ["linkedin.com", "lever.co", "greenhouse.io", "ashbyhq.com"]
        )


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    def test_cli_prints_summary(self, capsys):
        from scripts.job_posting_scanner import main
        from scripts.models import ScanResult, SignalType

        mock_result = ScanResult(
            scan_type=SignalType.JOB_POSTING,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
        )

        with patch("scripts.job_posting_scanner.JobPostingScanner") as MockScanner:
            mock_instance = MockScanner.return_value
            mock_instance.scan.return_value = mock_result
            main(["--lookback-days", "7"])

        captured = capsys.readouterr()
        assert "0" in captured.out

    def test_cli_with_min_strength_filters(self, capsys):
        from scripts.job_posting_scanner import main

        weak_signal = Signal(
            signal_type=SignalType.JOB_POSTING,
            company_name="weak-corp",
            signal_strength=SignalStrength.WEAK,
            source_url="https://jobs.lever.co/weak-corp/abc",
            raw_data={"postings": []},
            metadata={
                "job_titles": ["RL Engineer"],
                "posting_urls": ["https://jobs.lever.co/weak-corp/abc"],
                "posting_count": 1,
                "skills_mentioned": [],
            },
        )

        mock_result = ScanResult(
            scan_type=SignalType.JOB_POSTING,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[weak_signal],
            total_raw_results=1,
            total_after_dedup=1,
        )

        with patch("scripts.job_posting_scanner.JobPostingScanner") as MockScanner:
            mock_instance = MockScanner.return_value
            mock_instance.scan.return_value = mock_result
            main(["--lookback-days", "7", "--min-strength", "2"])

        captured = capsys.readouterr()
        # WEAK signals filtered out → 0 after filter
        assert "0" in captured.out

    def test_cli_writes_output_file(self, tmp_path):
        from scripts.job_posting_scanner import main

        mock_result = ScanResult(
            scan_type=SignalType.JOB_POSTING,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            signals_found=[],
            total_raw_results=0,
            total_after_dedup=0,
        )

        output_file = tmp_path / "output.json"

        with patch("scripts.job_posting_scanner.JobPostingScanner") as MockScanner:
            mock_instance = MockScanner.return_value
            mock_instance.scan.return_value = mock_result
            main(["--lookback-days", "7", "--output", str(output_file)])

        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert "scan_id" in data
        assert "signals" in data


# ---------------------------------------------------------------------------
# Fixture data tests
# ---------------------------------------------------------------------------


class TestFixtureData:
    def test_fixture_file_is_valid_json(self):
        fixture = load_fixture()
        assert isinstance(fixture, dict)

    def test_fixture_has_expected_keys(self):
        fixture = load_fixture()
        assert "search_rl_engineer" in fixture
        assert "search_simulation_engineer" in fixture
        assert "search_personal_blog" in fixture

    def test_fixture_deepmind_has_three_results(self):
        fixture = load_fixture()
        results = fixture["search_rl_engineer"]["results"]
        deepmind_results = [r for r in results if r.get("company") == "DeepMind"]
        assert len(deepmind_results) == 3

    def test_fixture_personal_blog_has_no_company(self):
        fixture = load_fixture()
        results = fixture["search_personal_blog"]["results"]
        assert len(results) == 1
        assert results[0]["company"] is None
