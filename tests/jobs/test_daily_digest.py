"""TDD tests for the daily digest job."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from radar.jobs.daily_digest import run_daily_digest_job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class StubDigestRepository:
    def __init__(self, items):
        self._items = list(items)
        self.get_digest_candidate_items_calls = 0

    def get_digest_candidate_items(self):
        self.get_digest_candidate_items_calls += 1
        return list(self._items)

    def get_digest_candidates(self):
        raise AssertionError("run_daily_digest_job should use get_digest_candidate_items()")


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


def test_run_daily_digest_job_uses_digest_candidate_items_and_dispatches_them_directly() -> None:
    repo = StubDigestRepository(
        [
            {
                "alert_id": 123,
                "alert_type": "github_burst",
                "source": "github",
                "score": 0.91,
                "repo_name": "vllm-project/vllm",
                "repo_url": "https://github.com/vllm-project/vllm",
                "repo_description": "A fast LLM serving engine",
            }
        ]
    )
    dispatched = []

    result = run_daily_digest_job(repo, dispatch=dispatched.append)

    assert result == 1
    assert repo.get_digest_candidate_items_calls == 1
    assert dispatched == [
        {
            "type": "daily_digest",
            "count": 1,
            "items": [
                {
                    "alert_id": 123,
                    "alert_type": "github_burst",
                    "source": "github",
                    "score": 0.91,
                    "repo_name": "vllm-project/vllm",
                    "repo_url": "https://github.com/vllm-project/vllm",
                    "repo_description": "A fast LLM serving engine",
                }
            ],
        }
    ]


def test_github_digest_items_include_repo_metadata(repo) -> None:
    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="vllm-project/vllm",
        display_name="vllm-project/vllm",
        url="https://github.com/vllm-project/vllm",
    )
    repo.record_observation(
        entity_id=entity.id,
        source="github",
        raw_payload={},
        normalized_payload={"description": "A fast LLM serving engine"},
        dedupe_key="github:vllm-project/vllm:obs",
        content_hash="github:vllm-project/vllm:content",
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.91,
        dedupe_key="github:vllm-project/vllm:digest",
        reason={"stars": 1234},
    )
    dispatched = []

    run_daily_digest_job(repo, dispatch=dispatched.append)

    assert dispatched[0]["items"][0]["repo_name"] == "vllm-project/vllm"
    assert dispatched[0]["items"][0]["repo_url"] == "https://github.com/vllm-project/vllm"
    assert dispatched[0]["items"][0]["repo_description"] == "A fast LLM serving engine"


def test_non_github_digest_items_do_not_get_repo_metadata_fields(repo) -> None:
    entity = repo.upsert_entity(
        source="arxiv",
        entity_type="paper",
        canonical_name="arxiv:1234.5678",
        display_name="Attention Is All You Need",
        url="https://arxiv.org/abs/1234.5678",
    )
    repo.create_alert(
        alert_type="paper_spike",
        entity_id=entity.id,
        source="arxiv",
        score=0.84,
        dedupe_key="arxiv:1234.5678:digest",
        reason={"citations": 42},
    )
    dispatched = []

    run_daily_digest_job(repo, dispatch=dispatched.append)

    item = dispatched[0]["items"][0]
    assert "repo_name" not in item
    assert "repo_url" not in item
    assert "repo_description" not in item


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
