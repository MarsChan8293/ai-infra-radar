"""API tests for grouped daily report browsing."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from radar.app import create_app
from radar.core.models import Alert
from radar.core.repositories import RadarRepository
from radar.reports.summarization import NullReportSummarizer


def _make_client(repo: RadarRepository) -> TestClient:
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.settings = None
    app.state.config_path = None
    app.state.report_summarizer = NullReportSummarizer()
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
