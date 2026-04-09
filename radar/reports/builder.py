from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from radar.reports.enrichment import (
    build_enriched_daily_report,
    build_filter_summary,
    build_filter_tags,
)


def _event_rank(event: dict[str, Any]) -> tuple[float, str, int]:
    return (event["score"], event["created_at"], event["id"])


def dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_entity: dict[str, dict[str, Any]] = {}
    for event in events:
        key = event["canonical_name"]
        current = best_by_entity.get(key)
        if current is None or _event_rank(event) > _event_rank(current):
            best_by_entity[key] = event
    return sorted(best_by_entity.values(), key=_event_rank, reverse=True)


def list_report_events(repo, day: str) -> list[dict[str, Any]]:
    return dedupe_events(repo.list_alerts_for_day(day))


def build_report_manifest(repo) -> dict[str, Any]:
    dates = []
    for day in repo.list_report_days():
        events = list_report_events(repo, day)
        filter_counts = {
            key: len(values)
            for key, values in build_filter_summary(
                [{**event, "filter_tags": build_filter_tags(event)} for event in events]
            ).items()
        }
        dates.append(
            {
                "date": day,
                "count": len(events),
                "topics": sorted({event["source"] for event in events}),
                "filter_counts": filter_counts,
                "briefing_available": False,
            }
        )
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "dates": dates}


def build_report_manifest_from_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dates": [
            {
                "date": report["date"],
                "count": report.get("summary", {}).get("total_alerts", 0),
                "topics": sorted(topic["topic"] for topic in report["topics"]),
                "filter_counts": {
                    key: len(values)
                    for key, values in report.get("filters", {}).items()
                },
                "briefing_available": bool(
                    report.get("summary", {}).get("briefing_zh")
                    or report.get("summary", {}).get("briefing_en")
                ),
            }
            for report in reports
        ],
    }


def build_report_payload(
    repo,
    day: str,
    *,
    report_summarizer,
    include_daily_briefing: bool = True,
) -> dict[str, Any]:
    events = list_report_events(repo, day)
    if not events:
        raise HTTPException(status_code=404, detail="report not found")
    return build_enriched_daily_report(
        date=day,
        events=events,
        summarizer=report_summarizer,
        include_daily_briefing=include_daily_briefing,
    )


def build_feed_xml_from_reports(
    reports: list[dict[str, Any]], *, limit_days: int | None = 7
) -> str:
    items: list[str] = []
    selected_reports = reports[:limit_days] if limit_days is not None else reports
    for report in selected_reports:
        for topic in report["topics"]:
            for event in topic["events"]:
                from datetime import datetime
                from email.utils import format_datetime
                from xml.sax.saxutils import escape

                description = (
                    event.get("reason_text_zh")
                    or event.get("reason_text_en")
                    or str(event.get("reason") or "")
                )
                pub_date = format_datetime(datetime.fromisoformat(event["created_at"]))
                items.append(
                    "<item>"
                    f"<title>{escape(event['display_name'])}</title>"
                    f"<link>{escape(event['url'])}</link>"
                    f"<description>{escape(description)}</description>"
                    f"<pubDate>{escape(pub_date)}</pubDate>"
                    f"<guid>{escape(str(event['id']))}</guid>"
                    "</item>"
                )

    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<rss version='2.0'><channel>"
        "<title>AI Infra Radar</title>"
        "<description>AI Infra Radar enriched daily report feed</description>"
        "<link>/feed.xml</link>"
        f"{''.join(items)}"
        "</channel></rss>"
    )
