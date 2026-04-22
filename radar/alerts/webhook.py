"""Webhook delivery channel."""
from __future__ import annotations

import time
from datetime import datetime
from datetime import timezone
from email.utils import parsedate_to_datetime

import httpx

_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0


def _rate_limit_delay_seconds(response: httpx.Response, attempt: int) -> float:
    raw_reset = response.headers.get("x-ogw-ratelimit-reset")
    if raw_reset is not None:
        try:
            parsed_reset = float(raw_reset)
        except ValueError:
            parsed_reset = None
        if parsed_reset is not None and parsed_reset > 0:
            return parsed_reset

    raw_retry_after = response.headers.get("retry-after")
    if raw_retry_after is not None:
        try:
            parsed_retry_after = float(raw_retry_after)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(raw_retry_after)
            except (TypeError, ValueError, IndexError, OverflowError):
                retry_at = None
            if retry_at is not None:
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delay_seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
                if delay_seconds > 0:
                    return delay_seconds
        else:
            if parsed_retry_after > 0:
                return parsed_retry_after
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
