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
from datetime import date

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


@respx.mock
def test_github_client_retries_transient_search_connect_errors() -> None:
    from radar.sources.github.client import GitHubClient

    payload = json.loads(FIXTURE_PATH.read_text())
    attempts = {"count": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ConnectError("tls eof", request=request)
        return httpx.Response(200, json=payload)

    respx.route(
        method="GET",
        url__startswith="https://api.github.com/search/repositories",
    ).mock(side_effect=_handler)

    items = GitHubClient().search_repositories(query="ai infrastructure")

    assert attempts["count"] == 2
    assert len(items) == 2


@respx.mock
def test_github_client_fetches_readme_text() -> None:
    from radar.sources.github.client import GitHubClient

    respx.get("https://api.github.com/repos/example-org/high-activity-repo/readme").mock(
        return_value=httpx.Response(200, text="# README\n\n## Citation\n\n@inproceedings{demo}")
    )

    readme = GitHubClient().fetch_readme_text("example-org/high-activity-repo")

    assert "Citation" in readme


@respx.mock
def test_github_client_retries_transient_readme_timeouts() -> None:
    from radar.sources.github.client import GitHubClient

    attempts = {"count": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, text="# README\n\n## Citation\n\n@inproceedings{demo}")

    respx.get("https://api.github.com/repos/example-org/high-activity-repo/readme").mock(
        side_effect=_handler
    )

    readme = GitHubClient().fetch_readme_text("example-org/high-activity-repo")

    assert attempts["count"] == 2
    assert "Citation" in readme


@respx.mock
def test_github_client_missing_readme_returns_none() -> None:
    from radar.sources.github.client import GitHubClient

    respx.get("https://api.github.com/repos/example-org/no-readme/readme").mock(
        return_value=httpx.Response(404, text="not found")
    )

    assert GitHubClient().fetch_readme_text("example-org/no-readme") is None


def test_expand_query_date_placeholders_resolves_today_minus_days() -> None:
    from radar.sources.github.client import expand_query_date_placeholders

    query = 'created:>@today-7d "speculative decoding"'

    expanded = expand_query_date_placeholders(query, today=date(2026, 4, 8))

    assert expanded == 'created:>2026-04-01 "speculative decoding"'


def test_expand_query_date_placeholders_resolves_today_literal() -> None:
    from radar.sources.github.client import expand_query_date_placeholders

    expanded = expand_query_date_placeholders("pushed:>=@today", today=date(2026, 4, 8))

    assert expanded == "pushed:>=2026-04-08"


def test_build_created_range_query_appends_date_window() -> None:
    from radar.sources.github.manual_fetch import build_created_range_query

    query = build_created_range_query(
        '"speculative decoding"',
        start_date="2026-04-01",
        end_date="2026-04-10",
    )

    assert query == '"speculative decoding" created:2026-04-01..2026-04-10'


def test_collect_readme_candidates_attaches_repository_metadata_and_status() -> None:
    from radar.sources.github.manual_fetch import collect_readme_candidates

    items = _load_items()

    def _fetch_readme_text(full_name: str) -> str | None:
        if full_name == "example-org/high-activity-repo":
            return "# README\n\nMentions inference serving and KV cache."
        return None

    candidates = collect_readme_candidates(items, fetch_readme_text=_fetch_readme_text)

    assert candidates[0]["full_name"] == "example-org/high-activity-repo"
    assert candidates[0]["html_url"] == items[0]["html_url"]
    assert candidates[0]["stars"] == items[0]["stargazers_count"]
    assert candidates[0]["forks"] == items[0]["forks_count"]
    assert candidates[0]["readme_status"] == "ok"
    assert "inference serving" in candidates[0]["readme_text"]
    assert candidates[0]["raw_item"] == items[0]
    assert candidates[1]["full_name"] == "example-org/low-activity-repo"
    assert candidates[1]["readme_status"] == "missing_readme"
    assert candidates[1]["readme_text"] is None


def test_collect_readme_candidates_marks_fetch_errors() -> None:
    from radar.sources.github.manual_fetch import collect_readme_candidates

    def _fetch_readme_text(full_name: str) -> str | None:
        raise httpx.ReadTimeout(f"timed out for {full_name}")

    candidates = collect_readme_candidates(
        [_load_items()[0]],
        fetch_readme_text=_fetch_readme_text,
    )

    assert candidates[0]["readme_status"] == "fetch_error"
    assert candidates[0]["readme_text"] is None
    assert "timed out" in candidates[0]["readme_error"]


def test_apply_readme_ai_second_pass_returns_structured_fields() -> None:
    from radar.sources.github.readme_ai_filter import apply_readme_ai_second_pass

    class _StubFilter:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def evaluate(
            self,
            *,
            repository: dict,
            readme_text: str,
            prompt: str,
        ) -> dict:
            self.calls.append(
                {
                    "repository": repository,
                    "readme_text": readme_text,
                    "prompt": prompt,
                }
            )
            return {
                "keep": True,
                "reason_zh": "README 明确提到了推理服务与 KV cache。",
                "matched_signals": ["inference serving", "kv cache"],
            }

    candidate = {
        "full_name": "example-org/high-activity-repo",
        "description": "High activity repo",
        "html_url": "https://github.com/example-org/high-activity-repo",
        "readme_status": "ok",
        "readme_text": "# README\n\nInference serving with KV cache.",
    }
    readme_filter = _StubFilter()

    result = apply_readme_ai_second_pass(
        candidate,
        prompt="Decide whether the repository is relevant to AI inference systems.",
        readme_ai_filter=readme_filter,
    )

    assert result == {
        "keep": True,
        "reason_zh": "README 明确提到了推理服务与 KV cache。",
        "matched_signals": ["inference serving", "kv cache"],
    }
    assert readme_filter.calls[0]["repository"]["full_name"] == candidate["full_name"]
    assert "KV cache" in readme_filter.calls[0]["readme_text"]


@pytest.mark.parametrize(
    ("provider_payload", "message"),
    [
        ({}, "field 'keep' must be a boolean"),
        (
            {"keep": True, "matched_signals": ["kv cache"]},
            "field 'reason_zh' must be a string",
        ),
        (
            {"keep": True, "reason_zh": "ok", "matched_signals": "kv cache"},
            "field 'matched_signals' must be a list of strings",
        ),
    ],
)
def test_apply_readme_ai_second_pass_raises_for_malformed_provider_output(
    provider_payload: dict,
    message: str,
) -> None:
    from radar.sources.github.readme_ai_filter import apply_readme_ai_second_pass

    class _StubFilter:
        def evaluate(
            self,
            *,
            repository: dict,
            readme_text: str,
            prompt: str,
        ) -> dict:
            return provider_payload

    candidate = {
        "full_name": "example-org/high-activity-repo",
        "readme_status": "ok",
        "readme_text": "# README",
    }

    with pytest.raises(RuntimeError, match=message):
        apply_readme_ai_second_pass(
            candidate,
            prompt="Decide relevance.",
            readme_ai_filter=_StubFilter(),
        )


def test_apply_readme_ai_second_pass_raises_when_candidate_has_no_ok_readme() -> None:
    from radar.sources.github.readme_ai_filter import apply_readme_ai_second_pass

    class _StubFilter:
        def evaluate(
            self,
            *,
            repository: dict,
            readme_text: str,
            prompt: str,
        ) -> dict:
            return {"keep": True, "reason_zh": "ok", "matched_signals": []}

    candidate = {
        "full_name": "example-org/high-activity-repo",
        "readme_status": "fetch_error",
        "readme_text": "# README",
    }

    with pytest.raises(RuntimeError, match="requires readme_status='ok' with README text"):
        apply_readme_ai_second_pass(
            candidate,
            prompt="Decide relevance.",
            readme_ai_filter=_StubFilter(),
        )


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
