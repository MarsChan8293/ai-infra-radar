async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed: ${response.status}`);
  }
  return response.json();
}

let activeDate = null;
let activeTopic = "all";
let activeReport = null;

function setStatus(message) {
  document.getElementById("report-status").textContent = message;
}

function renderManifest(manifest) {
  const dateList = document.getElementById("date-list");
  dateList.innerHTML = "";

  for (const entry of manifest.dates) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${entry.date} (${entry.count})`;
    if (entry.date === activeDate) {
      button.classList.add("is-active");
    }
    button.addEventListener("click", () => loadReport(entry.date));
    item.appendChild(button);
    dateList.appendChild(item);
  }
}

function renderTopics(report) {
  const topicList = document.getElementById("topic-list");
  topicList.innerHTML = "";

  const allTopics = [{ topic: "all", count: report.summary.total_alerts }, ...report.topics];
  for (const topicEntry of allTopics) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${topicEntry.topic} (${topicEntry.count})`;
    if (topicEntry.topic === activeTopic) {
      button.classList.add("is-active");
    }
    button.addEventListener("click", () => {
      activeTopic = topicEntry.topic;
      renderTopics(report);
      renderEvents(report);
    });
    item.appendChild(button);
    topicList.appendChild(item);
  }
}

function renderEvents(report) {
  const container = document.getElementById("report-events");
  const topics =
    activeTopic === "all"
      ? report.topics
      : report.topics.filter((entry) => entry.topic === activeTopic);
  const events = topics.flatMap((entry) => entry.events);

  if (events.length === 0) {
    container.innerHTML = '<article class="event-card empty-state">No events for this filter.</article>';
    return;
  }

  container.innerHTML = events
    .map(
      (event) => `
        <article class="event-card">
          <h3>${event.display_name}</h3>
          <p class="event-meta">${event.source} • ${event.alert_type} • score ${event.score}</p>
          <p>${JSON.stringify(event.reason)}</p>
          <a href="${event.url}" target="_blank" rel="noreferrer">Open source page</a>
        </article>
      `,
    )
    .join("");
}

function renderReport(report) {
  activeReport = report;
  document.getElementById("report-subtitle").textContent = `Showing ${report.date} grouped by source.`;
  document.getElementById("report-summary").textContent =
    `Total alerts: ${report.summary.total_alerts}\n` +
    `Top sources: ${report.summary.top_sources.map((entry) => `${entry.source}(${entry.count})`).join(", ")}\n` +
    `Highest score: ${report.summary.max_score}`;
  renderTopics(report);
  renderEvents(report);
}

async function loadReport(date) {
  activeDate = date;
  activeTopic = "all";
  setStatus(`Loading ${date}...`);
  renderManifest({ dates: Array.from(document.querySelectorAll("#date-list button")).map((button) => ({ date: button.textContent.split(" ")[0], count: 0 })) });
  try {
    const report = await fetchJson(`/reports/${date}`);
    renderReport(report);
    setStatus(`Loaded ${date}`);
  } catch (error) {
    activeReport = null;
    document.getElementById("report-summary").textContent = `Failed to load report: ${error.message}`;
    document.getElementById("report-events").innerHTML = "";
    setStatus(`Failed to load ${date}`);
  }
}

async function loadManifest() {
  setStatus("Loading reports...");
  try {
    const manifest = await fetchJson("/reports/manifest");
    if (manifest.dates.length === 0) {
      document.getElementById("date-list").innerHTML = "";
      document.getElementById("topic-list").innerHTML = "";
      document.getElementById("report-summary").textContent = "No reports have been generated yet.";
      document.getElementById("report-events").innerHTML = "";
      setStatus("No reports available");
      return;
    }
    activeDate = manifest.dates[0].date;
    renderManifest(manifest);
    await loadReport(activeDate);
  } catch (error) {
    document.getElementById("report-summary").textContent = `Failed to load reports: ${error.message}`;
    document.getElementById("date-list").innerHTML = "";
    document.getElementById("topic-list").innerHTML = "";
    document.getElementById("report-events").innerHTML = "";
    setStatus("Failed to load reports");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadManifest();
});

window.radarResultsUi = { fetchJson, renderManifest, renderReport, loadManifest, loadReport };
