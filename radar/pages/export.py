from __future__ import annotations

import json
from pathlib import Path

from radar.reports.builder import (
    build_feed_xml_from_reports,
    build_report_manifest_from_reports,
    build_report_payload,
)
from radar.reports.summarization import NullReportSummarizer

_RESULTS_UI_DIR = Path(__file__).resolve().parents[1] / "ui" / "results"


def _build_static_index() -> str:
    html = (_RESULTS_UI_DIR / "index.html").read_text()
    html = html.replace('href="/static/results/styles.css"', 'href="./styles.css"')
    html = html.replace(
        '<a class="ops-link" href="/ops">Open operations console</a>',
        '<span class="ops-link">GitHub Pages archive</span>',
    )
    html = html.replace(
        '<script src="/static/results/app.js" defer></script>',
        """<script>
      window.__RADAR_RESULTS_CONFIG__ = {
        mode: "static",
        manifestPath: "./manifest.json",
        reportBasePath: "./reports"
      };
    </script>
    <script src="./app.js" defer></script>""",
    )
    return html


def _load_existing_reports(output_dir: Path) -> list[dict]:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        return []

    data = json.loads(manifest_path.read_text())
    reports: list[dict] = []
    for entry in data.get("dates", []):
        report_path = output_dir / "reports" / f'{entry["date"]}.json'
        if report_path.exists():
            reports.append(json.loads(report_path.read_text()))
    return reports


def export_pages_site(repository, output_dir: Path, *, report_summarizer=None) -> None:
    if report_summarizer is None:
        report_summarizer = NullReportSummarizer()

    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "index.html").write_text(_build_static_index())
    (output_dir / "app.js").write_text((_RESULTS_UI_DIR / "app.js").read_text())
    (output_dir / "styles.css").write_text(
        (_RESULTS_UI_DIR / "styles.css").read_text()
    )

    reports = [
        build_report_payload(
            repository,
            day,
            report_summarizer=report_summarizer,
        )
        for day in repository.list_report_days()
    ]
    merged_reports = {report["date"]: report for report in _load_existing_reports(output_dir)}
    for report in reports:
        merged_reports[report["date"]] = report
    ordered_reports = [
        merged_reports[day] for day in sorted(merged_reports.keys(), reverse=True)
    ]
    manifest = build_report_manifest_from_reports(ordered_reports)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    for report in reports:
        (reports_dir / f'{report["date"]}.json').write_text(
            json.dumps(report, indent=2) + "\n"
        )
    (output_dir / "feed.xml").write_text(build_feed_xml_from_reports(ordered_reports))
