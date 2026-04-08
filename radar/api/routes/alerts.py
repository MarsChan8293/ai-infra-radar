"""Alert history API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _alert_to_dict(alert) -> dict:
    return {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "entity_id": alert.entity_id,
        "source": alert.source,
        "score": alert.score,
        "dedupe_key": alert.dedupe_key,
        "reason": alert.reason,
        "created_at": alert.created_at.isoformat(),
        "status": alert.status,
    }


@router.get("")
def list_alerts(request: Request) -> dict:
    repo = request.app.state.repo
    if repo is None:
        return {"alerts": []}
    return {"alerts": [_alert_to_dict(a) for a in repo.list_alerts()]}


@router.get("/{alert_id}")
def get_alert(alert_id: int, request: Request) -> dict:
    repo = request.app.state.repo
    if repo is None:
        raise HTTPException(status_code=404, detail="alert not found")
    alert = repo.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return _alert_to_dict(alert)
