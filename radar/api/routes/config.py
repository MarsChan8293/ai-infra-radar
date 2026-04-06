"""Config reload API route."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/config", tags=["config"])


@router.post("/reload")
def reload_config(request: Request) -> dict:
    """Reload configuration from the path stored in ``app.state.config_path``.

    Returns 422 if no config path is configured or the config is invalid.
    On success, updates ``app.state.settings`` and returns a summary.
    """
    config_path = getattr(request.app.state, "config_path", None)
    if config_path is None:
        raise HTTPException(
            status_code=422,
            detail="no config path configured; set RADAR_CONFIG env var before starting",
        )

    from radar.core.config import load_settings

    try:
        settings = load_settings(config_path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    request.app.state.settings = settings
    return {"status": "reloaded", "timezone": settings.app.timezone}
