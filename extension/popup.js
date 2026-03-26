const DEFAULT_SETTINGS = {
  monitorEnabled: false,
  serverBaseUrl: "http://localhost:6767",
  pollIntervalSeconds: 60,
};

const SETTINGS_KEYS = Object.keys(DEFAULT_SETTINGS);
const STATUS_KEYS = [
  "lastScanAt",
  "lastScanStatus",
  "lastScanError",
  "lastItemsFound",
  "lastItemsQueued",
  "favoritesTabId",
];

const monitorEnabledInput = document.querySelector("#monitor-enabled");
const serverBaseUrlInput = document.querySelector("#server-base-url");
const pollIntervalSecondsInput = document.querySelector("#poll-interval-seconds");
const saveButton = document.querySelector("#save-settings");
const monitorStateValue = document.querySelector("#monitor-state");
const lastScanValue = document.querySelector("#last-scan-at");
const lastResultValue = document.querySelector("#last-result");
const lastItemsFoundValue = document.querySelector("#last-items-found");
const lastItemsQueuedValue = document.querySelector("#last-items-queued");
const lastErrorValue = document.querySelector("#last-error");

function formatDateTime(value, fallback = "Never") {
  if (!value) {
    return fallback;
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return fallback;
  }

  return parsed.toLocaleString();
}

function humanizeStatus(status, monitorEnabled) {
  switch (status) {
    case "idle":
      return monitorEnabled ? "Idle" : "Disabled";
    case "scanning":
      return "Scanning";
    case "queued":
      return "Queued new favorites";
    case "baseline_ready":
      return "Baseline captured";
    case "duplicate_only":
      return "Duplicates only";
    case "waiting_for_tab":
      return "Waiting for favorites tab";
    case "wrong_page":
      return "Favorites page not open";
    case "parse_error":
      return "Could not parse favorites page";
    case "server_error":
      return "Server error";
    default:
      return monitorEnabled ? "Ready" : "Disabled";
  }
}

async function loadState() {
  const data = await chrome.storage.local.get([...SETTINGS_KEYS, ...STATUS_KEYS]);
  const settings = { ...DEFAULT_SETTINGS, ...data };

  monitorEnabledInput.checked = Boolean(settings.monitorEnabled);
  serverBaseUrlInput.value = settings.serverBaseUrl || DEFAULT_SETTINGS.serverBaseUrl;
  pollIntervalSecondsInput.value = String(settings.pollIntervalSeconds || DEFAULT_SETTINGS.pollIntervalSeconds);

  monitorStateValue.textContent = humanizeStatus(settings.lastScanStatus, settings.monitorEnabled);
  lastScanValue.textContent = formatDateTime(settings.lastScanAt);
  lastResultValue.textContent = settings.lastScanStatus || "idle";
  lastItemsFoundValue.textContent = String(settings.lastItemsFound || 0);
  lastItemsQueuedValue.textContent = String(settings.lastItemsQueued || 0);
  lastErrorValue.textContent = settings.lastScanError || "None";
}

async function saveSettings() {
  saveButton.disabled = true;
  const previousText = saveButton.textContent;
  saveButton.textContent = "Saving...";

  const serverBaseUrl = (serverBaseUrlInput.value || DEFAULT_SETTINGS.serverBaseUrl).trim().replace(/\/+$/, "");
  const parsedInterval = Number.parseInt(pollIntervalSecondsInput.value, 10);
  const pollIntervalSeconds = Number.isFinite(parsedInterval) ? parsedInterval : DEFAULT_SETTINGS.pollIntervalSeconds;
  pollIntervalSecondsInput.value = String(pollIntervalSeconds);

  await chrome.storage.local.set({
    monitorEnabled: monitorEnabledInput.checked,
    serverBaseUrl: serverBaseUrl || DEFAULT_SETTINGS.serverBaseUrl,
    pollIntervalSeconds,
  });

  await chrome.runtime.sendMessage({ type: "monitorSettingsUpdated" });
  await loadState();

  saveButton.disabled = false;
  saveButton.textContent = previousText;
}

saveButton.addEventListener("click", () => {
  saveSettings().catch((error) => {
    lastErrorValue.textContent = error?.message || String(error);
    saveButton.disabled = false;
    saveButton.textContent = "Save";
  });
});

document.addEventListener("DOMContentLoaded", () => {
  loadState().catch((error) => {
    lastErrorValue.textContent = error?.message || String(error);
  });
});
