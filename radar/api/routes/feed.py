from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from radar.reports.builder import build_feed_xml_from_reports, build_report_payload
from radar.reports.summarization import NullReportSummarizer

router = APIRouter(tags=["feed"])


def build_feed_xml(repo, *, report_summarizer) -> str:
    if repo is None:
        return (
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<rss version='2.0'><channel><title>AI Infra Radar</title></channel></rss>"
        )

    reports = [
        build_report_payload(
            repo,
            day,
            report_summarizer=report_summarizer,
            include_daily_briefing=False,
        )
        for day in repo.list_report_days()[:7]
    ]
    return build_feed_xml_from_reports(reports)


@router.get("/feed.xml", include_in_schema=False)
def get_feed(request: Request) -> Response:
    summarizer = getattr(request.app.state, "report_summarizer", None)
    if summarizer is None:
        summarizer = NullReportSummarizer()
    body = build_feed_xml(request.app.state.repo, report_summarizer=summarizer)
    return Response(content=body, media_type="application/rss+xml")
