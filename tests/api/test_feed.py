from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

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


def test_feed_route_falls_back_to_null_summarizer_when_state_is_missing(
    repo, monkeypatch
) -> None:
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
        dedupe_key="github:burst:fallback",
        reason={"full_name": "acme/tool", "stars": 25},
    )

    class StubNullReportSummarizer:
        def summarize_entry(self, entry: dict) -> dict[str, str | None]:
            return {
                "title_zh": "回退标题",
                "reason_text_zh": "回退摘要",
                "reason_text_en": "fallback summary",
            }

        def summarize_daily_briefing(
            self, *, date: str, entries: list[dict]
        ) -> dict[str, str | None]:
            return {"briefing_zh": "回退日报", "briefing_en": "fallback briefing"}

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "radar.api.routes.feed.NullReportSummarizer",
        StubNullReportSummarizer,
    )
    app = create_app()
    app.state.repo = repo
    if hasattr(app.state, "report_summarizer"):
        delattr(app.state, "report_summarizer")
    client = TestClient(app)

    response = client.get("/feed.xml")

    assert response.status_code == 200
    assert "回退摘要" in response.text


def test_feed_route_does_not_require_daily_briefing_generation(repo) -> None:
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
        dedupe_key="github:burst:no-briefing",
        reason={"full_name": "acme/tool", "stars": 25},
    )

    class CountingSummarizer:
        def __init__(self) -> None:
            self.entry_calls = 0
            self.briefing_calls = 0

        def summarize_entry(self, entry: dict) -> dict[str, str | None]:
            self.entry_calls += 1
            return {
                "title_zh": "标题",
                "reason_text_zh": "摘要",
                "reason_text_en": "summary",
            }

        def summarize_daily_briefing(
            self, *, date: str, entries: list[dict]
        ) -> dict[str, str | None]:
            self.briefing_calls += 1
            raise RuntimeError("feed should not build daily briefings")

        def close(self) -> None:
            return None

    app = create_app()
    app.state.repo = repo
    summarizer = CountingSummarizer()
    app.state.report_summarizer = summarizer
    client = TestClient(app)

    response = client.get("/feed.xml")

    assert response.status_code == 200
    assert "摘要" in response.text
    assert summarizer.entry_calls == 1
    assert summarizer.briefing_calls == 0


def test_feed_route_surfaces_summarizer_entry_failures(repo) -> None:
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
        dedupe_key="github:burst:feed-entry-failure",
        reason={"full_name": "acme/tool", "stars": 25},
    )

    class FailingSummarizer:
        def summarize_entry(self, entry: dict) -> dict[str, str | None]:
            raise RuntimeError("feed entry provider failed")

        def summarize_daily_briefing(
            self, *, date: str, entries: list[dict]
        ) -> dict[str, str | None]:
            return {"briefing_zh": None, "briefing_en": None}

        def close(self) -> None:
            return None

    app = create_app()
    app.state.repo = repo
    app.state.report_summarizer = FailingSummarizer()
    client = TestClient(app)

    with pytest.raises(RuntimeError, match="feed entry provider failed"):
        client.get("/feed.xml")
