"""TDD tests for the daily digest job."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from radar.jobs.daily_digest import run_daily_digest_job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_alert(repo, score: float, *, n: int = 1):
    """Insert *n* alerts at *score* via the repository and return them."""
    alerts = []
    for i in range(n):
        entity = repo.upsert_entity(
            source="github",
            entity_type="repository",
            canonical_name=f"org/repo-{score}-{i}",
            display_name=f"Repo {score} #{i}",
            url=f"https://github.com/org/repo-{score}-{i}",
        )
        alert = repo.create_alert(
            alert_type="github_burst",
            entity_id=entity.id,
            source="github",
            score=score,
            dedupe_key=f"digest-test:{score}:{i}",
            reason={"stars": 100},
        )
        alerts.append(alert)
    return alerts


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_candidates_returns_0(repo) -> None:
    dispatched = []
    result = run_daily_digest_job(repo, dispatch=dispatched.append)
    assert result == 0
    assert dispatched == []


def test_with_candidates_returns_1(repo) -> None:
    _seed_alert(repo, score=0.8)
    dispatched = []
    result = run_daily_digest_job(repo, dispatch=dispatched.append)
    assert result == 1
    assert len(dispatched) == 1


def test_dispatch_called_exactly_once_regardless_of_count(repo) -> None:
    _seed_alert(repo, score=0.9, n=5)
    dispatched = []
    run_daily_digest_job(repo, dispatch=dispatched.append)
    assert len(dispatched) == 1


def test_payload_type_is_daily_digest(repo) -> None:
    _seed_alert(repo, score=0.7)
    dispatched = []
    run_daily_digest_job(repo, dispatch=dispatched.append)
    assert dispatched[0]["type"] == "daily_digest"


def test_payload_count_matches_candidates(repo) -> None:
    _seed_alert(repo, score=0.6, n=3)
    dispatched = []
    run_daily_digest_job(repo, dispatch=dispatched.append)
    assert dispatched[0]["count"] == 3


def test_payload_items_ranked_by_score_descending(repo) -> None:
    _seed_alert(repo, score=0.5)
    _seed_alert(repo, score=0.9)
    _seed_alert(repo, score=0.7)
    dispatched = []
    run_daily_digest_job(repo, dispatch=dispatched.append)
    scores = [item["score"] for item in dispatched[0]["items"]]
    assert scores == sorted(scores, reverse=True)


def test_payload_items_contain_required_fields(repo) -> None:
    _seed_alert(repo, score=0.8)
    dispatched = []
    run_daily_digest_job(repo, dispatch=dispatched.append)
    item = dispatched[0]["items"][0]
    assert "alert_id" in item
    assert "score" in item
    assert "source" in item
    assert "alert_type" in item


def test_digest_excludes_alerts_older_than_24_hours(repo) -> None:
    from radar.core.models import Alert

    old_alert = _seed_alert(repo, score=0.95)[0]
    with repo._session_factory() as session:
        persisted = session.get(Alert, old_alert.id)
        assert persisted is not None
        persisted.created_at = datetime.now(timezone.utc) - timedelta(days=2)
        session.commit()

    _seed_alert(repo, score=0.75)
    dispatched = []
    run_daily_digest_job(repo, dispatch=dispatched.append)

    assert dispatched[0]["count"] == 1
    assert dispatched[0]["items"][0]["score"] == pytest.approx(0.75)


def test_payload_items_include_github_repo_metadata(repo) -> None:
    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="github:vllm-project/vllm",
        display_name="vllm-project/vllm",
        url="https://github.com/vllm-project/vllm",
    )
    repo.record_observation(
        entity_id=entity.id,
        source="github",
        raw_payload={"description": "A high-throughput and memory-efficient inference and serving engine for LLMs"},
        normalized_payload={"description": "A high-throughput and memory-efficient inference and serving engine for LLMs"},
        dedupe_key="obs:github:repo-metadata",
        content_hash="obs:github:repo-metadata",
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.8,
        dedupe_key="digest:github:repo-metadata",
        reason={"full_name": "vllm-project/vllm", "stars": 77644, "forks": 15924},
    )

    dispatched = []
    run_daily_digest_job(repo, dispatch=dispatched.append)

    assert dispatched[0]["items"][0]["repo_name"] == "vllm-project/vllm"
    assert dispatched[0]["items"][0]["repo_url"] == "https://github.com/vllm-project/vllm"
    assert dispatched[0]["items"][0]["repo_description"] == "A high-throughput and memory-efficient inference and serving engine for LLMs"


def test_payload_items_leave_non_github_sources_unenriched(repo) -> None:
    entity = repo.upsert_entity(
        source="official_pages",
        entity_type="page",
        canonical_name="official:deepseek",
        display_name="DeepSeek News",
        url="https://api-docs.deepseek.com/",
    )
    repo.create_alert(
        alert_type="official_release",
        entity_id=entity.id,
        source="official_pages",
        score=0.7,
        dedupe_key="digest:official:page",
        reason={"description": "DeepSeek release note"},
    )

    dispatched = []
    run_daily_digest_job(repo, dispatch=dispatched.append)

    item = dispatched[0]["items"][0]
    assert "repo_name" not in item
    assert "repo_url" not in item
    assert "repo_description" not in item
