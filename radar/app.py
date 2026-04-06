from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from radar.api.routes.alerts import router as alerts_router
from radar.api.routes.config import router as config_router
from radar.api.routes.health import router as health_router
from radar.api.routes.jobs import router as jobs_router


def create_app(lifespan: Any = None) -> FastAPI:
    app = FastAPI(title="AI Infra Radar", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(alerts_router)
    app.include_router(jobs_router)
    app.include_router(config_router)
    # Initialise default state so routes never hit AttributeError
    app.state.repo = None
    app.state.scheduler = None
    app.state.settings = None
    app.state.config_path = None
    return app
