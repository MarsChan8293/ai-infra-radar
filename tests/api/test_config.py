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
