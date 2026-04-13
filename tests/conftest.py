"""Shared pytest fixtures for Task 5 alert tests."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from radar.alerts.dispatcher import AlertDispatcher
from radar.alerts.service import AlertService
from radar.core.db import create_engine_and_session_factory, init_db
from radar.core.repositories import RadarRepository


@pytest.fixture()
def repo(tmp_path: Path) -> RadarRepository:
    """In-memory-style repository backed by a temp SQLite file."""
    engine, sf = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    return RadarRepository(sf)


@pytest.fixture()
def noop_dispatcher(repo: RadarRepository) -> AlertDispatcher:
    """Dispatcher whose senders are no-ops (no network calls)."""
    return AlertDispatcher(
        repository=repo,
        send_webhook=lambda url, payload: None,
        send_email=lambda payload: None,
    )


@pytest.fixture()
def alert_service(repo: RadarRepository, noop_dispatcher: AlertDispatcher) -> AlertService:
    """AlertService wired with noop dispatcher and a webhook+email channel config."""
    return AlertService(
        repository=repo,
        dispatcher=noop_dispatcher,
        channels={"webhook": "https://hooks.example.com/test", "email": True},
    )
