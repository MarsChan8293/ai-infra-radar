async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed: ${response.status}`);
  }
  return response.json();
}

function formatAlertSummary(alert) {
  return `${alert.alert_type} • ${alert.source} • score ${alert.score}`;
}

function renderAlertDetail(alert) {
  const detail = document.getElementById("alert-detail");
  detail.textContent =
    `ID: ${alert.id}\n` +
    `Type: ${alert.alert_type}\n` +
    `Source: ${alert.source}\n` +
    `Score: ${alert.score}\n` +
    `Status: ${alert.status}\n` +
    `Reason: ${JSON.stringify(alert.reason)}`;
}

function resetAlertDetail() {
  const detail = document.getElementById("alert-detail");
  detail.textContent = "Select an alert to inspect its details.";
}

async function loadAlertDetail(alertId) {
  const status = document.getElementById("alerts-status");
  status.textContent = `Loading alert ${alertId}...`;
  try {
    const alert = await fetchJson(`/alerts/${alertId}`);
    renderAlertDetail(alert);
    status.textContent = `Loaded alert ${alertId}`;
  } catch (error) {
    status.textContent = `Failed to load alert detail: ${error.message}`;
  }
}

async function loadAlerts() {
  const status = document.getElementById("alerts-status");
  const list = document.getElementById("alerts-list");
  status.textContent = "Loading alerts...";
  list.innerHTML = "";
  resetAlertDetail();
  try {
    const payload = await fetchJson("/alerts");
    for (const alert of payload.alerts) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = formatAlertSummary(alert);
      button.addEventListener("click", () => loadAlertDetail(alert.id));
      item.appendChild(button);
      list.appendChild(item);
    }
    status.textContent = `Loaded ${payload.alerts.length} alerts`;
  } catch (error) {
    status.textContent = `Failed to load alerts: ${error.message}`;
  }
}

function renderJobs(jobs) {
  const list = document.getElementById("jobs-list");
  list.innerHTML = "";
  for (const jobName of jobs) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.job = jobName;
    button.textContent = `Run ${jobName}`;
    button.addEventListener("click", () => triggerJob(jobName));
    list.appendChild(button);
  }
}

let manualFetchState = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatCount(value) {
  return Number(value ?? 0).toLocaleString();
}

function sanitizeUrl(value) {
  const url = String(value ?? "").trim();
  return url.startsWith("https://") ? url : "#";
}

function renderRepoListItem(repo, extraContent = "") {
  const fullName = escapeHtml(repo.full_name || repo.name || "Unknown repository");
  const description = escapeHtml(repo.description || "No description provided.");
  const stars = formatCount(repo.stars);
  const forks = formatCount(repo.forks);
  const link = sanitizeUrl(repo.html_url);
  const readmeStatus = escapeHtml(repo.readme_status || "unknown");
  return `
    <article class="manual-result-card">
      <div class="manual-result-header">
        <h4>${fullName}</h4>
        <a href="${link}" target="_blank" rel="noreferrer">GitHub</a>
      </div>
      <p>${description}</p>
      <p>Stars: ${stars} • Forks: ${forks}</p>
      <p>README status: ${readmeStatus}</p>
      ${extraContent}
    </article>
  `;
}

function renderManualFetchSummary(state) {
  const summary = state.summary || {};
  const request = state.request || {};
  return `
    <div><strong>Expanded query:</strong> ${escapeHtml(request.query || "")}</div>
    <div>Coarse count: ${formatCount(summary.coarse_count)}</div>
    <div>README successes: ${formatCount(summary.readme_success_count)}</div>
    <div>README failures: ${formatCount(summary.readme_failure_count)}</div>
    <div>Second-pass keep count: ${formatCount(summary.secondary_keep_count)}</div>
  `;
}

function renderManualFetchResults(state) {
  const summary = document.getElementById("manual-fetch-summary");
  const coarse = document.getElementById("manual-fetch-coarse-results");
  const secondary = document.getElementById("manual-fetch-secondary-results");
  const errors = document.getElementById("manual-fetch-errors");

  if (!state) {
    summary.textContent = "No manual fetch run yet.";
    coarse.textContent = "No coarse results yet.";
    secondary.textContent = "No second-pass results yet.";
    errors.textContent = "No per-item errors.";
    return;
  }

  const coarseResults = state.coarse_results || [];
  const secondaryResults = state.secondary_results || [];
  const errorResults = state.errors || [];

  summary.innerHTML = renderManualFetchSummary(state);
  coarse.innerHTML = coarseResults.length
    ? coarseResults.map((repo) => renderRepoListItem(repo)).join("")
    : "No coarse results returned.";
  secondary.innerHTML = secondaryResults.length
    ? secondaryResults
        .map((repo) =>
          renderRepoListItem(
            repo,
            `
              <p>Chinese reason: ${escapeHtml(repo.reason_zh || "")}</p>
              <p>Matched signals: ${escapeHtml((repo.matched_signals || []).join(", ") || "None")}</p>
            `
          )
        )
        .join("")
    : "No repositories passed the second pass.";
  errors.innerHTML = errorResults.length
    ? errorResults
        .map(
          (error) => `
            <article class="manual-result-card manual-result-card-error">
              <h4>${escapeHtml(error.full_name || "Unknown item")}</h4>
              <p>Stage: ${escapeHtml(error.stage || "unknown")}</p>
              <p>${escapeHtml(error.message || "Unknown error.")}</p>
            </article>
          `
        )
        .join("")
    : "No per-item errors.";
}

async function loadJobs() {
  const status = document.getElementById("jobs-status");
  status.textContent = "Loading jobs...";
  try {
    const payload = await fetchJson("/jobs");
    renderJobs(payload.jobs);
    status.textContent = `Loaded ${payload.jobs.length} jobs`;
  } catch (error) {
    renderJobs([]);
    status.textContent = `Failed to load jobs: ${error.message}`;
  }
}

async function triggerJob(jobName) {
  const status = document.getElementById("jobs-status");
  status.textContent = `Triggering ${jobName}...`;
  try {
    const payload = await fetchJson(`/jobs/run/${jobName}`, { method: "POST" });
    status.textContent = `${payload.job_name}: ${payload.status}`;
  } catch (error) {
    status.textContent = `Failed to trigger ${jobName}: ${error.message}`;
  }
}

async function runManualGitHubFetch(event) {
  event.preventDefault();
  const status = document.getElementById("manual-fetch-status");
  const submitButton = document.getElementById("manual-fetch-submit");
  submitButton.disabled = true;
  status.textContent = "Running manual GitHub fetch...";
  try {
    const payload = await fetchJson("/ops/github/manual-fetch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        start_date: document.getElementById("manual-fetch-start-date").value,
        end_date: document.getElementById("manual-fetch-end-date").value,
        query: document.getElementById("manual-fetch-query").value,
        readme_prompt: document.getElementById("manual-fetch-readme-prompt").value,
      }),
    });
    manualFetchState = payload;
    renderManualFetchResults(manualFetchState);
    status.textContent = "Manual GitHub fetch completed.";
  } catch (error) {
    status.textContent = `Manual GitHub fetch failed: ${error.message}`;
  } finally {
    submitButton.disabled = false;
  }
}

async function reloadConfig() {
  const status = document.getElementById("runtime-status");
  const result = document.getElementById("runtime-result");
  status.textContent = "Reloading config...";
  try {
    const payload = await fetchJson("/config/reload", { method: "POST" });
    status.textContent = payload.status;
    result.textContent = JSON.stringify(payload, null, 2);
    renderJobs(payload.jobs);
    document.getElementById("jobs-status").textContent = `Loaded ${payload.jobs.length} jobs`;
  } catch (error) {
    status.textContent = `Config reload failed: ${error.message}`;
    result.textContent = "Config reload failed.";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("refresh-alerts").addEventListener("click", loadAlerts);
  document.getElementById("reload-config").addEventListener("click", reloadConfig);
  document.getElementById("manual-fetch-form").addEventListener("submit", runManualGitHubFetch);
  renderManualFetchResults(manualFetchState);
  loadAlerts();
  loadJobs();
});

window.radarUi = {
  fetchJson,
  loadAlerts,
  loadAlertDetail,
  loadJobs,
  renderJobs,
  triggerJob,
  reloadConfig,
  renderManualFetchResults,
  runManualGitHubFetch,
};
