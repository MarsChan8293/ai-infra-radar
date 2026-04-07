from __future__ import annotations

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


def test_get_latest_observation_for_entity_returns_last_snapshot(
    repo: RadarRepository,
) -> None:
    entity = repo.upsert_entity(
        source="huggingface",
        entity_type="model",
        canonical_name="huggingface:deepseek/deepseek-v3",
        display_name="deepseek/deepseek-v3",
        url="https://huggingface.co/deepseek/deepseek-v3",
    )
    repo.record_observation(
        entity_id=entity.id,
        source="huggingface",
        raw_payload={"lastModified": "2026-04-06T00:00:00Z"},
        normalized_payload={"last_modified": "2026-04-06T00:00:00Z"},
        dedupe_key="hf:obs:1",
        content_hash="hash-1",
    )
    latest = repo.record_observation(
        entity_id=entity.id,
        source="huggingface",
        raw_payload={"lastModified": "2026-04-07T00:00:00Z"},
        normalized_payload={"last_modified": "2026-04-07T00:00:00Z"},
        dedupe_key="hf:obs:2",
        content_hash="hash-2",
    )

    fetched = repo.get_latest_observation_for_entity(entity.id, source="huggingface")
    assert fetched is not None
    assert fetched.id == latest.id
