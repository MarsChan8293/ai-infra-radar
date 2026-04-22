"""Job-layer contract tests for the daily digest job."""
from __future__ import annotations

from radar.jobs.daily_digest import run_daily_digest_job


class StubDigestRepository:
    def __init__(self, items):
        self._items = items
        self.get_digest_candidate_items_calls = 0

    def get_digest_candidate_items(self):
        self.get_digest_candidate_items_calls += 1
        return self._items

    def get_digest_candidates(self):
        raise AssertionError("run_daily_digest_job should use get_digest_candidate_items()")


def _run_job(items):
    repo = StubDigestRepository(items)
    dispatched = []

    result = run_daily_digest_job(repo, dispatch=dispatched.append)

    return result, repo, dispatched


def test_empty_helper_output_returns_0_and_dispatches_nothing() -> None:
    result, repo, dispatched = _run_job([])

    assert result == 0
    assert repo.get_digest_candidate_items_calls == 1
    assert dispatched == []


def test_non_empty_helper_output_returns_1_and_dispatches_once() -> None:
    items = [{"alert_id": 1}, {"alert_id": 2}]

    result, repo, dispatched = _run_job(items)

    assert result == 1
    assert repo.get_digest_candidate_items_calls == 1
    assert len(dispatched) == 1


def test_dispatched_payload_type_is_daily_digest() -> None:
    _, _, dispatched = _run_job([{"alert_id": 1}])

    assert dispatched[0]["type"] == "daily_digest"


def test_dispatched_payload_count_matches_helper_output_length() -> None:
    _, _, dispatched = _run_job([{"alert_id": 1}, {"alert_id": 2}, {"alert_id": 3}])

    assert dispatched[0]["count"] == 3


def test_dispatched_payload_items_forward_helper_output_unchanged() -> None:
    items = [
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

    _, _, dispatched = _run_job(items)

    assert dispatched[0]["items"] is items
