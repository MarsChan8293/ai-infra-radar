# Results Browser + GitHub Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current operations-console UI with a radar-results browser that reads grouped monitoring results by date/topic, and add static export so the same result archive can be published to GitHub Pages.

**Architecture:** Keep the product as a single FastAPI service with a thin static frontend, but shift the UI from “control panel” to “results reader”. Add backend read APIs that expose date-grouped result snapshots and a deterministic summary model, then add a static exporter that writes the same view-model as JSON plus a static shell for GitHub Pages deployment. Reuse one visual language and one data contract for both `/ui` and Pages, while moving operational controls out of the main browsing surface.

**Tech Stack:** FastAPI, Typer, SQLAlchemy, plain HTML/CSS/JavaScript, pytest, GitHub Actions Pages deploy

---

### Task 1: Add grouped result-query APIs for the browser

**Files:**
- Modify: `radar/core/repositories.py`
- Create: `radar/api/routes/reports.py`
- Modify: `radar/app.py`
- Test: `tests/api/test_reports.py`

- [ ] **Step 1: Write the failing API tests**

```python
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from radar.app import create_app


def test_reports_manifest_groups_alert_days(repo) -> None:
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
        score=0.9,
        dedupe_key="github:burst:1",
        reason={"full_name": "acme/tool"},
    )

    app = create_app()
    app.state.repo = repo
    client = TestClient(app)

    response = client.get("/reports/manifest")

    assert response.status_code == 200
    body = response.json()
    assert body["dates"][0]["date"]
    assert "github" in body["dates"][0]["topics"]


def test_reports_date_endpoint_returns_summary_and_events(repo) -> None:
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
        dedupe_key="modelscope:new:Qwen/Qwen3",
        reason={"model_id": "Qwen/Qwen3"},
    )

    app = create_app()
    app.state.repo = repo
    client = TestClient(app)

    manifest = client.get("/reports/manifest").json()
    date_str = manifest["dates"][0]["date"]

    response = client.get(f"/reports/{date_str}")

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == date_str
    assert body["summary"]["total_alerts"] == 1
    assert body["summary"]["top_sources"][0]["source"] == "modelscope"
    assert body["topics"][0]["topic"] == "modelscope"
    assert body["topics"][0]["events"][0]["display_name"] == "Qwen/Qwen3"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/api/test_reports.py -q`
Expected: FAIL with `ModuleNotFoundError` for `radar.api.routes.reports` or missing `/reports/*` routes.

- [ ] **Step 3: Write the minimal repository and route implementation**

```python
# radar/core/repositories.py
from sqlalchemy import select


def list_report_days(self) -> list[str]:
    with self._session_factory() as session:
        rows = session.execute(
            select(Alert.created_at).order_by(Alert.created_at.desc())
        ).all()
        seen: list[str] = []
        for created_at, in rows:
            day = created_at.date().isoformat()
            if day not in seen:
                seen.append(day)
        return seen


def list_alerts_for_day(self, day: str) -> list[dict]:
    start = datetime.fromisoformat(f"{day}T00:00:00+00:00")
    end = start + timedelta(days=1)
    with self._session_factory() as session:
        rows = session.execute(
            select(Alert, Entity)
            .join(Entity, Entity.id == Alert.entity_id)
            .where(Alert.created_at >= start, Alert.created_at < end)
            .order_by(Alert.score.desc(), Alert.id.desc())
        ).all()
        return [
            {
                "id": alert.id,
                "alert_type": alert.alert_type,
                "source": alert.source,
                "score": alert.score,
                "status": alert.status,
                "reason": alert.reason,
                "created_at": alert.created_at.isoformat(),
                "display_name": entity.display_name,
                "canonical_name": entity.canonical_name,
                "url": entity.url,
            }
            for alert, entity in rows
        ]
```

```python
# radar/api/routes/reports.py
from collections import Counter, defaultdict

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/reports", tags=["reports"])


def _group_events(events: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        grouped[event["source"]].append(event)
    return [
        {"topic": topic, "count": len(items), "events": items}
        for topic, items in sorted(grouped.items())
    ]


@router.get("/manifest")
def get_reports_manifest(request: Request) -> dict:
    repo = request.app.state.repo
    if repo is None:
        return {"generated_at": None, "dates": []}
    dates = []
    for day in repo.list_report_days():
        events = repo.list_alerts_for_day(day)
        dates.append(
            {
                "date": day,
                "count": len(events),
                "topics": sorted({event["source"] for event in events}),
            }
        )
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "dates": dates}


@router.get("/{day}")
def get_report_for_day(day: str, request: Request) -> dict:
    repo = request.app.state.repo
    if repo is None:
        raise HTTPException(status_code=404, detail="report not found")
    events = repo.list_alerts_for_day(day)
    if not events:
        raise HTTPException(status_code=404, detail="report not found")
    source_counts = Counter(event["source"] for event in events)
    return {
        "date": day,
        "summary": {
            "total_alerts": len(events),
            "top_sources": [
                {"source": source, "count": count}
                for source, count in source_counts.most_common()
            ],
            "max_score": max(event["score"] for event in events),
        },
        "topics": _group_events(events),
    }
```

```python
# radar/app.py
from radar.api.routes.reports import router as reports_router


app.include_router(reports_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/api/test_reports.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add radar/core/repositories.py radar/api/routes/reports.py radar/app.py tests/api/test_reports.py
git commit -m "feat: add report browsing APIs"
```

### Task 2: Replace the operations console with a results-browser UI

**Files:**
- Modify: `radar/ui/index.html`
- Modify: `radar/ui/styles.css`
- Modify: `radar/ui/app.js`
- Modify: `tests/api/test_ui.py`

- [ ] **Step 1: Write the failing UI tests**

```python
from fastapi.testclient import TestClient

from radar.app import create_app


def test_ui_shell_contains_results_browser_regions() -> None:
    client = TestClient(create_app())

    response = client.get("/ui")

    assert response.status_code == 200
    assert 'id="date-list"' in response.text
    assert 'id="topic-list"' in response.text
    assert 'id="report-summary"' in response.text
    assert 'id="report-events"' in response.text


def test_ui_script_loads_manifest_and_report_views() -> None:
    client = TestClient(create_app())

    response = client.get("/static/ui/app.js")

    assert response.status_code == 200
    assert 'fetchJson("/reports/manifest")' in response.text
    assert 'fetchJson(`/reports/${date}`)' in response.text
    assert "renderManifest" in response.text
    assert "renderReport" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/api/test_ui.py -q`
Expected: FAIL because the shell still exposes the operations-console structure.

- [ ] **Step 3: Write the minimal browser implementation**

```html
<!-- radar/ui/index.html -->
<main class="layout">
  <aside class="sidebar">
    <section class="sidebar-panel">
      <h2>Dates</h2>
      <ul id="date-list" class="nav-list"></ul>
    </section>
    <section class="sidebar-panel">
      <h2>Topics</h2>
      <ul id="topic-list" class="nav-list"></ul>
    </section>
  </aside>

  <section class="content">
    <header class="report-header">
      <h1>AI Infra Radar</h1>
      <p id="report-subtitle">Select a day to browse monitoring results.</p>
    </header>
    <article id="report-summary" class="summary-card"></article>
    <section id="report-events" class="events-list"></section>
  </section>
</main>
```

```javascript
// radar/ui/app.js
let manifestState = { dates: [] };
let activeDate = null;
let activeTopic = "all";

function renderManifest(manifest) {
  manifestState = manifest;
  const list = document.getElementById("date-list");
  list.innerHTML = "";
  for (const entry of manifest.dates) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${entry.date} (${entry.count})`;
    button.addEventListener("click", () => loadReport(entry.date));
    list.appendChild(button);
  }
}

function renderReport(report) {
  const summary = document.getElementById("report-summary");
  const topics = document.getElementById("topic-list");
  const events = document.getElementById("report-events");
  summary.textContent =
    `Alerts: ${report.summary.total_alerts}\n` +
    `Top sources: ${report.summary.top_sources.map((x) => `${x.source}(${x.count})`).join(", ")}`;
  topics.innerHTML = "";
  for (const topic of [{ topic: "all", count: report.summary.total_alerts }, ...report.topics]) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${topic.topic} (${topic.count})`;
    button.addEventListener("click", () => {
      activeTopic = topic.topic;
      renderEvents(report);
    });
    topics.appendChild(button);
  }
  renderEvents(report);
}

function renderEvents(report) {
  const events = document.getElementById("report-events");
  const groups = activeTopic === "all" ? report.topics : report.topics.filter((x) => x.topic === activeTopic);
  events.innerHTML = groups
    .flatMap((group) => group.events)
    .map((event) => `<article class="event-card"><h3>${event.display_name}</h3><p>${event.alert_type}</p></article>`)
    .join("");
}

async function loadManifest() {
  const manifest = await fetchJson("/reports/manifest");
  renderManifest(manifest);
  if (manifest.dates.length > 0) {
    await loadReport(manifest.dates[0].date);
  }
}

async function loadReport(date) {
  activeDate = date;
  activeTopic = "all";
  const report = await fetchJson(`/reports/${date}`);
  renderReport(report);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/api/test_ui.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add radar/ui/index.html radar/ui/styles.css radar/ui/app.js tests/api/test_ui.py
git commit -m "feat: redesign results browser UI"
```

### Task 3: Export static daily snapshots for GitHub Pages

**Files:**
- Create: `radar/pages/export.py`
- Modify: `radar/cli.py`
- Test: `tests/pages/test_export.py`
- Modify: `tests/core/test_config.py`

- [ ] **Step 1: Write the failing exporter tests**

```python
from pathlib import Path


def test_export_pages_writes_manifest_and_daily_json(tmp_path: Path, repo) -> None:
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
    assert (tmp_path / "manifest.json").exists()
    manifest = (tmp_path / "manifest.json").read_text()
    assert "dates" in manifest


def test_export_pages_cli_runs(monkeypatch, tmp_path: Path) -> None:
    from typer.testing import CliRunner
    from radar.cli import cli

    calls = []

    def fake_export(runtime, output_dir):
        calls.append(output_dir)

    monkeypatch.setattr("radar.cli.export_pages_site", fake_export)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["export-pages", "--config", str(tmp_path / "radar.yaml"), "--output", str(tmp_path / "site")],
    )

    assert result.exit_code == 0
    assert calls == [tmp_path / "site"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/pages/test_export.py tests/core/test_config.py -q`
Expected: FAIL because there is no exporter module or `export-pages` CLI command yet.

- [ ] **Step 3: Write the minimal static exporter**

```python
# radar/pages/export.py
import json
from pathlib import Path


def export_pages_site(runtime, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ui_dir = Path(__file__).resolve().parents[1] / "ui"
    (output_dir / "index.html").write_text((ui_dir / "index.html").read_text())
    (output_dir / "styles.css").write_text((ui_dir / "styles.css").read_text())
    (output_dir / "app.js").write_text((ui_dir / "app.js").read_text())

    dates = []
    for day in runtime.repo.list_report_days():
        events = runtime.repo.list_alerts_for_day(day)
        topics = sorted({event["source"] for event in events})
        dates.append({"date": day, "count": len(events), "topics": topics})
        daily_path = output_dir / "reports" / f"{day}.json"
        daily_path.parent.mkdir(parents=True, exist_ok=True)
        daily_path.write_text(json.dumps({"date": day, "events": events}, indent=2) + "\n")

    (output_dir / "manifest.json").write_text(
        json.dumps({"dates": dates}, indent=2) + "\n"
    )
```

```python
# radar/cli.py
from radar.pages.export import export_pages_site


@cli.command("export-pages")
def export_pages(
    config: Path = typer.Option(..., "--config", help="Path to radar.yaml"),
    output: Path = typer.Option(..., "--output", help="Directory to write static site"),
) -> None:
    runtime = build_runtime(config)
    try:
        export_pages_site(runtime, output)
        typer.echo(f"pages exported to {output}")
    finally:
        runtime.engine.dispose()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/pages/test_export.py tests/core/test_config.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add radar/pages/export.py radar/cli.py tests/pages/test_export.py tests/core/test_config.py
git commit -m "feat: export static pages site"
```

### Task 4: Add GitHub Pages deployment workflow and documentation

**Files:**
- Create: `.github/workflows/deploy-pages.yml`
- Modify: `README.md`
- Test: `tests/api/test_ui.py`

- [ ] **Step 1: Write the failing docs/workflow checks**

```python
from pathlib import Path


def test_readme_mentions_github_pages_export() -> None:
    readme = Path("README.md").read_text()
    assert "export-pages" in readme
    assert "GitHub Pages" in readme


def test_pages_workflow_exists() -> None:
    workflow = Path(".github/workflows/deploy-pages.yml")
    assert workflow.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/api/test_ui.py -q`
Expected: FAIL because README and workflow do not mention Pages export yet.

- [ ] **Step 3: Write the workflow and docs**

```yaml
# .github/workflows/deploy-pages.yml
name: Deploy Radar Pages

on:
  workflow_dispatch:
  schedule:
    - cron: "0 * * * *"

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: python3 -m radar.cli export-pages --config config/radar.yaml --output _site
      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

```md
## GitHub Pages

Generate a static archive from the current radar database:

```bash
python3 -m radar.cli export-pages --config config/radar.yaml --output _site
```

The exported site keeps historical daily snapshots and is suitable for GitHub Pages deployment.
```

- [ ] **Step 4: Run docs/UI checks to verify they pass**

Run: `python3 -m pytest tests/api/test_ui.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/deploy-pages.yml README.md tests/api/test_ui.py
git commit -m "docs: add GitHub Pages publishing flow"
```

### Task 5: Run integrated verification

**Files:**
- Modify: `README.md`
- Test: `tests/api/test_reports.py`
- Test: `tests/api/test_ui.py`
- Test: `tests/pages/test_export.py`
- Test: `tests/core/test_config.py`

- [ ] **Step 1: Run the focused redesign and export test suite**

```bash
python3 -m pytest \
  tests/api/test_reports.py \
  tests/api/test_ui.py \
  tests/pages/test_export.py \
  tests/core/test_config.py -q
```

Expected: PASS

- [ ] **Step 2: Run the full suite**

```bash
python3 -m pytest -q
```

Expected: PASS

- [ ] **Step 3: Commit the final verification/doc polish if needed**

```bash
git add README.md tests/api/test_reports.py tests/api/test_ui.py tests/pages/test_export.py tests/core/test_config.py
git commit -m "test: verify results browser and pages export"
```
