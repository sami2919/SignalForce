"""Unit tests for base API client.

Tests are written first (TDD RED phase) before implementation.
All HTTP calls are mocked — no real network requests.
"""

import pytest
import requests
from unittest.mock import patch, MagicMock, call

from scripts.api_client import APIError, RateLimitError, BaseAPIClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_response(status_code: int, json_body: dict | None = None, headers: dict | None = None):
    """Build a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.headers = headers or {}
    return resp


# ---------------------------------------------------------------------------
# APIError / RateLimitError tests
# ---------------------------------------------------------------------------


def test_api_error_has_correct_fields():
    err = APIError(status_code=404, message="Not found", url="https://api.example.com/v1/foo")
    assert err.status_code == 404
    assert err.message == "Not found"
    assert err.url == "https://api.example.com/v1/foo"
    assert isinstance(err, Exception)


def test_rate_limit_error_has_retry_after():
    err = RateLimitError(
        status_code=429,
        message="Rate limited",
        url="https://api.example.com/v1/bar",
        retry_after=60,
    )
    assert err.status_code == 429
    assert err.retry_after == 60
    assert isinstance(err, APIError)


def test_rate_limit_error_retry_after_optional():
    err = RateLimitError(status_code=429, message="Rate limited", url="https://x.com", retry_after=None)
    assert err.retry_after is None


# ---------------------------------------------------------------------------
# Successful request tests
# ---------------------------------------------------------------------------


def test_successful_get_request():
    """GET 200 returns parsed JSON body."""
    client = BaseAPIClient(base_url="https://api.example.com")
    mock_resp = make_response(200, {"key": "value"})

    with patch("requests.Session.request", return_value=mock_resp) as mock_req:
        result = client.get("/v1/resource", params={"q": "test"})

    assert result == {"key": "value"}
    mock_req.assert_called_once()
    args, kwargs = mock_req.call_args
    assert args[0] == "GET"
    assert "v1/resource" in args[1]


def test_successful_post_request():
    """POST 200 returns parsed JSON body."""
    client = BaseAPIClient(base_url="https://api.example.com")
    mock_resp = make_response(200, {"created": True})

    with patch("requests.Session.request", return_value=mock_resp):
        result = client.post("/v1/resource", json_data={"name": "test"})

    assert result == {"created": True}


# ---------------------------------------------------------------------------
# Rate limit retry tests
# ---------------------------------------------------------------------------


def test_429_triggers_retry():
    """429 response causes a sleep + retry; succeeds on second attempt."""
    client = BaseAPIClient(base_url="https://api.example.com")
    resp_429 = make_response(429, headers={"Retry-After": "1"})
    resp_200 = make_response(200, {"ok": True})

    with patch("requests.Session.request", side_effect=[resp_429, resp_200]) as mock_req:
        with patch("time.sleep") as mock_sleep:
            result = client.get("/v1/resource")

    assert result == {"ok": True}
    assert mock_req.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_403_rate_limit_triggers_retry():
    """403 with X-RateLimit-Remaining=0 causes a sleep + retry."""
    client = BaseAPIClient(base_url="https://api.example.com")
    resp_403 = make_response(
        403,
        headers={
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1",
        },
    )
    resp_200 = make_response(200, {"ok": True})

    with patch("requests.Session.request", side_effect=[resp_403, resp_200]) as mock_req:
        with patch("time.sleep"):
            result = client.get("/v1/resource")

    assert result == {"ok": True}
    assert mock_req.call_count == 2


# ---------------------------------------------------------------------------
# Server error retry / backoff tests
# ---------------------------------------------------------------------------


def test_500_retries_with_backoff():
    """500 is retried with exponential backoff; succeeds on third attempt."""
    client = BaseAPIClient(base_url="https://api.example.com")
    resp_500 = make_response(500)
    resp_200 = make_response(200, {"ok": True})

    with patch("requests.Session.request", side_effect=[resp_500, resp_500, resp_200]):
        with patch("time.sleep") as mock_sleep:
            result = client.get("/v1/resource")

    assert result == {"ok": True}
    # First retry waits 1s, second retry waits 2s
    assert mock_sleep.call_args_list[0] == call(1)
    assert mock_sleep.call_args_list[1] == call(2)


def test_max_retries_exceeded_raises():
    """After 3 retries on 500, APIError is raised."""
    client = BaseAPIClient(base_url="https://api.example.com")
    resp_500 = make_response(500)

    with patch("requests.Session.request", side_effect=[resp_500] * 4):
        with patch("time.sleep"):
            with pytest.raises(APIError) as exc_info:
                client.get("/v1/resource")

    assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Client error tests (no retry)
# ---------------------------------------------------------------------------


def test_400_raises_immediately():
    """400 raises APIError without any retry."""
    client = BaseAPIClient(base_url="https://api.example.com")
    resp_400 = make_response(400, {"error": "bad request"})

    with patch("requests.Session.request", return_value=resp_400) as mock_req:
        with pytest.raises(APIError) as exc_info:
            client.get("/v1/resource")

    assert exc_info.value.status_code == 400
    assert mock_req.call_count == 1  # no retry


def test_401_raises_immediately():
    """401 raises APIError without any retry."""
    client = BaseAPIClient(base_url="https://api.example.com")
    resp_401 = make_response(401, {"error": "unauthorized"})

    with patch("requests.Session.request", return_value=resp_401) as mock_req:
        with pytest.raises(APIError) as exc_info:
            client.get("/v1/resource")

    assert exc_info.value.status_code == 401
    assert mock_req.call_count == 1  # no retry


# ---------------------------------------------------------------------------
# Timeout retry test
# ---------------------------------------------------------------------------


def test_timeout_retries_once():
    """Timeout on first attempt triggers a single retry with a doubled timeout."""
    client = BaseAPIClient(base_url="https://api.example.com", timeout=10)
    resp_200 = make_response(200, {"ok": True})

    with patch("requests.Session.request", side_effect=[requests.Timeout(), resp_200]) as mock_req:
        result = client.get("/v1/resource")

    assert result == {"ok": True}
    assert mock_req.call_count == 2
    # Second call should use doubled timeout (20)
    _, kwargs = mock_req.call_args
    assert kwargs.get("timeout") == 20
