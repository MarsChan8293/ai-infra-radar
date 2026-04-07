"""API tests for POST /jobs/run/{job_name}."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from radar.app import create_app


class _MockScheduler:
    """Test double that records which jobs were triggered."""

    def __init__(self, known: set[str] | None = None) -> None:
        self._known: set[str] = known if known is not None else {"github_burst", "official_pages"}
        self.triggered: list[str] = []

    def known_jobs(self) -> list[str]:
        return list(self._known)

    def trigger(self, job_name: str) -> bool:
        if job_name not in self._known:
            return False
        self.triggered.append(job_name)
        return True


def _make_client(scheduler: _MockScheduler | None = None) -> tuple[TestClient, _MockScheduler]:
    sched = scheduler if scheduler is not None else _MockScheduler()
    app = create_app()
    app.state.repo = None
    app.state.scheduler = sched
    app.state.settings = None
    app.state.config_path = None
    return TestClient(app), sched


def test_trigger_github_burst_returns_202() -> None:
    client, scheduler = _make_client()
    resp = client.post("/jobs/run/github_burst")
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["job_name"] == "github_burst"
    assert "github_burst" in scheduler.triggered


def test_trigger_official_pages_returns_202() -> None:
    client, scheduler = _make_client()
    resp = client.post("/jobs/run/official_pages")
    assert resp.status_code == 202
    assert "official_pages" in scheduler.triggered


def test_list_jobs_returns_known_jobs() -> None:
    client, _ = _make_client(_MockScheduler({"daily_digest", "github_burst"}))
    resp = client.get("/jobs")
    assert resp.status_code == 200
    assert sorted(resp.json()["jobs"]) == ["daily_digest", "github_burst"]


def test_trigger_unknown_job_returns_404() -> None:
    client, _ = _make_client()
    resp = client.post("/jobs/run/nonexistent_job")
    assert resp.status_code == 404
    assert "nonexistent_job" in resp.json()["detail"]


def test_trigger_job_no_scheduler_returns_404() -> None:
    """When scheduler is None (no config), all jobs are unknown."""
    app = create_app()
    app.state.repo = None
    app.state.scheduler = None
    app.state.settings = None
    app.state.config_path = None
    client = TestClient(app)
    resp = client.post("/jobs/run/github_burst")
    assert resp.status_code == 404


def test_list_jobs_no_scheduler_returns_empty_list() -> None:
    app = create_app()
    app.state.repo = None
    app.state.scheduler = None
    app.state.settings = None
    app.state.config_path = None
    client = TestClient(app)
    resp = client.get("/jobs")
    assert resp.status_code == 200
    assert resp.json() == {"jobs": []}
