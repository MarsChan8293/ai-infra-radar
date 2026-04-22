from pathlib import Path
from datetime import timezone

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

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


# --- TDD: timezone-aware timestamps ---

def test_observation_observed_at_is_timezone_aware(tmp_path: Path) -> None:
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    entity = repo.upsert_entity(
        source="github",
        entity_type="repo",
        canonical_name="tz_test_entity",
        display_name="TZ Test",
        url="https://github.com/test/tz",
    )
    observation = repo.record_observation(
        entity_id=entity.id,
        source="github",
        raw_payload={"data": "x"},
        normalized_payload={"data": "x"},
        dedupe_key="tz:test:obs",
        content_hash="deadbeef",
    )

    assert observation.observed_at.tzinfo is not None
    assert observation.observed_at.tzinfo == timezone.utc


def test_job_run_started_at_is_timezone_aware(tmp_path: Path) -> None:
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    job_run = repo.record_job_run(job_name="tz-test-job", status="success")

    assert job_run.started_at.tzinfo is not None
    assert job_run.started_at.tzinfo == timezone.utc


# --- TDD: Alert composite unique (source, dedupe_key) ---

def test_alert_same_dedupe_key_different_source_is_allowed(tmp_path: Path) -> None:
    """Same dedupe_key from two distinct sources must not raise IntegrityError."""
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    entity = repo.upsert_entity(
        source="github",
        entity_type="repo",
        canonical_name="composite_test_entity",
        display_name="Composite Test",
        url="https://github.com/test/composite",
    )
    repo.create_alert(
        alert_type="burst",
        entity_id=entity.id,
        source="github",
        score=0.9,
        dedupe_key="shared:key",
        reason={},
    )
    # Same dedupe_key but different source — must succeed
    repo.create_alert(
        alert_type="burst",
        entity_id=entity.id,
        source="twitter",
        score=0.85,
        dedupe_key="shared:key",
        reason={},
    )


def test_alert_duplicate_source_and_dedupe_key_raises(tmp_path: Path) -> None:
    """Same (source, dedupe_key) pair must raise IntegrityError."""
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    entity = repo.upsert_entity(
        source="github",
        entity_type="repo",
        canonical_name="dup_test_entity",
        display_name="Dup Test",
        url="https://github.com/test/dup",
    )
    repo.create_alert(
        alert_type="burst",
        entity_id=entity.id,
        source="github",
        score=0.9,
        dedupe_key="dup:key",
        reason={},
    )
    with pytest.raises(IntegrityError):
        repo.create_alert(
            alert_type="burst",
            entity_id=entity.id,
            source="github",
            score=0.9,
            dedupe_key="dup:key",
            reason={},
        )


# --- TDD: explicit typed parameters (no **kwargs) ---

def test_upsert_entity_rejects_unknown_kwargs(tmp_path: Path) -> None:
    """upsert_entity must not silently accept arbitrary keyword arguments."""
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    with pytest.raises(TypeError):
        repo.upsert_entity(  # type: ignore[call-arg]
            source="github",
            entity_type="repo",
            canonical_name="strict_test",
            display_name="Strict",
            url="https://github.com/test",
            unknown_field="oops",
        )


def test_record_observation_rejects_unknown_kwargs(tmp_path: Path) -> None:
    """record_observation must not silently accept arbitrary keyword arguments."""
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    entity = repo.upsert_entity(
        source="github",
        entity_type="repo",
        canonical_name="strict_obs_entity",
        display_name="Strict Obs",
        url="https://github.com/test/strict",
    )
    with pytest.raises(TypeError):
        repo.record_observation(  # type: ignore[call-arg]
            entity_id=entity.id,
            source="github",
            raw_payload={"x": 1},
            normalized_payload={"x": 1},
            dedupe_key="strict:obs",
            content_hash="abc",
            unknown_field="oops",
        )


# --- TDD: create_alert keyword-only signature ---

def test_create_alert_rejects_positional_args(tmp_path: Path) -> None:
    """create_alert must enforce keyword-only arguments (no positional calls)."""
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    entity = repo.upsert_entity(
        source="github",
        entity_type="repo",
        canonical_name="kwonly_pos_test",
        display_name="KW Pos Test",
        url="https://github.com/test/kwonly",
    )
    with pytest.raises(TypeError):
        repo.create_alert(  # type: ignore[misc]
            "official_release", entity.id, "github", 0.9, "kwonly:pos:key", {}
        )


def test_create_alert_rejects_unknown_kwargs(tmp_path: Path) -> None:
    """create_alert must not silently accept arbitrary keyword arguments."""
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    entity = repo.upsert_entity(
        source="github",
        entity_type="repo",
        canonical_name="kwonly_unk_test",
        display_name="KW Unk Test",
        url="https://github.com/test/kwonly2",
    )
    with pytest.raises(TypeError):
        repo.create_alert(  # type: ignore[call-arg]
            alert_type="official_release",
            entity_id=entity.id,
            source="github",
            score=0.9,
            dedupe_key="kwonly:unk:key",
            reason={},
            unknown_field="oops",
        )


# --- TDD: db parent directory auto-creation ---

def test_engine_creates_parent_dirs(tmp_path: Path) -> None:
    """create_engine_and_session_factory must create missing parent directories."""
    nested_path = tmp_path / "a" / "b" / "c" / "radar.db"
    assert not nested_path.parent.exists()
    engine, _ = create_engine_and_session_factory(nested_path)
    init_db(engine)
    assert nested_path.parent.exists()


# --- TDD: SQLite foreign key enforcement ---

def test_foreign_key_violation_raises(tmp_path: Path) -> None:
    """Inserting an Observation with a non-existent entity_id must raise IntegrityError."""
    engine, session_factory = create_engine_and_session_factory(tmp_path / "fk.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    with pytest.raises(IntegrityError):
        repo.record_observation(
            entity_id=9999,  # no such entity
            source="github",
            raw_payload={"x": 1},
            normalized_payload={"x": 1},
            dedupe_key="fk:test",
            content_hash="abc",
        )


# --- TDD: finished_at is UTC-aware ---

def test_job_run_finished_at_is_timezone_aware(tmp_path: Path) -> None:
    """finished_at read back from DB must be timezone-aware UTC."""
    from datetime import datetime, timezone

    engine, session_factory = create_engine_and_session_factory(tmp_path / "fin.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    job_run = repo.record_job_run(job_name="fin-test-job", status="success")

    from sqlalchemy.orm import Session
    from radar.core.models import JobRun

    with session_factory() as session:
        session.get(JobRun, job_run.id)
        session.execute(
            __import__("sqlalchemy").update(JobRun)
            .where(JobRun.id == job_run.id)
            .values(finished_at=datetime.now(timezone.utc))
        )
        session.commit()
        refreshed = session.get(JobRun, job_run.id)

    assert refreshed is not None
    assert refreshed.finished_at is not None
    assert refreshed.finished_at.tzinfo is not None
    assert refreshed.finished_at.tzinfo == timezone.utc


def test_get_digest_candidate_items_includes_github_repo_metadata(tmp_path: Path) -> None:
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    entity = repo.upsert_entity(
        source="github",
        entity_type="repo",
        canonical_name="github:vllm-project/vllm",
        display_name="vllm-project/vllm",
        url="https://github.com/vllm-project/vllm",
    )
    observation = repo.record_observation(
        entity_id=entity.id,
        source="github",
        raw_payload={},
        normalized_payload={"description": "A high-throughput and memory-efficient inference and serving engine for LLMs"},
        dedupe_key="github:vllm:obs",
        content_hash="abc",
    )
    alert = repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.91,
        dedupe_key="digest:github:vllm",
        reason={"stars": 1234},
    )

    items = repo.get_digest_candidate_items()

    assert items == [
        {
            "alert_id": alert.id,
            "alert_type": "github_burst",
            "source": "github",
            "score": 0.91,
            "repo_name": "vllm-project/vllm",
            "repo_url": "https://github.com/vllm-project/vllm",
            "repo_description": "A high-throughput and memory-efficient inference and serving engine for LLMs",
        }
    ]


def test_get_digest_candidate_items_uses_latest_github_observation_description(
    tmp_path: Path,
) -> None:
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    entity = repo.upsert_entity(
        source="github",
        entity_type="repo",
        canonical_name="github:vllm-project/vllm",
        display_name="vllm-project/vllm",
        url="https://github.com/vllm-project/vllm",
    )
    repo.record_observation(
        entity_id=entity.id,
        source="github",
        raw_payload={},
        normalized_payload={"description": "Old description"},
        dedupe_key="github:vllm:obs:1",
        content_hash="abc",
    )
    repo.record_observation(
        entity_id=entity.id,
        source="github",
        raw_payload={},
        normalized_payload={"description": "New description"},
        dedupe_key="github:vllm:obs:2",
        content_hash="def",
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.91,
        dedupe_key="digest:github:vllm",
        reason={"stars": 1234},
    )

    statements: list[str] = []

    def capture_sql(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        items = repo.get_digest_candidate_items()
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)

    assert items[0]["repo_description"] == "New description"
    assert len(statements) == 1
