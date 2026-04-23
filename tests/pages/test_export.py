from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from radar.app import create_app
from radar.cli import cli
from radar.reports.summarization import NullReportSummarizer


def test_export_pages_writes_static_shell_manifest_and_daily_json(
    tmp_path: Path, repo
) -> None:
    from radar.pages.export import export_pages_site

    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="github:acme/tool",
        display_name="acme/tool",
        url="https://github.com/acme/tool",
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.8,
        dedupe_key="github:burst:export",
        reason={"full_name": "acme/tool"},
    )

    export_pages_site(
        repo,
        output_dir=tmp_path,
        report_summarizer=NullReportSummarizer(),
    )

    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "app.js").exists()
    assert (tmp_path / "styles.css").exists()
    assert (tmp_path / "manifest.json").exists()

    index_html = (tmp_path / "index.html").read_text()
    assert "window.__RADAR_RESULTS_CONFIG__" in index_html
    assert "./manifest.json" in index_html
    assert "./reports" in index_html
    assert "./feed.xml" in index_html
    assert 'href="/ops"' not in index_html
    assert 'id="search-input"' in index_html
    assert 'id="language-toggle"' in index_html
    assert 'id="feed-link"' in index_html

    app_js = (tmp_path / "app.js").read_text()
    assert "manifestPath" in app_js
    assert "reportPath" in app_js
    assert "window.location.hash" in app_js
    assert "loadReportForCurrentState" in app_js

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["dates"][0]["count"] == 1

    report_path = tmp_path / "reports" / f'{manifest["dates"][0]["date"]}.json'
    assert report_path.exists()

    report = json.loads(report_path.read_text())
    assert report["summary"]["total_alerts"] == 1
    assert report["topics"][0]["topic"] == "github"
    assert report["topics"][0]["events"][0]["display_name"] == "acme/tool"


def test_export_pages_site_uses_deduplicated_daily_report(
    tmp_path: Path, repo
) -> None:
    from radar.pages.export import export_pages_site

    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="github:acme/tool",
        display_name="acme/tool",
        url="https://github.com/acme/tool",
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.4,
        dedupe_key="github:burst:export:low",
        reason={"full_name": "acme/tool"},
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.9,
        dedupe_key="github:burst:export:high",
        reason={"full_name": "acme/tool"},
    )

    export_pages_site(
        repo,
        output_dir=tmp_path,
        report_summarizer=NullReportSummarizer(),
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    report = json.loads((tmp_path / "reports" / f'{manifest["dates"][0]["date"]}.json').read_text())

    assert manifest["dates"][0]["count"] == 1
    assert report["summary"]["total_alerts"] == 1
    assert report["topics"][0]["events"][0]["score"] == 0.9


def test_export_manifest_matches_live_manifest_briefing_availability(
    tmp_path: Path, repo
) -> None:
    from radar.pages.export import export_pages_site

    class BriefingSummarizer:
        def summarize_entry(self, entry: dict[str, object]) -> dict[str, str | None]:
            return {
                "title_zh": None,
                "reason_text_zh": None,
                "reason_text_en": None,
            }

        def summarize_daily_briefing(
            self, *, date: str, entries: list[dict[str, object]]
        ) -> dict[str, str | None]:
            return {"briefing_zh": f"{date} zh", "briefing_en": f"{date} en"}

        def close(self) -> None:
            return None

    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="github:acme/tool",
        display_name="acme/tool",
        url="https://github.com/acme/tool",
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.8,
        dedupe_key="github:burst:parity",
        reason={"full_name": "acme/tool"},
    )

    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.settings = None
    app.state.config_path = None
    app.state.report_summarizer = BriefingSummarizer()
    live_manifest = TestClient(app).get("/reports/manifest").json()

    export_pages_site(repo, output_dir=tmp_path, report_summarizer=BriefingSummarizer())

    static_manifest = json.loads((tmp_path / "manifest.json").read_text())

    assert static_manifest["dates"][0]["briefing_available"] is False
    assert (
        static_manifest["dates"][0]["briefing_available"]
        == live_manifest["dates"][0]["briefing_available"]
    )


def test_export_pages_cli_runs(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[Path, object]] = []
    disposed: list[bool] = []
    closed: list[bool] = []
    readme_ai_filter_closed: list[bool] = []

    class FakeSummarizer:
        def close(self) -> None:
            closed.append(True)

    report_summarizer = FakeSummarizer()

    class FakeEngine:
        def dispose(self) -> None:
            disposed.append(True)

    class FakeReadmeAIFilter:
        def close(self) -> None:
            readme_ai_filter_closed.append(True)

    class FakeRuntime:
        def __init__(self) -> None:
            self.repo = object()
            self.engine = FakeEngine()
            self.report_summarizer = report_summarizer
            self.github_readme_ai_filter = FakeReadmeAIFilter()

    def fake_build_runtime(path: Path) -> FakeRuntime:
        return FakeRuntime()

    def fake_export(repo, output_dir: Path, *, report_summarizer) -> None:
        calls.append((output_dir, report_summarizer))

    monkeypatch.setattr("radar.cli.build_runtime", fake_build_runtime)
    monkeypatch.setattr("radar.cli.export_pages_site", fake_export)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "export-pages",
            "--config",
            str(tmp_path / "radar.yaml"),
            "--output",
            str(tmp_path / "site"),
        ],
    )

    assert result.exit_code == 0
    assert calls == [(tmp_path / "site", report_summarizer)]
    assert closed == [True]
    assert readme_ai_filter_closed == [True]
    assert disposed == [True]
    assert "pages exported to" in result.output


def test_export_pages_preserves_existing_historical_reports(
    tmp_path: Path, repo
) -> None:
    from radar.pages.export import export_pages_site

    historical_date = "2026-04-07"
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "reports" / f"{historical_date}.json").write_text(
        json.dumps(
            {
                "date": historical_date,
                "summary": {"total_alerts": 2, "top_sources": [], "max_score": 0.7},
                "topics": [],
            }
        )
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-04-07T00:00:00+00:00",
                "dates": [
                    {
                        "date": historical_date,
                        "count": 2,
                        "topics": ["github"],
                    }
                ],
            }
        )
    )

    entity = repo.upsert_entity(
        source="modelscope",
        entity_type="model",
        canonical_name="modelscope:Qwen/Qwen3",
        display_name="Qwen/Qwen3",
        url="https://www.modelscope.cn/models/Qwen/Qwen3",
    )
    repo.create_alert(
        alert_type="modelscope_model_new",
        entity_id=entity.id,
        source="modelscope",
        score=1.0,
        dedupe_key="modelscope:new:history",
        reason={"model_id": "Qwen/Qwen3"},
    )

    export_pages_site(
        repo,
        output_dir=tmp_path,
        report_summarizer=NullReportSummarizer(),
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    dates = [entry["date"] for entry in manifest["dates"]]
    assert historical_date in dates
    assert len(dates) == 2
    assert (tmp_path / "reports" / f"{historical_date}.json").exists()


def test_export_pages_writes_feed_and_enriched_report_fields(
    tmp_path: Path, repo
) -> None:
    from radar.pages.export import export_pages_site

    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="github:acme/tool",
        display_name="acme/tool",
        url="https://github.com/acme/tool",
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.8,
        dedupe_key="github:burst:feed",
        reason={"full_name": "acme/tool"},
    )

    export_pages_site(
        repo,
        output_dir=tmp_path,
        report_summarizer=NullReportSummarizer(),
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    report = json.loads((tmp_path / "reports" / f'{manifest["dates"][0]["date"]}.json').read_text())

    assert (tmp_path / "feed.xml").exists()
    assert "filters" in report
    assert "briefing_zh" in report["summary"]
    assert "briefing_en" in report["summary"]
    assert "search_text" in report["topics"][0]["events"][0]


def test_export_pages_site_reuses_built_reports_for_manifest_and_feed(
    tmp_path: Path, repo
) -> None:
    from radar.pages.export import export_pages_site

    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="github:acme/tool",
        display_name="acme/tool",
        url="https://github.com/acme/tool",
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.8,
        dedupe_key="github:burst:reuse",
        reason={"full_name": "acme/tool"},
    )

    class CountingSummarizer:
        def __init__(self) -> None:
            self.entry_calls = 0
            self.briefing_calls = 0

        def summarize_entry(self, entry: dict) -> dict[str, str | None]:
            self.entry_calls += 1
            return {"title_zh": None, "reason_text_zh": None, "reason_text_en": "summary"}

        def summarize_daily_briefing(
            self, *, date: str, entries: list[dict]
        ) -> dict[str, str | None]:
            self.briefing_calls += 1
            return {"briefing_zh": "日报", "briefing_en": "briefing"}

        def close(self) -> None:
            return None

    summarizer = CountingSummarizer()

    export_pages_site(
        repo,
        output_dir=tmp_path,
        report_summarizer=summarizer,
    )

    assert summarizer.entry_calls == 1
    assert summarizer.briefing_calls == 1


def test_export_pages_feed_matches_live_seven_day_window(
    tmp_path: Path, repo
) -> None:
    from radar.api.routes.feed import build_feed_xml
    from radar.pages.export import export_pages_site

    for day in range(1, 10):
        entity = repo.upsert_entity(
            source="github",
            entity_type="repository",
            canonical_name=f"github:acme/tool-{day}",
            display_name=f"acme/tool-{day}",
            url=f"https://github.com/acme/tool-{day}",
        )
        alert = repo.create_alert(
            alert_type="github_burst",
            entity_id=entity.id,
            source="github",
            score=0.8,
            dedupe_key=f"github:burst:window:{day}",
            reason={"full_name": f"acme/tool-{day}"},
        )
        with repo._session_factory() as session:
            session_alert = session.get(type(alert), alert.id)
            session_alert.created_at = datetime(2026, 4, day, 12, tzinfo=timezone.utc)
            session.commit()

    summarizer = NullReportSummarizer()

    export_pages_site(
        repo,
        output_dir=tmp_path,
        report_summarizer=summarizer,
    )

    exported_feed = (tmp_path / "feed.xml").read_text()
    live_feed = build_feed_xml(repo, report_summarizer=summarizer)

    assert exported_feed == live_feed
    assert "acme/tool-1" not in exported_feed
    assert "acme/tool-9" in exported_feed


def test_export_pages_feed_matches_live_feed_when_preserved_reports_exist(
    tmp_path: Path, repo
) -> None:
    from radar.api.routes.feed import build_feed_xml
    from radar.pages.export import export_pages_site

    preserved_date = "2026-04-08"
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    preserved_report = {
        "date": preserved_date,
        "summary": {
            "total_alerts": 1,
            "top_sources": [{"source": "github", "count": 1}],
            "max_score": 0.8,
            "briefing_zh": None,
            "briefing_en": None,
        },
        "filters": {
            "sources": [{"value": "github", "count": 1}],
            "alert_types": [{"value": "github_burst", "count": 1}],
            "score_bands": [{"value": "high", "count": 1}],
            "topic_tags": [{"value": "github", "count": 1}],
        },
        "topics": [
            {
                "topic": "github",
                "count": 1,
                "events": [
                    {
                        "id": 101,
                        "display_name": "acme/preserved",
                        "url": "https://github.com/acme/preserved",
                        "created_at": "2026-04-08T12:00:00+00:00",
                        "reason": {"full_name": "acme/preserved"},
                        "reason_text_zh": None,
                        "reason_text_en": "preserved summary",
                    }
                ],
            }
        ],
    }
    (tmp_path / "reports" / f"{preserved_date}.json").write_text(
        json.dumps(preserved_report)
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-04-08T12:00:00+00:00",
                "dates": [
                    {
                        "date": preserved_date,
                        "count": 1,
                        "topics": ["github"],
                        "filter_counts": {
                            "sources": 1,
                            "alert_types": 1,
                            "score_bands": 1,
                            "topic_tags": 1,
                        },
                        "briefing_available": False,
                    }
                ],
            }
        )
    )

    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="github:acme/current",
        display_name="acme/current",
        url="https://github.com/acme/current",
    )
    alert = repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.9,
        dedupe_key="github:burst:current-feed-window",
        reason={"full_name": "acme/current"},
    )
    with repo._session_factory() as session:
        session_alert = session.get(type(alert), alert.id)
        session_alert.created_at = datetime(2026, 4, 9, 12, tzinfo=timezone.utc)
        session.commit()

    export_pages_site(
        repo,
        output_dir=tmp_path,
        report_summarizer=NullReportSummarizer(),
    )

    exported_feed = (tmp_path / "feed.xml").read_text()
    live_feed = build_feed_xml(repo, report_summarizer=NullReportSummarizer())

    assert exported_feed == live_feed
    assert "acme/current" in exported_feed
    assert "acme/preserved" not in exported_feed


def test_readme_mentions_github_pages_export() -> None:
    readme = Path("README.md").read_text()

    assert "GitHub Pages" in readme
    assert "export-pages" in readme


def test_pages_workflow_exists_and_supports_manual_publish() -> None:
    workflow = Path(".github/workflows/deploy-pages.yml")

    assert workflow.exists()
    content = workflow.read_text()
    assert "workflow_dispatch:" in content
    assert "schedule:" not in content
    assert "concurrency:" in content
    assert "ref:" in content
    assert "actions/deploy-pages" in content
    assert "export-pages" in content
    assert "git push origin HEAD:" in content
