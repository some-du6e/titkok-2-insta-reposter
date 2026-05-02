const queueGrid = document.querySelector("#queue-grid");
const queueCardTemplate = document.querySelector("#queue-card-template");
const queueReadyCount = document.querySelector("#queue-ready-count");
const queueSummaryCopy = document.querySelector("#queue-summary-copy");
const queueEmptyState = document.querySelector("#queue-empty-state");
const queueFeedback = document.querySelector("#queue-feedback");
const queueOperationStatus = document.querySelector("#queue-operation-status");
const queueOperationTitle = document.querySelector("#queue-operation-title");
const queueOperationCopy = document.querySelector("#queue-operation-copy");
const queueStatReady = document.querySelector("#queue-stat-ready");
const queueStatPublishing = document.querySelector("#queue-stat-publishing");
const queueStatFailed = document.querySelector("#queue-stat-failed");
const queueStatPublished = document.querySelector("#queue-stat-published");
const autoPostEnabledInput = document.querySelector("#auto-post-enabled");
const autoPostIntervalInput = document.querySelector("#auto-post-interval");
const prependCoverIntroEnabledInput = document.querySelector("#prepend-cover-intro-enabled");
const coverImageFileInput = document.querySelector("#cover-image-file");
const coverImageUploadButton = document.querySelector("#cover-image-upload");
const coverImageUrlInput = document.querySelector("#cover-image-url");
const coverImageFromUrlButton = document.querySelector("#cover-image-from-url");
const queueSettingsSaveButton = document.querySelector("#queue-settings-save");
const queueRunNextButton = document.querySelector("#queue-run-next");
const systemRestartButton = document.querySelector("#system-restart");
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
const COVER_IMAGE_API_URL = "/api/cover-image";
const COVER_IMAGE_FROM_URL_API_URL = "/api/cover-image/from-url";
const SYSTEM_RESTART_API_URL = "/api/system/restart";
const SYSTEM_UPDATE_API_URL = "/api/system/update";
const PUBLIC_COLLECTION_STATUS_API_URL = "/api/public-collection/status";
const PUBLIC_COLLECTION_TEST_API_URL = "/api/public-collection/test";
const PUBLIC_COLLECTION_SYNC_API_URL = "/api/public-collection/sync";
const HIDDEN_PUBLISHED_STORAGE_KEY = "tt2ig-hidden-published-ids";
const hiddenPublishedIds = new Set(loadHiddenPublishedIds());
const activeQueueOperations = new Set();

let operationHintTimerId = null;

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

function setOperationStatus({ title, detail, state = "working", persistent = true }) {
  if (operationHintTimerId !== null) {
    window.clearTimeout(operationHintTimerId);
    operationHintTimerId = null;
  }

  queueOperationStatus.hidden = false;
  queueOperationStatus.dataset.state = state;
  queueOperationTitle.textContent = title;
  queueOperationCopy.textContent = detail;

  if (!persistent) {
    operationHintTimerId = window.setTimeout(() => {
      queueOperationStatus.hidden = true;
      queueOperationStatus.dataset.state = "";
    }, 3200);
  }
}

function clearOperationStatus() {
  if (operationHintTimerId !== null) {
    window.clearTimeout(operationHintTimerId);
    operationHintTimerId = null;
  }

  queueOperationStatus.hidden = true;
  queueOperationStatus.dataset.state = "";
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

function formatOperationLabel(endpoint) {
  if (endpoint === "retry") {
    return "Retry";
  }

  return "Publish";
}

function setOperationBusyMessage(actionLabel, title) {
  setOperationStatus({
    title: `${actionLabel} in progress`,
    detail: `${title} is being processed now. This request can take a while while media is prepared and Instagram responds.`,
  });
}

function scheduleSlowOperationHint(actionLabel, title) {
  if (operationHintTimerId !== null) {
    window.clearTimeout(operationHintTimerId);
  }

  operationHintTimerId = window.setTimeout(() => {
    setOperationStatus({
      title: `${actionLabel} still running`,
      detail: `${title} has not finished yet. The request is still open; wait for a success or failure message before trying again.`,
    });
  }, 4500);
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

function updateQueueBusyState() {
  queueGrid.setAttribute("aria-busy", activeQueueOperations.size > 0 ? "true" : "false");
}

function renderRuntime(settings = {}) {
  autoPostEnabledInput.checked = Boolean(settings.auto_post_enabled);
  autoPostIntervalInput.value = settings.auto_post_interval_minutes || 15;
  prependCoverIntroEnabledInput.checked = Boolean(settings.prependCoverIntroEnabled);
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
  const publishingItems = visibleItems.filter((item) => item.status === "publishing");
  const failedItems = visibleItems.filter((item) => item.status === "failed");
  const publishedItems = items.filter((item) => item.status === "published");

  queueReadyCount.textContent = `${readyItems.length} post${readyItems.length === 1 ? "" : "s"} ready`;
  queueStatReady.textContent = String(readyItems.length);
  queueStatPublishing.textContent = String(publishingItems.length);
  queueStatFailed.textContent = String(failedItems.length);
  queueStatPublished.textContent = String(publishedItems.length);
  queueSummaryCopy.textContent = failedItems.length
    ? `${failedItems.length} failed item${failedItems.length === 1 ? "" : "s"} need review before the next clean run.`
    : readyItems.length
      ? "Queue is primed for the next manual or scheduled publish."
      : "No ready items in the queue right now.";

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
    const updatedAt = formatDateTime(item.updated_at || item.created_at, "Unknown");

    card.dataset.status = item.status || "queued";
    card.dataset.itemId = item.id;
    fragment.querySelector("[data-field='title']").textContent = title;
    fragment.querySelector("[data-field='fallback-title']").textContent = title;
    fragment.querySelector("[data-field='fallback-status']").textContent = `${sourceLabel} • ${statusLabel}`;
    fragment.querySelector("[data-field='status']").textContent = statusLabel;
    fragment.querySelector("[data-field='meta']").textContent = `Last updated ${updatedAt}`;

    const sourceLink = fragment.querySelector("[data-field='source-url']");
    sourceLink.href = item.source_url;
    sourceLink.textContent = `${sourceLabel} • ${formatSourceLabel(item.source_url)}`;

    const lastError = fragment.querySelector("[data-field='last-error']");
    if (item.last_error) {
      lastError.hidden = false;
      lastError.textContent = item.last_error;
    }

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

function markQueueCardBusy(itemId, isBusy, actionLabel = "Working") {
  const card = queueGrid.querySelector(`[data-item-id="${itemId}"]`);
  if (!card) {
    return;
  }

  card.classList.toggle("is-busy", isBusy);

  const actionButton = card.querySelector("[data-action='publish']");
  if (actionButton) {
    if (isBusy) {
      actionButton.dataset.previousDisabled = actionButton.disabled ? "true" : "false";
      actionButton.dataset.previousLabel = actionButton.textContent;
      actionButton.disabled = true;
      actionButton.textContent = `${actionLabel}...`;
    } else if (actionButton.dataset.previousLabel) {
      actionButton.disabled = actionButton.dataset.previousDisabled === "true";
      actionButton.textContent = actionButton.dataset.previousLabel;
      delete actionButton.dataset.previousDisabled;
      delete actionButton.dataset.previousLabel;
    }
  }

  const statusPill = card.querySelector("[data-field='status-pill']");
  const statusText = card.querySelector("[data-field='status']");
  if (statusPill && statusText) {
    if (isBusy) {
      statusPill.dataset.previousStatus = statusPill.dataset.status || "";
      statusText.dataset.previousText = statusText.textContent;
      statusPill.dataset.status = "working";
      statusText.textContent = `${actionLabel}...`;
    } else {
      if (statusPill.dataset.previousStatus) {
        statusPill.dataset.status = statusPill.dataset.previousStatus;
        delete statusPill.dataset.previousStatus;
      }
      if (statusText.dataset.previousText) {
        statusText.textContent = statusText.dataset.previousText;
        delete statusText.dataset.previousText;
      }
    }
  }
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

  const card = button.closest(".queue-card");
  const title = card?.querySelector("[data-field='title']")?.textContent || "Queue item";
  const actionLabel = formatOperationLabel(endpoint);

  activeQueueOperations.add(id);
  updateQueueBusyState();
  setOperationBusyMessage(actionLabel, title);
  scheduleSlowOperationHint(actionLabel, title);
  markQueueCardBusy(id, true, actionLabel);

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
      setOperationStatus({
        title: `${actionLabel} failed`,
        detail: `${title} did not pass. The latest error is shown on the card so you can decide whether to retry again.`,
        state: "error",
      });
    } else {
      if (resultStatus === "published" && data.item?.id) {
        hiddenPublishedIds.add(data.item.id);
        saveHiddenPublishedIds();
      }
      setFeedback("Queue updated.");
      setOperationStatus({
        title: `${actionLabel} finished`,
        detail: resultStatus === "published"
          ? `${title} published successfully.`
          : `${title} completed and the queue state has been refreshed.`,
        state: "success",
      });
    }

    await loadQueue({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({
      title: `${actionLabel} failed`,
      detail: `${title} could not be processed: ${error.message}`,
      state: "error",
    });
    button.disabled = false;
    button.textContent = previousText;
  } finally {
    activeQueueOperations.delete(id);
    updateQueueBusyState();
    markQueueCardBusy(id, false, actionLabel);
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
  setOperationStatus({
    title: "Saving queue settings",
    detail: "Updating scheduler controls and refreshing the runtime state.",
  });

  try {
    const response = await fetch(QUEUE_SETTINGS_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        auto_post_enabled: autoPostEnabledInput.checked,
        auto_post_interval_minutes: interval,
        prependCoverIntroEnabled: prependCoverIntroEnabledInput.checked,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to save queue settings");
    }

    renderRuntime(data.settings || {});
    setFeedback("Queue settings saved.");
    setOperationStatus({
      title: "Queue settings saved",
      detail: "Scheduler settings are stored and the latest runtime state is on screen.",
      state: "success",
      persistent: false,
    });
    await loadQueue({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({
      title: "Queue settings failed",
      detail: error.message,
      state: "error",
    });
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
  setOperationStatus({
    title: "Uploading cover image",
    detail: "Saving the new global cover intro frame.",
  });

  try {
    const formData = new FormData();
    formData.append("cover_image", selectedFile);

    const response = await fetch(COVER_IMAGE_API_URL, {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to upload cover image");
    }

    coverImageFileInput.value = "";
    setFeedback(`Cover image uploaded: ${data.filename}`);
    setOperationStatus({
      title: "Cover image uploaded",
      detail: `${data.filename} is now the active global cover intro frame.`,
      state: "success",
      persistent: false,
    });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({
      title: "Cover upload failed",
      detail: error.message,
      state: "error",
    });
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
  setOperationStatus({
    title: "Fetching video cover",
    detail: "Pulling a cover image from the TikTok URL you entered.",
  });

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
    setOperationStatus({
      title: "Video cover fetch failed",
      detail: error.message,
      state: "error",
    });
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
  setOperationStatus({
    title: "Saving collection monitor",
    detail: "Updating the public collection URL and poll cadence.",
  });

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
    setOperationStatus({
      title: "Collection monitor saved",
      detail: "The monitor settings are stored and the latest state is being refreshed.",
      state: "success",
      persistent: false,
    });
    await loadQueue({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({
      title: "Collection monitor save failed",
      detail: error.message,
      state: "error",
    });
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
  setOperationStatus({
    title: "Testing collection URL",
    detail: "Checking whether the collection is reachable and how many items are visible.",
  });

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
    setOperationStatus({
      title: "Collection test failed",
      detail: error.message,
      state: "error",
    });
  } finally {
    publicCollectionTestButton.disabled = false;
    publicCollectionTestButton.textContent = previousText;
  }
}

async function syncPublicCollection() {
  publicCollectionSyncButton.disabled = true;
  const previousText = publicCollectionSyncButton.textContent;
  publicCollectionSyncButton.textContent = "Syncing...";
  setOperationStatus({
    title: "Syncing collection",
    detail: "Checking the public collection and queueing any newly discovered items.",
  });

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
      setOperationStatus({
        title: "Collection sync finished",
        detail: `Seeded the baseline from ${data.items_found} collection items.`,
        state: "success",
        persistent: false,
      });
    } else {
      setFeedback(
        `Collection sync complete. Found ${data.items_found}, queued ${data.items_queued}, duplicates ${data.duplicates}.`,
      );
      setOperationStatus({
        title: "Collection sync finished",
        detail: `Found ${data.items_found}, queued ${data.items_queued}, duplicates ${data.duplicates}.`,
        state: "success",
        persistent: false,
      });
    }

    await loadQueue({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({
      title: "Collection sync failed",
      detail: error.message,
      state: "error",
    });
  } finally {
    publicCollectionSyncButton.disabled = false;
    publicCollectionSyncButton.textContent = previousText;
  }
}

async function runNextQueuedItem() {
  queueRunNextButton.disabled = true;
  const previousText = queueRunNextButton.textContent;
  queueRunNextButton.textContent = "Running...";
  setOperationStatus({
    title: "Running next queued item",
    detail: "Processing the oldest ready post now. This can take a while if media needs prep or Instagram is slow.",
  });

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
      setOperationStatus({
        title: "Nothing ran",
        detail: data.message || "No queued items were ready to publish.",
        state: "success",
        persistent: false,
      });
    } else if (resultItem.status === "failed") {
      setFeedback("Publish failed. Review the item error and retry when ready.", true);
      setOperationStatus({
        title: "Run failed",
        detail: "The queued item failed. Refresh completed and the latest error is shown in the queue.",
        state: "error",
      });
    } else if (resultItem.status === "published") {
      hiddenPublishedIds.add(resultItem.id);
      saveHiddenPublishedIds();
      setFeedback("Queued post published.");
      setOperationStatus({
        title: "Run finished",
        detail: "The queued item published successfully.",
        state: "success",
        persistent: false,
      });
    } else {
      setFeedback("Queue updated.");
      setOperationStatus({
        title: "Run finished",
        detail: "The queue state was refreshed after the manual run.",
        state: "success",
        persistent: false,
      });
    }

    await loadQueue({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({
      title: "Run failed",
      detail: error.message,
      state: "error",
    });
  } finally {
    queueRunNextButton.disabled = false;
    queueRunNextButton.textContent = previousText;
  }
}

async function runSystemUpdate() {
  systemUpdateButton.disabled = true;
  const previousText = systemUpdateButton.textContent;
  systemUpdateButton.textContent = "Updating...";
  setOperationStatus({
    title: "Updating app",
    detail: "Pulling the latest code and applying the update routine.",
  });

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
    setOperationStatus({
      title: "Update finished",
      detail: data.message || "The update completed and a restart was requested.",
      state: "success",
    });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({
      title: "Update failed",
      detail: error.message,
      state: "error",
    });
  } finally {
    systemUpdateButton.disabled = false;
    systemUpdateButton.textContent = previousText;
  }
}

async function runSystemRestart() {
  systemRestartButton.disabled = true;
  const previousText = systemRestartButton.textContent;
  systemRestartButton.textContent = "Restarting...";
  setOperationStatus({
    title: "Restarting app",
    detail: "The restart request is being sent now.",
  });

  try {
    const response = await fetch(SYSTEM_RESTART_API_URL, {
      method: "POST",
    });
    const data = await response.json();
    if (!response.ok) {
      const stageLabel = data.stage ? `${data.stage}: ` : "";
      const details = [data.error || "System restart failed", data.stderr || data.stdout || ""]
        .filter(Boolean)
        .join(" ");
      throw new Error(`${stageLabel}${details}`);
    }

    setFeedback(data.message || "Restart requested.");
    setOperationStatus({
      title: "Restart requested",
      detail: data.message || "The restart command was accepted.",
      state: "success",
    });
  } catch (error) {
    setFeedback(error.message, true);
    setOperationStatus({
      title: "Restart failed",
      detail: error.message,
      state: "error",
    });
  } finally {
    systemRestartButton.disabled = false;
    systemRestartButton.textContent = previousText;
  }
}

queueGrid.addEventListener("click", (event) => {
  const button = event.target.closest(".queue-action");
  if (
    !button
    || button.id === "queue-settings-save"
    || button.id === "queue-run-next"
    || button.id === "system-restart"
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

systemRestartButton.addEventListener("click", () => {
  runSystemRestart();
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

coverImageUploadButton.addEventListener("click", () => {
  uploadCoverImage();
});

coverImageFromUrlButton.addEventListener("click", () => {
  fetchCoverFromUrl();
});

loadQueue().catch((error) => {
  setFeedback(error.message, true);
  setOperationStatus({
    title: "Queue load failed",
    detail: error.message,
    state: "error",
  });
  renderRuntime({});
  renderQueue([]);
});
