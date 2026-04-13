"""API tests for POST /config/reload."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from radar.app import create_app


def _make_client(config_path: Path | None = None) -> TestClient:
    app = create_app()
    app.state.repo = None
    app.state.scheduler = None
    app.state.settings = None
    app.state.config_path = config_path
    return TestClient(app)


def _minimal_config(storage_path: str) -> dict:
    return {
        "app": {"timezone": "UTC"},
        "storage": {"path": storage_path},
        "channels": {
            "webhook": {"enabled": False},
            "email": {"enabled": False},
        },
        "sources": {
            "github": {"enabled": False},
            "official_pages": {"enabled": False},
            "huggingface": {"enabled": False},
            "modelscope": {"enabled": False},
            "modelers": {"enabled": False},
            "gitcode": {"enabled": False},
        },
    }


def test_reload_no_config_path_returns_422() -> None:
    client = _make_client(config_path=None)
    resp = client.post("/config/reload")
    assert resp.status_code == 422


def test_reload_with_valid_config(tmp_path: Path) -> None:
    config_path = tmp_path / "radar.yaml"
    config_path.write_text(yaml.dump(_minimal_config(str(tmp_path / "radar.db"))))

    client = _make_client(config_path=config_path)
    resp = client.post("/config/reload")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "reloaded"
    assert body["timezone"] == "UTC"
    assert body["jobs"] == ["daily_digest"]


def test_reload_updates_app_state(tmp_path: Path) -> None:
    config_path = tmp_path / "radar.yaml"
    config_path.write_text(yaml.dump(_minimal_config(str(tmp_path / "radar.db"))))

    app = create_app()
    app.state.repo = None
    app.state.scheduler = None
    app.state.settings = None
    app.state.config_path = config_path

    with TestClient(app) as client:
        assert app.state.settings is None
        client.post("/config/reload")
        assert app.state.settings is not None
        assert app.state.settings.app.timezone == "UTC"
        assert app.state.repo is not None
        assert app.state.scheduler is not None


def test_reload_rebuilds_runtime_with_new_jobs(tmp_path: Path) -> None:
    config_path = tmp_path / "radar.yaml"
    config_path.write_text(yaml.dump(_minimal_config(str(tmp_path / "radar.db"))))

    app = create_app()
    app.state.config_path = config_path

    with TestClient(app) as client:
        first = client.post("/config/reload")
        assert first.status_code == 200
        first_repo = app.state.repo

        config_path.write_text(
            yaml.dump(
                {
                    "app": {"timezone": "Asia/Singapore"},
                    "storage": {"path": str(tmp_path / "radar-updated.db")},
                    "channels": {
                        "webhook": {"enabled": False},
                        "email": {"enabled": False},
                    },
                    "sources": {
                        "github": {
                            "enabled": True,
                            "token": "ghp_example",
                            "queries": ["sglang"],
                        },
                        "official_pages": {
                            "enabled": True,
                            "pages": [
                                {
                                    "url": "https://api-docs.deepseek.com/",
                                    "whitelist_keywords": ["release"],
                                }
                            ],
                        },
                        "huggingface": {"enabled": False},
                        "modelscope": {"enabled": False},
                        "modelers": {"enabled": False},
                    },
                }
            )
        )

        second = client.post("/config/reload")
        assert second.status_code == 200
        assert app.state.repo is not None
        assert app.state.repo is not first_repo
        assert app.state.settings.app.timezone == "Asia/Singapore"
        assert set(app.state.scheduler.known_jobs()) == {"official_pages", "github_burst", "daily_digest"}


def test_reload_registers_huggingface_job_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["huggingface"] = {
        "enabled": True,
        "organizations": ["deepseek"],
    }
    config["sources"]["modelscope"] = {"enabled": False}
    config_path.write_text(yaml.dump(config))

    app = create_app()
    app.state.config_path = config_path

    with TestClient(app) as client:
        resp = client.post("/config/reload")
        assert resp.status_code == 200
        assert set(app.state.scheduler.known_jobs()) == {"daily_digest", "huggingface_models"}


def test_reload_registers_modelscope_job_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["modelscope"] = {
        "enabled": True,
        "organizations": ["Qwen"],
    }
    config_path.write_text(yaml.dump(config))

    app = create_app()
    app.state.config_path = config_path

    with TestClient(app) as client:
        resp = client.post("/config/reload")
        assert resp.status_code == 200
        assert set(app.state.scheduler.known_jobs()) == {"daily_digest", "modelscope_models"}


def test_reload_registers_modelers_job_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["modelers"] = {
        "enabled": True,
        "organizations": ["MindSpore-Lab"],
    }
    config_path.write_text(yaml.dump(config))

    app = create_app()
    app.state.config_path = config_path

    with TestClient(app) as client:
        resp = client.post("/config/reload")
        assert resp.status_code == 200
        assert set(app.state.scheduler.known_jobs()) == {"daily_digest", "modelers_models"}


def test_reload_registers_gitcode_job_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["gitcode"] = {
        "enabled": True,
        "token": "gitcode-token",
        "organizations": ["gitcode"],
    }
    config_path.write_text(yaml.dump(config))

    app = create_app()
    app.state.config_path = config_path

    with TestClient(app) as client:
        resp = client.post("/config/reload")
        assert resp.status_code == 200
        assert set(app.state.scheduler.known_jobs()) == {"daily_digest", "gitcode_repos"}


def test_github_job_filters_repositories_by_readme_keywords(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["github"] = {
        "enabled": True,
        "token": "ghp_example",
        "queries": ["kv cache"],
        "burst_threshold": 0.0,
        "readme_filter": {
            "enabled": True,
            "require_any": ["citation", "bibtex"],
        },
    }
    config_path.write_text(yaml.dump(config))

    class FakeGitHubClient:
        def __init__(self, token: str | None = None) -> None:
            self.token = token

        def search_repositories(self, query: str) -> list[dict]:
            return [
                {
                    "full_name": "acme/index-cache",
                    "html_url": "https://github.com/acme/index-cache",
                    "stargazers_count": 42,
                    "forks_count": 8,
                    "pushed_at": "2026-04-08T00:00:00Z",
                },
                {
                    "full_name": "acme/notes",
                    "html_url": "https://github.com/acme/notes",
                    "stargazers_count": 40,
                    "forks_count": 7,
                    "pushed_at": "2026-04-08T00:00:00Z",
                },
            ]

        def fetch_readme_text(self, full_name: str) -> str | None:
            if full_name == "acme/index-cache":
                return "# Citation\n\n```bibtex\n@inproceedings{indexcache}\n```"
            if full_name == "acme/notes":
                return "# Overview\n\nInference notes only."
            raise AssertionError(f"unexpected repository: {full_name}")

    monkeypatch.setattr("radar.app.GitHubClient", FakeGitHubClient)

    from radar.app import build_runtime

    runtime = build_runtime(config_path)
    try:
        runtime.scheduler.run("github_burst")
        alerts = runtime.repo.list_alerts()
        assert len(alerts) == 1
        assert alerts[0].reason["full_name"] == "acme/index-cache"
    finally:
        runtime.engine.dispose()


def test_github_job_runs_ai_second_pass_after_keyword_prefilter_and_alerts_only_kept_repositories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["github"] = {
        "enabled": True,
        "token": "ghp_example",
        "queries": ["kv cache"],
        "burst_threshold": 0.0,
        "readme_filter": {
            "enabled": True,
            "require_any": ["citation"],
        },
        "ai_readme_filter": {
            "enabled": True,
            "model": "gpt-test",
            "default_prompt": "Keep only README files that are relevant to inference systems.",
        },
    }
    config["summarization"] = {
        "enabled": False,
        "base_url": "https://llm.example.com/v1",
        "api_key": "test-key",
    }
    config_path.write_text(yaml.dump(config))

    call_log: list[str] = []
    ai_calls: list[str] = []

    class FakeGitHubClient:
        def __init__(self, token: str | None = None) -> None:
            self.token = token

        def search_repositories(self, query: str) -> list[dict]:
            call_log.append(f"search:{query}")
            return [
                {
                    "full_name": "acme/keep-repo",
                    "html_url": "https://github.com/acme/keep-repo",
                    "stargazers_count": 42,
                    "forks_count": 8,
                    "pushed_at": "2026-04-08T00:00:00Z",
                },
                {
                    "full_name": "acme/drop-repo",
                    "html_url": "https://github.com/acme/drop-repo",
                    "stargazers_count": 40,
                    "forks_count": 7,
                    "pushed_at": "2026-04-08T00:00:00Z",
                },
                {
                    "full_name": "acme/no-keyword",
                    "html_url": "https://github.com/acme/no-keyword",
                    "stargazers_count": 39,
                    "forks_count": 6,
                    "pushed_at": "2026-04-08T00:00:00Z",
                },
                {
                    "full_name": "acme/no-readme",
                    "html_url": "https://github.com/acme/no-readme",
                    "stargazers_count": 38,
                    "forks_count": 5,
                    "pushed_at": "2026-04-08T00:00:00Z",
                },
            ]

        def fetch_readme_text(self, full_name: str) -> str | None:
            call_log.append(f"fetch:{full_name}")
            if full_name == "acme/keep-repo":
                return "# Citation\n\nInference serving for KV cache."
            if full_name == "acme/drop-repo":
                return "# Citation\n\nTraining orchestration only."
            if full_name == "acme/no-keyword":
                return "# Overview\n\nInference notes only."
            if full_name == "acme/no-readme":
                return None
            raise AssertionError(f"unexpected repository: {full_name}")

    class FakeReadmeAIFilter:
        def __init__(self, **_: object) -> None:
            pass

        def evaluate(
            self,
            *,
            repository: dict,
            readme_text: str,
            prompt: str,
        ) -> dict:
            ai_calls.append(repository["full_name"])
            call_log.append(f"ai:{repository['full_name']}")
            assert prompt == config["sources"]["github"]["ai_readme_filter"]["default_prompt"]
            if repository["full_name"] == "acme/keep-repo":
                assert "Inference serving" in readme_text
                return {
                    "keep": True,
                    "reason_zh": "README 明确提到推理服务。",
                    "matched_signals": ["inference serving"],
                }
            if repository["full_name"] == "acme/drop-repo":
                return {
                    "keep": False,
                    "reason_zh": "README 主要是训练编排。",
                    "matched_signals": ["training orchestration"],
                }
            raise AssertionError(f"unexpected AI evaluation target: {repository['full_name']}")

        def close(self) -> None:
            return None

    monkeypatch.setattr("radar.app.GitHubClient", FakeGitHubClient)
    monkeypatch.setattr("radar.app.OpenAIGitHubReadmeAIFilter", FakeReadmeAIFilter)

    from radar.app import build_runtime

    runtime = build_runtime(config_path)
    try:
        runtime.scheduler.run("github_burst")
        alerts = runtime.repo.list_alerts()
        assert len(alerts) == 1
        assert alerts[0].reason["full_name"] == "acme/keep-repo"
        assert ai_calls == ["acme/keep-repo", "acme/drop-repo"]
        assert call_log == [
            "search:kv cache",
            "fetch:acme/keep-repo",
            "fetch:acme/drop-repo",
            "fetch:acme/no-keyword",
            "fetch:acme/no-readme",
            "ai:acme/keep-repo",
            "ai:acme/drop-repo",
        ]
    finally:
        runtime.engine.dispose()


def test_github_job_raises_when_ai_second_pass_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["github"] = {
        "enabled": True,
        "token": "ghp_example",
        "queries": ["kv cache"],
        "burst_threshold": 0.0,
        "readme_filter": {
            "enabled": True,
            "require_any": ["citation"],
        },
        "ai_readme_filter": {
            "enabled": True,
            "model": "gpt-test",
            "default_prompt": "Keep only README files that are relevant to inference systems.",
        },
    }
    config["summarization"] = {
        "enabled": False,
        "base_url": "https://llm.example.com/v1",
        "api_key": "test-key",
    }
    config_path.write_text(yaml.dump(config))

    class FakeGitHubClient:
        def __init__(self, token: str | None = None) -> None:
            self.token = token

        def search_repositories(self, query: str) -> list[dict]:
            return [
                {
                    "full_name": "acme/keep-repo",
                    "html_url": "https://github.com/acme/keep-repo",
                    "stargazers_count": 42,
                    "forks_count": 8,
                    "pushed_at": "2026-04-08T00:00:00Z",
                }
            ]

        def fetch_readme_text(self, full_name: str) -> str | None:
            assert full_name == "acme/keep-repo"
            return "# Citation\n\nInference serving for KV cache."

    class FakeReadmeAIFilter:
        def __init__(self, **_: object) -> None:
            pass

        def evaluate(
            self,
            *,
            repository: dict,
            readme_text: str,
            prompt: str,
        ) -> dict:
            raise RuntimeError(f"AI second-pass boom for {repository['full_name']}")

        def close(self) -> None:
            return None

    monkeypatch.setattr("radar.app.GitHubClient", FakeGitHubClient)
    monkeypatch.setattr("radar.app.OpenAIGitHubReadmeAIFilter", FakeReadmeAIFilter)

    from radar.app import build_runtime

    runtime = build_runtime(config_path)
    try:
        with pytest.raises(RuntimeError, match="AI second-pass boom for acme/keep-repo"):
            runtime.scheduler.run("github_burst")
        assert runtime.repo.list_alerts() == []
    finally:
        runtime.engine.dispose()


def test_github_job_expands_relative_date_placeholders(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["github"] = {
        "enabled": True,
        "token": "ghp_example",
        "queries": ['created:>@today-7d "kv cache"'],
        "burst_threshold": 1.1,
    }
    config_path.write_text(yaml.dump(config))
    captured_queries: list[str] = []

    class FakeGitHubClient:
        def __init__(self, token: str | None = None) -> None:
            self.token = token

        def search_repositories(self, query: str) -> list[dict]:
            captured_queries.append(query)
            return []

    monkeypatch.setattr("radar.app.GitHubClient", FakeGitHubClient)

    from radar.app import build_runtime

    runtime = build_runtime(config_path)
    try:
        runtime.scheduler.run("github_burst")
        assert len(captured_queries) == 1
        assert captured_queries[0].startswith("created:>20")
        assert "@today" not in captured_queries[0]
    finally:
        runtime.engine.dispose()


def test_huggingface_job_continues_after_organization_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["huggingface"] = {
        "enabled": True,
        "organizations": ["broken-org", "deepseek"],
    }
    config["sources"]["modelscope"] = {"enabled": False}
    config_path.write_text(yaml.dump(config))

    item = {
        "id": "deepseek/deepseek-v3",
        "lastModified": "2026-04-07T00:00:00Z",
        "downloads": 123,
        "likes": 9,
        "pipeline_tag": "text-generation",
    }

    class FakeHuggingFaceClient:
        def list_models_for_organization(self, organization: str) -> list[dict]:
            if organization == "broken-org":
                raise RuntimeError("boom")
            if organization == "deepseek":
                return [item]
            raise AssertionError(f"unexpected organization: {organization}")

    monkeypatch.setattr("radar.app.HuggingFaceClient", FakeHuggingFaceClient)

    from radar.app import build_runtime

    runtime = build_runtime(config_path)
    try:
        with pytest.raises(RuntimeError, match="broken-org"):
            runtime.scheduler.run("huggingface_models")
        alerts = runtime.repo.list_alerts()
        assert len(alerts) == 1
        assert alerts[0].alert_type == "huggingface_model_new"
    finally:
        runtime.engine.dispose()


def test_modelscope_job_continues_after_organization_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["modelscope"] = {
        "enabled": True,
        "organizations": ["broken-org", "Qwen"],
    }
    config_path.write_text(yaml.dump(config))

    item = {
        "Id": 665336,
        "Name": "Qwen3.5-397B-A17B",
        "Path": "Qwen",
        "CreatedTime": 1771213910,
        "LastUpdatedTime": 1772414875,
        "Downloads": 98560,
    }

    class FakeModelScopeClient:
        def list_models_for_organization(self, organization: str) -> list[dict]:
            if organization == "broken-org":
                raise RuntimeError("boom")
            if organization == "Qwen":
                return [item]
            raise AssertionError(f"unexpected organization: {organization}")

    monkeypatch.setattr("radar.app.ModelScopeClient", FakeModelScopeClient)

    from radar.app import build_runtime

    runtime = build_runtime(config_path)
    try:
        with pytest.raises(RuntimeError, match="broken-org"):
            runtime.scheduler.run("modelscope_models")
        alerts = runtime.repo.list_alerts()
        assert len(alerts) == 1
        assert alerts[0].alert_type == "modelscope_model_new"
    finally:
        runtime.engine.dispose()


def test_modelers_job_continues_after_organization_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["modelers"] = {
        "enabled": True,
        "organizations": ["broken-org", "MindSpore-Lab"],
    }
    config_path.write_text(yaml.dump(config))

    item = {
        "id": "80838",
        "owner": "MindSpore-Lab",
        "name": "Qwen3-VL-30B-A3B-Instruct",
        "created_at": 1759655730,
        "updated_at": 1759662143,
        "download_count": 3791,
        "visibility": "public",
    }

    class FakeModelersClient:
        def list_models_for_organization(self, organization: str) -> list[dict]:
            if organization == "broken-org":
                raise RuntimeError("boom")
            if organization == "MindSpore-Lab":
                return [item]
            raise AssertionError(f"unexpected organization: {organization}")

    monkeypatch.setattr("radar.app.ModelersClient", FakeModelersClient)

    from radar.app import build_runtime

    runtime = build_runtime(config_path)
    try:
        with pytest.raises(RuntimeError, match="broken-org"):
            runtime.scheduler.run("modelers_models")
        alerts = runtime.repo.list_alerts()
        assert len(alerts) == 1
        assert alerts[0].alert_type == "modelers_model_new"
    finally:
        runtime.engine.dispose()


def test_gitcode_job_continues_after_organization_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["gitcode"] = {
        "enabled": True,
        "token": "gitcode-token",
        "organizations": ["broken-org", "gitcode"],
    }
    config_path.write_text(yaml.dump(config))

    item = {
        "full_name": "gitcode/example-repo",
        "name": "example-repo",
        "html_url": "https://gitcode.com/gitcode/example-repo",
        "updated_at": "2026-04-07T00:00:00Z",
    }

    class FakeGitCodeClient:
        def __init__(self, token: str) -> None:
            assert token == "gitcode-token"

        def list_repositories_for_organization(self, organization: str) -> list[dict]:
            if organization == "broken-org":
                raise RuntimeError("boom")
            if organization == "gitcode":
                return [item]
            raise AssertionError(f"unexpected organization: {organization}")

    monkeypatch.setattr("radar.app.GitCodeClient", FakeGitCodeClient)

    from radar.app import build_runtime

    runtime = build_runtime(config_path)
    try:
        with pytest.raises(RuntimeError, match="broken-org"):
            runtime.scheduler.run("gitcode_repos")
        alerts = runtime.repo.list_alerts()
        assert len(alerts) == 1
        assert alerts[0].alert_type == "gitcode_repository_new"
    finally:
        runtime.engine.dispose()


def test_huggingface_job_continues_after_processing_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["huggingface"] = {
        "enabled": True,
        "organizations": ["broken-org", "deepseek"],
    }
    config_path.write_text(yaml.dump(config))

    broken_item = {
        "id": "broken-org/bad-model",
        "lastModified": "2026-04-07T00:00:00Z",
        "downloads": 1,
        "likes": 1,
        "pipeline_tag": "text-generation",
    }
    good_item = {
        "id": "deepseek/deepseek-v3",
        "lastModified": "2026-04-07T00:00:00Z",
        "downloads": 123,
        "likes": 9,
        "pipeline_tag": "text-generation",
    }

    class FakeHuggingFaceClient:
        def list_models_for_organization(self, organization: str) -> list[dict]:
            if organization == "broken-org":
                return [broken_item]
            if organization == "deepseek":
                return [good_item]
            raise AssertionError(f"unexpected organization: {organization}")

    original = create_app.__globals__["AlertService"].process_huggingface_model

    def flaky_process(self, observation: dict) -> int:
        if observation["normalized_payload"]["organization"] == "broken-org":
            raise RuntimeError("processing boom")
        return original(self, observation)

    monkeypatch.setattr("radar.app.HuggingFaceClient", FakeHuggingFaceClient)
    monkeypatch.setattr("radar.app.AlertService.process_huggingface_model", flaky_process)

    from radar.app import build_runtime

    runtime = build_runtime(config_path)
    try:
        with pytest.raises(RuntimeError, match="broken-org"):
            runtime.scheduler.run("huggingface_models")
        alerts = runtime.repo.list_alerts()
        assert len(alerts) == 1
        assert alerts[0].alert_type == "huggingface_model_new"
    finally:
        runtime.engine.dispose()


def test_modelscope_job_continues_after_processing_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["modelscope"] = {
        "enabled": True,
        "organizations": ["broken-org", "Qwen"],
    }
    config_path.write_text(yaml.dump(config))

    broken_item = {
        "Id": 1,
        "Name": "bad-model",
        "Path": "broken-org",
        "CreatedTime": 1771213910,
        "LastUpdatedTime": 1772414875,
        "Downloads": 1,
    }
    good_item = {
        "Id": 665336,
        "Name": "Qwen3.5-397B-A17B",
        "Path": "Qwen",
        "CreatedTime": 1771213910,
        "LastUpdatedTime": 1772414875,
        "Downloads": 98560,
    }

    class FakeModelScopeClient:
        def list_models_for_organization(self, organization: str) -> list[dict]:
            if organization == "broken-org":
                return [broken_item]
            if organization == "Qwen":
                return [good_item]
            raise AssertionError(f"unexpected organization: {organization}")

    original = create_app.__globals__["AlertService"].process_modelscope_model

    def flaky_process(self, observation: dict) -> int:
        if observation["normalized_payload"]["organization"] == "broken-org":
            raise RuntimeError("processing boom")
        return original(self, observation)

    monkeypatch.setattr("radar.app.ModelScopeClient", FakeModelScopeClient)
    monkeypatch.setattr("radar.app.AlertService.process_modelscope_model", flaky_process)

    from radar.app import build_runtime

    runtime = build_runtime(config_path)
    try:
        with pytest.raises(RuntimeError, match="broken-org"):
            runtime.scheduler.run("modelscope_models")
        alerts = runtime.repo.list_alerts()
        assert len(alerts) == 1
        assert alerts[0].alert_type == "modelscope_model_new"
    finally:
        runtime.engine.dispose()


def test_modelers_job_continues_after_processing_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["modelers"] = {
        "enabled": True,
        "organizations": ["broken-org", "MindSpore-Lab"],
    }
    config_path.write_text(yaml.dump(config))

    broken_item = {
        "id": "1",
        "owner": "broken-org",
        "name": "bad-model",
        "created_at": 1759655730,
        "updated_at": 1759662143,
        "download_count": 1,
        "visibility": "public",
    }
    good_item = {
        "id": "80838",
        "owner": "MindSpore-Lab",
        "name": "Qwen3-VL-30B-A3B-Instruct",
        "created_at": 1759655730,
        "updated_at": 1759662143,
        "download_count": 3791,
        "visibility": "public",
    }

    class FakeModelersClient:
        def list_models_for_organization(self, organization: str) -> list[dict]:
            if organization == "broken-org":
                return [broken_item]
            if organization == "MindSpore-Lab":
                return [good_item]
            raise AssertionError(f"unexpected organization: {organization}")

    original = create_app.__globals__["AlertService"].process_modelers_model

    def flaky_process(self, observation: dict) -> int:
        if observation["normalized_payload"]["organization"] == "broken-org":
            raise RuntimeError("processing boom")
        return original(self, observation)

    monkeypatch.setattr("radar.app.ModelersClient", FakeModelersClient)
    monkeypatch.setattr("radar.app.AlertService.process_modelers_model", flaky_process)

    from radar.app import build_runtime

    runtime = build_runtime(config_path)
    try:
        with pytest.raises(RuntimeError, match="broken-org"):
            runtime.scheduler.run("modelers_models")
        alerts = runtime.repo.list_alerts()
        assert len(alerts) == 1
        assert alerts[0].alert_type == "modelers_model_new"
    finally:
        runtime.engine.dispose()


def test_gitcode_job_continues_after_processing_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "radar.yaml"
    config = _minimal_config(str(tmp_path / "radar.db"))
    config["sources"]["gitcode"] = {
        "enabled": True,
        "token": "gitcode-token",
        "organizations": ["broken-org", "gitcode"],
    }
    config_path.write_text(yaml.dump(config))

    broken_item = {
        "full_name": "broken-org/bad-repo",
        "name": "bad-repo",
        "html_url": "https://gitcode.com/broken-org/bad-repo",
        "updated_at": "2026-04-07T00:00:00Z",
    }
    good_item = {
        "full_name": "gitcode/example-repo",
        "name": "example-repo",
        "html_url": "https://gitcode.com/gitcode/example-repo",
        "updated_at": "2026-04-07T00:00:00Z",
    }

    class FakeGitCodeClient:
        def __init__(self, token: str) -> None:
            assert token == "gitcode-token"

        def list_repositories_for_organization(self, organization: str) -> list[dict]:
            if organization == "broken-org":
                return [broken_item]
            if organization == "gitcode":
                return [good_item]
            raise AssertionError(f"unexpected organization: {organization}")

    original = create_app.__globals__["AlertService"].process_gitcode_repository

    def flaky_process(self, observation: dict) -> int:
        if observation["normalized_payload"]["full_name"].startswith("broken-org/"):
            raise RuntimeError("processing boom")
        return original(self, observation)

    monkeypatch.setattr("radar.app.GitCodeClient", FakeGitCodeClient)
    monkeypatch.setattr("radar.app.AlertService.process_gitcode_repository", flaky_process)

    from radar.app import build_runtime

    runtime = build_runtime(config_path)
    try:
        with pytest.raises(RuntimeError, match="broken-org"):
            runtime.scheduler.run("gitcode_repos")
        alerts = runtime.repo.list_alerts()
        assert len(alerts) == 1
        assert alerts[0].alert_type == "gitcode_repository_new"
    finally:
        runtime.engine.dispose()


def test_reload_with_invalid_config_returns_422(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("not_a_valid_radar_config: true\n")

    client = _make_client(config_path=config_path)
    resp = client.post("/config/reload")

    assert resp.status_code == 422


def test_reload_with_missing_file_returns_422(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.yaml"

    client = _make_client(config_path=missing)
    resp = client.post("/config/reload")

    assert resp.status_code == 422
