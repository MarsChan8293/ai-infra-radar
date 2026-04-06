from pathlib import Path

from radar.core.db import create_engine_and_session_factory, init_db
from radar.core.repositories import RadarRepository


def test_repository_persists_entity_and_alert(tmp_path: Path) -> None:
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    entity = repo.upsert_entity(
        source="official_pages",
        entity_type="page",
        canonical_name="deepseek_news",
        display_name="DeepSeek News",
        url="https://api-docs.deepseek.com/",
    )
    observation = repo.record_observation(
        entity_id=entity.id,
        source="official_pages",
        raw_payload={"html": "<h1>DeepSeek V3 released</h1>"},
        normalized_payload={"title": "DeepSeek V3 released"},
        dedupe_key="official_pages:deepseek:v3",
        content_hash="abc123",
    )
    alert = repo.create_alert(
        alert_type="official_release",
        entity_id=entity.id,
        source="official_pages",
        score=0.91,
        dedupe_key="abc123",
        reason={"title": "DeepSeek V3 released"},
    )
    job_run = repo.record_job_run(job_name="official-pages", status="success")

    assert observation.entity_id == entity.id
    assert alert.entity_id == entity.id
    assert job_run.job_name == "official-pages"


def test_alert_exists_dedupe(tmp_path: Path) -> None:
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    entity = repo.upsert_entity(
        source="github",
        entity_type="repo",
        canonical_name="sglang_burst",
        display_name="sglang",
        url="https://github.com/sgl-project/sglang",
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.8,
        dedupe_key="github:sglang:burst:2026",
        reason={"stars": 1000},
    )

    assert repo.alert_exists(source="github", dedupe_key="github:sglang:burst:2026") is True
    assert repo.alert_exists(source="github", dedupe_key="github:sglang:burst:9999") is False


def test_record_delivery_log(tmp_path: Path) -> None:
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    entity = repo.upsert_entity(
        source="github",
        entity_type="repo",
        canonical_name="test_entity",
        display_name="Test",
        url="https://github.com/test",
    )
    alert = repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.7,
        dedupe_key="test:delivery:log",
        reason={},
    )
    log = repo.record_delivery_log(alert_id=alert.id, channel="webhook", status="sent")

    assert log.alert_id == alert.id
    assert log.channel == "webhook"
    assert log.status == "sent"
