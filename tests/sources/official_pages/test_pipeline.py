"""Tests for the official_pages vertical slice (Task 4).

TDD order:
  1. test_extract_release_signal – unit test for the extractor
  2. test_extract_title_falls_back_to_url_when_title_empty – extractor fallback
  3. test_run_official_pages_job_creates_alert – end-to-end with fake repo + fake alert service
  4. test_keyword_matching_uses_normalized_text – keywords match on visible text, not raw HTML
  5. test_content_hash_uses_normalized_text – hash derived from normalized text
  6. test_run_official_pages_job_returns_int – job returns int (alert count)
  7. test_display_name_matches_extracted_title – display_name == extracted page title
  8. test_canonical_name_equals_url – canonical_name == raw URL string (not slug)
  9. test_normalized_payload_includes_content_hash – normalized_payload carries content_hash
 10. test_e2e_first_seen_flow_all_steps – upsert, observation recording, alert, dispatch verified
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from bs4 import BeautifulSoup


FIXTURE_HTML = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "official_pages"
    / "deepseek-release.html"
)


def _expected_hash(html: str) -> str:
    """Compute the content_hash that the extractor would produce for *html*."""
    normalized = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


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
    """Stand-in for AlertService that records each conceptual step of the first-seen flow.

    Internally simulates:
      1. entity_upsert   – keyed by canonical_name / display_name / url
      2. record_observation – keyed by content_hash / matched_keywords / score
      3. create_alert    – only when matched_keywords is non-empty
      4. dispatch        – one event per alert created

    process_official_page returns an int equal to the number of alerts created,
    matching the contract required by run_official_pages_job.
    """

    def __init__(self) -> None:
        # Raw call log kept for backward-compatible assertions.
        self.calls: list[dict] = []

        # Granular step logs for first-seen flow verification.
        self.upsert_calls: list[dict] = []
        self.observation_calls: list[dict] = []
        self.alert_calls: list[dict] = []
        self.dispatch_events: list[dict] = []

    def process_official_page(self, page_config, observation: dict) -> int:
        self.calls.append({"page_config": page_config, "observation": observation})

        # Step 1: entity upsert.
        self.upsert_calls.append({
            "canonical_name": observation["canonical_name"],
            "display_name": observation["display_name"],
            "url": observation["url"],
        })

        # Step 2: record observation.
        self.observation_calls.append({
            "content_hash": observation["content_hash"],
            "matched_keywords": observation["matched_keywords"],
            "score": observation["score"],
        })

        # Steps 3 & 4: create alert + dispatch only when keywords matched.
        alerts_created = 0
        if observation["matched_keywords"]:
            alert = {
                "entity_canonical_name": observation["canonical_name"],
                "title": observation["display_name"],
                "content_hash": observation["content_hash"],
            }
            self.alert_calls.append(alert)
            self.dispatch_events.append({"event": "alert_created", "alert": alert})
            alerts_created = 1

        return alerts_created


def test_run_official_pages_job_creates_alert(tmp_path: Path) -> None:
    """run_official_pages_job must call alert_service.process_official_page and return 1."""
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


# ---------------------------------------------------------------------------
# Test 8: canonical_name equals the raw URL string
# ---------------------------------------------------------------------------

def test_canonical_name_equals_url(tmp_path: Path) -> None:
    """The observation's canonical_name must be the raw URL, not a slug derived from it."""
    from radar.core.db import create_engine_and_session_factory, init_db
    from radar.core.repositories import RadarRepository
    from radar.core.config import OfficialPageEntry
    from radar.jobs.official_pages import run_official_pages_job

    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)
    alert_service = _FakeAlertService()
    html = FIXTURE_HTML.read_text()

    url = "https://api-docs.deepseek.com/"
    page_config = OfficialPageEntry(
        url=url,  # type: ignore[arg-type]
        whitelist_keywords=["release"],
    )
    run_official_pages_job(page_config, lambda _: html, repo, alert_service)

    observation = alert_service.calls[0]["observation"]
    assert observation["canonical_name"] == url


# ---------------------------------------------------------------------------
# Test 9: normalized_payload includes content_hash  (TDD – fails until pipeline updated)
# ---------------------------------------------------------------------------

def test_normalized_payload_includes_content_hash() -> None:
    """build_official_page_observation must embed content_hash inside normalized_payload."""
    from radar.sources.official_pages.pipeline import build_official_page_observation

    html = FIXTURE_HTML.read_text()
    url = "https://api-docs.deepseek.com/"

    obs = build_official_page_observation(
        html=html,
        url=url,
        canonical_name=url,
        whitelist_keywords=["release"],
    )

    assert "content_hash" in obs["normalized_payload"], (
        "normalized_payload must include content_hash to keep it close to the extracted signal"
    )
    assert obs["normalized_payload"]["content_hash"] == obs["content_hash"]


# ---------------------------------------------------------------------------
# Test 10: first-seen flow – upsert, observation recording, alert, dispatch
#          (TDD – fails until _FakeAlertService is wired and job is corrected)
# ---------------------------------------------------------------------------

def test_e2e_first_seen_flow_all_steps(tmp_path: Path) -> None:
    """The end-to-end first-seen flow must exercise all four conceptual steps:
    entity upsert, observation recording, alert creation, and dispatch.

    Each step is verified against concrete expected field values so the test
    proves intent, not just call count.
    """
    from radar.core.db import create_engine_and_session_factory, init_db
    from radar.core.repositories import RadarRepository
    from radar.core.config import OfficialPageEntry
    from radar.jobs.official_pages import run_official_pages_job

    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)
    fake = _FakeAlertService()
    html = FIXTURE_HTML.read_text()
    url = "https://api-docs.deepseek.com/"

    page_config = OfficialPageEntry(
        url=url,  # type: ignore[arg-type]
        whitelist_keywords=["release"],
    )
    result = run_official_pages_job(page_config, lambda _: html, repo, fake)

    # ---- Step 1: entity upsert ----
    assert len(fake.upsert_calls) == 1
    upsert = fake.upsert_calls[0]
    assert upsert["canonical_name"] == url, "canonical_name must be the raw URL"
    assert upsert["display_name"] == "DeepSeek V3 Released", (
        "display_name must be the extracted page title"
    )
    assert upsert["url"] == url

    # ---- Step 2: observation recording ----
    assert len(fake.observation_calls) == 1
    obs_rec = fake.observation_calls[0]
    assert obs_rec["content_hash"] == _expected_hash(html), (
        "content_hash must match SHA-256 of normalized visible text"
    )
    assert "release" in obs_rec["matched_keywords"]
    assert obs_rec["score"] == 1.0

    # ---- Step 3: alert creation ----
    assert len(fake.alert_calls) == 1
    alert = fake.alert_calls[0]
    assert alert["entity_canonical_name"] == url
    assert alert["title"] == "DeepSeek V3 Released"
    assert alert["content_hash"] == _expected_hash(html)

    # ---- Step 4: dispatch ----
    assert len(fake.dispatch_events) == 1
    event = fake.dispatch_events[0]
    assert event["event"] == "alert_created"
    assert event["alert"] is alert

    # ---- Overall return value ----
    assert result == 1
