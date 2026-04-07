from __future__ import annotations

import httpx
import pytest
import respx


@respx.mock
def test_modelers_client_lists_models_for_organization() -> None:
    from radar.sources.modelers.client import ModelersClient

    payload = {
        "code": "",
        "msg": "",
        "data": {
            "total": 1,
            "models": [
                {
                    "id": "80838",
                    "owner": "MindSpore-Lab",
                    "name": "Qwen3-VL-30B-A3B-Instruct",
                    "created_at": 1759655730,
                    "updated_at": 1759662143,
                    "download_count": 3791,
                    "visibility": "public",
                }
            ],
        },
    }
    route = respx.get("https://modelers.cn/server/model").mock(
        return_value=httpx.Response(200, json=payload)
    )

    client = ModelersClient()
    items = client.list_models_for_organization("MindSpore-Lab")

    assert route.called
    assert items[0]["owner"] == "MindSpore-Lab"


@respx.mock
def test_modelers_client_raises_on_non_2xx_response() -> None:
    from radar.sources.modelers.client import ModelersClient

    request = httpx.Request("GET", "https://modelers.cn/server/model")
    respx.get("https://modelers.cn/server/model").mock(
        return_value=httpx.Response(503, request=request)
    )

    client = ModelersClient()

    with pytest.raises(httpx.HTTPStatusError):
        client.list_models_for_organization("MindSpore-Lab")


@respx.mock
def test_modelers_client_propagates_timeout_failure() -> None:
    from radar.sources.modelers.client import ModelersClient

    request = httpx.Request("GET", "https://modelers.cn/server/model")
    respx.get("https://modelers.cn/server/model").mock(
        side_effect=httpx.ReadTimeout("timed out", request=request)
    )

    client = ModelersClient()

    with pytest.raises(httpx.ReadTimeout):
        client.list_models_for_organization("MindSpore-Lab")


@respx.mock
def test_modelers_client_rejects_malformed_success_payload() -> None:
    from radar.sources.modelers.client import ModelersClient

    respx.get("https://modelers.cn/server/model").mock(
        return_value=httpx.Response(200, json={"code": "", "msg": "", "data": {}})
    )

    client = ModelersClient()

    with pytest.raises(ValueError):
        client.list_models_for_organization("MindSpore-Lab")


def test_build_modelers_observation_normalizes_core_fields() -> None:
    from radar.sources.modelers.pipeline import build_modelers_observation

    item = {
        "id": "80838",
        "owner": "MindSpore-Lab",
        "name": "Qwen3-VL-30B-A3B-Instruct",
        "created_at": 1759655730,
        "updated_at": 1759662143,
        "download_count": 3791,
        "visibility": "public",
    }
    observation = build_modelers_observation(item)

    assert observation["canonical_name"] == "modelers:MindSpore-Lab/Qwen3-VL-30B-A3B-Instruct"
    assert observation["display_name"] == "MindSpore-Lab/Qwen3-VL-30B-A3B-Instruct"
    assert observation["url"] == "https://modelers.cn/models/MindSpore-Lab/Qwen3-VL-30B-A3B-Instruct"
    assert observation["normalized_payload"]["updated_at"] == 1759662143


def test_process_modelers_model_creates_new_model_alert(repo) -> None:
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.sources.modelers.pipeline import build_modelers_observation

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
    item = {
        "id": "80838",
        "owner": "MindSpore-Lab",
        "name": "Qwen3-VL-30B-A3B-Instruct",
        "created_at": 1759655730,
        "updated_at": 1759662143,
        "download_count": 3791,
        "visibility": "public",
    }
    observation = build_modelers_observation(item)

    created = service.process_modelers_model(observation)

    assert created == 1
    alerts = repo.list_alerts()
    assert len(alerts) == 1
    assert alerts[0].alert_type == "modelers_model_new"


def test_process_modelers_model_skips_unchanged_model(repo) -> None:
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.sources.modelers.pipeline import build_modelers_observation

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
    item = {
        "id": "80838",
        "owner": "MindSpore-Lab",
        "name": "Qwen3-VL-30B-A3B-Instruct",
        "created_at": 1759655730,
        "updated_at": 1759662143,
        "download_count": 3791,
        "visibility": "public",
    }
    observation = build_modelers_observation(item)

    first = service.process_modelers_model(observation)
    second = service.process_modelers_model(observation)

    assert first == 1
    assert second == 0
    assert len(repo.list_alerts()) == 1


def test_process_modelers_model_emits_updated_model_alert(repo) -> None:
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.sources.modelers.pipeline import build_modelers_observation

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
    item = {
        "id": "80838",
        "owner": "MindSpore-Lab",
        "name": "Qwen3-VL-30B-A3B-Instruct",
        "created_at": 1759655730,
        "updated_at": 1759662143,
        "download_count": 3791,
        "visibility": "public",
    }
    updated_item = {**item, "updated_at": 1759669999}

    first = service.process_modelers_model(build_modelers_observation(item))
    second = service.process_modelers_model(build_modelers_observation(updated_item))

    assert first == 1
    assert second == 1
    alerts = repo.list_alerts()
    assert len(alerts) == 2
    assert alerts[0].alert_type == "modelers_model_updated"
    assert alerts[1].alert_type == "modelers_model_new"


def test_run_modelers_models_job_returns_created_count(repo) -> None:
    from radar.jobs.modelers_models import run_modelers_models_job

    item = {
        "id": "80838",
        "owner": "MindSpore-Lab",
        "name": "Qwen3-VL-30B-A3B-Instruct",
        "created_at": 1759655730,
        "updated_at": 1759662143,
        "download_count": 3791,
        "visibility": "public",
    }

    class FakeAlertService:
        def process_modelers_model(self, observation: dict) -> int:
            assert observation["canonical_name"] == "modelers:MindSpore-Lab/Qwen3-VL-30B-A3B-Instruct"
            return 1

    created = run_modelers_models_job(
        [item],
        alert_service=FakeAlertService(),
    )

    assert created == 1
