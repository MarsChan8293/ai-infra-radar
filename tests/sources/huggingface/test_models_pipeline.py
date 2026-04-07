from __future__ import annotations

from datetime import datetime, timezone

from radar.core.models import Observation
from radar.core.repositories import RadarRepository


def test_get_entity_by_canonical_name_returns_existing(repo: RadarRepository) -> None:
    entity = repo.upsert_entity(
        source="huggingface",
        entity_type="model",
        canonical_name="huggingface:deepseek/deepseek-v3",
        display_name="deepseek/deepseek-v3",
        url="https://huggingface.co/deepseek/deepseek-v3",
    )

    fetched = repo.get_entity_by_canonical_name("huggingface:deepseek/deepseek-v3")
    assert fetched is not None
    assert fetched.id == entity.id


def test_get_latest_observation_for_entity_filters_entity_source_and_uses_newest_observation(
    repo: RadarRepository,
) -> None:
    entity = repo.upsert_entity(
        source="huggingface",
        entity_type="model",
        canonical_name="huggingface:deepseek/deepseek-v3",
        display_name="deepseek/deepseek-v3",
        url="https://huggingface.co/deepseek/deepseek-v3",
    )
    other_entity = repo.upsert_entity(
        source="huggingface",
        entity_type="model",
        canonical_name="huggingface:meta-llama/llama-3.1-8b",
        display_name="meta-llama/llama-3.1-8b",
        url="https://huggingface.co/meta-llama/llama-3.1-8b",
    )
    newest_matching = repo.record_observation(
        entity_id=entity.id,
        source="huggingface",
        raw_payload={"lastModified": "2026-04-08T00:00:00Z"},
        normalized_payload={"last_modified": "2026-04-08T00:00:00Z"},
        dedupe_key="hf:obs:1",
        content_hash="hash-1",
    )
    repo.record_observation(
        entity_id=other_entity.id,
        source="huggingface",
        raw_payload={"lastModified": "2026-04-09T00:00:00Z"},
        normalized_payload={"last_modified": "2026-04-09T00:00:00Z"},
        dedupe_key="hf:obs:other-entity",
        content_hash="hash-other-entity",
    )
    repo.record_observation(
        entity_id=entity.id,
        source="other-source",
        raw_payload={"lastModified": "2026-04-10T00:00:00Z"},
        normalized_payload={"last_modified": "2026-04-10T00:00:00Z"},
        dedupe_key="hf:obs:other-source",
        content_hash="hash-other-source",
    )
    older_matching = repo.record_observation(
        entity_id=entity.id,
        source="huggingface",
        raw_payload={"lastModified": "2026-04-07T00:00:00Z"},
        normalized_payload={"last_modified": "2026-04-07T00:00:00Z"},
        dedupe_key="hf:obs:2",
        content_hash="hash-2",
    )

    with repo._session_factory() as session:
        session.get(Observation, newest_matching.id).observed_at = datetime(
            2026, 4, 8, tzinfo=timezone.utc
        )
        session.get(Observation, older_matching.id).observed_at = datetime(
            2026, 4, 7, tzinfo=timezone.utc
        )
        session.commit()

    fetched = repo.get_latest_observation_for_entity(entity.id, source="huggingface")
    assert fetched is not None
    assert fetched.entity_id == entity.id
    assert fetched.source == "huggingface"
    assert fetched.id == newest_matching.id
