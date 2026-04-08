from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from radar.cli import cli


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

    export_pages_site(repo, output_dir=tmp_path)

    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "app.js").exists()
    assert (tmp_path / "styles.css").exists()
    assert (tmp_path / "manifest.json").exists()

    index_html = (tmp_path / "index.html").read_text()
    assert "window.__RADAR_RESULTS_CONFIG__" in index_html
    assert "./manifest.json" in index_html
    assert "./reports" in index_html

    app_js = (tmp_path / "app.js").read_text()
    assert "manifestPath" in app_js
    assert "reportPath" in app_js

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["dates"][0]["count"] == 1

    report_path = tmp_path / "reports" / f'{manifest["dates"][0]["date"]}.json'
    assert report_path.exists()

    report = json.loads(report_path.read_text())
    assert report["summary"]["total_alerts"] == 1
    assert report["topics"][0]["topic"] == "github"
    assert report["topics"][0]["events"][0]["display_name"] == "acme/tool"


def test_export_pages_cli_runs(monkeypatch, tmp_path: Path) -> None:
    calls: list[Path] = []
    disposed: list[bool] = []

    class FakeEngine:
        def dispose(self) -> None:
            disposed.append(True)

    class FakeRuntime:
        def __init__(self) -> None:
            self.repo = object()
            self.engine = FakeEngine()

    def fake_build_runtime(path: Path) -> FakeRuntime:
        return FakeRuntime()

    def fake_export(repo, output_dir: Path) -> None:
        calls.append(output_dir)

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
    assert calls == [tmp_path / "site"]
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

    export_pages_site(repo, output_dir=tmp_path)

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    dates = [entry["date"] for entry in manifest["dates"]]
    assert historical_date in dates
    assert len(dates) == 2
    assert (tmp_path / "reports" / f"{historical_date}.json").exists()


def test_readme_mentions_github_pages_export() -> None:
    readme = Path("README.md").read_text()

    assert "GitHub Pages" in readme
    assert "export-pages" in readme


def test_pages_workflow_exists_and_supports_auto_and_manual_publish() -> None:
    workflow = Path(".github/workflows/deploy-pages.yml")

    assert workflow.exists()
    content = workflow.read_text()
    assert "workflow_dispatch:" in content
    assert "schedule:" in content
    assert "actions/deploy-pages" in content
    assert "export-pages" in content
