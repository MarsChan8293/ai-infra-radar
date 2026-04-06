"""API tests for GET /alerts and GET /alerts/{id}."""
from __future__ import annotations

import pytest
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


@pytest.fixture()
def client(repo: RadarRepository) -> TestClient:
    return _make_client(repo)


def test_list_alerts_empty(client: TestClient) -> None:
    resp = client.get("/alerts")
    assert resp.status_code == 200
    assert resp.json() == {"alerts": []}


def test_list_alerts_contains_created_alert(
    client: TestClient, repo: RadarRepository
) -> None:
    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="org/repo",
        display_name="org/repo",
        url="https://github.com/org/repo",
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.9,
        dedupe_key="key-1",
        reason={"stars": 100},
    )
    resp = client.get("/alerts")
    assert resp.status_code == 200
    alerts = resp.json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "github_burst"
    assert alerts[0]["source"] == "github"
    assert alerts[0]["score"] == pytest.approx(0.9)


def test_list_alerts_multiple(client: TestClient, repo: RadarRepository) -> None:
    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="org/multi",
        display_name="org/multi",
        url="https://github.com/org/multi",
    )
    for i in range(3):
        repo.create_alert(
            alert_type="github_burst",
            entity_id=entity.id,
            source="github",
            score=0.7 + i * 0.05,
            dedupe_key=f"key-multi-{i}",
            reason={"stars": 100 + i},
        )
    resp = client.get("/alerts")
    assert resp.status_code == 200
    assert len(resp.json()["alerts"]) == 3


def test_get_alert_not_found(client: TestClient) -> None:
    resp = client.get("/alerts/99999")
    assert resp.status_code == 404


def test_get_alert_found(client: TestClient, repo: RadarRepository) -> None:
    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="org/repo2",
        display_name="org/repo2",
        url="https://github.com/org/repo2",
    )
    alert = repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.8,
        dedupe_key="key-2",
        reason={"stars": 50},
    )
    resp = client.get(f"/alerts/{alert.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == alert.id
    assert data["alert_type"] == "github_burst"
    assert data["score"] == pytest.approx(0.8)
    assert data["reason"] == {"stars": 50}
