from __future__ import annotations

import time
from collections.abc import Callable
from collections.abc import Collection

import httpx

_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0


def send_with_retries(
    send: Callable[[], httpx.Response],
    *,
    allowed_status_codes: Collection[int] = (),
) -> httpx.Response:
    last_exc: Exception | None = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = send()
            if response.status_code in allowed_status_codes:
                return response
            if response.status_code not in _RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response
            last_exc = httpx.HTTPStatusError(
                f"HTTP {response.status_code}",
                request=response.request,
                response=response,
            )
        except httpx.HTTPStatusError:
            raise
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc

        if attempt < _MAX_ATTEMPTS - 1:
            time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))

    if last_exc is None:
        raise RuntimeError("HTTP retry helper exhausted without a response or captured exception.")
    raise last_exc
