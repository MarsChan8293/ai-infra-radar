from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx


@respx.mock
def test_huggingface_client_lists_models_for_organization() -> None:
    from radar.sources.huggingface.client import HuggingFaceClient

    payload = json.loads(Path("tests/fixtures/huggingface/models_by_org.json").read_text())
    route = respx.get("https://huggingface.co/api/models").mock(
        return_value=httpx.Response(200, json=payload["items"])
    )

    client = HuggingFaceClient()
    items = client.list_models_for_organization("deepseek")

    assert route.called
    assert items[0]["id"] == "deepseek/deepseek-v3"


@respx.mock
def test_huggingface_client_raises_on_non_2xx_response() -> None:
    from radar.sources.huggingface.client import HuggingFaceClient

    request = httpx.Request("GET", "https://huggingface.co/api/models")
    respx.get("https://huggingface.co/api/models").mock(
        return_value=httpx.Response(503, request=request)
    )

    client = HuggingFaceClient()

    with pytest.raises(httpx.HTTPStatusError):
        client.list_models_for_organization("deepseek")


@respx.mock
def test_huggingface_client_propagates_timeout_failure() -> None:
    from radar.sources.huggingface.client import HuggingFaceClient

    request = httpx.Request("GET", "https://huggingface.co/api/models")
    respx.get("https://huggingface.co/api/models").mock(
        side_effect=httpx.ReadTimeout("timed out", request=request)
    )

    client = HuggingFaceClient()

    with pytest.raises(httpx.ReadTimeout):
        client.list_models_for_organization("deepseek")


def test_build_huggingface_observation_normalizes_core_fields() -> None:
    from radar.sources.huggingface.pipeline import build_huggingface_observation

    item = json.loads(Path("tests/fixtures/huggingface/models_by_org.json").read_text())["items"][0]
    observation = build_huggingface_observation(item)

    assert observation["canonical_name"] == "huggingface:deepseek/deepseek-v3"
    assert observation["display_name"] == "deepseek/deepseek-v3"
    assert observation["url"] == "https://huggingface.co/deepseek/deepseek-v3"
    assert observation["normalized_payload"]["last_modified"] == "2026-04-07T00:00:00Z"


def test_process_huggingface_model_creates_new_model_alert(repo) -> None:
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.sources.huggingface.pipeline import build_huggingface_observation

    dispatcher = AlertDispatcher(
        repository=repo,
        send_webhook=lambda url, payload: None,
        send_email=None,
    )
    service = AlertService(
        repository=repo,
        dispatcher=dispatcher,
        channels={"webhook": "https://hooks.example.com/test"},
    )
    item = json.loads(Path("tests/fixtures/huggingface/models_by_org.json").read_text())["items"][0]
    observation = build_huggingface_observation(item)

    created = service.process_huggingface_model(observation)

    assert created == 1
    alerts = repo.list_alerts()
    assert len(alerts) == 1
    assert alerts[0].alert_type == "huggingface_model_new"


def test_process_huggingface_model_skips_unchanged_model(repo) -> None:
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.sources.huggingface.pipeline import build_huggingface_observation

    dispatcher = AlertDispatcher(
        repository=repo,
        send_webhook=lambda url, payload: None,
        send_email=None,
    )
    service = AlertService(
        repository=repo,
        dispatcher=dispatcher,
        channels={"webhook": "https://hooks.example.com/test"},
    )
    item = json.loads(Path("tests/fixtures/huggingface/models_by_org.json").read_text())["items"][0]
    observation = build_huggingface_observation(item)

    first = service.process_huggingface_model(observation)
    second = service.process_huggingface_model(observation)

    assert first == 1
    assert second == 0
    assert len(repo.list_alerts()) == 1


def test_process_huggingface_model_emits_updated_model_alert(repo) -> None:
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.sources.huggingface.pipeline import build_huggingface_observation

    dispatcher = AlertDispatcher(
        repository=repo,
        send_webhook=lambda url, payload: None,
        send_email=None,
    )
    service = AlertService(
        repository=repo,
        dispatcher=dispatcher,
        channels={"webhook": "https://hooks.example.com/test"},
    )
    item = json.loads(Path("tests/fixtures/huggingface/models_by_org.json").read_text())["items"][0]
    updated_item = {**item, "lastModified": "2026-04-08T00:00:00Z"}

    first = service.process_huggingface_model(build_huggingface_observation(item))
    second = service.process_huggingface_model(build_huggingface_observation(updated_item))

    assert first == 1
    assert second == 1
    alerts = repo.list_alerts()
    assert len(alerts) == 2
    assert alerts[0].alert_type == "huggingface_model_updated"
    assert alerts[1].alert_type == "huggingface_model_new"


def test_run_huggingface_models_job_returns_created_count(repo) -> None:
    from radar.jobs.huggingface_models import run_huggingface_models_job

    item = json.loads(Path("tests/fixtures/huggingface/models_by_org.json").read_text())["items"][0]

    class FakeAlertService:
        def process_huggingface_model(self, observation: dict) -> int:
            assert observation["canonical_name"] == "huggingface:deepseek/deepseek-v3"
            return 1

    created = run_huggingface_models_job(
        [item],
        repository=repo,
        alert_service=FakeAlertService(),
    )

    assert created == 1
