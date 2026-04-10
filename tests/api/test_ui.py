import json
import shutil
import subprocess
import textwrap
from fastapi.testclient import TestClient
from pathlib import Path

from radar.app import create_app


def _run_results_app_scenario(
    *,
    hash_value: str,
    manifest: dict,
    reports: dict[str, dict],
    extra_steps: str = "",
) -> dict[str, str]:
    node = shutil.which("node")
    assert node is not None

    script = textwrap.dedent(
        f"""
        const fs = require("fs");
        const vm = require("vm");

        class ClassList {{
          constructor() {{
            this.classes = new Set();
          }}
          add(name) {{
            this.classes.add(name);
          }}
          remove(name) {{
            this.classes.delete(name);
          }}
          toggle(name, force) {{
            if (force === undefined) {{
              if (this.classes.has(name)) {{
                this.classes.delete(name);
              }} else {{
                this.classes.add(name);
              }}
              return;
            }}
            if (force) {{
              this.classes.add(name);
              return;
            }}
            this.classes.delete(name);
          }}
        }}

        class Element {{
          constructor(id = "") {{
            this.id = id;
            this.children = [];
            this.listeners = {{}};
            this._innerHTML = "";
            this.textContent = "";
            this.value = "";
            this.href = "";
            this.disabled = false;
            this.dataset = {{}};
            this.classList = new ClassList();
          }}
          appendChild(child) {{
            this.children.push(child);
            return child;
          }}
          addEventListener(name, handler) {{
            (this.listeners[name] ||= []).push(handler);
          }}
          dispatchEvent(event) {{
            for (const handler of this.listeners[event.type] || []) {{
              handler(event);
            }}
          }}
          set innerHTML(value) {{
            this._innerHTML = value;
            this.children = [];
          }}
          get innerHTML() {{
            if (this.children.length) {{
              return this.children.map((child) => child.innerHTML).join("");
            }}
            return this._innerHTML;
          }}
          querySelectorAll(selector) {{
            if (selector !== "[data-group]") {{
              return [];
            }}
            const matches = [...this.innerHTML.matchAll(/data-group="([^"]+)" data-value="([^"]+)"/g)];
            return matches.map((match) => {{
              const button = new Element();
              button.dataset = {{ group: match[1], value: match[2] }};
              return button;
            }});
          }}
        }}

        const elements = new Map();
        function getElementById(id) {{
          if (!elements.has(id)) {{
            elements.set(id, new Element(id));
          }}
          return elements.get(id);
        }}

        const languageButtons = ["en", "zh"].map((language) => {{
          const button = new Element();
          button.dataset = {{ language }};
          return button;
        }});

        const documentListeners = {{}};
        const document = {{
          getElementById,
          createElement(tag) {{
            return new Element(tag);
          }},
          querySelectorAll(selector) {{
            if (selector === "#language-toggle [data-language]") {{
              return languageButtons;
            }}
            return [];
          }},
          addEventListener(name, handler) {{
            (documentListeners[name] ||= []).push(handler);
          }},
          dispatchEvent(event) {{
            for (const handler of documentListeners[event.type] || []) {{
              handler(event);
            }}
          }},
        }};

        const locationState = {{ value: {json.dumps(hash_value)} }};
        const location = {{}};
        Object.defineProperty(location, "hash", {{
          get() {{
            return locationState.value;
          }},
          set(value) {{
            if (!value) {{
              locationState.value = "";
              return;
            }}
            locationState.value = value.startsWith("#") ? value : `#${{value}}`;
          }},
        }});

        const windowListeners = {{}};
        const window = {{
          document,
          location,
          __RADAR_RESULTS_CONFIG__: {{
            mode: "static",
            manifestPath: "/reports/manifest.json",
            reportBasePath: "/reports",
            feedPath: "/feed.xml",
          }},
          addEventListener(name, handler) {{
            (windowListeners[name] ||= []).push(handler);
          }},
          dispatchEvent(event) {{
            for (const handler of windowListeners[event.type] || []) {{
              handler(event);
            }}
          }},
          setTimeout(handler) {{
            handler();
            return 0;
          }},
        }};

        function buildResponse(payload) {{
          return {{
            ok: true,
            async json() {{
              return JSON.parse(JSON.stringify(payload));
            }},
            async text() {{
              return JSON.stringify(payload);
            }},
          }};
        }}

        const manifest = {json.dumps(manifest)};
        const reports = {json.dumps(reports)};
        async function fetch(url) {{
          if (url === "/reports/manifest.json") {{
            return buildResponse(manifest);
          }}
          if (url.startsWith("/reports/") && url.endsWith(".json")) {{
            const date = url.replace("/reports/", "").replace(".json", "");
            return buildResponse(reports[date]);
          }}
          throw new Error(`Unexpected fetch ${{url}}`);
        }}

        const context = {{
          window,
          document,
          fetch,
          console,
          URLSearchParams,
          setTimeout: window.setTimeout,
        }};
        context.globalThis = context;

        const source = fs.readFileSync("radar/ui/results/app.js", "utf8");
        vm.createContext(context);
        vm.runInContext(source, context);

        async function flush() {{
          for (let index = 0; index < 6; index += 1) {{
            await Promise.resolve();
          }}
        }}

        async function main() {{
          document.dispatchEvent({{ type: "DOMContentLoaded" }});
          await flush();
          {extra_steps}
          await flush();
          console.log(JSON.stringify({{
            hash: window.location.hash,
            summary: document.getElementById("summary-stats").innerHTML,
            filters: document.getElementById("filter-groups").innerHTML,
            events: document.getElementById("report-events").innerHTML,
          }}));
        }}

        main().catch((error) => {{
          console.error(error);
          process.exit(1);
        }});
        """
    )

    completed = subprocess.run(
        [node, "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_home_route_returns_html_shell() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "AI Infra Radar" in response.text
    assert "Radar Results" in response.text


def test_home_static_assets_are_served() -> None:
    client = TestClient(create_app())

    styles = client.get("/static/results/styles.css")
    script = client.get("/static/results/app.js")

    assert styles.status_code == 200
    assert styles.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert 'fetchJson("/reports/manifest")' in script.text


def test_home_shell_contains_results_browser_regions() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="date-list"' in response.text
    assert 'id="topic-list"' in response.text
    assert 'id="search-input"' in response.text
    assert 'id="filter-groups"' in response.text
    assert 'id="language-toggle"' in response.text
    assert 'id="feed-link"' in response.text
    assert 'id="permalink-link"' in response.text
    assert 'id="report-summary"' in response.text
    assert 'id="daily-briefing"' in response.text
    assert 'id="report-events"' in response.text


def test_home_script_contains_report_api_wiring() -> None:
    client = TestClient(create_app())

    response = client.get("/static/results/app.js")

    assert response.status_code == 200
    assert 'fetchJson("/reports/manifest")' in response.text
    assert 'window.location.hash' in response.text
    assert "URLSearchParams" in response.text
    assert "loadReportForCurrentState" in response.text
    assert "search-input" in response.text
    assert "language-toggle" in response.text
    assert "feedPath" in response.text
    assert "renderManifest" in response.text
    assert "renderReport" in response.text
    assert "daily briefing" in response.text.lower()


def test_results_app_normalizes_stale_hash_filters_when_switching_reports() -> None:
    manifest = {
        "dates": [
            {"date": "2026-04-09", "count": 1},
            {"date": "2026-04-08", "count": 1},
        ]
    }
    reports = {
        "2026-04-09": {
            "date": "2026-04-09",
            "summary": {
                "total_alerts": 1,
                "top_sources": [{"source": "github", "count": 1}],
                "max_score": 0.91,
                "briefing_en": "GitHub activity stayed elevated.",
                "briefing_zh": None,
            },
            "filters": {
                "sources": [{"value": "github", "count": 1}],
                "alert_types": [{"value": "repo_burst", "count": 1}],
                "score_bands": [{"value": "0.8-1.0", "count": 1}],
                "topic_tags": [{"value": "github", "count": 1}],
            },
            "topics": [
                {
                    "topic": "github",
                    "count": 1,
                    "events": [
                        {
                            "display_name": "acme/project",
                            "title_zh": None,
                            "reason_text_en": "Burst detected.",
                            "reason_text_zh": None,
                            "reason": {"stars": 42},
                            "score": 0.91,
                            "source": "github",
                            "alert_type": "repo_burst",
                            "created_at": "2026-04-09T12:00:00Z",
                            "url": "https://example.com/acme/project",
                            "search_text": "acme project burst",
                            "filter_tags": {
                                "source": "github",
                                "alert_type": "repo_burst",
                                "score_band": "0.8-1.0",
                                "topic_tags": ["github"],
                            },
                        }
                    ],
                }
            ],
        },
        "2026-04-08": {
            "date": "2026-04-08",
            "summary": {
                "total_alerts": 1,
                "top_sources": [{"source": "official_pages", "count": 1}],
                "max_score": 0.74,
                "briefing_en": "Official pages changed.",
                "briefing_zh": None,
            },
            "filters": {
                "sources": [{"value": "official_pages", "count": 1}],
                "alert_types": [{"value": "page_update", "count": 1}],
                "score_bands": [{"value": "0.6-0.8", "count": 1}],
                "topic_tags": [{"value": "official_pages", "count": 1}],
            },
            "topics": [
                {
                    "topic": "official_pages",
                    "count": 1,
                    "events": [
                        {
                            "display_name": "Vendor release notes",
                            "title_zh": None,
                            "reason_text_en": "Release notes updated.",
                            "reason_text_zh": None,
                            "reason": {"url": "https://example.com/releases"},
                            "score": 0.74,
                            "source": "official_pages",
                            "alert_type": "page_update",
                            "created_at": "2026-04-08T08:00:00Z",
                            "url": "https://example.com/releases",
                            "search_text": "official release notes updated",
                            "filter_tags": {
                                "source": "official_pages",
                                "alert_type": "page_update",
                                "score_band": "0.6-0.8",
                                "topic_tags": ["official_pages"],
                            },
                        }
                    ],
                }
            ],
        },
    }

    result = _run_results_app_scenario(
        hash_value="#date=2026-04-09&source=github",
        manifest=manifest,
        reports=reports,
        extra_steps=textwrap.dedent(
            """
            window.location.hash = "#date=2026-04-08&source=github";
            window.dispatchEvent({ type: "hashchange" });
            """
        ),
    )

    assert result["hash"] == "#date=2026-04-08"
    assert "No additional filters" in result["summary"]
    assert 'data-group="source" data-value="all">All <span>1</span></button>' in result["filters"]
    assert "is-active" in result["filters"]
    assert "No entries match the current search or filters." not in result["events"]
    assert "Vendor release notes" in result["events"]


def test_ops_route_returns_html_shell() -> None:
    client = TestClient(create_app())

    response = client.get("/ops")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "AI Infra Radar Operations UI" in response.text


def test_ops_static_assets_are_served() -> None:
    client = TestClient(create_app())

    styles = client.get("/static/ops/styles.css")
    script = client.get("/static/ops/app.js")

    assert styles.status_code == 200
    assert styles.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert 'fetchJson("/alerts")' in script.text


def test_ops_shell_contains_alerts_jobs_and_runtime_controls() -> None:
    client = TestClient(create_app())

    response = client.get("/ops")

    assert response.status_code == 200
    assert 'data-panel="alerts"' in response.text
    assert 'id="alerts-list"' in response.text
    assert 'id="alert-detail"' in response.text
    assert 'id="jobs-list"' in response.text
    assert 'id="reload-config"' in response.text


def test_ops_script_contains_jobs_and_reload_api_wiring() -> None:
    client = TestClient(create_app())

    response = client.get("/static/ops/app.js")

    assert response.status_code == 200
    assert 'fetchJson("/jobs")' in response.text
    assert 'fetchJson(`/jobs/run/${jobName}`' in response.text
    assert 'fetchJson("/config/reload"' in response.text
    assert "renderJobs" in response.text


def test_ui_route_is_removed() -> None:
    client = TestClient(create_app())

    response = client.get("/ui")

    assert response.status_code == 404


def test_readme_mentions_homepage_and_ops_entrypoints() -> None:
    readme = Path("README.md").read_text()

    assert "/" in readme
    assert "/ops" in readme
