"""Tests for the GitHub burst pipeline (Task 6).

TDD order:
  1.  test_normalize_github_item_shape              - observation dict has all required keys
  2.  test_normalize_canonical_name_uses_full_name  - canonical_name = "github:{full_name}"
  3.  test_normalize_url_equals_html_url            - url equals html_url from item
  4.  test_normalize_content_hash_is_deterministic  - same item → same hash
  5.  test_score_high_activity_item_above_threshold - 5000 stars/400 forks → score > 0.6
  6.  test_score_low_activity_item_below_threshold  - 10 stars/2 forks → score < 0.6
  7.  test_score_is_deterministic                   - same input → same float
  8.  test_score_is_in_range                        - score ∈ [0.0, 1.0] for all fixture items
  9.  test_run_github_burst_job_creates_alert_for_high_activity
 10.  test_run_github_burst_job_skips_item_below_threshold
 11.  test_run_github_burst_job_returns_int
 12.  test_github_client_fetches_search_items       - respx mock of GitHub search API
 13.  test_process_github_burst_creates_entity_and_alert
 14.  test_duplicate_burst_alert_is_suppressed
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "fixtures" / "github" / "search_response.json"
)


def _load_items() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text())["items"]


# ---------------------------------------------------------------------------
# Test 1: Normalization produces required keys
# ---------------------------------------------------------------------------

def test_normalize_github_item_shape() -> None:
    """normalize_github_item must return a dict with all required observation keys."""
    from radar.sources.github.pipeline import normalize_github_item

    obs = normalize_github_item(_load_items()[0])
    for key in (
        "canonical_name",
        "display_name",
        "url",
        "content_hash",
        "raw_payload",
        "normalized_payload",
    ):
        assert key in obs, f"Missing required key: {key!r}"


# ---------------------------------------------------------------------------
# Test 2: canonical_name is namespaced
# ---------------------------------------------------------------------------

def test_normalize_canonical_name_uses_full_name() -> None:
    """canonical_name must be 'github:{full_name}' to namespace from other sources."""
    from radar.sources.github.pipeline import normalize_github_item

    item = _load_items()[0]
    obs = normalize_github_item(item)
    assert obs["canonical_name"] == f"github:{item['full_name']}"


# ---------------------------------------------------------------------------
# Test 3: url comes from html_url
# ---------------------------------------------------------------------------

def test_normalize_url_equals_html_url() -> None:
    """url in observation must equal the item's html_url."""
    from radar.sources.github.pipeline import normalize_github_item

    item = _load_items()[0]
    obs = normalize_github_item(item)
    assert obs["url"] == item["html_url"]


# ---------------------------------------------------------------------------
# Test 4: content_hash is deterministic
# ---------------------------------------------------------------------------

def test_normalize_content_hash_is_deterministic() -> None:
    """Same item must produce the same content_hash on repeated calls."""
    from radar.sources.github.pipeline import normalize_github_item

    item = _load_items()[0]
    assert normalize_github_item(item)["content_hash"] == normalize_github_item(item)["content_hash"]


# ---------------------------------------------------------------------------
# Test 5: High-activity item scores above threshold
# ---------------------------------------------------------------------------

def test_score_high_activity_item_above_threshold() -> None:
    """A high-activity item (5000 stars, 400 forks) must score above 0.6."""
    from radar.sources.github.scoring import score_github_item

    score = score_github_item(_load_items()[0])
    assert score > 0.6, f"Expected score > 0.6, got {score}"


# ---------------------------------------------------------------------------
# Test 6: Low-activity item scores below threshold
# ---------------------------------------------------------------------------

def test_score_low_activity_item_below_threshold() -> None:
    """A low-activity item (10 stars, 2 forks) must score below 0.6."""
    from radar.sources.github.scoring import score_github_item

    score = score_github_item(_load_items()[1])
    assert score < 0.6, f"Expected score < 0.6, got {score}"


# ---------------------------------------------------------------------------
# Test 7: Score is deterministic
# ---------------------------------------------------------------------------

def test_score_is_deterministic() -> None:
    """score_github_item must return the same value for the same input."""
    from radar.sources.github.scoring import score_github_item

    item = _load_items()[0]
    assert score_github_item(item) == score_github_item(item)


# ---------------------------------------------------------------------------
# Test 8: Score is in [0.0, 1.0]
# ---------------------------------------------------------------------------

def test_score_is_in_range() -> None:
    """score_github_item must return a float in [0.0, 1.0] for all fixture items."""
    from radar.sources.github.scoring import score_github_item

    for item in _load_items():
        score = score_github_item(item)
        assert 0.0 <= score <= 1.0, f"score {score} out of range for {item['full_name']}"


# ---------------------------------------------------------------------------
# Fake alert service for job tests
# ---------------------------------------------------------------------------

class _FakeAlertService:
    """Records calls to process_github_burst for inspection in tests."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def process_github_burst(self, observation: dict) -> int:
        self.calls.append(observation)
        return 1


# ---------------------------------------------------------------------------
# Test 9: Job creates alerts for items at or above threshold
# ---------------------------------------------------------------------------

def test_run_github_burst_job_creates_alert_for_high_activity() -> None:
    """run_github_burst_job must call process_github_burst only for items that meet threshold."""
    from radar.jobs.github_burst import run_github_burst_job

    fake = _FakeAlertService()
    result = run_github_burst_job(
        search_items=_load_items(),
        threshold=0.6,
        repository=None,
        alert_service=fake,
    )

    assert result == 1, "Only one high-activity item should produce an alert"
    assert len(fake.calls) == 1
    assert fake.calls[0]["normalized_payload"]["full_name"] == "example-org/high-activity-repo"


# ---------------------------------------------------------------------------
# Test 10: Job skips items below threshold
# ---------------------------------------------------------------------------

def test_run_github_burst_job_skips_item_below_threshold() -> None:
    """run_github_burst_job must not emit alerts for items below threshold."""
    from radar.jobs.github_burst import run_github_burst_job

    fake = _FakeAlertService()
    result = run_github_burst_job(
        search_items=[_load_items()[1]],
        threshold=0.6,
        repository=None,
        alert_service=fake,
    )

    assert result == 0
    assert len(fake.calls) == 0


# ---------------------------------------------------------------------------
# Test 11: Job returns int
# ---------------------------------------------------------------------------

def test_run_github_burst_job_returns_int() -> None:
    """run_github_burst_job must return an int (count of alerts created)."""
    from radar.jobs.github_burst import run_github_burst_job

    result = run_github_burst_job(
        search_items=_load_items(),
        threshold=0.6,
        repository=None,
        alert_service=_FakeAlertService(),
    )
    assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Test 12: GitHub client fetches search items via respx mock
# ---------------------------------------------------------------------------

@respx.mock
def test_github_client_fetches_search_items() -> None:
    """fetch_search_results must call the GitHub search API and return the items list."""
    from radar.sources.github.client import GitHubClient

    payload = json.loads(FIXTURE_PATH.read_text())
    respx.route(
        method="GET",
        url__startswith="https://api.github.com/search/repositories",
    ).mock(return_value=httpx.Response(200, json=payload))

    items = GitHubClient().search_repositories(query="ai infrastructure")

    assert len(items) == 2
    assert items[0]["full_name"] == "example-org/high-activity-repo"
    assert items[1]["full_name"] == "example-org/low-activity-repo"


# ---------------------------------------------------------------------------
# Test 13: process_github_burst creates entity and alert (full integration)
# ---------------------------------------------------------------------------

def test_process_github_burst_creates_entity_and_alert(tmp_path: Path) -> None:
    """process_github_burst must upsert entity, record observation, and emit one alert."""
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.core.db import create_engine_and_session_factory, init_db
    from radar.core.repositories import RadarRepository
    from radar.sources.github.pipeline import build_github_observation

    engine, sf = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(sf)
    dispatcher = AlertDispatcher(
        repository=repo,
        send_webhook=lambda url, payload: None,
        send_email=lambda payload: None,
    )
    service = AlertService(
        repository=repo,
        dispatcher=dispatcher,
        channels={"webhook": "https://hooks.example.com/test"},
    )

    observation = build_github_observation(_load_items()[0])

    result = service.process_github_burst(observation)

    assert result == 1


# ---------------------------------------------------------------------------
# Test 14: Duplicate burst alert is suppressed
# ---------------------------------------------------------------------------

def test_duplicate_burst_alert_is_suppressed(tmp_path: Path) -> None:
    """Calling process_github_burst twice for the same item must return 0 on the second call."""
    from radar.alerts.dispatcher import AlertDispatcher
    from radar.alerts.service import AlertService
    from radar.core.db import create_engine_and_session_factory, init_db
    from radar.core.repositories import RadarRepository
    from radar.sources.github.pipeline import build_github_observation

    engine, sf = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(sf)
    dispatcher = AlertDispatcher(
        repository=repo,
        send_webhook=lambda url, payload: None,
        send_email=lambda payload: None,
    )
    service = AlertService(
        repository=repo,
        dispatcher=dispatcher,
        channels={},
    )

    observation = build_github_observation(_load_items()[0])

    assert service.process_github_burst(observation) == 1
    assert service.process_github_burst(observation) == 0
