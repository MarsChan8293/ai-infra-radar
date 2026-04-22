"""Webhook delivery channel."""
from __future__ import annotations

import httpx

from radar.core.http_retry import send_with_retries


def send_webhook(url: str, payload: dict) -> None:
    """POST *payload* as JSON to *url*. Raises on non-2xx response."""
    response = send_with_retries(lambda: httpx.post(url, json=payload, timeout=10))
    response.raise_for_status()
