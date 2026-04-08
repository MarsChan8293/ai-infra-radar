from __future__ import annotations

import json
from pathlib import Path

from radar.api.routes.reports import build_report_manifest, build_report_payload

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


def _load_existing_entries(output_dir: Path) -> list[dict]:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        return []

    data = json.loads(manifest_path.read_text())
    entries: list[dict] = []
    for entry in data.get("dates", []):
        if (output_dir / "reports" / f'{entry["date"]}.json').exists():
            entries.append(entry)
    return entries


def export_pages_site(repository, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "index.html").write_text(_build_static_index())
    (output_dir / "app.js").write_text((_RESULTS_UI_DIR / "app.js").read_text())
    (output_dir / "styles.css").write_text(
        (_RESULTS_UI_DIR / "styles.css").read_text()
    )

    current_manifest = build_report_manifest(repository)
    merged_entries = {
        entry["date"]: entry for entry in _load_existing_entries(output_dir)
    }
    for entry in current_manifest["dates"]:
        merged_entries[entry["date"]] = entry
    manifest = {
        "generated_at": current_manifest["generated_at"],
        "dates": [
        merged_entries[day] for day in sorted(merged_entries.keys(), reverse=True)
        ],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    for entry in current_manifest["dates"]:
        report = build_report_payload(repository, entry["date"])
        (reports_dir / f'{entry["date"]}.json').write_text(
            json.dumps(report, indent=2) + "\n"
        )
