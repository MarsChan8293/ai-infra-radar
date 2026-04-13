"""API tests for grouped daily report browsing."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
import pytest

from radar.app import create_app
from radar.core.models import Alert
from radar.core.repositories import RadarRepository
from radar.reports.summarization import NullReportSummarizer


def _make_client(
    repo: RadarRepository, *, with_report_summarizer: bool = True
) -> TestClient:
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.settings = None
    app.state.config_path = None
    if with_report_summarizer:
        app.state.report_summarizer = NullReportSummarizer()
    elif hasattr(app.state, "report_summarizer"):
        delattr(app.state, "report_summarizer")
    return TestClient(app)


def test_reports_manifest_groups_alert_days(repo: RadarRepository) -> None:
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
        dedupe_key="github:burst:1",
        reason={"full_name": "acme/tool"},
    )

    client = _make_client(repo)

    response = client.get("/reports/manifest")

    assert response.status_code == 200
    body = response.json()
    assert body["dates"][0]["date"]
    assert body["dates"][0]["count"] == 1
    assert "github" in body["dates"][0]["topics"]


def test_reports_date_endpoint_returns_summary_and_events(repo: RadarRepository) -> None:
    entity = repo.upsert_entity(
        source="modelscope",
        entity_type="model",
        canonical_name="modelscope:Qwen/Qwen3",
        display_name="Qwen/Qwen3",
        url="https://www.modelscope.cn/models/Qwen/Qwen3",
    )
    repo.create_alert(
        alert_type="modelscope_model_new",
        entity_id=entity.id,
        source="modelscope",
        score=1.0,
        dedupe_key="modelscope:new:Qwen/Qwen3",
        reason={"model_id": "Qwen/Qwen3"},
    )

    client = _make_client(repo)
    manifest = client.get("/reports/manifest").json()
    date_str = manifest["dates"][0]["date"]

    response = client.get(f"/reports/{date_str}")

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == date_str
    assert body["summary"]["total_alerts"] == 1
    assert body["summary"]["top_sources"][0]["source"] == "modelscope"
    assert body["topics"][0]["topic"] == "modelscope"
    assert body["topics"][0]["events"][0]["display_name"] == "Qwen/Qwen3"


def test_reports_date_endpoint_deduplicates_same_entity_by_highest_score(
    repo: RadarRepository,
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
        score=0.4,
        dedupe_key="github:burst:low",
        reason={"full_name": "acme/tool", "stars": 10},
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.9,
        dedupe_key="github:burst:high",
        reason={"full_name": "acme/tool", "stars": 25},
    )

    client = _make_client(repo)
    date_str = client.get("/reports/manifest").json()["dates"][0]["date"]

    response = client.get(f"/reports/{date_str}")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total_alerts"] == 1
    assert body["summary"]["top_sources"] == [{"source": "github", "count": 1}]
    assert body["topics"][0]["count"] == 1
    assert body["topics"][0]["events"][0]["score"] == 0.9
    assert body["topics"][0]["events"][0]["reason"]["stars"] == 25


def test_reports_manifest_counts_unique_entities_per_day(repo: RadarRepository) -> None:
    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="github:acme/tool",
        display_name="acme/tool",
        url="https://github.com/acme/tool",
    )
    for idx, score in enumerate((0.4, 0.9), start=1):
        repo.create_alert(
            alert_type="github_burst",
            entity_id=entity.id,
            source="github",
            score=score,
            dedupe_key=f"github:burst:{idx}",
            reason={"full_name": "acme/tool"},
        )

    client = _make_client(repo)

    response = client.get("/reports/manifest")

    assert response.status_code == 200
    body = response.json()
    assert body["dates"][0]["count"] == 1


def test_reports_manifest_does_not_call_report_summarizer(repo: RadarRepository) -> None:
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
        dedupe_key="github:burst:manifest-no-summary",
        reason={"full_name": "acme/tool"},
    )

    class CountingSummarizer:
        def __init__(self) -> None:
            self.entry_calls = 0
            self.briefing_calls = 0

        def summarize_entry(self, entry: dict) -> dict[str, str | None]:
            self.entry_calls += 1
            return {"title_zh": "标题", "reason_text_zh": "摘要", "reason_text_en": "summary"}

        def summarize_daily_briefing(
            self, *, date: str, entries: list[dict]
        ) -> dict[str, str | None]:
            self.briefing_calls += 1
            return {"briefing_zh": "日报", "briefing_en": "briefing"}

        def close(self) -> None:
            return None

    app = create_app()
    app.state.repo = repo
    summarizer = CountingSummarizer()
    app.state.report_summarizer = summarizer
    client = TestClient(app)

    response = client.get("/reports/manifest")

    assert response.status_code == 200
    assert summarizer.entry_calls == 0
    assert summarizer.briefing_calls == 0


def test_reports_date_endpoint_prefers_newer_alert_when_scores_match(
    repo: RadarRepository,
) -> None:
    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="github:acme/tool",
        display_name="acme/tool",
        url="https://github.com/acme/tool",
    )
    older = repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.9,
        dedupe_key="github:burst:older",
        reason={"full_name": "acme/tool", "stars": 10},
    )
    newer = repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.9,
        dedupe_key="github:burst:newer",
        reason={"full_name": "acme/tool", "stars": 25},
    )
    with repo._session_factory() as session:
        session.get(Alert, older.id).created_at = datetime(2026, 4, 8, 10, tzinfo=timezone.utc)
        session.get(Alert, newer.id).created_at = datetime(2026, 4, 8, 11, tzinfo=timezone.utc)
        session.commit()

    client = _make_client(repo)
    date_str = client.get("/reports/manifest").json()["dates"][0]["date"]

    body = client.get(f"/reports/{date_str}").json()

    assert body["summary"]["total_alerts"] == 1
    assert body["topics"][0]["events"][0]["id"] == newer.id
    assert body["topics"][0]["events"][0]["reason"]["stars"] == 25


def test_reports_date_endpoint_prefers_larger_id_when_score_and_time_match(
    repo: RadarRepository,
) -> None:
    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="github:acme/tool",
        display_name="acme/tool",
        url="https://github.com/acme/tool",
    )
    first = repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.9,
        dedupe_key="github:burst:first",
        reason={"full_name": "acme/tool", "stars": 10},
    )
    second = repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.9,
        dedupe_key="github:burst:second",
        reason={"full_name": "acme/tool", "stars": 25},
    )
    same_timestamp = datetime(2026, 4, 8, 10, tzinfo=timezone.utc)
    with repo._session_factory() as session:
        session.get(Alert, first.id).created_at = same_timestamp
        session.get(Alert, second.id).created_at = same_timestamp
        session.commit()

    client = _make_client(repo)
    date_str = client.get("/reports/manifest").json()["dates"][0]["date"]

    body = client.get(f"/reports/{date_str}").json()

    assert body["summary"]["total_alerts"] == 1
    assert body["topics"][0]["events"][0]["id"] == second.id
    assert body["topics"][0]["events"][0]["reason"]["stars"] == 25


def test_reports_date_endpoint_exposes_search_filter_and_bilingual_fields(
    repo: RadarRepository,
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
        dedupe_key="github:burst:rich",
        reason={"full_name": "acme/tool", "stars": 25},
    )

    client = _make_client(repo)
    date_str = client.get("/reports/manifest").json()["dates"][0]["date"]

    response = client.get(f"/reports/{date_str}")

    assert response.status_code == 200
    body = response.json()
    event = body["topics"][0]["events"][0]

    assert "filters" in body
    assert "briefing_zh" in body["summary"]
    assert "briefing_en" in body["summary"]
    assert "filter_counts" in client.get("/reports/manifest").json()["dates"][0]
    assert "briefing_available" in client.get("/reports/manifest").json()["dates"][0]
    assert "search_text" in event
    assert "filter_tags" in event
    assert "reason_text_zh" in event
    assert "reason_text_en" in event
    assert "title_zh" in event
    assert body["filters"]["sources"][0]["value"] == "github"


def test_reports_date_endpoint_builds_github_chinese_fallback_without_model(
    repo: RadarRepository,
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
        dedupe_key="github:burst:zh-fallback",
        reason={
            "full_name": "acme/tool",
            "stars": 25,
            "forks": 4,
            "description": "Fast speculative decoding runtime.",
        },
    )

    client = _make_client(repo)
    date_str = client.get("/reports/manifest").json()["dates"][0]["date"]

    response = client.get(f"/reports/{date_str}")

    assert response.status_code == 200
    event = response.json()["topics"][0]["events"][0]
    assert event["title_zh"] == "GitHub 仓库 acme/tool 热度上升"
    assert event["reason_text_zh"] is not None
    assert "25" in event["reason_text_zh"]
    assert "4" in event["reason_text_zh"]
    assert "Fast speculative decoding runtime." in event["reason_text_zh"]


def test_reports_date_endpoint_falls_back_to_null_summarizer_when_state_is_missing(
    repo: RadarRepository, monkeypatch
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
        "radar.api.routes.reports.NullReportSummarizer",
        StubNullReportSummarizer,
    )
    client = _make_client(repo, with_report_summarizer=False)
    date_str = client.get("/reports/manifest").json()["dates"][0]["date"]

    response = client.get(f"/reports/{date_str}")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["briefing_zh"] == "回退日报"
    assert body["summary"]["briefing_en"] == "fallback briefing"
    assert body["topics"][0]["events"][0]["title_zh"] == "回退标题"
    assert body["topics"][0]["events"][0]["reason_text_zh"] == "回退摘要"
    assert body["topics"][0]["events"][0]["reason_text_en"] == "fallback summary"


def test_reports_date_endpoint_surfaces_summarizer_entry_failures(
    repo: RadarRepository,
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
        dedupe_key="github:burst:entry-failure",
        reason={"full_name": "acme/tool"},
    )

    class FailingSummarizer:
        def summarize_entry(self, entry: dict) -> dict[str, str | None]:
            raise RuntimeError("entry provider failed")

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
    date_str = client.get("/reports/manifest").json()["dates"][0]["date"]

    with pytest.raises(RuntimeError, match="entry provider failed"):
        client.get(f"/reports/{date_str}")


def test_reports_date_endpoint_surfaces_daily_briefing_failures(
    repo: RadarRepository,
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
        dedupe_key="github:burst:briefing-failure",
        reason={"full_name": "acme/tool"},
    )

    class FailingSummarizer:
        def summarize_entry(self, entry: dict) -> dict[str, str | None]:
            return {"title_zh": None, "reason_text_zh": None, "reason_text_en": "summary"}

        def summarize_daily_briefing(
            self, *, date: str, entries: list[dict]
        ) -> dict[str, str | None]:
            raise RuntimeError("briefing provider failed")

        def close(self) -> None:
            return None

    app = create_app()
    app.state.repo = repo
    app.state.report_summarizer = FailingSummarizer()
    client = TestClient(app)
    date_str = client.get("/reports/manifest").json()["dates"][0]["date"]

    with pytest.raises(RuntimeError, match="briefing provider failed"):
        client.get(f"/reports/{date_str}")
