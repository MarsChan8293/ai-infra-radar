from fastapi import FastAPI

from radar.api.routes.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Infra Radar")
    app.include_router(health_router)
    return app
