"""Smoke tests covering the three MVP paths end-to-end (no real network calls)."""
from __future__ import annotations

from pydantic import HttpUrl

from radar.core.config import OfficialPageEntry
from radar.jobs.daily_digest import run_daily_digest_job
from radar.jobs.github_burst import run_github_burst_job
from radar.jobs.official_pages import run_official_pages_job


# ---------------------------------------------------------------------------
# Path 1 – Official page
# ---------------------------------------------------------------------------

def test_official_page_path_creates_alert(repo, alert_service) -> None:
    """Full official-page path: fake HTML → observation → alert persisted."""
    html = "<html><title>v2 release</title><body>new release v2 available</body></html>"
    page_config = OfficialPageEntry(
        url=HttpUrl("https://example.com/releases"),
        whitelist_keywords=["release"],
    )

    created = run_official_pages_job(
        page_config=page_config,
        fetch_html=lambda _url: html,
        repository=repo,
        alert_service=alert_service,
    )

    assert created == 1
    alerts = repo.list_alerts()
    assert len(alerts) == 1
    assert alerts[0].alert_type == "official_release"


def test_official_page_path_deduplicates(repo, alert_service) -> None:
    """Running the same page twice with identical content yields only one alert."""
    html = "<html><body>release v3</body></html>"
    page_config = OfficialPageEntry(
        url=HttpUrl("https://example.com/releases"),
        whitelist_keywords=["release"],
    )
    fetch_html = lambda _url: html

    run_official_pages_job(
        page_config=page_config, fetch_html=fetch_html,
        repository=repo, alert_service=alert_service,
    )
    run_official_pages_job(
        page_config=page_config, fetch_html=fetch_html,
        repository=repo, alert_service=alert_service,
    )

    assert len(repo.list_alerts()) == 1


# ---------------------------------------------------------------------------
# Path 2 – GitHub burst
# ---------------------------------------------------------------------------

def test_github_burst_path_creates_alert(repo, alert_service) -> None:
    """Full GitHub burst path: above-threshold item → alert persisted."""
    item = {
        "full_name": "acme/supermodel",
        "html_url": "https://github.com/acme/supermodel",
        "stargazers_count": 5000,
        "forks_count": 800,
    }

    created = run_github_burst_job(
        search_items=[item],
        threshold=0.0,
        repository=repo,
        alert_service=alert_service,
    )

    assert created == 1
    alerts = repo.list_alerts()
    assert len(alerts) == 1
    assert alerts[0].alert_type == "github_burst"


def test_github_burst_path_below_threshold_skips(repo, alert_service) -> None:
    """Items whose burst score is below threshold must not create an alert."""
    item = {
        "full_name": "acme/tiny",
        "html_url": "https://github.com/acme/tiny",
        "stargazers_count": 0,
        "forks_count": 0,
    }

    created = run_github_burst_job(
        search_items=[item],
        threshold=0.99,  # effectively unreachable score
        repository=repo,
        alert_service=alert_service,
    )

    assert created == 0
    assert repo.list_alerts() == []


# ---------------------------------------------------------------------------
# Path 3 – Daily digest
# ---------------------------------------------------------------------------

def _seed_alert(repo, source: str, score: float, idx: int = 0):
    entity = repo.upsert_entity(
        source=source,
        entity_type="repository",
        canonical_name=f"org/smoke-{source}-{score}-{idx}",
        display_name="Smoke repo",
        url=f"https://github.com/org/smoke-{source}-{score}-{idx}",
    )
    return repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source=source,
        score=score,
        dedupe_key=f"smoke:{source}:{score}:{idx}",
        reason={},
    )


def test_daily_digest_path_dispatches_payload(repo) -> None:
    """Digest job with seeded alerts dispatches exactly one payload."""
    _seed_alert(repo, "github", 0.9)
    _seed_alert(repo, "official_pages", 0.7)

    dispatched = []
    result = run_daily_digest_job(repo, dispatch=dispatched.append)

    assert result == 1
    assert len(dispatched) == 1
    payload = dispatched[0]
    assert payload["type"] == "daily_digest"
    assert payload["count"] == 2


def test_daily_digest_path_empty_repo_returns_0(repo) -> None:
    """Digest job with no alerts must return 0 and not dispatch."""
    dispatched = []
    result = run_daily_digest_job(repo, dispatch=dispatched.append)
    assert result == 0
    assert dispatched == []
