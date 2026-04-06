"""Tests for alert dispatcher and alert service (Task 5)."""
from __future__ import annotations

import pytest

from radar.alerts.dispatcher import AlertDispatcher
from radar.alerts.service import AlertService
from radar.core.repositories import RadarRepository

# ---------------------------------------------------------------------------
# Dispatcher: delivery log recording
# ---------------------------------------------------------------------------


def test_dispatcher_records_delivery_logs_for_all_channels(repo: RadarRepository) -> None:
    entity = repo.upsert_entity(
        source="official_pages",
        entity_type="page",
        canonical_name="dispatch_test_entity",
        display_name="Test Page",
        url="https://example.com",
    )
    alert = repo.create_alert(
        alert_type="official_release",
        entity_id=entity.id,
        source="official_pages",
        score=0.9,
        dedupe_key="test:dispatch:001",
        reason={"title": "New release"},
    )

    webhook_calls: list[tuple[str, dict]] = []
    email_calls: list[dict] = []

    def fake_webhook(url: str, payload: dict) -> None:
        webhook_calls.append((url, payload))

    def fake_email(payload: dict) -> None:
        email_calls.append(payload)

    dispatcher = AlertDispatcher(
        repository=repo,
        send_webhook=fake_webhook,
        send_email=fake_email,
    )

    dispatcher.dispatch(
        alert_id=alert.id,
        alert_payload={"title": "New release", "score": 0.9},
        channels={"webhook": "https://hooks.example.com/notify", "email": True},
    )

    assert len(webhook_calls) == 1
    assert webhook_calls[0][0] == "https://hooks.example.com/notify"
    assert len(email_calls) == 1

    logs = repo.get_delivery_logs(alert_id=alert.id)
    assert len(logs) == 2
    channels_logged = {log.channel for log in logs}
    assert "webhook" in channels_logged
    assert "email" in channels_logged
    assert all(log.status == "sent" for log in logs)


def test_dispatcher_records_failed_status_on_sender_error(repo: RadarRepository) -> None:
    entity = repo.upsert_entity(
        source="official_pages",
        entity_type="page",
        canonical_name="fail_test_entity",
        display_name="Fail Test",
        url="https://example.com/fail",
    )
    alert = repo.create_alert(
        alert_type="official_release",
        entity_id=entity.id,
        source="official_pages",
        score=0.8,
        dedupe_key="test:dispatch:fail",
        reason={},
    )

    def bad_webhook(url: str, payload: dict) -> None:
        raise RuntimeError("connection refused")

    dispatcher = AlertDispatcher(
        repository=repo,
        send_webhook=bad_webhook,
        send_email=None,
    )

    dispatcher.dispatch(
        alert_id=alert.id,
        alert_payload={"score": 0.8},
        channels={"webhook": "https://dead.example.com/hook"},
    )

    logs = repo.get_delivery_logs(alert_id=alert.id)
    assert len(logs) == 1
    assert logs[0].status == "failed"


def test_dispatcher_records_skipped_status_when_sender_is_missing(repo: RadarRepository) -> None:
    entity = repo.upsert_entity(
        source="official_pages",
        entity_type="page",
        canonical_name="skip_test_entity",
        display_name="Skip Test",
        url="https://example.com/skip",
    )
    alert = repo.create_alert(
        alert_type="official_release",
        entity_id=entity.id,
        source="official_pages",
        score=0.7,
        dedupe_key="test:dispatch:skip",
        reason={},
    )

    dispatcher = AlertDispatcher(
        repository=repo,
        send_webhook=lambda url, payload: None,
        send_email=None,
    )

    dispatcher.dispatch(
        alert_id=alert.id,
        alert_payload={"score": 0.7},
        channels={"webhook": "https://hooks.example.com/notify", "email": True},
    )

    logs = {log.channel: log.status for log in repo.get_delivery_logs(alert_id=alert.id)}
    assert logs == {"webhook": "sent", "email": "skipped"}


# ---------------------------------------------------------------------------
# AlertService: emit_alert dedupe/suppression
# ---------------------------------------------------------------------------


def test_emit_alert_creates_alert_and_returns_1_on_new(
    repo: RadarRepository,
    alert_service: AlertService,
) -> None:
    entity = repo.upsert_entity(
        source="official_pages",
        entity_type="page",
        canonical_name="emit_test_entity",
        display_name="Emit Test",
        url="https://example.com/emit",
    )

    count = alert_service.emit_alert(
        alert_type="official_release",
        entity_id=entity.id,
        source="official_pages",
        score=0.9,
        dedupe_key="emit:test:001",
        reason={"title": "Release 1.0"},
        alert_payload={"title": "Release 1.0"},
    )
    assert count == 1


def test_emit_alert_suppresses_duplicate_and_returns_0(
    repo: RadarRepository,
    alert_service: AlertService,
) -> None:
    entity = repo.upsert_entity(
        source="official_pages",
        entity_type="page",
        canonical_name="dup_emit_entity",
        display_name="Dup Emit Test",
        url="https://example.com/dup",
    )

    count_first = alert_service.emit_alert(
        alert_type="official_release",
        entity_id=entity.id,
        source="official_pages",
        score=0.9,
        dedupe_key="emit:dup:key",
        reason={"title": "Release 2.0"},
        alert_payload={"title": "Release 2.0"},
    )
    count_second = alert_service.emit_alert(
        alert_type="official_release",
        entity_id=entity.id,
        source="official_pages",
        score=0.9,
        dedupe_key="emit:dup:key",
        reason={"title": "Release 2.0"},
        alert_payload={"title": "Release 2.0"},
    )

    assert count_first == 1
    assert count_second == 0


# ---------------------------------------------------------------------------
# AlertService: process_official_page
# ---------------------------------------------------------------------------


def test_process_official_page_upserts_entity_and_emits_alert(repo: RadarRepository) -> None:
    from radar.core.config import OfficialPageEntry

    dispatched_alerts: list[int] = []

    def fake_webhook(url: str, payload: dict) -> None:
        dispatched_alerts.append(payload.get("alert_id", -1))

    dispatcher = AlertDispatcher(
        repository=repo,
        send_webhook=fake_webhook,
        send_email=None,
    )
    service = AlertService(
        repository=repo,
        dispatcher=dispatcher,
        channels={"webhook": "https://hooks.example.com/"},
    )

    page_config = OfficialPageEntry(
        url="https://example.com/releases",
        whitelist_keywords=["release"],
    )
    observation = {
        "canonical_name": "https://example.com/releases",
        "display_name": "Example Releases",
        "url": "https://example.com/releases",
        "title": "Version 1.0 release",
        "content_hash": "hash_abc123",
        "matched_keywords": ["release"],
        "normalized_payload": {"title": "Version 1.0 release"},
        "raw_payload": {"html_snippet": "<h1>Version 1.0 release</h1>"},
        "score": 1.0,
    }

    count = service.process_official_page(page_config, observation)
    assert count == 1
