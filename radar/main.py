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

from radar.app import apply_runtime, build_runtime, create_app, shutdown_runtime


@asynccontextmanager
async def _lifespan(app: FastAPI):
    config_path_str = os.environ.get("RADAR_CONFIG")
    if config_path_str:
        apply_runtime(app, build_runtime(Path(config_path_str)))
    yield
    shutdown_runtime(app)


app = create_app(lifespan=_lifespan)
