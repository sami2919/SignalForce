"""Tests for scripts/verify/extractor.py — Anthropic API mocked throughout.

ADR-0008 (verify-layer extraction) and ADR-0007 Decision 1 (declared identity keys)
are the spec. See docs/decisions/0008-verify-layer-extraction.md and
docs/decisions/0007-diff-based-signal-events.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest
from pydantic import ConfigDict

from scripts.verify.extractor import (
    _derive_identity,
    CareersFacts,
    ExtractorError,
    Fact,
    JobFact,
    _RawCareersExtraction,
    _RawJob,
    extract_careers,
)

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _fixture(name: str) -> str:
    return (_FIXTURES / name).read_text()


def _mock_usage(input_tokens=1000, output_tokens=200, cache_read=0, cache_creation=0):
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_read_input_tokens = cache_read
    usage.cache_creation_input_tokens = cache_creation
    return usage


def _mock_parsed_response(raw: _RawCareersExtraction, **usage_kwargs) -> MagicMock:
    response = MagicMock()
    response.parsed_output = raw
    response.usage = _mock_usage(**usage_kwargs)
    return response


def _mock_client(raw: _RawCareersExtraction, **usage_kwargs) -> MagicMock:
    client = MagicMock()
    client.messages.parse.return_value = _mock_parsed_response(raw, **usage_kwargs)
    return client


# ---------------------------------------------------------------------------
# Schema shape
# ---------------------------------------------------------------------------


def test_extract_careers_returns_declared_schema_shape():
    raw = _RawCareersExtraction(
        jobs=[
            _RawJob(
                title="Senior Backend Engineer",
                location="Remote - US",
                url="https://job-boards.greenhouse.io/acme/jobs/5023394008",
            ),
            _RawJob(
                title="Staff Product Designer",
                location="San Francisco, CA",
                url="https://job-boards.greenhouse.io/acme/jobs/5023394115",
            ),
        ]
    )
    client = _mock_client(raw)

    facts = extract_careers(_fixture("careers_page.html"), client=client)

    assert isinstance(facts, CareersFacts)
    assert len(facts.jobs) == 2
    for job in facts.jobs:
        assert isinstance(job, JobFact)
    assert facts.jobs[0].title == "Senior Backend Engineer"
    assert facts.jobs[0].location == "Remote - US"


# ---------------------------------------------------------------------------
# Identity key from href, not title
# ---------------------------------------------------------------------------


def test_identity_key_is_populated_from_url_id_not_title():
    raw = _RawCareersExtraction(
        jobs=[
            _RawJob(
                title="Senior Backend Engineer",
                location="Remote - US",
                url="https://job-boards.greenhouse.io/acme/jobs/5023394008",
            )
        ]
    )
    client = _mock_client(raw)

    facts = extract_careers(_fixture("careers_page.html"), client=client)

    job = facts.jobs[0]
    assert job.identity_key == "5023394008"
    assert job.identity_key != job.title
    assert job.identity_degraded is False


def test_identity_key_is_populated_from_uuid_path_segment_ashby_style():
    raw = _RawCareersExtraction(
        jobs=[
            _RawJob(
                title="Infra Engineer",
                location="San Francisco, CA",
                url="https://jobs.ashbyhq.com/modal/0d4c15af-afa7-4430-b3db-dd8258950aec",
            )
        ]
    )
    client = _mock_client(raw)

    facts = extract_careers(_fixture("careers_page.html"), client=client)

    job = facts.jobs[0]
    assert job.identity_key == "0d4c15af-afa7-4430-b3db-dd8258950aec"
    assert job.identity_degraded is False


def test_identity_key_degrades_visibly_when_no_stable_id_present():
    raw = _RawCareersExtraction(
        jobs=[
            _RawJob(
                title="Support Engineer",
                location="New York, NY",
                url="/careers/apply?role=support-engineer",
            )
        ]
    )
    client = _mock_client(raw)

    facts = extract_careers(_fixture("careers_page.html"), client=client)

    job = facts.jobs[0]
    # Explicit, visible degraded mode: identity_degraded=True, and the fallback
    # key is a declared tuple (title + location), never the title alone.
    assert job.identity_degraded is True
    assert "Support Engineer" in job.identity_key
    assert "New York, NY" in job.identity_key


# ---------------------------------------------------------------------------
# Zero jobs is a legitimate state, not an error
# ---------------------------------------------------------------------------


def test_zero_jobs_yields_empty_fact_list_not_error():
    raw = _RawCareersExtraction(jobs=[])
    client = _mock_client(raw)

    facts = extract_careers(_fixture("careers_page_empty.html"), client=client)

    assert isinstance(facts, CareersFacts)
    assert facts.jobs == ()


# ---------------------------------------------------------------------------
# A fact type without a declared identity key fails loudly at definition time
# ---------------------------------------------------------------------------


def test_fact_type_without_identity_fields_fails_at_definition():
    with pytest.raises(TypeError, match="identity_fields"):

        class _BadFact(Fact):
            model_config = ConfigDict(frozen=True)
            identity_fields: ClassVar[tuple[str, ...]] = ()
            some_field: str


def test_fact_type_with_identity_fields_defines_cleanly():
    class _GoodFact(Fact):
        model_config = ConfigDict(frozen=True)
        identity_fields: ClassVar[tuple[str, ...]] = ("some_field",)
        some_field: str

    instance = _GoodFact(some_field="x")
    assert instance.some_field == "x"


# ---------------------------------------------------------------------------
# API errors propagate as a typed extractor error, never as empty facts
# ---------------------------------------------------------------------------


def test_api_status_error_propagates_as_extractor_error_not_empty_facts():
    client = MagicMock()
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(500, request=request)
    client.messages.parse.side_effect = anthropic.APIStatusError(
        "server error", response=response, body=None
    )

    with pytest.raises(ExtractorError):
        extract_careers(_fixture("careers_page.html"), client=client)


def test_api_connection_error_propagates_as_extractor_error_not_empty_facts():
    client = MagicMock()
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    client.messages.parse.side_effect = anthropic.APIConnectionError(request=request)

    with pytest.raises(ExtractorError):
        extract_careers(_fixture("careers_page.html"), client=client)


# ---------------------------------------------------------------------------
# Prompt caching: cache_control on the system block, page content in user turn
# ---------------------------------------------------------------------------


def test_request_sets_cache_control_on_system_block_and_page_content_in_user_turn():
    raw = _RawCareersExtraction(jobs=[])
    client = _mock_client(raw)

    html = _fixture("careers_page_empty.html")
    extract_careers(html, client=client)

    _, kwargs = client.messages.parse.call_args
    system = kwargs["system"]
    assert isinstance(system, list)
    assert any(block.get("cache_control") == {"type": "ephemeral"} for block in system)

    messages = kwargs["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    # The user turn carries the STRIPPED representation (Task 2.1c), not the raw
    # HTML — but the page's actual content must survive the reduction.
    assert "Check back soon" in messages[0]["content"]
    assert "<html" not in messages[0]["content"]
    # Page content must not leak into the cached system block.
    assert all("Check back soon" not in block.get("text", "") for block in system)


def test_default_client_used_when_none_provided(monkeypatch):
    raw = _RawCareersExtraction(jobs=[])
    fake_client = _mock_client(raw)
    monkeypatch.setattr("scripts.verify.extractor._default_client", lambda: fake_client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    facts = extract_careers(_fixture("careers_page_empty.html"))

    assert facts.jobs == ()
    fake_client.messages.parse.assert_called_once()


# ---------------------------------------------------------------------------
# _strip_for_extraction (Task 2.1c, ADR-0008 Decision 1 amendment)
# ---------------------------------------------------------------------------


class TestStripForExtraction:
    """Href-preserving reduction. Gated on reproducing the raw-HTML baseline
    (Task 2.1a Step 5), not on being cheaper — see the acceptance criterion in
    ADR-0008's Decision 1 amendment."""

    def test_drops_non_content_tags(self):
        from scripts.verify.extractor import _strip_for_extraction

        html = (
            "<html><head><title>x</title></head><body>"
            "<script>evil()</script><style>.x{}</style>"
            "<p>Real content</p>"
            "</body></html>"
        )
        out = _strip_for_extraction(html)
        assert "evil()" not in out
        assert ".x{}" not in out
        assert "Real content" in out

    def test_preserves_every_href_paired_with_its_link_text(self):
        from scripts.verify.extractor import _strip_for_extraction

        out = _strip_for_extraction(_fixture("careers_page.html"))
        assert (
            "Senior Backend Engineer <https://job-boards.greenhouse.io/acme/jobs/5023394008>" in out
        )
        assert (
            "Staff Product Designer <https://job-boards.greenhouse.io/acme/jobs/5023394115>" in out
        )
        assert "Support Engineer </careers/apply?role=support-engineer>" in out

    def test_output_is_much_smaller_than_input_for_a_realistic_page(self):
        from scripts.verify.extractor import _strip_for_extraction

        # A page with a lot of markup weight around a small number of real links —
        # the shape that made railway.app measure a 99% reduction in Step 5.
        html = (
            "<html><body>"
            + ("<div class='chrome'>filler</div>" * 500)
            + ('<a href="/jobs/1">Engineer</a>')
            + "</body></html>"
        )
        out = _strip_for_extraction(html)
        assert len(out) < len(html) / 2
        assert "/jobs/1" in out

    def test_body_text_is_capped_so_a_pathological_page_cannot_balloon_the_request(self):
        from scripts.verify.extractor import _MAX_BODY_CHARS, _strip_for_extraction

        # No links at all — an uncapped body-text run of prose, larger than the cap,
        # with a link at the very end to prove truncation, not just brevity.
        html = "<html><body>" + ("word " * 50_000) + '<a href="/jobs/1">Engineer</a></body></html>'
        out = _strip_for_extraction(html)
        body_part = out.split("\n\nLINKS:\n")[0]
        assert len(body_part) < 25_000  # absolute, independent of the constant
        assert len(body_part) <= _MAX_BODY_CHARS
        assert len(out) < len(html) / 2

    def test_empty_input_returns_empty_string(self):
        from scripts.verify.extractor import _strip_for_extraction

        assert _strip_for_extraction("") == ""

    def test_malformed_html_degrades_to_raw_bytes_rather_than_raising(self):
        from scripts.verify.extractor import _strip_for_extraction

        # Not actually malformed enough to break selectolax, but confirms the
        # function never raises on a real page — matches normalize_html's posture.
        weird = "<div><a href='/x'>unterminated"
        out = _strip_for_extraction(weird)
        assert "/x" in out or "unterminated" in out  # degrades, does not crash

    def test_extract_careers_sends_stripped_form_not_raw_html(self):
        raw = _RawCareersExtraction(jobs=[])
        client = _mock_client(raw)

        html = _fixture("careers_page.html")
        extract_careers(html, client=client)

        _, kwargs = client.messages.parse.call_args
        sent = kwargs["messages"][0]["content"]
        assert "<div" not in sent  # markup gone
        assert "5023394008" in sent  # the job id survives


# ---------------------------------------------------------------------------
# Identity regex scoping (review C1): the stable-id search must run on the URL
# PATH only, must match a WHOLE path segment, must have a floor that actually
# excludes a bare year, and must degrade rather than guess when ambiguous.
# ---------------------------------------------------------------------------


class TestNumericIdScoping:
    def test_bare_year_in_path_is_not_a_confident_identity_key(self):
        # A year is exactly 4 digits. The original `\d{4,}` matched it and
        # returned ('2026', degraded=False) — two different jobs posted under
        # the same year collapsed onto one non-degraded key.
        raw = _RawJob(title="Backend Engineer", location="Remote", url="/careers/2026/backend-eng")
        key, degraded = _derive_identity(raw)
        assert degraded is True
        assert key != "2026"
        assert "Backend Engineer" in key

    def test_two_jobs_sharing_only_a_year_do_not_share_an_identity_key(self):
        a = _derive_identity(_RawJob(title="Backend Eng", url="/careers/2026/backend-eng"))
        b = _derive_identity(_RawJob(title="Frontend Eng", url="/careers/2026/frontend-eng"))
        assert a[0] != b[0]

    def test_query_string_digits_never_become_the_identity_key(self):
        raw = _RawJob(title="Engineer", location="Remote", url="/careers/list?limit=1000&page=3")
        key, degraded = _derive_identity(raw)
        assert key != "1000"
        assert degraded is True

    def test_host_digits_never_become_the_identity_key(self):
        raw = _RawJob(title="Data Scientist", location="NYC", url="https://acme2024.com/careers/ds")
        key, degraded = _derive_identity(raw)
        assert key != "2024"
        assert degraded is True

    def test_digits_embedded_in_a_longer_path_token_are_not_a_whole_segment_id(self):
        raw = _RawJob(title="Engineer", url="/en-US/jobs/senior-engineer-2026")
        key, degraded = _derive_identity(raw)
        assert key != "2026"
        assert degraded is True

    def test_long_digit_run_embedded_in_a_slug_is_not_a_whole_segment_id(self):
        # Above the length floor, so only the WHOLE-SEGMENT anchoring rejects it.
        # Without anchoring (a bare `\d{6,}` search over the URL) this returns a
        # confident "123456" for what is really an arbitrary slug substring.
        raw = _RawJob(title="Engineer", location="Remote", url="/careers/senior-eng-123456-v2")
        key, degraded = _derive_identity(raw)
        assert key != "123456"
        assert degraded is True

    def test_long_digit_run_in_a_query_param_is_not_an_identity_key(self):
        # Also above the floor: only path-only scoping rejects it.
        raw = _RawJob(title="Engineer", location="Remote", url="/careers/engineer?utm_id=987654")
        key, degraded = _derive_identity(raw)
        assert key != "987654"
        assert degraded is True

    def test_long_digit_run_in_the_host_is_not_an_identity_key(self):
        raw = _RawJob(title="Engineer", location="Remote", url="https://acme123456.com/careers/e")
        key, degraded = _derive_identity(raw)
        assert key != "123456"
        assert degraded is True

    def test_long_digit_run_in_the_fragment_is_not_an_identity_key(self):
        raw = _RawJob(title="Engineer", location="Remote", url="/careers/engineer#job-654321")
        key, degraded = _derive_identity(raw)
        assert key != "654321"
        assert degraded is True

    def test_five_digit_segment_is_below_the_floor_and_degrades(self):
        # Load-bearing guard on _MIN_NUMERIC_ID_DIGITS: drop the floor to 5 and
        # this must fail. Five digits is a US zip code / a small ordinal, not an
        # ATS id (Greenhouse measured at 10 digits).
        raw = _RawJob(title="Engineer", location="Remote", url="/careers/12345/engineer")
        key, degraded = _derive_identity(raw)
        assert key != "12345"
        assert degraded is True

    def test_six_digit_segment_is_at_the_floor_and_is_accepted(self):
        # Raise the floor to 7 and this must fail. Together with the test above
        # this pins the floor at exactly 6 from both sides.
        raw = _RawJob(title="Engineer", url="/careers/123456")
        assert _derive_identity(raw) == ("123456", False)

    def test_ambiguous_multiple_numeric_segments_degrade_rather_than_guess(self):
        # Two whole-segment candidates: picking "first" would be a silent guess.
        raw = _RawJob(title="Engineer", location="Remote", url="/jobs/1234567/apply/7654321")
        key, degraded = _derive_identity(raw)
        assert degraded is True
        assert "Engineer" in key

    # --- regression: the existing measured baselines must still resolve ---

    def test_greenhouse_id_still_resolves_non_degraded(self):
        raw = _RawJob(title="X", url="https://job-boards.greenhouse.io/acme/jobs/5023394008")
        assert _derive_identity(raw) == ("5023394008", False)

    def test_greenhouse_id_with_tracking_query_still_resolves_non_degraded(self):
        raw = _RawJob(title="X", url="https://boards.greenhouse.io/acme/jobs/5023394008?gh_src=ab1")
        assert _derive_identity(raw) == ("5023394008", False)

    def test_ashby_uuid_still_resolves_non_degraded(self):
        raw = _RawJob(
            title="X", url="https://jobs.ashbyhq.com/modal/0d4c15af-afa7-4430-b3db-dd8258950aec"
        )
        assert _derive_identity(raw) == ("0d4c15af-afa7-4430-b3db-dd8258950aec", False)

    def test_lever_uuid_with_tracking_query_still_resolves_non_degraded(self):
        raw = _RawJob(
            title="X",
            url="https://jobs.lever.co/acme/0d4c15af-afa7-4430-b3db-dd8258950aec?lever-source=LI",
        )
        assert _derive_identity(raw) == ("0d4c15af-afa7-4430-b3db-dd8258950aec", False)

    def test_trailing_slash_does_not_hide_the_id(self):
        raw = _RawJob(title="X", url="https://job-boards.greenhouse.io/acme/jobs/5023394008/")
        assert _derive_identity(raw) == ("5023394008", False)


# ---------------------------------------------------------------------------
# Script-tag hydration payloads (review C2): __NEXT_DATA__ / ld+json carry real
# job records. Blanket-dropping <script> silently lost them.
# ---------------------------------------------------------------------------


class TestScriptDataPreservation:
    _HYDRATED = (
        '<html><body><div id="__next">'
        '<h1>Careers</h1><a href="/jobs/9001">Only Statically Rendered Job</a>'
        "</div>"
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"jobs":['
        '{"title":"Backend Engineer","location":"Remote - US","url":"/jobs/9002"},'
        '{"title":"ML Engineer","location":"San Francisco, CA","url":"/jobs/9003"}'
        "]}}}</script></body></html>"
    )

    def test_hydration_json_survives_the_strip(self):
        from scripts.verify.extractor import _strip_for_extraction

        out = _strip_for_extraction(self._HYDRATED)
        assert "9001" in out
        assert "9002" in out, "job from __NEXT_DATA__ lost by the strip"
        assert "9003" in out, "job from __NEXT_DATA__ lost by the strip"
        assert "Backend Engineer" in out
        assert "ML Engineer" in out

    def test_ld_json_in_head_survives_the_strip(self):
        # schema.org JobPosting is the standard structured form and normally
        # lives in <head>, which is itself a dropped tag.
        from scripts.verify.extractor import _strip_for_extraction

        html = (
            "<html><head><title>Careers</title>"
            '<script type="application/ld+json">'
            '{"@type":"JobPosting","title":"Staff SRE","url":"/jobs/778899"}'
            "</script></head><body><h1>Careers</h1></body></html>"
        )
        out = _strip_for_extraction(html)
        assert "JobPosting" in out
        assert "778899" in out
        assert "Staff SRE" in out

    def test_executable_script_is_still_dropped(self):
        # Control: this narrows the drop, it does not remove it.
        from scripts.verify.extractor import _strip_for_extraction

        html = (
            "<html><body><p>Real content</p>"
            "<script>alert(1)</script>"
            '<script type="text/javascript">var tracking = "beacon123456";</script>'
            '<script type="module">import x from "y";</script>'
            "</body></html>"
        )
        out = _strip_for_extraction(html)
        assert "alert(1)" not in out
        assert "beacon123456" not in out
        assert "import x" not in out
        assert "Real content" in out

    def test_script_data_section_is_capped(self):
        from scripts.verify.extractor import _strip_for_extraction

        blob = '{"pad":"' + ("x" * 500_000) + '"}'
        html = (
            '<html><body><p>Careers</p><script type="application/json">'
            f"{blob}</script></body></html>"
        )
        out = _strip_for_extraction(html)
        # Absolute ceiling, not expressed via the constant under test.
        assert len(out) < 50_000
        assert "[truncated]" in out  # the cut is announced, not silent


# ---------------------------------------------------------------------------
# LINKS section cap (review I2): body text was capped, the link list was not.
# ---------------------------------------------------------------------------


def test_links_section_is_capped_so_a_link_dense_page_cannot_balloon_the_request():
    from scripts.verify.extractor import _MAX_LINKS_CHARS, _strip_for_extraction

    html = (
        "<html><body>"
        + "".join(
            f'<a href="https://boards.example.com/acme/jobs/{5000000000 + i}">'
            f"Senior Staff Engineer, Platform Infrastructure {i}</a>"
            for i in range(3000)
        )
        + "</body></html>"
    )
    # ~305,000 chars of links alone before any cap — measured in review.
    assert len(html) > 300_000

    out = _strip_for_extraction(html)
    links_part = out.split("\n\nLINKS:\n", 1)[1]

    # ABSOLUTE ceiling, deliberately not expressed in terms of _MAX_LINKS_CHARS:
    # a test that reads the constant it is guarding moves with the mutation and
    # proves nothing. 60,000 chars is ~16k tokens, the outer bound of what
    # ADR-0008's amended cost model tolerates for one extraction.
    assert len(links_part) < 60_000
    assert len(out) < 100_000
    assert "[truncated]" in links_part  # the cut is announced, not silent
    assert "5000000000" in out  # the first links are still there
    assert len(links_part) <= _MAX_LINKS_CHARS + 200  # +truncation marker


# ---------------------------------------------------------------------------
# Error boundary (review I1): every plausible failure becomes ExtractorError.
# ---------------------------------------------------------------------------


def test_truncated_model_output_becomes_extractor_error_not_raw_validation_error():
    # This is what the SDK really raises when max_tokens truncates the JSON:
    # Messages.parse -> parse_response -> parse_text -> TypeAdapter.validate_json
    from anthropic.lib._parse._response import parse_text

    try:
        parse_text('{"jobs": [{"title": "Senior Backend Eng', _RawCareersExtraction)
        raise AssertionError("expected the SDK to reject truncated JSON")
    except Exception as exc:  # noqa: BLE001
        real_validation_error = exc

    assert not isinstance(real_validation_error, anthropic.AnthropicError)

    client = MagicMock()
    client.messages.parse.side_effect = real_validation_error

    with pytest.raises(ExtractorError):
        extract_careers(_fixture("careers_page.html"), client=client)


def test_api_response_validation_error_becomes_extractor_error():
    client = MagicMock()
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    client.messages.parse.side_effect = anthropic.APIResponseValidationError(
        response=httpx.Response(200, request=request, json={}), body=None
    )

    with pytest.raises(ExtractorError):
        extract_careers(_fixture("careers_page.html"), client=client)


def test_missing_parsed_output_becomes_extractor_error():
    client = MagicMock()
    response = MagicMock()
    response.parsed_output = None
    response.usage = _mock_usage()
    client.messages.parse.return_value = response

    with pytest.raises(ExtractorError):
        extract_careers(_fixture("careers_page.html"), client=client)


def test_strip_failure_degrades_to_raw_html_rather_than_raising(monkeypatch):
    from scripts.verify import extractor as mod

    def boom(_html):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(mod, "HTMLParser", boom)
    html = "<html><body><a href='/jobs/123456'>Engineer</a></body></html>"
    assert mod._strip_for_extraction(html) == html


# ---------------------------------------------------------------------------
# Degraded-key collisions must be visible (review I3).
# ---------------------------------------------------------------------------


def test_colliding_identity_keys_are_logged_not_silent(caplog):
    raw = _RawCareersExtraction(
        jobs=[
            _RawJob(title="Software Engineer", location="Remote", url=None),
            _RawJob(title="Software Engineer", location="Remote", url="/careers/apply"),
            _RawJob(title="Data Scientist", location="NYC", url="/jobs/5023394008"),
        ]
    )
    client = _mock_client(raw)

    with caplog.at_level("WARNING"):
        facts = extract_careers(_fixture("careers_page.html"), client=client)

    # Both facts survive — the extractor never merges them.
    assert len(facts.jobs) == 3
    assert facts.jobs[0].identity_key == facts.jobs[1].identity_key
    # ...but the ambiguity is visible.
    assert any(
        "title:Software Engineer|location:Remote" in rec.message for rec in caplog.records
    ), "colliding identity key was not reported"


def test_no_collision_warning_when_all_keys_are_distinct(caplog):
    raw = _RawCareersExtraction(
        jobs=[
            _RawJob(title="A", location="Remote", url="/jobs/5023394008"),
            _RawJob(title="B", location="Remote", url="/jobs/5023394115"),
        ]
    )
    client = _mock_client(raw)

    with caplog.at_level("WARNING"):
        extract_careers(_fixture("careers_page.html"), client=client)

    assert not [r for r in caplog.records if "identity key" in r.message]


def test_missing_api_key_raises_extractor_error(monkeypatch):
    from scripts.verify.extractor import _default_client

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ExtractorError):
        _default_client()
