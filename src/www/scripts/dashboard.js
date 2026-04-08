const DASHBOARD_API_URL = "/api/dashboard";

const dashboardFeedback = document.querySelector("#dashboard-feedback");
const activityList = document.querySelector("#activity-list");

function setFeedback(message, isError = false) {
  if (!dashboardFeedback) {
    return;
  }

  if (!message) {
    dashboardFeedback.hidden = true;
    dashboardFeedback.textContent = "";
    dashboardFeedback.dataset.state = "";
    return;
  }

  dashboardFeedback.hidden = false;
  dashboardFeedback.textContent = message;
  dashboardFeedback.dataset.state = isError ? "error" : "info";
}

function formatDateTime(value, fallback = "Unknown") {
  if (!value) {
    return fallback;
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
}

function formatRelativeStatus(queue = {}) {
  if (queue.failed > 0) {
    return "Needs attention";
  }

  if (queue.queued > 0) {
    return "Ready to move";
  }

  if (queue.publishing > 0) {
    return "Publishing";
  }

  return "Quiet";
}

function textForLastResult(lastResult) {
  if (!lastResult) {
    return "Nothing recorded yet";
  }

  const status = lastResult.status ? `[${lastResult.status}] ` : "";
  return `${status}${lastResult.message || "No message"}`;
}

function renderSummary(data) {
  const queue = data.queue || {};
  const automation = data.automation || {};
  const captions = data.captions || {};
  const monitor = data.public_collection || {};

  document.querySelector("#metric-queued").textContent = String(queue.queued || 0);
  document.querySelector("#metric-failed").textContent = String(queue.failed || 0);
  document.querySelector("#metric-captions").textContent = String(captions.filled_clouds || 0);
  document.querySelector("#metric-monitor").textContent = monitor.last_status || "idle";

  document.querySelector("#metric-queued-copy").textContent =
    queue.queued ? `${queue.queued} post${queue.queued === 1 ? "" : "s"} can publish now.` : "Nothing is queued yet.";
  document.querySelector("#metric-failed-copy").textContent =
    queue.failed ? "Retry or inspect the failed items before the next run." : "No failed publishes in the current queue.";
  document.querySelector("#metric-captions-copy").textContent =
    `${captions.total_clouds || 0} cloud${captions.total_clouds === 1 ? "" : "s"}, ${captions.total_characters || 0} characters total.`;
  document.querySelector("#metric-monitor-copy").textContent =
    monitor.enabled
      ? `${monitor.last_items_found || 0} found, ${monitor.last_items_queued || 0} queued on the last pass.`
      : "Collection monitor is currently disabled.";

  const focusTitle = document.querySelector("#overview-focus-title");
  const focusCopy = document.querySelector("#overview-focus-copy");

  if (queue.failed > 0) {
    focusTitle.textContent = `${queue.failed} failed item${queue.failed === 1 ? "" : "s"} need review`;
    focusCopy.textContent = "Clear queue errors first so the scheduler can return to a predictable cadence.";
  } else if (queue.next_item) {
    focusTitle.textContent = queue.next_item.title || "Next queued item";
    focusCopy.textContent = automation.enabled
      ? `Scheduler is active. Next run is ${formatDateTime(automation.next_run_at, "not scheduled yet")}.`
      : "Scheduler is off. Use the queue page when you want to run the next item manually.";
  } else {
    focusTitle.textContent = "Queue is clear";
    focusCopy.textContent = "Ingest a new TikTok or wait for the collection monitor to queue fresh items.";
  }
}

function renderPriority(data) {
  const queue = data.queue || {};
  const automation = data.automation || {};
  const nextItem = queue.next_item;

  document.querySelector("#priority-status").textContent = formatRelativeStatus(queue);
  document.querySelector("#next-item-title").textContent = nextItem ? nextItem.title : "No queued item";
  document.querySelector("#next-item-meta").textContent = nextItem
    ? `${nextItem.status} • Updated ${formatDateTime(nextItem.updated_at)}`
    : "The queue has no ready item to publish.";

  document.querySelector("#auto-next-run").textContent = automation.enabled
    ? formatDateTime(automation.next_run_at, "Waiting for next schedule")
    : "Disabled";
  document.querySelector("#auto-last-attempt").textContent = formatDateTime(
    automation.last_attempt_at,
    "No attempts yet",
  );
  document.querySelector("#auto-last-result").textContent = textForLastResult(automation.last_result);
  document.querySelector("#auto-cover-intro").textContent = automation.prepend_cover_intro_enabled
    ? "Enabled"
    : "Disabled";

  document.querySelector("#automation-mode").textContent = automation.enabled ? "Automatic" : "Manual";
  document.querySelector("#automation-cadence").textContent = automation.enabled
    ? `Every ${automation.interval_minutes || "?"} minute${automation.interval_minutes === 1 ? "" : "s"}`
    : "Run from queue page";
  document.querySelector("#automation-last-result").textContent = textForLastResult(automation.last_result);
}

function renderCaptions(data) {
  const captions = data.captions || {};

  document.querySelector("#captions-total").textContent = String(captions.total_clouds || 0);
  document.querySelector("#captions-filled").textContent = String(captions.filled_clouds || 0);
  document.querySelector("#captions-characters").textContent = String(captions.total_characters || 0);
}

function renderMonitor(data) {
  const monitor = data.public_collection || {};

  document.querySelector("#monitor-status").textContent = monitor.last_status || "idle";
  document.querySelector("#monitor-last-checked").textContent = formatDateTime(
    monitor.last_checked_at,
    "Never",
  );
  document.querySelector("#monitor-items-found").textContent = String(monitor.last_items_found || 0);
  document.querySelector("#monitor-items-queued").textContent = String(monitor.last_items_queued || 0);
}

function renderActivity(data) {
  const items = Array.isArray(data.activity) ? data.activity : [];
  activityList.replaceChildren();

  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "empty-note";
    empty.textContent = "No queue activity recorded yet.";
    activityList.append(empty);
    return;
  }

  items.forEach((item) => {
    const row = document.createElement("article");
    row.className = "activity-item";

    const title = document.createElement("strong");
    title.textContent = item.title || "Queue item";

    const meta = document.createElement("p");
    const errorSuffix = item.last_error ? ` • ${item.last_error}` : "";
    meta.textContent = `${item.status || "unknown"} • ${formatDateTime(item.updated_at)}${errorSuffix}`;

    row.append(title, meta);
    activityList.append(row);
  });
}

async function loadDashboard() {
  setFeedback("");

  const response = await fetch(DASHBOARD_API_URL);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || "Failed to load overview");
  }

  renderSummary(data);
  renderPriority(data);
  renderCaptions(data);
  renderMonitor(data);
  renderActivity(data);
}

loadDashboard().catch((error) => {
  setFeedback(error.message, true);
});
