"""Security tests for BaseAPIClient and scanners that make outbound HTTP calls.

Covers:
  1. Secret leakage via URL logging — SerpAPI key embedded as query param
  2. Unbounded sleep via attacker-controlled Retry-After / X-RateLimit-Reset headers
  3. response.json() crash on non-JSON 400 body (DoS / silent swallow risk)
  4. Timeout always present on every outbound call
  5. SSRF — FundingClient accepts arbitrary base_url without allowlisting
  6. G2 scanner: raw requests.Session calls still carry a timeout

All HTTP is mocked — no real network requests are made.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.api_client import APIError, BaseAPIClient
from scripts.scanners.job_scanner import JobPostingClient
from scripts.scanners.funding_scanner import FundingClient
from scripts.scanners.g2_authenticated_scanner import G2AuthenticatedScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_response(
    status_code: int,
    json_body: dict | list | None = None,
    headers: dict | None = None,
    text: str = "",
) -> MagicMock:
    """Build a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = text
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = requests.exceptions.JSONDecodeError("No JSON", "", 0)
    return resp


def make_json_response(
    status_code: int, body: dict | list, headers: dict | None = None
) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.json.return_value = body
    return resp


# ---------------------------------------------------------------------------
# FINDING 1 (HIGH): SerpAPI key leaks into log output via URL query params
#
# Root cause: job_scanner.py:64 passes api_key as a URL query parameter.
# BaseAPIClient logs the full URL at DEBUG level (api_client.py:111) and
# WARNING level (api_client.py:148, 159, 180).
# ---------------------------------------------------------------------------


class TestSerpAPIKeyLeaksInLogs:
    """Assert that the SerpAPI key must NOT appear in any log output."""

    def test_api_key_not_logged_on_successful_request(self, caplog):
        """api_key= must not appear in any log record on a 200 response."""
        client = JobPostingClient(api_key="sk-secret-serpapi-key-12345")
        ok_resp = make_json_response(200, {"organic_results": []})

        with caplog.at_level(logging.DEBUG, logger="scripts.api_client"):
            with patch("requests.Session.request", return_value=ok_resp):
                client.search_jobs("RL engineer", num_results=5)

        for record in caplog.records:
            assert "sk-secret-serpapi-key-12345" not in record.getMessage(), (
                f"API key leaked in log: {record.getMessage()!r}"
            )
        for record in caplog.records:
            assert "api_key=" not in record.getMessage(), (
                f"api_key param leaked in log: {record.getMessage()!r}"
            )

    def test_api_key_not_logged_on_429_retry(self, caplog):
        """On a 429, the retry warning logs the URL — key must not appear in it."""
        client = JobPostingClient(api_key="sk-secret-serpapi-key-12345")
        resp_429 = make_json_response(429, {}, headers={"Retry-After": "1"})
        resp_200 = make_json_response(200, {"organic_results": []})

        with caplog.at_level(logging.WARNING, logger="scripts.api_client"):
            with patch("requests.Session.request", side_effect=[resp_429, resp_200]):
                with patch("time.sleep"):
                    client.search_jobs("ML ops", num_results=5)

        for record in caplog.records:
            assert "sk-secret-serpapi-key-12345" not in record.getMessage(), (
                f"API key leaked in 429 warning: {record.getMessage()!r}"
            )

    def test_api_key_not_logged_on_500_error(self, caplog):
        """Server error warning should not expose the api_key in the URL."""
        client = JobPostingClient(api_key="sk-secret-serpapi-key-12345")
        resp_500 = make_json_response(500, {})
        resp_200 = make_json_response(200, {"organic_results": []})

        with caplog.at_level(logging.WARNING, logger="scripts.api_client"):
            with patch("requests.Session.request", side_effect=[resp_500, resp_500, resp_200]):
                with patch("time.sleep"):
                    client.search_jobs("data engineer", num_results=5)

        for record in caplog.records:
            assert "sk-secret-serpapi-key-12345" not in record.getMessage(), (
                f"API key leaked in 500 warning: {record.getMessage()!r}"
            )

    def test_api_key_not_in_api_error_message(self, caplog):
        """When a 400 is returned, the warning log for the failed search must not embed the key.

        JobPostingClient.search_jobs intentionally catches APIError and logs a
        warning rather than re-raising, so we assert the warning text is clean.
        """
        client = JobPostingClient(api_key="sk-secret-serpapi-key-12345")
        resp_400 = make_json_response(400, {"error": "bad request"})

        with caplog.at_level(logging.WARNING, logger="scripts.scanners.job_scanner"):
            with patch("requests.Session.request", return_value=resp_400):
                result = client.search_jobs("engineer", num_results=5)

        assert result == [], "Expected empty list on failed search"
        for record in caplog.records:
            assert "sk-secret-serpapi-key-12345" not in record.getMessage(), (
                f"API key leaked in warning log: {record.getMessage()!r}"
            )

    def test_api_key_not_in_stored_url_on_error(self, caplog):
        """The APIError raised internally must not include the api_key in its url attribute.

        We test this by calling BaseAPIClient._request directly (bypassing the
        try/except in search_jobs) and asserting the safe_url is used.
        """
        # Build a raw BaseAPIClient that has the api_key baked into params
        client = BaseAPIClient(base_url="https://serpapi.com")
        resp_400 = make_json_response(400, {"error": "bad request"})

        with patch("requests.Session.request", return_value=resp_400):
            with pytest.raises(APIError) as exc_info:
                client._request(
                    "GET",
                    "/search",
                    params={"q": "engineer", "api_key": "sk-secret-serpapi-key-12345"},
                )

        assert "sk-secret-serpapi-key-12345" not in exc_info.value.url, (
            f"API key exposed in exc.url: {exc_info.value.url!r}"
        )
        assert "sk-secret-serpapi-key-12345" not in str(exc_info.value), (
            f"API key exposed in str(exc): {exc_info.value!s}"
        )


# ---------------------------------------------------------------------------
# FINDING 2 (HIGH): Unbounded sleep — attacker-controlled Retry-After header
#
# Root cause: api_client.py:145-149 and 156-160 do int(header_value) and pass
# it directly to time.sleep() with no cap.  A compromised/malicious API
# endpoint can respond with Retry-After: 86400 (24 hours) and the client will
# block for that duration indefinitely.
# ---------------------------------------------------------------------------


class TestUnboundedSleepRetryAfter:
    """Retry-After and X-RateLimit-Reset sleep must be capped at a safe maximum."""

    _MAX_ALLOWED_SLEEP = 300  # 5 minutes is a generous cap for production scanners

    def test_large_retry_after_is_capped(self):
        """A Retry-After: 86400 must NOT result in time.sleep(86400)."""
        client = BaseAPIClient(base_url="https://api.example.com")
        resp_429 = make_json_response(429, {}, headers={"Retry-After": "86400"})
        resp_200 = make_json_response(200, {"ok": True})

        sleep_calls: list[float] = []

        def record_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with patch("requests.Session.request", side_effect=[resp_429, resp_200]):
            with patch("time.sleep", side_effect=record_sleep):
                client.get("/resource")

        assert sleep_calls, "Expected at least one sleep call"
        for sleep_val in sleep_calls:
            assert sleep_val <= self._MAX_ALLOWED_SLEEP, (
                f"Unbounded sleep: time.sleep({sleep_val}) exceeds safe cap of "
                f"{self._MAX_ALLOWED_SLEEP}s. A malicious endpoint can trigger a "
                f"86400s (24h) hang."
            )

    def test_large_ratelimit_reset_is_capped(self):
        """X-RateLimit-Reset: 999999 must NOT result in time.sleep(999999)."""
        client = BaseAPIClient(base_url="https://api.example.com")
        resp_403 = make_json_response(
            403,
            {},
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "999999"},
        )
        resp_200 = make_json_response(200, {"ok": True})

        sleep_calls: list[float] = []

        def record_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with patch("requests.Session.request", side_effect=[resp_403, resp_200]):
            with patch("time.sleep", side_effect=record_sleep):
                client.get("/resource")

        assert sleep_calls, "Expected at least one sleep call"
        for sleep_val in sleep_calls:
            assert sleep_val <= self._MAX_ALLOWED_SLEEP, (
                f"Unbounded sleep: time.sleep({sleep_val}) exceeds safe cap of "
                f"{self._MAX_ALLOWED_SLEEP}s."
            )

    def test_negative_retry_after_does_not_sleep_negative(self):
        """A negative or zero Retry-After must not cause time.sleep(<= 0)."""
        client = BaseAPIClient(base_url="https://api.example.com")
        resp_429 = make_json_response(429, {}, headers={"Retry-After": "-5"})
        resp_200 = make_json_response(200, {"ok": True})

        sleep_calls: list[float] = []

        def record_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with patch("requests.Session.request", side_effect=[resp_429, resp_200]):
            with patch("time.sleep", side_effect=record_sleep):
                client.get("/resource")

        for sleep_val in sleep_calls:
            assert sleep_val >= 0, f"time.sleep({sleep_val}) must not be negative"


# ---------------------------------------------------------------------------
# FINDING 3 (MEDIUM): response.json() called unconditionally on 400 body
#
# Root cause: api_client.py:167 calls response.json() inside the
# _CLIENT_ERROR_NO_RETRY branch. If the server returns a 400 with a non-JSON
# body (HTML error page, plain text), this raises JSONDecodeError, which
# bubbles up as an unhandled exception instead of a clean APIError.
# ---------------------------------------------------------------------------


class TestNonJsonErrorBodyHandling:
    """Non-JSON error responses on 400/401/404 must not raise JSONDecodeError."""

    def test_400_with_html_body_raises_api_error_not_json_error(self):
        """A 400 with Content-Type: text/html must raise APIError, not JSONDecodeError."""
        client = BaseAPIClient(base_url="https://api.example.com")
        resp_400 = make_response(400, json_body=None, text="<html>Bad Request</html>")

        with patch("requests.Session.request", return_value=resp_400):
            with pytest.raises(APIError) as exc_info:
                client.get("/resource")

        assert exc_info.value.status_code == 400
        # Should NOT be a JSONDecodeError
        assert not isinstance(exc_info.value.__cause__, requests.exceptions.JSONDecodeError)

    def test_401_with_plain_text_body_raises_api_error(self):
        """A 401 with plain text body must raise APIError with status_code=401."""
        client = BaseAPIClient(base_url="https://api.example.com")
        resp_401 = make_response(401, json_body=None, text="Unauthorized")

        with patch("requests.Session.request", return_value=resp_401):
            with pytest.raises(APIError) as exc_info:
                client.get("/resource")

        assert exc_info.value.status_code == 401

    def test_404_with_empty_body_raises_api_error(self):
        """A 404 with empty body must raise APIError with status_code=404."""
        client = BaseAPIClient(base_url="https://api.example.com")
        resp_404 = make_response(404, json_body=None, text="")

        with patch("requests.Session.request", return_value=resp_404):
            with pytest.raises(APIError) as exc_info:
                client.get("/resource")

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# FINDING 4 (MEDIUM): Timeout is always set on all BaseAPIClient requests
#
# Verifying the baseline good behavior so a future regression is caught.
# ---------------------------------------------------------------------------


class TestTimeoutAlwaysSet:
    """Every outbound request must include an explicit timeout."""

    def test_default_timeout_is_passed(self):
        """Requests use the configured timeout by default."""
        client = BaseAPIClient(base_url="https://api.example.com", timeout=30)
        resp_200 = make_json_response(200, {"ok": True})

        with patch("requests.Session.request", return_value=resp_200) as mock_req:
            client.get("/resource")

        _, kwargs = mock_req.call_args
        assert kwargs.get("timeout") == 30, f"Expected timeout=30 in request kwargs, got: {kwargs}"

    def test_custom_timeout_is_passed(self):
        """A custom timeout set on the client is forwarded to every request."""
        client = BaseAPIClient(base_url="https://api.example.com", timeout=10)
        resp_200 = make_json_response(200, {"ok": True})

        with patch("requests.Session.request", return_value=resp_200) as mock_req:
            client.post("/resource", json_data={"x": 1})

        _, kwargs = mock_req.call_args
        assert kwargs.get("timeout") == 10

    def test_timeout_never_none(self):
        """Timeout must never be None (would mean no timeout = hang forever)."""
        client = BaseAPIClient(base_url="https://api.example.com")
        resp_200 = make_json_response(200, {"ok": True})

        with patch("requests.Session.request", return_value=resp_200) as mock_req:
            client.get("/resource")

        _, kwargs = mock_req.call_args
        assert kwargs.get("timeout") is not None, (
            "Timeout must never be None — hanging requests can exhaust worker threads"
        )

    def test_g2_scanner_includes_timeout_in_fetch(self):
        """G2AuthenticatedScanner._fetch_reviews must pass timeout to its raw Session.get."""
        scanner = G2AuthenticatedScanner(cookie="session=abc123")

        page1 = make_json_response(
            200,
            {
                "reviews": [],
                "meta": {"total_pages": 1},
            },
        )

        with patch.object(scanner._session, "get", return_value=page1) as mock_get:
            list(scanner._fetch_reviews({"slug": "hubspot", "display": "HubSpot"}, stars=2))

        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert kwargs.get("timeout") is not None, (
            "G2AuthenticatedScanner.get call must include a timeout"
        )
        assert isinstance(kwargs["timeout"], (int, float))


# ---------------------------------------------------------------------------
# FINDING 5 (MEDIUM): SSRF — FundingClient accepts arbitrary base_url
#
# Root cause: funding_scanner.py:FundingClient takes base_url as a plain
# constructor arg. If this came from user-controlled config it could point
# at internal services (e.g., http://169.254.169.254/latest/meta-data/).
# The current hardcoded default is safe; test asserts the allowlist guard
# that should exist.
# ---------------------------------------------------------------------------


class TestSSRFBaseUrlValidation:
    """Document the current SSRF exposure in FundingClient.

    KNOWN GAP (MEDIUM): FundingClient accepts arbitrary base_url without
    validation.  In the current codebase the value is hardcoded in
    FundingTracker, so there is no live injection path. The tests below
    document the DESIRED behavior (safe URLs accepted, unsafe rejected) and
    the CURRENT behavior (no validation — unsafe URLs silently accepted).

    Once allowlist validation is added to FundingClient.__init__, the
    "current behavior" assertions below should be inverted to match the
    desired behavior.
    """

    _SAFE_URLS = [
        "https://api.crunchbase.com/api/v4",
        "https://api.pitchbook.com/v1",
    ]

    def test_safe_https_urls_are_accepted(self):
        """Legitimate HTTPS API base URLs must be constructable without error."""
        for url in self._SAFE_URLS:
            client = FundingClient(base_url=url, api_key=None)
            assert client.base_url.startswith("https://"), (
                f"Expected https:// base_url, got: {client.base_url}"
            )

    def test_internal_ip_url_currently_not_validated(self):
        """KNOWN GAP: internal-network base_url is NOT currently rejected.

        This test documents the current (unsafe) behavior. When SSRF
        allowlist validation is implemented, change this assertion to
        pytest.raises(ValueError).
        """
        # Currently FundingClient accepts any URL — this is the gap.
        client = FundingClient(base_url="http://169.254.169.254/latest/meta-data", api_key=None)
        # The client is in simulation mode (no api_key), so no real request is made.
        assert client.simulation_mode, (
            "SSRF gap: FundingClient accepted a cloud metadata URL without validation. "
            "Add allowlist validation to FundingClient.__init__."
        )

    def test_http_scheme_currently_not_validated(self):
        """KNOWN GAP: plain HTTP base_url is NOT currently rejected.

        This test documents the current (unsafe) behavior. When TLS enforcement
        is added, change this assertion to pytest.raises(ValueError).
        """
        client = FundingClient(base_url="http://api.crunchbase.com/api/v4", api_key=None)
        assert client.simulation_mode, (
            "TLS gap: FundingClient accepted http:// without raising. "
            "Add scheme validation to enforce https://."
        )


# ---------------------------------------------------------------------------
# FINDING 6 (LOW): Confirm auth headers are never echoed in log output
#
# Logging the full URL is fine; logging headers (which carry Bearer tokens)
# would be a secret leakage. Verify no header logging occurs.
# ---------------------------------------------------------------------------


class TestAuthHeadersNotLogged:
    """Authorization / x-api-key headers must never appear in log output."""

    def test_bearer_token_not_in_logs(self, caplog):
        """Bearer token in auth_headers must not appear in any log message."""
        client = BaseAPIClient(
            base_url="https://api.example.com",
            auth_headers={"Authorization": "Bearer top-secret-token-xyz"},
        )
        ok_resp = make_json_response(200, {"result": "ok"})

        with caplog.at_level(logging.DEBUG, logger="scripts.api_client"):
            with patch("requests.Session.request", return_value=ok_resp):
                client.get("/resource")

        for record in caplog.records:
            assert "top-secret-token-xyz" not in record.getMessage(), (
                f"Bearer token leaked in log: {record.getMessage()!r}"
            )

    def test_api_key_header_not_in_logs(self, caplog):
        """x-api-key header value must not appear in any log message."""
        client = BaseAPIClient(
            base_url="https://api.semanticscholar.org",
            auth_headers={"x-api-key": "scholar-key-abc999"},
        )
        resp_429 = make_json_response(429, {}, headers={"Retry-After": "1"})
        ok_resp = make_json_response(200, {"data": []})

        with caplog.at_level(logging.WARNING, logger="scripts.api_client"):
            with patch("requests.Session.request", side_effect=[resp_429, ok_resp]):
                with patch("time.sleep"):
                    client.get("/paper/search", params={"query": "RL"})

        for record in caplog.records:
            assert "scholar-key-abc999" not in record.getMessage(), (
                f"x-api-key leaked in log: {record.getMessage()!r}"
            )
