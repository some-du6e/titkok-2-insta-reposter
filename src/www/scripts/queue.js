const queueGrid = document.querySelector("#queue-grid");
const queueCardTemplate = document.querySelector("#queue-card-template");
const queueReadyCount = document.querySelector("#queue-ready-count");
const queueEmptyState = document.querySelector("#queue-empty-state");
const queueFeedback = document.querySelector("#queue-feedback");
const autoPostEnabledInput = document.querySelector("#auto-post-enabled");
const autoPostIntervalInput = document.querySelector("#auto-post-interval");
const queueSettingsSaveButton = document.querySelector("#queue-settings-save");
const queueRunNextButton = document.querySelector("#queue-run-next");
const systemUpdateButton = document.querySelector("#system-update");
const queueNextRun = document.querySelector("#queue-next-run");
const queueLastAttempt = document.querySelector("#queue-last-attempt");
const queueLastResult = document.querySelector("#queue-last-result");
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

const QUEUE_API_URL = "/api/queue";
const QUEUE_SETTINGS_API_URL = "/api/queue/settings";
const QUEUE_RUN_NEXT_API_URL = "/api/queue/run-next";
const SYSTEM_UPDATE_API_URL = "/api/system/update";
const PUBLIC_COLLECTION_STATUS_API_URL = "/api/public-collection/status";
const PUBLIC_COLLECTION_TEST_API_URL = "/api/public-collection/test";
const PUBLIC_COLLECTION_SYNC_API_URL = "/api/public-collection/sync";
const HIDDEN_PUBLISHED_STORAGE_KEY = "tt2ig-hidden-published-ids";
const hiddenPublishedIds = new Set(loadHiddenPublishedIds());

function loadHiddenPublishedIds() {
  try {
    const rawValue = window.localStorage.getItem(HIDDEN_PUBLISHED_STORAGE_KEY);
    if (!rawValue) {
      return [];
    }

    const parsed = JSON.parse(rawValue);
    return Array.isArray(parsed) ? parsed.filter((value) => typeof value === "string") : [];
  } catch (error) {
    return [];
  }
}

function saveHiddenPublishedIds() {
  window.localStorage.setItem(
    HIDDEN_PUBLISHED_STORAGE_KEY,
    JSON.stringify(Array.from(hiddenPublishedIds)),
  );
}

function setFeedback(message, isError = false) {
  if (!message) {
    queueFeedback.hidden = true;
    queueFeedback.textContent = "";
    queueFeedback.dataset.state = "";
    return;
  }

  queueFeedback.hidden = false;
  queueFeedback.textContent = message;
  queueFeedback.dataset.state = isError ? "error" : "info";
}

function formatDateTime(value, fallback = "Unknown") {
  if (!value) {
    return fallback;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function getStatusLabel(status) {
  switch (status) {
    case "queued":
      return "Ready to post";
    case "publishing":
      return "Publishing now";
    case "published":
      return "Published";
    case "failed":
      return "Publish failed";
    default:
      return status || "Unknown";
  }
}

function formatSourceLabel(url) {
  try {
    const parsed = new URL(url);
    return `${parsed.hostname}${parsed.pathname}`;
  } catch (error) {
    return url;
  }
}

function getMediaSourceLabel(item) {
  if (item?.rendered_from_photo || item?.source_media_kind === "photo_post") {
    return "Photo post rendered as reel";
  }

  return "Video ready";
}

function getActionConfig(status) {
  if (status === "queued") {
    return { label: "Publish", endpoint: "publish", disabled: false };
  }

  if (status === "failed") {
    return { label: "Retry", endpoint: "retry", disabled: false };
  }

  if (status === "publishing") {
    return { label: "Publishing...", endpoint: "", disabled: true };
  }

  return { label: "Published", endpoint: "", disabled: true };
}

function renderRuntime(settings = {}) {
  autoPostEnabledInput.checked = Boolean(settings.auto_post_enabled);
  autoPostIntervalInput.value = settings.auto_post_interval_minutes || 15;
  queueNextRun.textContent = settings.auto_post_enabled
    ? formatDateTime(settings.next_auto_post_at, "Waiting for schedule")
    : "Disabled";
  queueLastAttempt.textContent = formatDateTime(settings.last_auto_post_attempt_at, "No attempts yet");

  const lastResult = settings.last_auto_post_result;
  if (!lastResult) {
    queueLastResult.textContent = "Nothing recorded yet";
    return;
  }

  const resultStatus = lastResult.status ? `[${lastResult.status}] ` : "";
  queueLastResult.textContent = `${resultStatus}${lastResult.message || "No message"}`;
}

function renderPublicCollectionStatus(settings = {}) {
  publicCollectionEnabledInput.checked = Boolean(settings.enabled);
  publicCollectionUrlInput.value = settings.url || "";
  publicCollectionPollSecondsInput.value = settings.poll_seconds || 300;
  publicCollectionStatus.textContent = settings.last_status || "idle";
  publicCollectionLastChecked.textContent = formatDateTime(settings.last_checked_at, "Never");
  publicCollectionItemsFound.textContent = String(settings.last_items_found || 0);
  publicCollectionItemsQueued.textContent = String(settings.last_items_queued || 0);
  publicCollectionStrategy.textContent = settings.last_extract_strategy || "none";
  publicCollectionError.textContent = settings.last_error || "None";
}

function renderQueue(items) {
  const visibleItems = items.filter(
    (item) => item.status !== "published" && !hiddenPublishedIds.has(item.id),
  );
  const readyItems = visibleItems.filter((item) => item.status === "queued");
  queueReadyCount.textContent = `${readyItems.length} post${readyItems.length === 1 ? "" : "s"} ready`;

  queueEmptyState.hidden = visibleItems.length > 0;
  queueGrid.replaceChildren();

  if (!visibleItems.length) {
    return;
  }

  visibleItems.forEach((item, index) => {
    const fragment = queueCardTemplate.content.cloneNode(true);
    const card = fragment.querySelector(".queue-card");
    const actionButton = fragment.querySelector("[data-action='publish']");
    const statusPill = fragment.querySelector("[data-field='status-pill']");
    const previewImage = fragment.querySelector("[data-field='preview-image']");
    const previewFallback = fragment.querySelector("[data-role='preview-fallback']");
    const statusLabel = getStatusLabel(item.status);
    const action = getActionConfig(item.status);
    const title = item.download?.title || item.video_filename || "Queued post";
    const sourceLabel = getMediaSourceLabel(item);

    card.dataset.status = item.status || "queued";
    fragment.querySelector("[data-field='title']").textContent = title;
    fragment.querySelector("[data-field='fallback-title']").textContent = title;
    fragment.querySelector("[data-field='fallback-status']").textContent = `${sourceLabel} • ${statusLabel}`;
    fragment.querySelector("[data-field='status']").textContent = statusLabel;

    const sourceLink = fragment.querySelector("[data-field='source-url']");
    sourceLink.href = item.source_url;
    sourceLink.textContent = `${sourceLabel} • ${formatSourceLabel(item.source_url)}`;

    statusPill.dataset.status = item.status || "queued";
    actionButton.textContent = action.label;
    actionButton.disabled = action.disabled;
    actionButton.dataset.id = item.id;
    actionButton.dataset.endpoint = action.endpoint;

    previewImage.src = `${QUEUE_API_URL}/${item.id}/preview`;
    previewImage.alt = `${title} preview`;
    previewImage.addEventListener("load", () => {
      previewImage.hidden = false;
      previewFallback.hidden = true;
    });
    previewImage.addEventListener("error", () => {
      previewImage.hidden = true;
      previewFallback.hidden = false;
    });

    queueGrid.append(fragment);
  });
}

async function loadQueue({ preserveFeedback = false } = {}) {
  if (!preserveFeedback) {
    setFeedback("");
  }

  const response = await fetch(QUEUE_API_URL);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Failed to load queue");
  }

  renderRuntime(data.settings || {});
  renderQueue(Array.isArray(data.items) ? data.items : []);

  const publicCollectionResponse = await fetch(PUBLIC_COLLECTION_STATUS_API_URL);
  const publicCollectionData = await publicCollectionResponse.json();
  if (!publicCollectionResponse.ok) {
    throw new Error(publicCollectionData.error || "Failed to load public collection monitor");
  }
  renderPublicCollectionStatus(publicCollectionData || {});
}

async function runQueueAction(button) {
  const { endpoint, id } = button.dataset;
  if (!endpoint || !id) {
    return;
  }

  button.disabled = true;
  const previousText = button.textContent;
  button.textContent = endpoint === "retry" ? "Retrying..." : "Publishing...";

  try {
    const response = await fetch(`${QUEUE_API_URL}/${id}/${endpoint}`, {
      method: "POST",
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Queue action failed");
    }

    const resultStatus = data.item?.status;
    if (resultStatus === "failed") {
      setFeedback("Publish failed. Review the item error and retry when ready.", true);
    } else {
      if (resultStatus === "published" && data.item?.id) {
        hiddenPublishedIds.add(data.item.id);
        saveHiddenPublishedIds();
      }
      setFeedback("Queue updated.");
    }

    await loadQueue({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
    button.disabled = false;
    button.textContent = previousText;
  }
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

  try {
    const response = await fetch(QUEUE_SETTINGS_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        auto_post_enabled: autoPostEnabledInput.checked,
        auto_post_interval_minutes: interval,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to save queue settings");
    }

    renderRuntime(data.settings || {});
    setFeedback("Auto-post settings saved.");
    await loadQueue({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
  } finally {
    queueSettingsSaveButton.disabled = false;
    queueSettingsSaveButton.textContent = previousText;
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

  try {
    const response = await fetch(QUEUE_SETTINGS_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
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
    await loadQueue({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
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

  try {
    const response = await fetch(PUBLIC_COLLECTION_TEST_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ url }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Collection test failed");
    }

    setFeedback(
      `Collection reachable. Found ${data.items_found} items using ${data.extract_strategy}.`,
    );
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
  } finally {
    publicCollectionTestButton.disabled = false;
    publicCollectionTestButton.textContent = previousText;
  }
}

async function syncPublicCollection() {
  publicCollectionSyncButton.disabled = true;
  const previousText = publicCollectionSyncButton.textContent;
  publicCollectionSyncButton.textContent = "Syncing...";

  try {
    const response = await fetch(PUBLIC_COLLECTION_SYNC_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        url: publicCollectionUrlInput.value.trim() || undefined,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Collection sync failed");
    }

    if (data.baseline_seeded) {
      setFeedback(`Baseline seeded from ${data.items_found} collection items.`);
    } else {
      setFeedback(
        `Collection sync complete. Found ${data.items_found}, queued ${data.items_queued}, duplicates ${data.duplicates}.`,
      );
    }

    await loadQueue({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
  } finally {
    publicCollectionSyncButton.disabled = false;
    publicCollectionSyncButton.textContent = previousText;
  }
}

async function runNextQueuedItem() {
  queueRunNextButton.disabled = true;
  const previousText = queueRunNextButton.textContent;
  queueRunNextButton.textContent = "Running...";

  try {
    const response = await fetch(QUEUE_RUN_NEXT_API_URL, {
      method: "POST",
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to run the next queued item");
    }

    const resultItem = data.item;
    if (!resultItem) {
      setFeedback(data.message || "No queued items were ready to publish.");
    } else if (resultItem.status === "failed") {
      setFeedback("Publish failed. Review the item error and retry when ready.", true);
    } else if (resultItem.status === "published") {
      hiddenPublishedIds.add(resultItem.id);
      saveHiddenPublishedIds();
      setFeedback("Queued post published.");
    } else {
      setFeedback("Queue updated.");
    }

    await loadQueue({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
  } finally {
    queueRunNextButton.disabled = false;
    queueRunNextButton.textContent = previousText;
  }
}

async function runSystemUpdate() {
  systemUpdateButton.disabled = true;
  const previousText = systemUpdateButton.textContent;
  systemUpdateButton.textContent = "Updating...";

  try {
    const response = await fetch(SYSTEM_UPDATE_API_URL, {
      method: "POST",
    });
    const data = await response.json();
    if (!response.ok) {
      const stageLabel = data.stage ? `${data.stage}: ` : "";
      const details = [data.error || "System update failed", data.stderr || data.stdout || ""]
        .filter(Boolean)
        .join(" ");
      throw new Error(`${stageLabel}${details}`);
    }

    setFeedback(data.message || "Update pulled. Restart requested.");
  } catch (error) {
    setFeedback(error.message, true);
  } finally {
    systemUpdateButton.disabled = false;
    systemUpdateButton.textContent = previousText;
  }
}

queueGrid.addEventListener("click", (event) => {
  const button = event.target.closest(".queue-action");
  if (
    !button
    || button.id === "queue-settings-save"
    || button.id === "queue-run-next"
    || button.id === "system-update"
  ) {
    return;
  }

  runQueueAction(button);
});

queueSettingsSaveButton.addEventListener("click", () => {
  saveQueueSettings();
});

queueRunNextButton.addEventListener("click", () => {
  runNextQueuedItem();
});

systemUpdateButton.addEventListener("click", () => {
  runSystemUpdate();
});

publicCollectionSaveButton.addEventListener("click", () => {
  savePublicCollectionSettings();
});

publicCollectionTestButton.addEventListener("click", () => {
  testPublicCollection();
});

publicCollectionSyncButton.addEventListener("click", () => {
  syncPublicCollection();
});

loadQueue().catch((error) => {
  setFeedback(error.message, true);
  renderRuntime({});
  renderQueue([]);
});
