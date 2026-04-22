"""Webhook delivery channel."""
from __future__ import annotations

import time

import httpx

_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0


def _rate_limit_delay_seconds(response: httpx.Response, attempt: int) -> float:
    for header_name in ("x-ogw-ratelimit-reset", "retry-after"):
        raw_value = response.headers.get(header_name)
        if raw_value is None:
            continue
        try:
            parsed = float(raw_value)
        except ValueError:
            continue
        if parsed > 0:
            return parsed
    return _BACKOFF_BASE_SECONDS * (2**attempt)


def send_webhook(url: str, payload: dict) -> None:
    """POST *payload* as JSON to *url*. Raises on non-2xx response."""
    for attempt in range(_MAX_ATTEMPTS):
        response = httpx.post(url, json=payload, timeout=10)
        if response.status_code != 429:
            response.raise_for_status()
            return
        if attempt == _MAX_ATTEMPTS - 1:
            response.raise_for_status()
        time.sleep(_rate_limit_delay_seconds(response, attempt))
