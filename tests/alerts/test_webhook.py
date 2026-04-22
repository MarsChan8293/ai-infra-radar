from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime

import httpx
import pytest

import radar.alerts.webhook as webhook_module
from radar.alerts.webhook import _rate_limit_delay_seconds, send_webhook


def test_send_webhook_retries_rate_limit_and_honors_reset_header(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("POST", "https://hooks.example.com/notify")
    responses = [
        httpx.Response(429, headers={"x-ogw-ratelimit-reset": "3"}, request=request),
        httpx.Response(200, request=request),
    ]
    calls: list[tuple[str, dict, int]] = []
    sleeps: list[float] = []

    def fake_post(url: str, json: dict, timeout: int) -> httpx.Response:
        calls.append((url, json, timeout))
        return responses.pop(0)

    monkeypatch.setattr("radar.core.http_retry.time.sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(webhook_module, "time", type("T", (), {"sleep": lambda _self, seconds: sleeps.append(seconds)})(), raising=False)
    monkeypatch.setattr(httpx, "post", fake_post)

    send_webhook("https://hooks.example.com/notify", {"event_type": "daily_digest_item"})

    assert calls == [
        ("https://hooks.example.com/notify", {"event_type": "daily_digest_item"}, 10),
        ("https://hooks.example.com/notify", {"event_type": "daily_digest_item"}, 10),
    ]
    assert sleeps == [3.0]


def test_send_webhook_does_not_retry_timeout_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def raise_timeout(url: str, json: dict, timeout: int) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "post", raise_timeout)
    monkeypatch.setattr("radar.core.http_retry.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(webhook_module, "time", type("T", (), {"sleep": lambda _self, _seconds: None})(), raising=False)

    with pytest.raises(httpx.TimeoutException):
        send_webhook("https://hooks.example.com/notify", {"event_type": "daily_digest_item"})

    assert calls == 1


def test_rate_limit_delay_parses_retry_after_http_date(monkeypatch: pytest.MonkeyPatch) -> None:
    class FixedDateTime:
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            return datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    request = httpx.Request("POST", "https://hooks.example.com/notify")
    response = httpx.Response(
        429,
        headers={"retry-after": format_datetime(datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc), usegmt=True)},
        request=request,
    )

    monkeypatch.setattr(webhook_module, "datetime", FixedDateTime, raising=False)

    assert _rate_limit_delay_seconds(response, 0) == pytest.approx(5.0)
