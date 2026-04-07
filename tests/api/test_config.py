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
