"""HTTP client for official release pages."""
from __future__ import annotations

import time

import httpx

# Retryable HTTP status codes (server-side / rate-limit transients).
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
# Maximum number of attempts (1 initial + 2 retries).
_MAX_ATTEMPTS = 3
# Base back-off in seconds; doubles each retry.
_BACKOFF_BASE = 1.0


def fetch_html(url: str) -> str:
    """Fetch *url* and return the response body as text.

    Retries up to ``_MAX_ATTEMPTS - 1`` times on retryable HTTP status codes
    (429, 5xx) and transient network errors, with exponential back-off.
    Raises on permanent errors or after exhausting retries.
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = httpx.get(url, timeout=10.0, follow_redirects=True)
            if response.status_code not in _RETRYABLE_STATUS:
                response.raise_for_status()
                return response.text
            # Retryable HTTP status — treat as a retriable exception.
            last_exc = httpx.HTTPStatusError(
                f"HTTP {response.status_code}",
                request=response.request,
                response=response,
            )
        except httpx.HTTPStatusError:
            raise  # Non-retryable 4xx/5xx already raised by raise_for_status.
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc

        if attempt < _MAX_ATTEMPTS - 1:
            time.sleep(_BACKOFF_BASE * (2**attempt))

    raise last_exc  # type: ignore[misc]
