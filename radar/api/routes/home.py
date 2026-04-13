from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["home"])
_RESULTS_UI_DIR = Path(__file__).resolve().parents[2] / "ui" / "results"


@router.get("/", include_in_schema=False)
def radar_home() -> FileResponse:
    return FileResponse(_RESULTS_UI_DIR / "index.html", media_type="text/html")
