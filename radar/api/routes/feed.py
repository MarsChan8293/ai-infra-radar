from __future__ import annotations

from datetime import datetime
from email.utils import format_datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, Request
from fastapi.responses import Response

from radar.api.routes.reports import build_report_payload
from radar.reports.summarization import NullReportSummarizer

router = APIRouter(tags=["feed"])


def build_feed_xml(repo, *, report_summarizer) -> str:
    if repo is None:
        return (
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<rss version='2.0'><channel><title>AI Infra Radar</title></channel></rss>"
        )

    items: list[str] = []
    for day in repo.list_report_days()[:7]:
        report = build_report_payload(
            repo,
            day,
            report_summarizer=report_summarizer,
        )
        for topic in report["topics"]:
            for event in topic["events"]:
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


@router.get("/feed.xml", include_in_schema=False)
def get_feed(request: Request) -> Response:
    summarizer = getattr(request.app.state, "report_summarizer", None)
    if summarizer is None:
        summarizer = NullReportSummarizer()
    body = build_feed_xml(request.app.state.repo, report_summarizer=summarizer)
    return Response(content=body, media_type="application/rss+xml")
