"""Report browsing API routes."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from radar.reports.enrichment import build_enriched_daily_report
from radar.reports.summarization import NullReportSummarizer

router = APIRouter(prefix="/reports", tags=["reports"])


def _event_rank(event: dict) -> tuple[float, str, int]:
    return (event["score"], event["created_at"], event["id"])


def _dedupe_events(events: list[dict]) -> list[dict]:
    best_by_entity: dict[str, dict] = {}
    for event in events:
        key = event["canonical_name"]
        current = best_by_entity.get(key)
        if current is None or _event_rank(event) > _event_rank(current):
            best_by_entity[key] = event
    return sorted(best_by_entity.values(), key=_event_rank, reverse=True)


def _get_report_summarizer(request: Request):
    summarizer = getattr(request.app.state, "report_summarizer", None)
    if summarizer is None:
        return NullReportSummarizer()
    return summarizer


def build_report_manifest(repo, *, report_summarizer) -> dict:
    dates = []
    for day in repo.list_report_days():
        payload = build_report_payload(repo, day, report_summarizer=report_summarizer)
        dates.append(
            {
                "date": day,
                "count": payload["summary"]["total_alerts"],
                "topics": sorted(topic["topic"] for topic in payload["topics"]),
                "filter_counts": {
                    key: len(values) for key, values in payload["filters"].items()
                },
                "briefing_available": bool(
                    payload["summary"].get("briefing_zh")
                    or payload["summary"].get("briefing_en")
                ),
            }
        )
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "dates": dates}


def build_report_payload(repo, day: str, *, report_summarizer) -> dict:
    events = _dedupe_events(repo.list_alerts_for_day(day))
    if not events:
        raise HTTPException(status_code=404, detail="report not found")
    return build_enriched_daily_report(
        date=day,
        events=events,
        summarizer=report_summarizer,
    )


@router.get("/manifest")
def get_reports_manifest(request: Request) -> dict:
    repo = request.app.state.repo
    if repo is None:
        return {"generated_at": None, "dates": []}
    return build_report_manifest(
        repo,
        report_summarizer=_get_report_summarizer(request),
    )


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
