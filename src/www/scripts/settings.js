const settingsFeedback = document.querySelector("#settings-feedback");
const settingsOperationStatus = document.querySelector("#settings-operation-status");
const settingsOperationTitle = document.querySelector("#settings-operation-title");
const settingsOperationCopy = document.querySelector("#settings-operation-copy");
const settingsPosture = document.querySelector("#settings-posture");
const settingsPostureCopy = document.querySelector("#settings-posture-copy");
const autoPostStatus = document.querySelector("#auto-post-status");
const autoPostEnabledInput = document.querySelector("#auto-post-enabled");
const autoPostIntervalInput = document.querySelector("#auto-post-interval");
const prependCoverIntroEnabledInput = document.querySelector("#prepend-cover-intro-enabled");
const queueSettingsSaveButton = document.querySelector("#queue-settings-save");
const queueNextRun = document.querySelector("#queue-next-run");
const queueLastAttempt = document.querySelector("#queue-last-attempt");
const queueLastResult = document.querySelector("#queue-last-result");
const coverImageFileInput = document.querySelector("#cover-image-file");
const coverImageUploadButton = document.querySelector("#cover-image-upload");
const coverImageUrlInput = document.querySelector("#cover-image-url");
const coverImageFromUrlButton = document.querySelector("#cover-image-from-url");
const publicCollectionLiveStatus = document.querySelector("#public-collection-live-status");
const publicCollectionEnabledInput = document.querySelector("#public-collection-enabled");
const publicCollectionUrlInput = document.querySelector("#public-collection-url");
const publicCollectionPollSecondsInput = document.querySelector("#public-collection-poll-seconds");
const publicCollectionSaveButton = document.querySelector("#public-collection-save");
const publicCollectionTestButton = document.querySelector("#public-collection-test");
const publicCollectionSyncButton = document.querySelector("#public-collection-sync");
const publicCollectionStatus = document.querySelector("#public-collection-status");
const publicCollectionLastChecked = document.querySelector("#public-collection-last-checked");
const publicCollectionItemsFound = document.querySelector("#public-collection-items-found");
const publicCollectionItemsQueued = document.querySelector("#public-collection-items-queued");
const publicCollectionStrategy = document.querySelector("#public-collection-strategy");
const publicCollectionError = document.querySelector("#public-collection-error");
const systemRestartButton = document.querySelector("#system-restart");
const systemUpdateButton = document.querySelector("#system-update");

const QUEUE_API_URL = "/api/queue";
const QUEUE_SETTINGS_API_URL = "/api/queue/settings";
const COVER_IMAGE_API_URL = "/api/cover-image";
const COVER_IMAGE_FROM_URL_API_URL = "/api/cover-image/from-url";
const PUBLIC_COLLECTION_STATUS_API_URL = "/api/public-collection/status";
const PUBLIC_COLLECTION_TEST_API_URL = "/api/public-collection/test";
const PUBLIC_COLLECTION_SYNC_API_URL = "/api/public-collection/sync";
const SYSTEM_RESTART_API_URL = "/api/system/restart";
const SYSTEM_UPDATE_API_URL = "/api/system/update";

let operationHintTimerId = null;

function setFeedback(message, isError = false) {
  if (!message) {
    settingsFeedback.hidden = true;
    settingsFeedback.textContent = "";
    settingsFeedback.dataset.state = "";
    return;
  }

  settingsFeedback.hidden = false;
  settingsFeedback.textContent = message;
  settingsFeedback.dataset.state = isError ? "error" : "info";
}

function setOperationStatus({ title, detail, state = "working", persistent = true }) {
  if (operationHintTimerId !== null) {
    window.clearTimeout(operationHintTimerId);
    operationHintTimerId = null;
  }

  settingsOperationStatus.hidden = false;
  settingsOperationStatus.dataset.state = state;
  settingsOperationTitle.textContent = title;
  settingsOperationCopy.textContent = detail;

  if (!persistent) {
    operationHintTimerId = window.setTimeout(() => {
      settingsOperationStatus.hidden = true;
      settingsOperationStatus.dataset.state = "";
    }, 3200);
  }
}

function formatDateTime(value, fallback = "Unknown") {
  if (!value) {
    return fallback;
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function textForLastResult(lastResult) {
  if (!lastResult) {
    return "Nothing recorded yet";
  }

  const resultStatus = lastResult.status ? `[${lastResult.status}] ` : "";
  return `${resultStatus}${lastResult.message || "No message"}`;
}

function renderRuntime(settings = {}) {
  const isEnabled = Boolean(settings.auto_post_enabled);
  autoPostEnabledInput.checked = isEnabled;
  autoPostIntervalInput.value = settings.auto_post_interval_minutes || 15;
  prependCoverIntroEnabledInput.checked = Boolean(settings.prependCoverIntroEnabled);
  autoPostStatus.textContent = isEnabled ? "Automatic" : "Manual";
  queueNextRun.textContent = isEnabled
    ? formatDateTime(settings.next_auto_post_at, "Waiting for schedule")
    : "Disabled";
  queueLastAttempt.textContent = formatDateTime(settings.last_auto_post_attempt_at, "No attempts yet");
  queueLastResult.textContent = textForLastResult(settings.last_auto_post_result);
}

function renderPublicCollectionStatus(settings = {}) {
  publicCollectionEnabledInput.checked = Boolean(settings.enabled);
  publicCollectionUrlInput.value = settings.url || "";
  publicCollectionPollSecondsInput.value = settings.poll_seconds || 300;
  publicCollectionLiveStatus.textContent = settings.enabled ? "Enabled" : "Disabled";
  publicCollectionStatus.textContent = settings.last_status || "idle";
  publicCollectionLastChecked.textContent = formatDateTime(settings.last_checked_at, "Never");
  publicCollectionItemsFound.textContent = String(settings.last_items_found || 0);
  publicCollectionItemsQueued.textContent = String(settings.last_items_queued || 0);
  publicCollectionStrategy.textContent = settings.last_extract_strategy || "none";
  publicCollectionError.textContent = settings.last_error || "None";
}

function renderPosture(queueSettings = {}, collectionSettings = {}) {
  const autoLabel = queueSettings.auto_post_enabled ? "Scheduler on" : "Scheduler off";
  const monitorLabel = collectionSettings.enabled ? "monitor on" : "monitor off";
  settingsPosture.textContent = `${autoLabel}, ${monitorLabel}`;
  settingsPostureCopy.textContent = queueSettings.auto_post_enabled
    ? `Next publish is ${formatDateTime(queueSettings.next_auto_post_at, "not scheduled yet")}.`
    : "Queue publishes are manual until automation is enabled.";
}

async function loadSettings({ preserveFeedback = false } = {}) {
  if (!preserveFeedback) {
    setFeedback("");
  }

  const queueResponse = await fetch(QUEUE_API_URL);
  const queueData = await queueResponse.json();
  if (!queueResponse.ok) {
    throw new Error(queueData.error || "Failed to load queue settings");
  }

  const collectionResponse = await fetch(PUBLIC_COLLECTION_STATUS_API_URL);
  const collectionData = await collectionResponse.json();
  if (!collectionResponse.ok) {
    throw new Error(collectionData.error || "Failed to load collection monitor settings");
  }

  renderRuntime(queueData.settings || {});
  renderPublicCollectionStatus(collectionData || {});
  renderPosture(queueData.settings || {}, collectionData || {});
}

async function saveQueueSettings() {
  const interval = Number.parseInt(autoPostIntervalInput.value, 10);
  if (!Number.isInteger(interval) || interval < 1) {
    setFeedback("Interval must be an integer of at least 1 minute.", true);
    return;
  }

  queueSettingsSaveButton.disabled = true;
  const previousText = queueSettingsSaveButton.textContent;
  queueSettingsSaveButton.textContent = "Saving...";
  setOperationStatus({ title: "Saving scheduler", detail: "Updating automation settings." });

  try {
    const response = await fetch(QUEUE_SETTINGS_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        auto_post_enabled: autoPostEnabledInput.checked,
        auto_post_interval_minutes: interval,
        prependCoverIntroEnabled: prependCoverIntroEnabledInput.checked,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to save scheduler settings");
    }

    renderRuntime(data.settings || {});
    setFeedback("Scheduler settings saved.");
    setOperationStatus({
      title: "Scheduler saved",
      detail: "Automation settings are stored.",
      state: "success",
      persistent: false,
    });
    await loadSettings({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({ title: "Scheduler save failed", detail: error.message, state: "error" });
  } finally {
    queueSettingsSaveButton.disabled = false;
    queueSettingsSaveButton.textContent = previousText;
  }
}

async function uploadCoverImage() {
  const selectedFile = coverImageFileInput.files?.[0];
  if (!selectedFile) {
    setFeedback("Choose an image file before uploading.", true);
    return;
  }

  coverImageUploadButton.disabled = true;
  const previousText = coverImageUploadButton.textContent;
  coverImageUploadButton.textContent = "Uploading...";
  setOperationStatus({ title: "Uploading cover image", detail: "Saving the global cover intro frame." });

  try {
    const formData = new FormData();
    formData.append("cover_image", selectedFile);
    const response = await fetch(COVER_IMAGE_API_URL, { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to upload cover image");
    }

    coverImageFileInput.value = "";
    setFeedback(`Cover image uploaded: ${data.filename}`);
    setOperationStatus({
      title: "Cover image uploaded",
      detail: `${data.filename} is now the active cover intro frame.`,
      state: "success",
      persistent: false,
    });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({ title: "Cover upload failed", detail: error.message, state: "error" });
  } finally {
    coverImageUploadButton.disabled = false;
    coverImageUploadButton.textContent = previousText;
  }
}

async function fetchCoverFromUrl() {
  const url = coverImageUrlInput.value.trim();
  if (!url) {
    setFeedback("Enter a video URL before fetching the cover image.", true);
    return;
  }

  coverImageFromUrlButton.disabled = true;
  const previousText = coverImageFromUrlButton.textContent;
  coverImageFromUrlButton.textContent = "Fetching...";
  setOperationStatus({ title: "Fetching video cover", detail: "Pulling a cover image from the TikTok URL." });

  try {
    const response = await fetch(COVER_IMAGE_FROM_URL_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to fetch cover image from URL");
    }

    coverImageUrlInput.value = "";
    setFeedback(`Cover image saved from video: ${data.filename}`);
    setOperationStatus({
      title: "Video cover saved",
      detail: `${data.filename} is ready for the cover intro frame.`,
      state: "success",
      persistent: false,
    });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({ title: "Video cover fetch failed", detail: error.message, state: "error" });
  } finally {
    coverImageFromUrlButton.disabled = false;
    coverImageFromUrlButton.textContent = previousText;
  }
}

async function savePublicCollectionSettings() {
  const pollSeconds = Number.parseInt(publicCollectionPollSecondsInput.value, 10);
  if (!Number.isInteger(pollSeconds) || pollSeconds < 1) {
    setFeedback("Collection poll interval must be an integer of at least 1 second.", true);
    return;
  }

  publicCollectionSaveButton.disabled = true;
  const previousText = publicCollectionSaveButton.textContent;
  publicCollectionSaveButton.textContent = "Saving...";
  setOperationStatus({ title: "Saving collection monitor", detail: "Updating URL and poll cadence." });

  try {
    const response = await fetch(QUEUE_SETTINGS_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        publicCollectionEnabled: publicCollectionEnabledInput.checked,
        publicCollectionUrl: publicCollectionUrlInput.value.trim() || null,
        publicCollectionPollSeconds: pollSeconds,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to save collection monitor settings");
    }

    setFeedback("Collection monitor settings saved.");
    setOperationStatus({
      title: "Collection monitor saved",
      detail: "Monitor settings are stored.",
      state: "success",
      persistent: false,
    });
    await loadSettings({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({ title: "Collection monitor save failed", detail: error.message, state: "error" });
  } finally {
    publicCollectionSaveButton.disabled = false;
    publicCollectionSaveButton.textContent = previousText;
  }
}

async function testPublicCollection() {
  const url = publicCollectionUrlInput.value.trim();
  if (!url) {
    setFeedback("Enter a public collection URL before testing.", true);
    return;
  }

  publicCollectionTestButton.disabled = true;
  const previousText = publicCollectionTestButton.textContent;
  publicCollectionTestButton.textContent = "Testing...";
  setOperationStatus({ title: "Testing collection URL", detail: "Checking reachability and visible items." });

  try {
    const response = await fetch(PUBLIC_COLLECTION_TEST_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Collection test failed");
    }

    setFeedback(`Collection reachable. Found ${data.items_found} items using ${data.extract_strategy}.`);
    setOperationStatus({
      title: "Collection test finished",
      detail: `Found ${data.items_found} items using ${data.extract_strategy}.`,
      state: "success",
      persistent: false,
    });
    renderPublicCollectionStatus({
      ...data,
      enabled: publicCollectionEnabledInput.checked,
      url: data.normalized_url || url,
      poll_seconds: Number.parseInt(publicCollectionPollSecondsInput.value, 10) || 300,
      last_status: data.fetch_ok ? "test_ok" : "test_failed",
      last_checked_at: new Date().toISOString(),
      last_items_found: data.items_found,
      last_items_queued: 0,
      last_extract_strategy: data.extract_strategy,
      last_error: data.error || "",
    });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({ title: "Collection test failed", detail: error.message, state: "error" });
  } finally {
    publicCollectionTestButton.disabled = false;
    publicCollectionTestButton.textContent = previousText;
  }
}

async function syncPublicCollection() {
  publicCollectionSyncButton.disabled = true;
  const previousText = publicCollectionSyncButton.textContent;
  publicCollectionSyncButton.textContent = "Syncing...";
  setOperationStatus({ title: "Syncing collection", detail: "Checking for newly discovered items." });

  try {
    const response = await fetch(PUBLIC_COLLECTION_SYNC_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: publicCollectionUrlInput.value.trim() || undefined }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Collection sync failed");
    }

    const detail = data.baseline_seeded
      ? `Seeded the baseline from ${data.items_found} collection items.`
      : `Found ${data.items_found}, queued ${data.items_queued}, duplicates ${data.duplicates}.`;
    setFeedback(`Collection sync complete. ${detail}`);
    setOperationStatus({ title: "Collection sync finished", detail, state: "success", persistent: false });
    await loadSettings({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({ title: "Collection sync failed", detail: error.message, state: "error" });
  } finally {
    publicCollectionSyncButton.disabled = false;
    publicCollectionSyncButton.textContent = previousText;
  }
}

async function runSystemAction(button, endpoint, activeText, successTitle) {
  button.disabled = true;
  const previousText = button.textContent;
  button.textContent = activeText;
  setOperationStatus({ title: successTitle, detail: "Sending the system request." });

  try {
    const response = await fetch(endpoint, { method: "POST" });
    const data = await response.json();
    if (!response.ok) {
      const stageLabel = data.stage ? `${data.stage}: ` : "";
      const details = [data.error || "System request failed", data.stderr || data.stdout || ""]
        .filter(Boolean)
        .join(" ");
      throw new Error(`${stageLabel}${details}`);
    }

    setFeedback(data.message || `${successTitle} requested.`);
    setOperationStatus({
      title: `${successTitle} requested`,
      detail: data.message || "The system request was accepted.",
      state: "success",
    });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({ title: `${successTitle} failed`, detail: error.message, state: "error" });
  } finally {
    button.disabled = false;
    button.textContent = previousText;
  }
}

queueSettingsSaveButton.addEventListener("click", saveQueueSettings);
coverImageUploadButton.addEventListener("click", uploadCoverImage);
coverImageFromUrlButton.addEventListener("click", fetchCoverFromUrl);
publicCollectionSaveButton.addEventListener("click", savePublicCollectionSettings);
publicCollectionTestButton.addEventListener("click", testPublicCollection);
publicCollectionSyncButton.addEventListener("click", syncPublicCollection);
systemUpdateButton.addEventListener("click", () => {
  runSystemAction(systemUpdateButton, SYSTEM_UPDATE_API_URL, "Updating...", "Update");
});
systemRestartButton.addEventListener("click", () => {
  runSystemAction(systemRestartButton, SYSTEM_RESTART_API_URL, "Restarting...", "Restart");
});

loadSettings().catch((error) => {
  setFeedback(error.message, true);
  setOperationStatus({ title: "Settings load failed", detail: error.message, state: "error" });
  renderRuntime({});
  renderPublicCollectionStatus({});
});
