from fastapi.testclient import TestClient
from pathlib import Path

from radar.app import create_app


def test_ui_route_returns_html_shell() -> None:
    client = TestClient(create_app())

    response = client.get("/ui")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "AI Infra Radar Operations UI" in response.text


def test_ui_static_assets_are_served() -> None:
    client = TestClient(create_app())

    styles = client.get("/static/ui/styles.css")
    script = client.get("/static/ui/app.js")

    assert styles.status_code == 200
    assert styles.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert "fetch" in script.text


def test_ui_shell_contains_alerts_panel_hooks() -> None:
    client = TestClient(create_app())

    response = client.get("/ui")

    assert response.status_code == 200
    assert 'data-panel="alerts"' in response.text
    assert 'id="alerts-list"' in response.text
    assert 'id="alert-detail"' in response.text
    assert 'id="refresh-alerts"' in response.text


def test_ui_script_contains_alerts_api_wiring() -> None:
    client = TestClient(create_app())

    response = client.get("/static/ui/app.js")

    assert response.status_code == 200
    assert 'fetchJson("/alerts")' in response.text
    assert "loadAlertDetail" in response.text


def test_ui_shell_contains_job_controls() -> None:
    client = TestClient(create_app())

    response = client.get("/ui")

    assert response.status_code == 200
    assert 'id="jobs-list"' in response.text
    assert 'id="jobs-status"' in response.text


def test_ui_shell_contains_runtime_controls() -> None:
    client = TestClient(create_app())

    response = client.get("/ui")

    assert response.status_code == 200
    assert 'id="reload-config"' in response.text
    assert 'id="runtime-status"' in response.text
    assert 'id="jobs-status"' in response.text


def test_ui_script_contains_jobs_and_reload_api_wiring() -> None:
    client = TestClient(create_app())

    response = client.get("/static/ui/app.js")

    assert response.status_code == 200
    assert 'fetchJson("/jobs")' in response.text
    assert 'fetchJson(`/jobs/run/${jobName}`' in response.text
    assert 'fetchJson("/config/reload"' in response.text
    assert "renderJobs" in response.text


def test_ui_script_clears_stale_ui_state() -> None:
    client = TestClient(create_app())

    response = client.get("/static/ui/app.js")

    assert response.status_code == 200
    assert 'detail.textContent = "Select an alert to inspect its details."' in response.text
    assert 'result.textContent = "Config reload failed."' in response.text


def test_readme_mentions_ui_entrypoint() -> None:
    readme = Path("README.md").read_text()

    assert "/ui" in readme
    assert "Operations UI" in readme
