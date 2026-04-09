async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed: ${response.status}`);
  }
  return response.json();
}

const FILTER_GROUPS = [
  { id: "sources", stateKey: "source", tagKey: "source", label: "Sources" },
  { id: "alert_types", stateKey: "alert_type", tagKey: "alert_type", label: "Alert types" },
  { id: "score_bands", stateKey: "score_band", tagKey: "score_band", label: "Score bands" },
  { id: "topic_tags", stateKey: "topic_tag", tagKey: "topic_tags", label: "Tags" },
];

const DEFAULT_FILTERS = Object.freeze({
  source: "all",
  alert_type: "all",
  score_band: "all",
  topic_tag: "all",
});

const state = {
  manifest: { dates: [] },
  reportCache: new Map(),
  activeDate: null,
  activeTopic: "all",
  activeReport: null,
  search: "",
  language: "en",
  filters: { ...DEFAULT_FILTERS },
};

let isUpdatingHash = false;

function getResultsConfig() {
  const config = window.__RADAR_RESULTS_CONFIG__ || {};
  const manifestPath = config.manifestPath || "/reports/manifest";
  const reportBasePath = config.reportBasePath || "/reports";
  return {
    manifestPath,
    feedPath: config.feedPath || "/feed.xml",
    reportPath(date) {
      return config.mode === "static"
        ? `${reportBasePath}/${date}.json`
        : `${reportBasePath}/${date}`;
    },
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setStatus(message) {
  document.getElementById("report-status").textContent = message;
}

function readHashState() {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  return {
    date: params.get("date"),
    topic: params.get("topic") || "all",
    q: params.get("q") || "",
    lang: params.get("lang") === "zh" ? "zh" : "en",
    source: params.get("source") || "all",
    alert_type: params.get("alert_type") || "all",
    score_band: params.get("score_band") || "all",
    topic_tag: params.get("topic_tag") || "all",
  };
}

function applyHashState(hashState) {
  state.activeDate = hashState.date || null;
  state.activeTopic = hashState.topic || "all";
  state.search = hashState.q || "";
  state.language = hashState.lang === "zh" ? "zh" : "en";
  state.filters = {
    source: hashState.source || "all",
    alert_type: hashState.alert_type || "all",
    score_band: hashState.score_band || "all",
    topic_tag: hashState.topic_tag || "all",
  };
}

function buildHashState() {
  const params = new URLSearchParams();
  if (state.activeDate) {
    params.set("date", state.activeDate);
  }
  if (state.activeTopic !== "all") {
    params.set("topic", state.activeTopic);
  }
  if (state.search) {
    params.set("q", state.search);
  }
  if (state.language !== "en") {
    params.set("lang", state.language);
  }
  for (const [key, value] of Object.entries(state.filters)) {
    if (value && value !== "all") {
      params.set(key, value);
    }
  }
  return params.toString();
}

function syncHashFromState() {
  const nextHash = buildHashState();
  const currentHash = window.location.hash.replace(/^#/, "");
  if (currentHash === nextHash) {
    return;
  }
  isUpdatingHash = true;
  window.location.hash = nextHash;
  window.setTimeout(() => {
    isUpdatingHash = false;
  }, 0);
}

function normalizeStateForManifest() {
  if (!state.manifest.dates.length) {
    state.activeDate = null;
    return;
  }
  const availableDates = new Set(state.manifest.dates.map((entry) => entry.date));
  if (!state.activeDate || !availableDates.has(state.activeDate)) {
    state.activeDate = state.manifest.dates[0].date;
  }
}

function normalizeStateForReport(report) {
  const topicValues = new Set(report.topics.map((entry) => entry.topic));
  if (state.activeTopic !== "all" && !topicValues.has(state.activeTopic)) {
    state.activeTopic = "all";
  }
}

function getAllEvents(report) {
  return report.topics.flatMap((entry) => entry.events);
}

function eventMatchesFilters(event, { ignoreTopic = false, ignoreFilter = null } = {}) {
  if (!ignoreTopic && state.activeTopic !== "all" && event.source !== state.activeTopic) {
    return false;
  }

  const searchQuery = state.search.trim().toLowerCase();
  if (searchQuery && !String(event.search_text || "").toLowerCase().includes(searchQuery)) {
    return false;
  }

  for (const group of FILTER_GROUPS) {
    if (ignoreFilter === group.stateKey) {
      continue;
    }
    const selected = state.filters[group.stateKey];
    if (!selected || selected === "all") {
      continue;
    }
    const tagValue = event.filter_tags?.[group.tagKey];
    if (Array.isArray(tagValue)) {
      if (!tagValue.includes(selected)) {
        return false;
      }
      continue;
    }
    if (tagValue !== selected) {
      return false;
    }
  }

  return true;
}

function getVisibleEvents(report) {
  return getAllEvents(report).filter((event) => eventMatchesFilters(event));
}

function getTopicCounts(report) {
  const counts = { all: 0 };
  for (const event of getAllEvents(report)) {
    if (!eventMatchesFilters(event, { ignoreTopic: true })) {
      continue;
    }
    counts.all += 1;
    counts[event.source] = (counts[event.source] || 0) + 1;
  }
  return counts;
}

function getFilterOptionCounts(report, group) {
  const counts = { all: 0 };
  for (const event of getAllEvents(report)) {
    if (!eventMatchesFilters(event, { ignoreFilter: group.stateKey })) {
      continue;
    }
    counts.all += 1;
    const tagValue = event.filter_tags?.[group.tagKey];
    if (Array.isArray(tagValue)) {
      for (const value of tagValue) {
        counts[value] = (counts[value] || 0) + 1;
      }
      continue;
    }
    if (tagValue) {
      counts[tagValue] = (counts[tagValue] || 0) + 1;
    }
  }
  return counts;
}

function pickBriefing(report) {
  if (state.language === "zh") {
    return report.summary.briefing_zh || report.summary.briefing_en;
  }
  return report.summary.briefing_en || report.summary.briefing_zh;
}

function pickEventTitle(event) {
  if (state.language === "zh" && event.title_zh) {
    return event.title_zh;
  }
  return event.display_name;
}

function pickEventSecondaryTitle(event) {
  if (state.language === "zh") {
    return event.title_zh ? event.display_name : "";
  }
  return event.title_zh || "";
}

function pickEventDescription(event) {
  if (state.language === "zh") {
    return event.reason_text_zh || event.reason_text_en || JSON.stringify(event.reason);
  }
  return event.reason_text_en || event.reason_text_zh || JSON.stringify(event.reason);
}

function formatDateTime(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function summarizeActiveFilters() {
  const parts = [];
  if (state.search) {
    parts.push(`search “${state.search}”`);
  }
  if (state.activeTopic !== "all") {
    parts.push(`topic ${state.activeTopic}`);
  }
  for (const group of FILTER_GROUPS) {
    const value = state.filters[group.stateKey];
    if (value && value !== "all") {
      parts.push(`${group.label.toLowerCase()} ${value}`);
    }
  }
  return parts.length ? parts.join(" • ") : "No additional filters";
}

function renderManifest(manifest) {
  state.manifest = manifest;
  const dateList = document.getElementById("date-list");
  dateList.innerHTML = "";

  for (const entry of manifest.dates) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.innerHTML = `
      <span>${escapeHtml(entry.date)}</span>
      <span class="nav-meta">${escapeHtml(entry.count)}</span>
    `;
    if (entry.date === state.activeDate) {
      button.classList.add("is-active");
    }
    button.addEventListener("click", () => {
      state.activeDate = entry.date;
      syncHashFromState();
      loadReportForCurrentState();
    });
    item.appendChild(button);
    dateList.appendChild(item);
  }
}

function renderTopics(report) {
  const topicList = document.getElementById("topic-list");
  topicList.innerHTML = "";

  const topicCounts = getTopicCounts(report);
  const topics = [{ topic: "all", count: topicCounts.all }, ...report.topics.map((entry) => ({
    topic: entry.topic,
    count: topicCounts[entry.topic] || 0,
  }))];

  for (const topicEntry of topics) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.innerHTML = `
      <span>${escapeHtml(topicEntry.topic)}</span>
      <span class="nav-meta">${escapeHtml(topicEntry.count)}</span>
    `;
    if (topicEntry.topic === state.activeTopic) {
      button.classList.add("is-active");
    }
    if (topicEntry.count === 0 && topicEntry.topic !== state.activeTopic) {
      button.disabled = true;
    }
    button.addEventListener("click", () => {
      state.activeTopic = topicEntry.topic;
      syncHashFromState();
      renderCurrentReport();
    });
    item.appendChild(button);
    topicList.appendChild(item);
  }
}

function renderFilters(report) {
  const container = document.getElementById("filter-groups");
  container.innerHTML = "";

  for (const group of FILTER_GROUPS) {
    const section = document.createElement("section");
    section.className = "filter-group";

    const counts = getFilterOptionCounts(report, group);
    const options = report.filters?.[group.id] || [];
    const selectedValue = state.filters[group.stateKey] || "all";
    const chips = [
      `<button type="button" class="filter-chip ${selectedValue === "all" ? "is-active" : ""}" data-group="${group.stateKey}" data-value="all">All <span>${counts.all || 0}</span></button>`,
      ...options.map((option) => {
        const count = counts[option.value] || 0;
        const classes = ["filter-chip"];
        if (selectedValue === option.value) {
          classes.push("is-active");
        }
        return `<button type="button" class="${classes.join(" ")}" data-group="${group.stateKey}" data-value="${escapeHtml(option.value)}" ${count === 0 && selectedValue !== option.value ? "disabled" : ""}>${escapeHtml(option.value)} <span>${escapeHtml(count)}</span></button>`;
      }),
    ].join("");

    section.innerHTML = `
      <h3>${escapeHtml(group.label)}</h3>
      <div class="chip-row">${chips}</div>
    `;
    container.appendChild(section);
  }

  container.querySelectorAll("[data-group]").forEach((button) => {
    button.addEventListener("click", () => {
      state.filters[button.dataset.group] = button.dataset.value || "all";
      syncHashFromState();
      renderCurrentReport();
    });
  });
}

function renderSummary(report, visibleEvents) {
  const subtitle = document.getElementById("report-subtitle");
  const summaryStats = document.getElementById("summary-stats");
  const briefing = document.getElementById("daily-briefing");
  const visibleSources = new Set(visibleEvents.map((event) => event.source));
  const visibleMaxScore = visibleEvents.reduce(
    (current, event) => Math.max(current, Number(event.score || 0)),
    0,
  );

  subtitle.textContent = `Showing ${visibleEvents.length} of ${report.summary.total_alerts} alerts for ${report.date}.`;
  summaryStats.innerHTML = `
    <div class="summary-header">
      <div>
        <p class="eyebrow">Daily summary</p>
        <h2>${escapeHtml(report.date)}</h2>
      </div>
      <p class="summary-filters">${escapeHtml(summarizeActiveFilters())}</p>
    </div>
    <div class="summary-grid">
      <div class="summary-stat">
        <span class="stat-label">Visible entries</span>
        <strong>${escapeHtml(visibleEvents.length)}</strong>
      </div>
      <div class="summary-stat">
        <span class="stat-label">Topics in view</span>
        <strong>${escapeHtml(visibleSources.size)}</strong>
      </div>
      <div class="summary-stat">
        <span class="stat-label">Highest visible score</span>
        <strong>${escapeHtml(visibleMaxScore.toFixed(2))}</strong>
      </div>
      <div class="summary-stat">
        <span class="stat-label">Available filter groups</span>
        <strong>${escapeHtml(FILTER_GROUPS.length)}</strong>
      </div>
    </div>
    <p class="summary-topline">
      Top sources: ${escapeHtml(report.summary.top_sources.map((entry) => `${entry.source} (${entry.count})`).join(", ") || "none")}
    </p>
  `;

  const briefingText = pickBriefing(report);
  briefing.innerHTML = briefingText
    ? `
      <p class="eyebrow">Daily briefing</p>
      <p>${escapeHtml(briefingText)}</p>
    `
    : `
      <p class="eyebrow">Daily briefing</p>
      <p class="empty-state">No daily briefing available for this report.</p>
    `;
}

function renderEvents(report) {
  const container = document.getElementById("report-events");
  const visibleEvents = getVisibleEvents(report);

  renderSummary(report, visibleEvents);

  if (!visibleEvents.length) {
    container.innerHTML =
      '<article class="event-card empty-state">No entries match the current search or filters.</article>';
    return;
  }

  container.innerHTML = visibleEvents
    .map((event) => {
      const secondaryTitle = pickEventSecondaryTitle(event);
      const description = pickEventDescription(event);
      const reasonJson = JSON.stringify(event.reason, null, 2);
      const tags = [
        event.filter_tags?.source,
        event.filter_tags?.alert_type,
        event.filter_tags?.score_band,
      ]
        .filter(Boolean)
        .map((value) => `<span class="pill">${escapeHtml(value)}</span>`)
        .join("");

      return `
        <article class="event-card">
          <div class="event-heading">
            <div>
              <h3>${escapeHtml(pickEventTitle(event))}</h3>
              ${secondaryTitle ? `<p class="event-secondary-title">${escapeHtml(secondaryTitle)}</p>` : ""}
            </div>
            <div class="event-score">score ${escapeHtml(Number(event.score).toFixed(2))}</div>
          </div>
          <p class="event-meta">${escapeHtml(event.source)} • ${escapeHtml(event.alert_type)} • ${escapeHtml(formatDateTime(event.created_at))}</p>
          <div class="event-tags">${tags}</div>
          <p class="event-description">${escapeHtml(description)}</p>
          <details class="event-reason">
            <summary>Raw reason</summary>
            <pre>${escapeHtml(reasonJson)}</pre>
          </details>
          <a href="${escapeHtml(event.url)}" target="_blank" rel="noreferrer">Open source page</a>
        </article>
      `;
    })
    .join("");
}

function updateToolbarUi() {
  document.getElementById("search-input").value = state.search;
  document.querySelectorAll("#language-toggle [data-language]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.language === state.language);
  });
  const feedLink = document.getElementById("feed-link");
  const reportJsonLink = document.getElementById("report-json-link");
  const permalinkLink = document.getElementById("permalink-link");
  const config = getResultsConfig();
  feedLink.href = config.feedPath;
  reportJsonLink.href = state.activeDate ? config.reportPath(state.activeDate) : config.manifestPath;
  permalinkLink.href = `#${buildHashState()}`;
}

function renderReport(report) {
  state.activeReport = report;
  normalizeStateForReport(report);
  syncHashFromState();
  updateToolbarUi();
  renderManifest(state.manifest);
  renderTopics(report);
  renderFilters(report);
  renderEvents(report);
}

function renderCurrentReport() {
  if (!state.activeReport) {
    updateToolbarUi();
    return;
  }
  renderReport(state.activeReport);
}

async function fetchReport(date) {
  if (state.reportCache.has(date)) {
    return state.reportCache.get(date);
  }

  const config = getResultsConfig();
  const report =
    config.manifestPath === "/reports/manifest"
      ? await fetchJson(`/reports/${date}`)
      : await fetchJson(config.reportPath(date));
  state.reportCache.set(date, report);
  return report;
}

async function loadReportForCurrentState() {
  if (!state.activeDate) {
    return;
  }

  setStatus(`Loading ${state.activeDate}...`);
  updateToolbarUi();
  renderManifest(state.manifest);

  try {
    const report = await fetchReport(state.activeDate);
    renderReport(report);
    setStatus(`Loaded ${state.activeDate}`);
  } catch (error) {
    state.activeReport = null;
    document.getElementById("summary-stats").textContent = `Failed to load report: ${error.message}`;
    document.getElementById("daily-briefing").innerHTML = "";
    document.getElementById("report-events").innerHTML = "";
    document.getElementById("topic-list").innerHTML = "";
    document.getElementById("filter-groups").innerHTML = "";
    setStatus(`Failed to load ${state.activeDate}`);
  }
}

async function loadManifest() {
  setStatus("Loading reports...");
  updateToolbarUi();

  try {
    const config = getResultsConfig();
    const manifest =
      config.manifestPath === "/reports/manifest"
        ? await fetchJson("/reports/manifest")
        : await fetchJson(config.manifestPath);
    state.manifest = manifest;

    if (manifest.dates.length === 0) {
      document.getElementById("date-list").innerHTML = "";
      document.getElementById("topic-list").innerHTML = "";
      document.getElementById("filter-groups").innerHTML = "";
      document.getElementById("summary-stats").textContent = "No reports have been generated yet.";
      document.getElementById("daily-briefing").innerHTML = "";
      document.getElementById("report-events").innerHTML = "";
      setStatus("No reports available");
      return;
    }

    normalizeStateForManifest();
    syncHashFromState();
    renderManifest(manifest);
    await loadReportForCurrentState();
  } catch (error) {
    document.getElementById("summary-stats").textContent = `Failed to load reports: ${error.message}`;
    document.getElementById("daily-briefing").innerHTML = "";
    document.getElementById("date-list").innerHTML = "";
    document.getElementById("topic-list").innerHTML = "";
    document.getElementById("filter-groups").innerHTML = "";
    document.getElementById("report-events").innerHTML = "";
    setStatus("Failed to load reports");
  }
}

function installEventHandlers() {
  document.getElementById("search-input").addEventListener("input", (event) => {
    state.search = event.target.value;
    syncHashFromState();
    renderCurrentReport();
  });

  document.getElementById("clear-search").addEventListener("click", () => {
    state.search = "";
    syncHashFromState();
    renderCurrentReport();
  });

  document.querySelectorAll("#language-toggle [data-language]").forEach((button) => {
    button.addEventListener("click", () => {
      state.language = button.dataset.language === "zh" ? "zh" : "en";
      syncHashFromState();
      renderCurrentReport();
    });
  });

  window.addEventListener("hashchange", () => {
    if (isUpdatingHash) {
      return;
    }
    const previousDate = state.activeDate;
    applyHashState(readHashState());
    normalizeStateForManifest();
    updateToolbarUi();
    if (state.activeDate !== previousDate) {
      loadReportForCurrentState();
      return;
    }
    renderCurrentReport();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  applyHashState(readHashState());
  installEventHandlers();
  loadManifest();
});

window.radarResultsUi = {
  fetchJson,
  renderManifest,
  renderReport,
  renderCurrentReport,
  loadManifest,
  loadReportForCurrentState,
  getResultsConfig,
  readHashState,
};
