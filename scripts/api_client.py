"""Base HTTP API client with retry logic, rate-limit handling, and backoff.

Provides:
- APIError / RateLimitError exception hierarchy
- BaseAPIClient: generic session-based HTTP client that scanners inherit from
"""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exception types
# ---------------------------------------------------------------------------


class APIError(Exception):
    """Raised when an API request fails with a non-retryable error."""

    def __init__(self, *, status_code: int, message: str, url: str) -> None:
        super().__init__(f"HTTP {status_code} — {message} [{url}]")
        self.status_code = status_code
        self.message = message
        self.url = url


class RateLimitError(APIError):
    """Raised when all retry attempts have been exhausted due to rate limiting."""

    def __init__(self, *, status_code: int, message: str, url: str, retry_after: int | None) -> None:
        super().__init__(status_code=status_code, message=message, url=url)
        self.retry_after = retry_after


# ---------------------------------------------------------------------------
# Base client
# ---------------------------------------------------------------------------

_SERVER_ERROR_CODES = {500, 502, 503}
_CLIENT_ERROR_NO_RETRY = {400, 401, 404}
_MAX_RETRIES = 3
_BACKOFF_BASE = 1  # seconds


class BaseAPIClient:
    """Generic HTTP client with exponential backoff and rate-limit handling."""

    def __init__(
        self,
        base_url: str,
        auth_headers: dict | None = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        if auth_headers:
            self._session.headers.update(auth_headers)

    # ------------------------------------------------------------------
    # Public convenience methods
    # ------------------------------------------------------------------

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        """Perform a GET request and return the parsed JSON response."""
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, json_data: dict | None = None) -> dict:
        """Perform a POST request and return the parsed JSON response."""
        return self._request("POST", endpoint, json_data=json_data)

    # ------------------------------------------------------------------
    # Core request method
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_data: dict | None = None,
    ) -> dict:
        """Make an HTTP request with retry / backoff logic.

        Retry strategy:
        - 429: sleep Retry-After (or 1s default), retry immediately (not counted as backoff retry)
        - 403 + X-RateLimit-Remaining=0: sleep until X-RateLimit-Reset, retry
        - 500/502/503: exponential backoff (1s, 2s, 4s), max 3 retries
        - Timeout: retry once with doubled timeout
        - 400/401/404: raise immediately, no retry

        Returns:
            Parsed JSON response body as a dict.

        Raises:
            APIError: On non-retryable errors or when retries are exhausted.
            RateLimitError: When rate-limit retries are exhausted.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        current_timeout = self.timeout
        server_error_retries = 0

        while True:
            logger.debug("%s %s", method, url)

            try:
                response = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json_data,
                    timeout=current_timeout,
                )
            except requests.Timeout:
                logger.warning("Request timed out: %s %s — retrying with doubled timeout", method, url)
                current_timeout *= 2
                # Only retry once for timeout
                response = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json_data,
                    timeout=current_timeout,
                )

            status = response.status_code
            logger.debug("Response status: %d for %s %s", status, method, url)

            if status == 200:
                return response.json()

            # --- Rate limit: 429 ---
            if status == 429:
                retry_after_raw = response.headers.get("Retry-After", "1")
                try:
                    retry_after = int(retry_after_raw)
                except (ValueError, TypeError):
                    retry_after = 1
                logger.warning("429 rate limited on %s — sleeping %ds", url, retry_after)
                time.sleep(retry_after)
                continue  # retry without counting against backoff limit

            # --- Rate limit: 403 with exhausted quota ---
            if status == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
                reset_raw = response.headers.get("X-RateLimit-Reset", "1")
                try:
                    sleep_for = int(reset_raw)
                except (ValueError, TypeError):
                    sleep_for = 1
                logger.warning("403 quota exhausted on %s — sleeping %ds", url, sleep_for)
                time.sleep(sleep_for)
                continue  # retry without counting against backoff limit

            # --- Client errors: raise immediately ---
            if status in _CLIENT_ERROR_NO_RETRY:
                raise APIError(
                    status_code=status,
                    message=f"Client error: {response.json()}",
                    url=url,
                )

            # --- Server errors: exponential backoff ---
            if status in _SERVER_ERROR_CODES:
                if server_error_retries >= _MAX_RETRIES:
                    raise APIError(
                        status_code=status,
                        message=f"Server error after {_MAX_RETRIES} retries",
                        url=url,
                    )
                sleep_time = _BACKOFF_BASE * (2**server_error_retries)
                logger.warning(
                    "Server error %d on %s — retry %d/%d in %ds",
                    status,
                    url,
                    server_error_retries + 1,
                    _MAX_RETRIES,
                    sleep_time,
                )
                time.sleep(sleep_time)
                server_error_retries += 1
                continue

            # --- Any other unexpected status ---
            raise APIError(
                status_code=status,
                message="Unexpected response status",
                url=url,
            )
