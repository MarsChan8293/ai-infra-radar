from __future__ import annotations

import httpx
import pytest
import respx


@respx.mock
def test_modelscope_client_lists_models_for_organization() -> None:
    from radar.sources.modelscope.client import ModelScopeClient

    payload = {
        "Code": 0,
        "Data": {"Models": [{"Id": 1, "Name": "deepseek-v1", "Path": "deepseek/deepseek-v1", "CreatedTime": "2026-04-01T00:00:00Z", "LastUpdatedTime": "2026-04-07T00:00:00Z", "Downloads": 10}]},
        "Message": "ok",
        "RequestId": "",
        "Success": True,
    }
    route = respx.put("https://www.modelscope.cn/api/v1/models/").mock(
        return_value=httpx.Response(200, json=payload)
    )

    client = ModelScopeClient()
    items = client.list_models_for_organization("deepseek")

    assert route.called
    assert items[0]["Id"] == 1


@respx.mock
def test_modelscope_client_raises_on_non_2xx_response() -> None:
    from radar.sources.modelscope.client import ModelScopeClient

    request = httpx.Request("PUT", "https://www.modelscope.cn/api/v1/models/")
    respx.put("https://www.modelscope.cn/api/v1/models/").mock(
        return_value=httpx.Response(503, request=request)
    )

    client = ModelScopeClient()

    with pytest.raises(httpx.HTTPStatusError):
        client.list_models_for_organization("deepseek")


@respx.mock
def test_modelscope_client_propagates_timeout_failure() -> None:
    from radar.sources.modelscope.client import ModelScopeClient

    request = httpx.Request("PUT", "https://www.modelscope.cn/api/v1/models/")
    respx.put("https://www.modelscope.cn/api/v1/models/").mock(
        side_effect=httpx.ReadTimeout("timed out", request=request)
    )

    client = ModelScopeClient()

    with pytest.raises(httpx.ReadTimeout):
        client.list_models_for_organization("deepseek")


def test_build_modelscope_observation_normalizes_core_fields() -> None:
    from radar.sources.modelscope.pipeline import build_modelscope_observation

    item = {"Id": 1, "Name": "deepseek-v1", "Path": "deepseek/deepseek-v1", "LastUpdatedTime": "2026-04-07T00:00:00Z", "Downloads": 10}
    observation = build_modelscope_observation(item)

    assert observation["canonical_name"] == "modelscope:deepseek/deepseek-v1"
    assert observation["display_name"] == "deepseek-v1"
    assert observation["url"] == "https://www.modelscope.cn/models/deepseek/deepseek-v1"
    assert observation["normalized_payload"]["last_updated_time"] == "2026-04-07T00:00:00Z"


def test_process_modelscope_model_creates_new_model_alert(repo) -> None:
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.sources.modelscope.pipeline import build_modelscope_observation

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
    item = {"Id": 1, "Name": "deepseek-v1", "Path": "deepseek/deepseek-v1", "LastUpdatedTime": "2026-04-07T00:00:00Z", "Downloads": 10}
    observation = build_modelscope_observation(item)

    created = service.process_modelscope_model(observation)

    assert created == 1
    alerts = repo.list_alerts()
    assert len(alerts) == 1
    assert alerts[0].alert_type == "modelscope_model_new"


def test_process_modelscope_model_skips_unchanged_model(repo) -> None:
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.sources.modelscope.pipeline import build_modelscope_observation

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
    item = {"Id": 1, "Name": "deepseek-v1", "Path": "deepseek/deepseek-v1", "LastUpdatedTime": "2026-04-07T00:00:00Z", "Downloads": 10}
    observation = build_modelscope_observation(item)

    first = service.process_modelscope_model(observation)
    second = service.process_modelscope_model(observation)

    assert first == 1
    assert second == 0
    assert len(repo.list_alerts()) == 1


def test_process_modelscope_model_emits_updated_model_alert(repo) -> None:
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.sources.modelscope.pipeline import build_modelscope_observation

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
    item = {"Id": 1, "Name": "deepseek-v1", "Path": "deepseek/deepseek-v1", "LastUpdatedTime": "2026-04-07T00:00:00Z", "Downloads": 10}
    updated_item = {**item, "LastUpdatedTime": "2026-04-08T00:00:00Z"}

    first = service.process_modelscope_model(build_modelscope_observation(item))
    second = service.process_modelscope_model(build_modelscope_observation(updated_item))

    assert first == 1
    assert second == 1
    alerts = repo.list_alerts()
    assert len(alerts) == 2
    assert alerts[0].alert_type == "modelscope_model_updated"
    assert alerts[1].alert_type == "modelscope_model_new"


def test_run_modelscope_models_job_returns_created_count(repo) -> None:
    from radar.jobs.modelscope_models import run_modelscope_models_job

    item = {"Id": 1, "Name": "deepseek-v1", "Path": "deepseek/deepseek-v1", "LastUpdatedTime": "2026-04-07T00:00:00Z", "Downloads": 10}

    class FakeAlertService:
        def process_modelscope_model(self, observation: dict) -> int:
            assert observation["canonical_name"] == "modelscope:deepseek/deepseek-v1"
            return 1

    created = run_modelscope_models_job(
        [item],
        repository=repo,
        alert_service=FakeAlertService(),
    )

    assert created == 1
