"""Report browsing API routes."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/reports", tags=["reports"])


def _group_events(events: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        grouped[event["source"]].append(event)
    return [
        {"topic": topic, "count": len(items), "events": items}
        for topic, items in sorted(grouped.items())
    ]


def build_report_manifest(repo) -> dict:
    dates = []
    for day in repo.list_report_days():
        events = repo.list_alerts_for_day(day)
        dates.append(
            {
                "date": day,
                "count": len(events),
                "topics": sorted({event["source"] for event in events}),
            }
        )
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "dates": dates}


def build_report_payload(repo, day: str) -> dict:
    events = repo.list_alerts_for_day(day)
    if not events:
        raise HTTPException(status_code=404, detail="report not found")

    top_sources = Counter(event["source"] for event in events).most_common()
    return {
        "date": day,
        "summary": {
            "total_alerts": len(events),
            "top_sources": [
                {"source": source, "count": count} for source, count in top_sources
            ],
            "max_score": max(event["score"] for event in events),
        },
        "topics": _group_events(events),
    }


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
    return build_report_payload(repo, day)
