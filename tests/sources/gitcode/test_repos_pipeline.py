from __future__ import annotations

import httpx
import pytest
import respx


@respx.mock
def test_gitcode_client_lists_org_repositories() -> None:
    from radar.sources.gitcode.client import GitCodeClient

    route = respx.get("https://api.gitcode.com/api/v5/orgs/gitcode/repos").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "full_name": "gitcode/example-repo",
                    "name": "example-repo",
                    "html_url": "https://gitcode.com/gitcode/example-repo",
                    "updated_at": "2026-04-07T00:00:00Z",
                }
            ],
        )
    )

    client = GitCodeClient(token="token")
    items = client.list_repositories_for_organization("gitcode")

    assert route.called
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer token"
    assert request.url.params["type"] == "public"
    assert request.url.params["page"] == "1"
    assert request.url.params["per_page"] == "100"
    assert items[0]["full_name"] == "gitcode/example-repo"


@respx.mock
def test_gitcode_client_raises_on_non_2xx_response() -> None:
    from radar.sources.gitcode.client import GitCodeClient

    request = httpx.Request("GET", "https://api.gitcode.com/api/v5/orgs/gitcode/repos")
    respx.get("https://api.gitcode.com/api/v5/orgs/gitcode/repos").mock(
        return_value=httpx.Response(403, request=request)
    )

    client = GitCodeClient(token="token")

    with pytest.raises(httpx.HTTPStatusError):
        client.list_repositories_for_organization("gitcode")


@respx.mock
def test_gitcode_client_propagates_timeout_failure() -> None:
    from radar.sources.gitcode.client import GitCodeClient

    request = httpx.Request("GET", "https://api.gitcode.com/api/v5/orgs/gitcode/repos")
    respx.get("https://api.gitcode.com/api/v5/orgs/gitcode/repos").mock(
        side_effect=httpx.ReadTimeout("timed out", request=request)
    )

    client = GitCodeClient(token="token")

    with pytest.raises(httpx.ReadTimeout):
        client.list_repositories_for_organization("gitcode")


def test_build_gitcode_observation_maps_fields() -> None:
    from radar.sources.gitcode.pipeline import build_gitcode_observation

    observation = build_gitcode_observation(
        {
            "full_name": "gitcode/example-repo",
            "name": "example-repo",
            "html_url": "https://gitcode.com/gitcode/example-repo",
            "updated_at": "2026-04-07T00:00:00Z",
        }
    )

    assert observation["canonical_name"] == "gitcode:gitcode/example-repo"
    assert observation["display_name"] == "gitcode/example-repo"
    assert observation["url"] == "https://gitcode.com/gitcode/example-repo"
    assert observation["normalized_payload"]["organization"] == "gitcode"
    assert observation["normalized_payload"]["repo_name"] == "example-repo"
    assert observation["normalized_payload"]["updated_at"] == "2026-04-07T00:00:00Z"


def test_process_gitcode_repository_creates_new_repository_alert(repo) -> None:
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.sources.gitcode.pipeline import build_gitcode_observation

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
    observation = build_gitcode_observation(
        {
            "full_name": "gitcode/example-repo",
            "name": "example-repo",
            "html_url": "https://gitcode.com/gitcode/example-repo",
            "updated_at": "2026-04-07T00:00:00Z",
        }
    )

    created = service.process_gitcode_repository(observation)

    assert created == 1
    alerts = repo.list_alerts()
    assert len(alerts) == 1
    assert alerts[0].alert_type == "gitcode_repository_new"


def test_process_gitcode_repository_skips_unchanged_repository(repo) -> None:
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.sources.gitcode.pipeline import build_gitcode_observation

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
    observation = build_gitcode_observation(
        {
            "full_name": "gitcode/example-repo",
            "name": "example-repo",
            "html_url": "https://gitcode.com/gitcode/example-repo",
            "updated_at": "2026-04-07T00:00:00Z",
        }
    )

    first = service.process_gitcode_repository(observation)
    second = service.process_gitcode_repository(observation)

    assert first == 1
    assert second == 0
    assert len(repo.list_alerts()) == 1


def test_process_gitcode_repository_emits_updated_repository_alert(repo) -> None:
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.sources.gitcode.pipeline import build_gitcode_observation

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
        "full_name": "gitcode/example-repo",
        "name": "example-repo",
        "html_url": "https://gitcode.com/gitcode/example-repo",
        "updated_at": "2026-04-07T00:00:00Z",
    }
    updated_item = {**item, "updated_at": "2026-04-08T00:00:00Z"}

    first = service.process_gitcode_repository(build_gitcode_observation(item))
    second = service.process_gitcode_repository(build_gitcode_observation(updated_item))

    assert first == 1
    assert second == 1
    alerts = repo.list_alerts()
    assert len(alerts) == 2
    assert alerts[0].alert_type == "gitcode_repository_updated"
    assert alerts[1].alert_type == "gitcode_repository_new"


def test_run_gitcode_repos_job_returns_created_count(repo) -> None:
    from radar.jobs.gitcode_repos import run_gitcode_repos_job

    item = {
        "full_name": "gitcode/example-repo",
        "name": "example-repo",
        "html_url": "https://gitcode.com/gitcode/example-repo",
        "updated_at": "2026-04-07T00:00:00Z",
    }

    class FakeAlertService:
        def process_gitcode_repository(self, observation: dict) -> int:
            assert observation["canonical_name"] == "gitcode:gitcode/example-repo"
            return 1

    created = run_gitcode_repos_job(
        [item],
        alert_service=FakeAlertService(),
    )

    assert created == 1
