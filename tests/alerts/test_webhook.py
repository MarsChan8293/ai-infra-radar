from __future__ import annotations

import httpx

from radar.alerts.webhook import send_webhook


def test_send_webhook_retries_rate_limit_and_succeeds(monkeypatch: object) -> None:
    request = httpx.Request("POST", "https://hooks.example.com/notify")
    responses = [
        httpx.Response(429, request=request),
        httpx.Response(429, request=request),
        httpx.Response(200, request=request),
    ]
    calls: list[tuple[str, dict, int]] = []

    def fake_post(url: str, json: dict, timeout: int) -> httpx.Response:
        calls.append((url, json, timeout))
        return responses.pop(0)

    monkeypatch.setattr("radar.core.http_retry.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(httpx, "post", fake_post)

    send_webhook("https://hooks.example.com/notify", {"event_type": "daily_digest_item"})

    assert calls == [
        ("https://hooks.example.com/notify", {"event_type": "daily_digest_item"}, 10),
        ("https://hooks.example.com/notify", {"event_type": "daily_digest_item"}, 10),
        ("https://hooks.example.com/notify", {"event_type": "daily_digest_item"}, 10),
    ]
