"""Tests for the official_pages vertical slice (Task 4).

TDD order:
  1. test_extract_release_signal – unit test for the extractor
  2. test_extract_title_falls_back_to_url_when_title_empty – extractor fallback
  3. test_run_official_pages_job_creates_alert – end-to-end with fake repo + fake alert service
  4. test_keyword_matching_uses_normalized_text – keywords match on visible text, not raw HTML
  5. test_content_hash_uses_normalized_text – hash derived from normalized text
  6. test_run_official_pages_job_returns_int – job returns int (alert count)
  7. test_display_name_matches_extracted_title – display_name == extracted page title
"""
from __future__ import annotations

from pathlib import Path


FIXTURE_HTML = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "official_pages"
    / "deepseek-release.html"
)


# ---------------------------------------------------------------------------
# Test 1: extractor unit test
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
# Test 2: extractor fallback: <h1> missing, <title> empty → url
# ---------------------------------------------------------------------------

def test_extract_title_falls_back_to_url_when_title_empty() -> None:
    """When <h1> is absent and <title> is empty/whitespace, title must equal the url."""
    from radar.sources.official_pages.extractor import extract_release_signal

    html = "<html><head><title>   </title></head><body></body></html>"
    url = "https://example.com/release"

    signal = extract_release_signal(html=html, url=url, keywords=[])

    assert signal["title"] == url


# ---------------------------------------------------------------------------
# Test 3: end-to-end job test with fake repo + fake alert service
# ---------------------------------------------------------------------------

class _FakeAlertService:
    """Minimal stand-in for AlertService that counts process_official_page calls."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def process_official_page(self, page_config, observation: dict) -> dict:
        self.calls.append({"page_config": page_config, "observation": observation})
        return {"created": 1}


def test_run_official_pages_job_creates_alert(tmp_path: Path) -> None:
    """run_official_pages_job(page_config, fetch_html, repository, alert_service) must
    call alert_service.process_official_page and return created == 1."""
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
        page_config,
        lambda url: html,
        repo,
        alert_service,
    )

    assert result == 1
    assert len(alert_service.calls) == 1


# ---------------------------------------------------------------------------
# Test 4: keyword matching ignores raw HTML tags/attributes
# ---------------------------------------------------------------------------

def test_keyword_matching_uses_normalized_text() -> None:
    """Keywords must only match visible text, not raw HTML attributes or script content."""
    from radar.sources.official_pages.extractor import extract_release_signal

    # "release" appears only inside a <script> block and an HTML attribute, NOT in visible text.
    html = (
        '<html><head><script>var release="1.0";</script></head>'
        '<body><a href="/release-notes">Download</a></body></html>'
    )
    signal = extract_release_signal(html=html, url="https://example.com", keywords=["release"])
    # Should NOT match: "release" is only in script/attribute, not visible text.
    assert "release" not in signal["matched_keywords"]


# ---------------------------------------------------------------------------
# Test 5: content_hash derived from normalized visible text
# ---------------------------------------------------------------------------

def test_content_hash_uses_normalized_text() -> None:
    """Two HTML pages with same visible text but different whitespace/markup produce same hash."""
    import hashlib
    from bs4 import BeautifulSoup
    from radar.sources.official_pages.extractor import extract_release_signal

    html_a = "<html><body><p>Hello world</p></body></html>"
    html_b = "<html><body><div>Hello world</div></body></html>"

    sig_a = extract_release_signal(html=html_a, url="https://x.com", keywords=[])
    sig_b = extract_release_signal(html=html_b, url="https://x.com", keywords=[])

    # Both normalized to "Hello world"; hashes must match.
    expected = hashlib.sha256(
        BeautifulSoup(html_a, "html.parser").get_text(" ", strip=True).lower().encode()
    ).hexdigest()
    assert sig_a["content_hash"] == expected
    assert sig_a["content_hash"] == sig_b["content_hash"]


# ---------------------------------------------------------------------------
# Test 6: run_official_pages_job returns int
# ---------------------------------------------------------------------------

def test_run_official_pages_job_returns_int(tmp_path: Path) -> None:
    """run_official_pages_job must return an int (number of alerts created)."""
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
    result = run_official_pages_job(page_config, lambda url: html, repo, alert_service)

    assert isinstance(result, int)
    assert result == 1


# ---------------------------------------------------------------------------
# Test 7: display_name matches extracted page title
# ---------------------------------------------------------------------------

def test_display_name_matches_extracted_title(tmp_path: Path) -> None:
    """The observation's display_name must equal the extracted page title, not a URL slug."""
    from radar.core.db import create_engine_and_session_factory, init_db
    from radar.core.repositories import RadarRepository
    from radar.core.config import OfficialPageEntry
    from radar.jobs.official_pages import run_official_pages_job

    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)
    alert_service = _FakeAlertService()
    html = FIXTURE_HTML.read_text()  # <h1>DeepSeek V3 Released</h1>

    page_config = OfficialPageEntry(
        url="https://api-docs.deepseek.com/",  # type: ignore[arg-type]
        whitelist_keywords=["release"],
    )
    run_official_pages_job(page_config, lambda url: html, repo, alert_service)

    observation = alert_service.calls[0]["observation"]
    # display_name must be the extracted <h1> title, NOT a URL-derived slug.
    assert observation["display_name"] == "DeepSeek V3 Released"
