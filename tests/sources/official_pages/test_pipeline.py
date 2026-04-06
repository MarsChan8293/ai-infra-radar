"""Tests for the official_pages vertical slice (Task 4).

TDD order:
  1. test_extract_release_signal – unit test for the extractor
  2. test_run_official_pages_job_creates_alert – end-to-end with fake repo + fake alert service
"""
from __future__ import annotations

from pathlib import Path

import pytest


FIXTURE_HTML = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "official_pages"
    / "deepseek-release.html"
)


# ---------------------------------------------------------------------------
# Test 1: extractor unit test (written BEFORE the extractor exists)
# ---------------------------------------------------------------------------

def test_extract_release_signal_title_and_keywords() -> None:
    """extract_release_signal must return title from <h1> and match 'release' keyword."""
    from radar.sources.official_pages.extractor import extract_release_signal

    html = FIXTURE_HTML.read_text()
    url = "https://api-docs.deepseek.com/"
    keywords = ["release", "update"]

    signal = extract_release_signal(html=html, url=url, keywords=keywords)

    assert signal["title"] == "DeepSeek V3 Released"
    assert "release" in signal["matched_keywords"]


# ---------------------------------------------------------------------------
# Test 2: end-to-end job test with fake repo + fake alert service
# ---------------------------------------------------------------------------

class _FakeAlertService:
    """Minimal stand-in for AlertService that counts process_official_page calls."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def process_official_page(self, page_config, observation: dict) -> dict:
        self.calls.append({"page_config": page_config, "observation": observation})
        return {"created": 1}


def test_run_official_pages_job_creates_alert(tmp_path: Path) -> None:
    """run_official_pages_job must call alert_service.process_official_page and return created == 1."""
    from radar.core.db import create_engine_and_session_factory, init_db
    from radar.core.repositories import RadarRepository
    from radar.core.config import OfficialPageEntry
    from radar.jobs.official_pages import run_official_pages_job

    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    alert_service = _FakeAlertService()

    html = FIXTURE_HTML.read_text()

    page_config = OfficialPageEntry(
        url="https://api-docs.deepseek.com/",  # type: ignore[arg-type]
        whitelist_keywords=["release"],
    )

    result = run_official_pages_job(
        pages=[page_config],
        repo=repo,
        alert_service=alert_service,
        fetch_html=lambda url: html,
    )

    assert result["created"] == 1
    assert len(alert_service.calls) == 1
