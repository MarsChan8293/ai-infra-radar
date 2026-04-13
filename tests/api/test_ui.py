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
    mode: str = "static",
    deferred_dates: tuple[str, ...] = (),
    defer_manifest: bool = False,
) -> dict[str, object]:
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
        const mode = {json.dumps(mode)};
        const window = {{
          document,
          location,
          __RADAR_RESULTS_CONFIG__: {{
            mode,
            manifestPath: mode === "static" ? "/reports/manifest.json" : "/reports/manifest",
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
        const deferredDates = new Set({json.dumps(list(deferred_dates))});
        const deferManifest = {json.dumps(defer_manifest)};
        const fetchCounts = {{}};
        let pendingManifestFetch = null;
        const pendingReportFetches = new Map();

        function queueDeferredReport(date, payload) {{
          return new Promise((resolve) => {{
            const pending = pendingReportFetches.get(date) || [];
            pending.push({{ payload, resolve }});
            pendingReportFetches.set(date, pending);
          }});
        }}

        async function resolveDeferredReport(date) {{
          const pending = pendingReportFetches.get(date) || [];
          if (!pending.length) {{
            throw new Error(`No deferred report fetch queued for ${{date}}`);
          }}
          const next = pending.shift();
          if (pending.length) {{
            pendingReportFetches.set(date, pending);
          }} else {{
            pendingReportFetches.delete(date);
          }}
          next.resolve(buildResponse(next.payload));
          await Promise.resolve();
        }}

        async function resolveDeferredManifest() {{
          if (!pendingManifestFetch) {{
            throw new Error("No deferred manifest fetch queued");
          }}
          const resolve = pendingManifestFetch;
          pendingManifestFetch = null;
          resolve(buildResponse(manifest));
          await Promise.resolve();
        }}

        async function fetch(url) {{
          fetchCounts[url] = (fetchCounts[url] || 0) + 1;
          if (url === "/reports/manifest.json" || url === "/reports/manifest") {{
            if (deferManifest) {{
              return new Promise((resolve) => {{
                pendingManifestFetch = resolve;
              }});
            }}
            return buildResponse(manifest);
          }}
          if (url.startsWith("/reports/")) {{
             const date = url.replace("/reports/", "").replace(".json", "");
             const reportPayload = reports[date];
             if (Array.isArray(reportPayload)) {{
               const fetchIndex = fetchCounts[url] - 1;
               const payload = reportPayload[Math.min(fetchIndex, reportPayload.length - 1)];
               if (deferredDates.has(date)) {{
                 return queueDeferredReport(date, payload);
               }}
               return buildResponse(payload);
             }}
             if (deferredDates.has(date)) {{
               return queueDeferredReport(date, reportPayload);
             }}
             return buildResponse(reportPayload);
           }}
           throw new Error(`Unexpected fetch ${{url}}`);
         }}

        window.__resolveReportFetch = resolveDeferredReport;
        window.__resolveManifestFetch = resolveDeferredManifest;

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
            status: document.getElementById("report-status").textContent,
            fetchCounts,
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


def _run_ops_app_scenario(
    *,
    manual_response: dict,
    extra_steps: str = "",
    defer_manual_fetch: bool = False,
) -> dict[str, object]:
    node = shutil.which("node")
    assert node is not None

    script = textwrap.dedent(
        f"""
        const fs = require("fs");
        const vm = require("vm");

        class Element {{
          constructor(tagName = "div", id = "") {{
            this.tagName = tagName.toLowerCase();
            this.id = id;
            this.children = [];
            this.listeners = {{}};
            this._innerHTML = "";
            this._textContent = "";
            this.value = "";
            this.href = "";
            this.disabled = false;
            this.dataset = {{}};
            this.type = "";
            this.className = "";
          }}
          appendChild(child) {{
            this.children.push(child);
            return child;
          }}
          addEventListener(name, handler) {{
            (this.listeners[name] ||= []).push(handler);
          }}
          dispatchEvent(event) {{
            event.preventDefault ||= (() => {{
              event.defaultPrevented = true;
            }});
            event.target ||= this;
            for (const handler of this.listeners[event.type] || []) {{
              handler(event);
            }}
          }}
          set innerHTML(value) {{
            this._innerHTML = value;
            this._textContent = "";
            this.children = [];
          }}
          get innerHTML() {{
            if (this._innerHTML) {{
              return this._innerHTML;
            }}
            if (this.children.length) {{
              return this.children.map((child) => child.outerHTML).join("");
            }}
            return this._textContent;
          }}
          set textContent(value) {{
            this._textContent = value == null ? "" : String(value);
            this._innerHTML = "";
            this.children = [];
          }}
          get textContent() {{
            if (this.children.length) {{
              return this.children.map((child) => child.textContent).join("");
            }}
            return this._innerHTML || this._textContent;
          }}
          get outerHTML() {{
            const attrs = [];
            if (this.id) {{
              attrs.push(` id="${{this.id}}"`);
            }}
            if (this.href) {{
              attrs.push(` href="${{this.href}}"`);
            }}
            if (this.className) {{
              attrs.push(` class="${{this.className}}"`);
            }}
            if (this.disabled) {{
              attrs.push(" disabled");
            }}
            if (this.type) {{
              attrs.push(` type="${{this.type}}"`);
            }}
            const content = this.innerHTML;
            return `<${{this.tagName}}${{attrs.join("")}}>${{content}}</${{this.tagName}}>`;
          }}
        }}

        const elements = new Map();
        function getElementById(id) {{
          if (!elements.has(id)) {{
            elements.set(id, new Element("div", id));
          }}
          return elements.get(id);
        }}

        const documentListeners = {{}};
        const document = {{
          getElementById,
          createElement(tagName) {{
            return new Element(tagName);
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

        const fetchCounts = {{}};
        const manualResponse = {json.dumps(manual_response)};
        const deferManualFetch = {json.dumps(defer_manual_fetch)};
        let pendingManualFetch = null;
        let lastManualRequest = null;

        async function fetch(url, options = undefined) {{
          fetchCounts[url] = (fetchCounts[url] || 0) + 1;
          if (url === "/alerts") {{
            return buildResponse({{ alerts: [] }});
          }}
          if (url === "/jobs") {{
            return buildResponse({{ jobs: [] }});
          }}
          if (url === "/config/reload") {{
            return buildResponse({{ status: "reloaded", jobs: [] }});
          }}
          if (url === "/ops/github/manual-fetch") {{
            lastManualRequest = {{
              url,
              method: options?.method || "GET",
              body: options?.body || null,
            }};
            if (deferManualFetch) {{
              return new Promise((resolve) => {{
                pendingManualFetch = resolve;
              }});
            }}
            return buildResponse(manualResponse);
          }}
          throw new Error(`Unexpected fetch ${{url}}`);
        }}

        const window = {{
          document,
          addEventListener() {{}},
          setTimeout(handler) {{
            handler();
            return 0;
          }},
        }};
        window.__resolveManualFetch = async function resolveManualFetch() {{
          if (!pendingManualFetch) {{
            throw new Error("No deferred manual fetch queued");
          }}
          const resolve = pendingManualFetch;
          pendingManualFetch = null;
          resolve(buildResponse(manualResponse));
          await Promise.resolve();
        }};

        const context = {{
          window,
          document,
          fetch,
          console,
          setTimeout: window.setTimeout,
        }};
        context.globalThis = context;

        const source = fs.readFileSync("radar/ui/app.js", "utf8");
        vm.createContext(context);
        vm.runInContext(source, context);

        async function flush() {{
          for (let index = 0; index < 6; index += 1) {{
            await Promise.resolve();
          }}
        }}

        const scenarioState = {{}};

        async function main() {{
          document.dispatchEvent({{ type: "DOMContentLoaded" }});
          await flush();
          {extra_steps}
          await flush();
          console.log(JSON.stringify({{
            scenarioState,
            fetchCounts,
            lastManualRequest,
            alerts: document.getElementById("alerts-list").innerHTML,
            manualStatus: document.getElementById("manual-fetch-status").textContent,
            manualButtonDisabled: document.getElementById("manual-fetch-submit").disabled,
            manualSummary: document.getElementById("manual-fetch-summary").innerHTML,
            coarseResults: document.getElementById("manual-fetch-coarse-results").innerHTML,
            secondaryResults: document.getElementById("manual-fetch-secondary-results").innerHTML,
            errorResults: document.getElementById("manual-fetch-errors").innerHTML,
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


def test_results_app_preserves_startup_hash_change_while_manifest_is_loading() -> None:
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
                            "display_name": "stale-github-event",
                            "title_zh": None,
                            "reason_text_en": "Stale event.",
                            "reason_text_zh": None,
                            "reason": {"stars": 42},
                            "score": 0.91,
                            "source": "github",
                            "alert_type": "repo_burst",
                            "created_at": "2026-04-09T12:00:00Z",
                            "url": "https://example.com/stale",
                            "search_text": "stale github event",
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
                            "display_name": "fresh-official-pages-event",
                            "title_zh": None,
                            "reason_text_en": "Fresh event.",
                            "reason_text_zh": None,
                            "reason": {"url": "https://example.com/fresh"},
                            "score": 0.74,
                            "source": "official_pages",
                            "alert_type": "page_update",
                            "created_at": "2026-04-08T08:00:00Z",
                            "url": "https://example.com/fresh",
                            "search_text": "fresh official pages event",
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
        hash_value="#date=2026-04-09",
        manifest=manifest,
        reports=reports,
        defer_manifest=True,
        extra_steps=textwrap.dedent(
            """
            window.location.hash = "#date=2026-04-08";
            window.dispatchEvent({ type: "hashchange" });
            await flush();
            await window.__resolveManifestFetch();
            await flush();
            """
        ),
    )

    assert result["hash"] == "#date=2026-04-08"
    assert result["status"] == "Loaded 2026-04-08"
    assert "2026-04-08" in result["summary"]
    assert "fresh-official-pages-event" in result["events"]
    assert "stale-github-event" not in result["events"]


def test_results_app_refetches_live_reports_but_reuses_static_cache() -> None:
    manifest = {
        "dates": [
            {"date": "2026-04-09", "count": 1},
            {"date": "2026-04-08", "count": 1},
        ]
    }
    reports = {
        "2026-04-09": [
            {
                "date": "2026-04-09",
                "summary": {
                    "total_alerts": 1,
                    "top_sources": [{"source": "github", "count": 1}],
                    "max_score": 0.91,
                    "briefing_en": "Initial live briefing.",
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
                                "display_name": "live-report-initial",
                                "title_zh": None,
                                "reason_text_en": "Initial live event.",
                                "reason_text_zh": None,
                                "reason": {"stars": 42},
                                "score": 0.91,
                                "source": "github",
                                "alert_type": "repo_burst",
                                "created_at": "2026-04-09T12:00:00Z",
                                "url": "https://example.com/live-initial",
                                "search_text": "live report initial",
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
            {
                "date": "2026-04-09",
                "summary": {
                    "total_alerts": 1,
                    "top_sources": [{"source": "github", "count": 1}],
                    "max_score": 0.97,
                    "briefing_en": "Refetched live briefing.",
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
                                "display_name": "live-report-refetched",
                                "title_zh": None,
                                "reason_text_en": "Refetched live event.",
                                "reason_text_zh": None,
                                "reason": {"stars": 108},
                                "score": 0.97,
                                "source": "github",
                                "alert_type": "repo_burst",
                                "created_at": "2026-04-09T13:00:00Z",
                                "url": "https://example.com/live-refetched",
                                "search_text": "live report refetched",
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
        ],
        "2026-04-08": {
            "date": "2026-04-08",
            "summary": {
                "total_alerts": 1,
                "top_sources": [{"source": "official_pages", "count": 1}],
                "max_score": 0.74,
                "briefing_en": "Static comparison report.",
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
                            "display_name": "comparison-report",
                            "title_zh": None,
                            "reason_text_en": "Comparison event.",
                            "reason_text_zh": None,
                            "reason": {"url": "https://example.com/comparison"},
                            "score": 0.74,
                            "source": "official_pages",
                            "alert_type": "page_update",
                            "created_at": "2026-04-08T08:00:00Z",
                            "url": "https://example.com/comparison",
                            "search_text": "comparison report event",
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
    extra_steps = textwrap.dedent(
        """
        window.location.hash = "#date=2026-04-08";
        window.dispatchEvent({ type: "hashchange" });
        await flush();
        window.location.hash = "#date=2026-04-09";
        window.dispatchEvent({ type: "hashchange" });
        await flush();
        """
    )

    live_result = _run_results_app_scenario(
        hash_value="#date=2026-04-09",
        manifest=manifest,
        reports=reports,
        extra_steps=extra_steps,
        mode="live",
    )

    assert live_result["fetchCounts"]["/reports/2026-04-09"] == 2
    assert "live-report-refetched" in live_result["events"]

    static_result = _run_results_app_scenario(
        hash_value="#date=2026-04-09",
        manifest=manifest,
        reports=reports,
        extra_steps=extra_steps,
        mode="static",
    )

    assert static_result["fetchCounts"]["/reports/2026-04-09.json"] == 1
    assert "live-report-initial" in static_result["events"]


def test_results_app_ignores_stale_report_response_after_later_date_selection() -> None:
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
                "briefing_en": "Older report should stay hidden.",
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
                            "display_name": "stale-github-event",
                            "title_zh": None,
                            "reason_text_en": "Older report resolved last.",
                            "reason_text_zh": None,
                            "reason": {"stars": 42},
                            "score": 0.91,
                            "source": "github",
                            "alert_type": "repo_burst",
                            "created_at": "2026-04-09T12:00:00Z",
                            "url": "https://example.com/stale",
                            "search_text": "stale github event",
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
                "briefing_en": "Latest selection should win.",
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
                            "display_name": "fresh-official-pages-event",
                            "title_zh": None,
                            "reason_text_en": "Latest report resolved first.",
                            "reason_text_zh": None,
                            "reason": {"url": "https://example.com/fresh"},
                            "score": 0.74,
                            "source": "official_pages",
                            "alert_type": "page_update",
                            "created_at": "2026-04-08T08:00:00Z",
                            "url": "https://example.com/fresh",
                            "search_text": "fresh official pages event",
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
        hash_value="#date=2026-04-09",
        manifest=manifest,
        reports=reports,
        deferred_dates=("2026-04-09", "2026-04-08"),
        extra_steps=textwrap.dedent(
            """
            window.location.hash = "#date=2026-04-08";
            window.dispatchEvent({ type: "hashchange" });
            await flush();
            await window.__resolveReportFetch("2026-04-08");
            await flush();
            await window.__resolveReportFetch("2026-04-09");
            """
        ),
    )

    assert result["hash"] == "#date=2026-04-08"
    assert result["status"] == "Loaded 2026-04-08"
    assert "2026-04-08" in result["summary"]
    assert "fresh-official-pages-event" in result["events"]
    assert "stale-github-event" not in result["events"]


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


def test_ops_shell_contains_manual_github_fetch_controls() -> None:
    client = TestClient(create_app())

    response = client.get("/ops")

    assert response.status_code == 200
    assert 'data-panel="manual-github-fetch"' in response.text
    assert 'id="manual-fetch-form"' in response.text
    assert 'id="manual-fetch-start-date"' in response.text
    assert 'id="manual-fetch-end-date"' in response.text
    assert 'id="manual-fetch-query"' in response.text
    assert 'id="manual-fetch-readme-prompt"' in response.text
    assert 'id="manual-fetch-submit"' in response.text
    assert 'id="manual-fetch-summary"' in response.text
    assert 'id="manual-fetch-coarse-results"' in response.text
    assert 'id="manual-fetch-secondary-results"' in response.text
    assert 'id="manual-fetch-errors"' in response.text


def test_ops_script_contains_jobs_and_reload_api_wiring() -> None:
    client = TestClient(create_app())

    response = client.get("/static/ops/app.js")

    assert response.status_code == 200
    assert 'fetchJson("/jobs")' in response.text
    assert 'fetchJson(`/jobs/run/${jobName}`' in response.text
    assert 'fetchJson("/config/reload"' in response.text
    assert "renderJobs" in response.text


def test_ops_script_runs_manual_fetch_and_renders_results() -> None:
    result = _run_ops_app_scenario(
        manual_response={
            "request": {
                "query": '"speculative decoding" created:2026-04-01..2026-04-10',
                "start_date": "2026-04-01",
                "end_date": "2026-04-10",
                "readme_prompt": "",
            },
            "summary": {
                "coarse_count": 2,
                "readme_success_count": 1,
                "readme_failure_count": 1,
                "secondary_keep_count": 1,
            },
            "coarse_results": [
                {
                    "full_name": "acme/serve-fast",
                    "description": "High-throughput inference server",
                    "stars": 120,
                    "forks": 17,
                    "html_url": "https://github.com/acme/serve-fast",
                    "readme_status": "ok",
                },
                {
                    "full_name": "acme/missing-docs",
                    "description": "Repository without a README",
                    "stars": 8,
                    "forks": 1,
                    "html_url": "https://github.com/acme/missing-docs",
                    "readme_status": "missing_readme",
                },
            ],
            "secondary_results": [
                {
                    "full_name": "acme/serve-fast",
                    "description": "High-throughput inference server",
                    "stars": 120,
                    "forks": 17,
                    "html_url": "https://github.com/acme/serve-fast",
                    "reason_zh": "README 明确描述了推理服务能力。",
                    "matched_signals": ["serving", "throughput"],
                }
            ],
            "errors": [
                {
                    "full_name": "acme/missing-docs",
                    "stage": "readme_fetch",
                    "message": "README not found.",
                }
            ],
        },
        defer_manual_fetch=True,
        extra_steps=textwrap.dedent(
            """
            document.getElementById("manual-fetch-start-date").value = "2026-04-01";
            document.getElementById("manual-fetch-end-date").value = "2026-04-10";
            document.getElementById("manual-fetch-query").value = '"speculative decoding"';
            document.getElementById("manual-fetch-readme-prompt").value = "";
            document.getElementById("manual-fetch-form").dispatchEvent({ type: "submit" });
            await flush();
            scenarioState.beforeResolve = {
              disabled: document.getElementById("manual-fetch-submit").disabled,
              status: document.getElementById("manual-fetch-status").textContent,
            };
            await window.__resolveManualFetch();
            await flush();
            """
        ),
    )

    assert result["fetchCounts"]["/alerts"] == 1
    assert result["fetchCounts"]["/jobs"] == 1
    assert result["fetchCounts"]["/ops/github/manual-fetch"] == 1
    assert result["scenarioState"]["beforeResolve"] == {
        "disabled": True,
        "status": "Running manual GitHub fetch...",
    }
    assert json.loads(result["lastManualRequest"]["body"]) == {
        "start_date": "2026-04-01",
        "end_date": "2026-04-10",
        "query": '"speculative decoding"',
        "readme_prompt": "",
    }
    assert result["manualButtonDisabled"] is False
    assert result["manualStatus"] == "Manual GitHub fetch completed."
    assert "speculative decoding" in result["manualSummary"]
    assert "Coarse count: 2" in result["manualSummary"]
    assert "README successes: 1" in result["manualSummary"]
    assert "README failures: 1" in result["manualSummary"]
    assert "Second-pass keep count: 1" in result["manualSummary"]
    assert "acme/serve-fast" in result["coarseResults"]
    assert "https://github.com/acme/serve-fast" in result["coarseResults"]
    assert "missing_readme" in result["coarseResults"]
    assert "README 明确描述了推理服务能力。" in result["secondaryResults"]
    assert "serving, throughput" in result["secondaryResults"]
    assert "acme/missing-docs" in result["errorResults"]
    assert "README not found." in result["errorResults"]
    assert result["alerts"] == ""


def test_ops_script_sanitizes_manual_fetch_repo_links() -> None:
    result = _run_ops_app_scenario(
        manual_response={
            "request": {
                "query": '"speculative decoding" created:2026-04-01..2026-04-10',
                "start_date": "2026-04-01",
                "end_date": "2026-04-10",
                "readme_prompt": "",
            },
            "summary": {
                "coarse_count": 1,
                "readme_success_count": 1,
                "readme_failure_count": 0,
                "secondary_keep_count": 0,
            },
            "coarse_results": [
                {
                    "full_name": "acme/suspicious-link",
                    "description": "Unexpected URL scheme",
                    "stars": 5,
                    "forks": 1,
                    "html_url": "javascript:alert(1)",
                    "readme_status": "ok",
                }
            ],
            "secondary_results": [],
            "errors": [],
        },
        extra_steps=textwrap.dedent(
            """
            document.getElementById("manual-fetch-start-date").value = "2026-04-01";
            document.getElementById("manual-fetch-end-date").value = "2026-04-10";
            document.getElementById("manual-fetch-query").value = '"speculative decoding"';
            document.getElementById("manual-fetch-form").dispatchEvent({ type: "submit" });
            """
        ),
    )

    assert 'href="#"' in result["coarseResults"]
    assert "javascript:alert(1)" not in result["coarseResults"]


def test_ops_script_handles_manual_fetch_payloads_without_result_lists() -> None:
    result = _run_ops_app_scenario(
        manual_response={
            "request": {
                "query": '"speculative decoding" created:2026-04-01..2026-04-10',
                "start_date": "2026-04-01",
                "end_date": "2026-04-10",
                "readme_prompt": "",
            },
            "summary": {
                "coarse_count": 0,
                "readme_success_count": 0,
                "readme_failure_count": 0,
                "secondary_keep_count": 0,
            },
        },
        extra_steps=textwrap.dedent(
            """
            document.getElementById("manual-fetch-start-date").value = "2026-04-01";
            document.getElementById("manual-fetch-end-date").value = "2026-04-10";
            document.getElementById("manual-fetch-query").value = '"speculative decoding"';
            document.getElementById("manual-fetch-form").dispatchEvent({ type: "submit" });
            """
        ),
    )

    assert result["manualStatus"] == "Manual GitHub fetch completed."
    assert result["coarseResults"] == "No coarse results returned."
    assert result["secondaryResults"] == "No repositories passed the second pass."
    assert result["errorResults"] == "No per-item errors."


def test_ui_route_is_removed() -> None:
    client = TestClient(create_app())

    response = client.get("/ui")

    assert response.status_code == 404


def test_readme_mentions_homepage_and_ops_entrypoints() -> None:
    readme = Path("README.md").read_text()

    assert "/" in readme
    assert "/ops" in readme
