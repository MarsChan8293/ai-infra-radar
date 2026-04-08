from fastapi.testclient import TestClient
from pathlib import Path

from radar.app import create_app


def test_home_route_returns_html_shell() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "AI Infra Radar" in response.text
    assert "Radar Results" in response.text


def test_home_static_assets_are_served() -> None:
    client = TestClient(create_app())

    styles = client.get("/static/results/styles.css")
    script = client.get("/static/results/app.js")

    assert styles.status_code == 200
    assert styles.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert 'fetchJson("/reports/manifest")' in script.text


def test_home_shell_contains_results_browser_regions() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="date-list"' in response.text
    assert 'id="topic-list"' in response.text
    assert 'id="report-summary"' in response.text
    assert 'id="report-events"' in response.text


def test_home_script_contains_report_api_wiring() -> None:
    client = TestClient(create_app())

    response = client.get("/static/results/app.js")

    assert response.status_code == 200
    assert 'fetchJson("/reports/manifest")' in response.text
    assert 'fetchJson(`/reports/${date}`)' in response.text
    assert "renderManifest" in response.text
    assert "renderReport" in response.text


def test_ops_route_returns_html_shell() -> None:
    client = TestClient(create_app())

    response = client.get("/ops")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "AI Infra Radar Operations UI" in response.text


def test_ops_static_assets_are_served() -> None:
    client = TestClient(create_app())

    styles = client.get("/static/ops/styles.css")
    script = client.get("/static/ops/app.js")

    assert styles.status_code == 200
    assert styles.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert 'fetchJson("/alerts")' in script.text


def test_ops_shell_contains_alerts_jobs_and_runtime_controls() -> None:
    client = TestClient(create_app())

    response = client.get("/ops")

    assert response.status_code == 200
    assert 'data-panel="alerts"' in response.text
    assert 'id="alerts-list"' in response.text
    assert 'id="alert-detail"' in response.text
    assert 'id="jobs-list"' in response.text
    assert 'id="reload-config"' in response.text


def test_ops_script_contains_jobs_and_reload_api_wiring() -> None:
    client = TestClient(create_app())

    response = client.get("/static/ops/app.js")

    assert response.status_code == 200
    assert 'fetchJson("/jobs")' in response.text
    assert 'fetchJson(`/jobs/run/${jobName}`' in response.text
    assert 'fetchJson("/config/reload"' in response.text
    assert "renderJobs" in response.text


def test_ui_route_is_removed() -> None:
    client = TestClient(create_app())

    response = client.get("/ui")

    assert response.status_code == 404


def test_readme_mentions_homepage_and_ops_entrypoints() -> None:
    readme = Path("README.md").read_text()

    assert "/" in readme
    assert "/ops" in readme
