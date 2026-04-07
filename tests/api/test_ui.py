from fastapi.testclient import TestClient

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
