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
    assert html in messages[0]["content"]
    # Page content must not leak into the cached system block.
    assert all(html not in block.get("text", "") for block in system)


def test_default_client_used_when_none_provided(monkeypatch):
    raw = _RawCareersExtraction(jobs=[])
    fake_client = _mock_client(raw)
    monkeypatch.setattr("scripts.verify.extractor._default_client", lambda: fake_client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    facts = extract_careers(_fixture("careers_page_empty.html"))

    assert facts.jobs == ()
    fake_client.messages.parse.assert_called_once()
