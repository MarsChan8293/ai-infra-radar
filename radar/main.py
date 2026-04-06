"""ASGI entry point for AI Infra Radar.

Reads RADAR_CONFIG env var to optionally wire DB, repository, and scheduler on
startup.  If the env var is absent the app starts without persistence – useful
for health checks and import-time test collection.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from radar.app import create_app


@asynccontextmanager
async def _lifespan(app: FastAPI):
    config_path_str = os.environ.get("RADAR_CONFIG")
    if config_path_str:
        _setup_from_config(app, Path(config_path_str))
    yield
    if app.state.scheduler is not None:
        app.state.scheduler.stop()


def _setup_from_config(app: FastAPI, path: Path) -> None:
    from radar.core.config import load_settings
    from radar.core.db import create_engine_and_session_factory, init_db
    from radar.core.repositories import RadarRepository
    from radar.core.scheduler import RadarScheduler

    settings = load_settings(path)
    engine, sf = create_engine_and_session_factory(settings.storage.path)
    init_db(engine)
    repo = RadarRepository(sf)
    scheduler = RadarScheduler()
    _register_jobs(scheduler, settings, repo)

    app.state.settings = settings
    app.state.config_path = path
    app.state.repo = repo
    app.state.scheduler = scheduler
    scheduler.start()


def _register_jobs(scheduler, settings, repo) -> None:
    """Wire APScheduler jobs based on enabled sources in *settings*."""
    if settings.sources.official_pages.enabled:
        import httpx

        from radar.jobs.official_pages import run_official_pages_job

        pages = settings.sources.official_pages.pages

        def _official_pages() -> None:
            def _fetch(url: str) -> str:
                return httpx.get(url, timeout=30).text

            for page in pages:
                run_official_pages_job(page, _fetch, repo, None)

        scheduler.register("official_pages", _official_pages, hours=1)

    if settings.sources.github.enabled:
        from radar.jobs.github_burst import run_github_burst_job

        threshold = settings.sources.github.burst_threshold

        def _github_burst() -> None:
            # Full client wiring is completed in Task 8; placeholder keeps
            # the job name discoverable and triggerable via the API/CLI.
            pass

        scheduler.register("github_burst", _github_burst, hours=1)


app = create_app(lifespan=_lifespan)
