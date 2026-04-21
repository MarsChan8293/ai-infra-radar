from __future__ import annotations

from radar.app import (
    _build_daily_digest_webhook_payloads,
    _dispatch_daily_digest_payload,
)


class RecordingDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, dict, str]] = []

    def dispatch_raw(
        self,
        *,
        alert_payload: dict,
        channels: dict,
        delivery_key_prefix: str,
    ) -> None:
        self.calls.append((alert_payload, channels, delivery_key_prefix))


def test_build_daily_digest_webhook_payloads_expands_each_item() -> None:
    payload = {
        "type": "daily_digest",
        "count": 2,
        "items": [
            {
                "alert_id": 101,
                "alert_type": "github_burst",
                "source": "github",
                "score": 0.91,
            },
            {
                "alert_id": 102,
                "alert_type": "official_release",
                "source": "official_pages",
                "score": 0.77,
            },
        ],
    }

    assert _build_daily_digest_webhook_payloads(payload) == [
        {
            "event_type": "daily_digest_item",
            "digest_type": "daily_digest",
            "digest_count": 2,
            "item_index": 1,
            "alert_id": 101,
            "alert_type": "github_burst",
            "source": "github",
            "score": 0.91,
        },
        {
            "event_type": "daily_digest_item",
            "digest_type": "daily_digest",
            "digest_count": 2,
            "item_index": 2,
            "alert_id": 102,
            "alert_type": "official_release",
            "source": "official_pages",
            "score": 0.77,
        },
    ]


def test_dispatch_daily_digest_payload_sends_webhook_per_item_and_email_once() -> None:
    dispatcher = RecordingDispatcher()
    payload = {
        "type": "daily_digest",
        "count": 2,
        "items": [
            {
                "alert_id": 101,
                "alert_type": "github_burst",
                "source": "github",
                "score": 0.91,
            },
            {
                "alert_id": 102,
                "alert_type": "official_release",
                "source": "official_pages",
                "score": 0.77,
            },
        ],
    }

    _dispatch_daily_digest_payload(
        dispatcher=dispatcher,
        payload=payload,
        channels={
            "webhook": "https://hooks.example.com/notify",
            "email": True,
        },
    )

    assert dispatcher.calls == [
        (
            {
                "event_type": "daily_digest_item",
                "digest_type": "daily_digest",
                "digest_count": 2,
                "item_index": 1,
                "alert_id": 101,
                "alert_type": "github_burst",
                "source": "github",
                "score": 0.91,
            },
            {"webhook": "https://hooks.example.com/notify"},
            "daily_digest:1",
        ),
        (
            {
                "event_type": "daily_digest_item",
                "digest_type": "daily_digest",
                "digest_count": 2,
                "item_index": 2,
                "alert_id": 102,
                "alert_type": "official_release",
                "source": "official_pages",
                "score": 0.77,
            },
            {"webhook": "https://hooks.example.com/notify"},
            "daily_digest:2",
        ),
        (
            payload,
            {"email": True},
            "daily_digest",
        ),
    ]
