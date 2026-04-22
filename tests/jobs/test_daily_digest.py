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
# Job-level Tests (narrow scope: verify contract with repository helper)
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


def test_run_daily_digest_job_uses_digest_candidate_items_and_dispatches_them_directly() -> None:
    # The job should call repository.get_digest_candidate_items() once,
    # forward the items unchanged, and report count == len(items).
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
