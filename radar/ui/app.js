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

async function reloadConfig() {
  const status = document.getElementById("runtime-status");
  const result = document.getElementById("runtime-result");
  status.textContent = "Reloading config...";
  try {
    const payload = await fetchJson("/config/reload", { method: "POST" });
    status.textContent = payload.status;
    result.textContent = JSON.stringify(payload, null, 2);
  } catch (error) {
    status.textContent = `Config reload failed: ${error.message}`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("refresh-alerts").addEventListener("click", loadAlerts);
  document
    .querySelectorAll("[data-job]")
    .forEach((button) =>
      button.addEventListener("click", () => triggerJob(button.dataset.job)),
    );
  document.getElementById("reload-config").addEventListener("click", reloadConfig);
  loadAlerts();
});

window.radarUi = { fetchJson, loadAlerts, loadAlertDetail, triggerJob, reloadConfig };
