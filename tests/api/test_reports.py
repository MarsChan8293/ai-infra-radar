"""API tests for grouped daily report browsing."""
from __future__ import annotations

from fastapi.testclient import TestClient

from radar.app import create_app
from radar.core.repositories import RadarRepository


def _make_client(repo: RadarRepository) -> TestClient:
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.settings = None
    app.state.config_path = None
    return TestClient(app)


def test_reports_manifest_groups_alert_days(repo: RadarRepository) -> None:
    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="github:acme/tool",
        display_name="acme/tool",
        url="https://github.com/acme/tool",
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.9,
        dedupe_key="github:burst:1",
        reason={"full_name": "acme/tool"},
    )

    client = _make_client(repo)

    response = client.get("/reports/manifest")

    assert response.status_code == 200
    body = response.json()
    assert body["dates"][0]["date"]
    assert body["dates"][0]["count"] == 1
    assert "github" in body["dates"][0]["topics"]


def test_reports_date_endpoint_returns_summary_and_events(repo: RadarRepository) -> None:
    entity = repo.upsert_entity(
        source="modelscope",
        entity_type="model",
        canonical_name="modelscope:Qwen/Qwen3",
        display_name="Qwen/Qwen3",
        url="https://www.modelscope.cn/models/Qwen/Qwen3",
    )
    repo.create_alert(
        alert_type="modelscope_model_new",
        entity_id=entity.id,
        source="modelscope",
        score=1.0,
        dedupe_key="modelscope:new:Qwen/Qwen3",
        reason={"model_id": "Qwen/Qwen3"},
    )

    client = _make_client(repo)
    manifest = client.get("/reports/manifest").json()
    date_str = manifest["dates"][0]["date"]

    response = client.get(f"/reports/{date_str}")

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == date_str
    assert body["summary"]["total_alerts"] == 1
    assert body["summary"]["top_sources"][0]["source"] == "modelscope"
    assert body["topics"][0]["topic"] == "modelscope"
    assert body["topics"][0]["events"][0]["display_name"] == "Qwen/Qwen3"
