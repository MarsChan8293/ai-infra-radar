from __future__ import annotations

from fastapi.testclient import TestClient

from radar.app import create_app
from radar.reports.summarization import NullReportSummarizer


def test_feed_route_returns_rss_from_enriched_reports(repo) -> None:
    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="github:acme/tool",
        display_name="acme/tool",
        url="https://github.com/acme/tool",
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.9,
        dedupe_key="github:burst:rss",
        reason={"full_name": "acme/tool", "stars": 25},
    )

    app = create_app()
    app.state.repo = repo
    app.state.report_summarizer = NullReportSummarizer()
    client = TestClient(app)

    response = client.get("/feed.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/rss+xml")
    assert "<rss" in response.text
    assert "acme/tool" in response.text
