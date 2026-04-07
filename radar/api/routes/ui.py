from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["ui"])
_UI_DIR = Path(__file__).resolve().parents[2] / "ui"


@router.get("/ui", include_in_schema=False)
def operations_ui() -> FileResponse:
    return FileResponse(_UI_DIR / "index.html", media_type="text/html")
