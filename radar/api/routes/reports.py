from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from radar.reports.builder import build_report_manifest, build_report_payload
from radar.reports.summarization import NullReportSummarizer

router = APIRouter(prefix="/reports", tags=["reports"])


def _get_report_summarizer(request: Request):
    summarizer = getattr(request.app.state, "report_summarizer", None)
    if summarizer is None:
        return NullReportSummarizer()
    return summarizer

@router.get("/manifest")
def get_reports_manifest(request: Request) -> dict:
    repo = request.app.state.repo
    if repo is None:
        return {"generated_at": None, "dates": []}
    return build_report_manifest(repo)


@router.get("/{day}")
def get_report_for_day(day: str, request: Request) -> dict:
    repo = request.app.state.repo
    if repo is None:
        raise HTTPException(status_code=404, detail="report not found")
    return build_report_payload(
        repo,
        day,
        report_summarizer=_get_report_summarizer(request),
    )
