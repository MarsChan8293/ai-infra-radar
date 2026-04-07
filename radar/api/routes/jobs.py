"""Job trigger API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(request: Request) -> dict:
    """Return currently registered job names."""
    scheduler = request.app.state.scheduler
    if scheduler is None:
        return {"jobs": []}
    return {"jobs": scheduler.known_jobs()}


@router.post("/run/{job_name}", status_code=202)
def trigger_job(job_name: str, request: Request) -> dict:
    """Trigger a named job immediately.

    Returns 202 Accepted if the job was dispatched.
    Returns 404 if the job name is unknown or no scheduler is configured.
    """
    scheduler = request.app.state.scheduler
    if scheduler is None or job_name not in scheduler.known_jobs():
        raise HTTPException(status_code=404, detail=f"unknown job: {job_name!r}")
    scheduler.trigger(job_name)
    return {"status": "accepted", "job_name": job_name}
