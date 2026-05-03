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
const queueRunNextButton = document.querySelector("#queue-run-next");
const queueAutoMode = document.querySelector("#queue-auto-mode");
const queueAutoCadence = document.querySelector("#queue-auto-cadence");
const queueNextRun = document.querySelector("#queue-next-run");
const queueLastAttempt = document.querySelector("#queue-last-attempt");
const queueLastResult = document.querySelector("#queue-last-result");
const queueCoverIntro = document.querySelector("#queue-cover-intro");
const publicCollectionMode = document.querySelector("#public-collection-mode");
const publicCollectionCadence = document.querySelector("#public-collection-cadence");
const publicCollectionStatus = document.querySelector("#public-collection-status");
const publicCollectionLastChecked = document.querySelector("#public-collection-last-checked");
const publicCollectionItemsFound = document.querySelector("#public-collection-items-found");
const publicCollectionItemsQueued = document.querySelector("#public-collection-items-queued");
const publicCollectionStrategy = document.querySelector("#public-collection-strategy");
const publicCollectionError = document.querySelector("#public-collection-error");

const QUEUE_API_URL = "/api/queue";
const QUEUE_RUN_NEXT_API_URL = "/api/queue/run-next";
const PUBLIC_COLLECTION_STATUS_API_URL = "/api/public-collection/status";
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
  const autoPostEnabled = Boolean(settings.auto_post_enabled);
  queueAutoMode.textContent = autoPostEnabled ? "Automatic" : "Manual";
  queueAutoCadence.textContent = autoPostEnabled
    ? `Every ${settings.auto_post_interval_minutes || "?"} minute${settings.auto_post_interval_minutes === 1 ? "" : "s"}`
    : "Disabled";
  queueNextRun.textContent = settings.auto_post_enabled
    ? formatDateTime(settings.next_auto_post_at, "Waiting for schedule")
    : "Disabled";
  queueLastAttempt.textContent = formatDateTime(settings.last_auto_post_attempt_at, "No attempts yet");
  queueCoverIntro.textContent = settings.prependCoverIntroEnabled ? "Enabled" : "Disabled";

  const lastResult = settings.last_auto_post_result;
  if (!lastResult) {
    queueLastResult.textContent = "Nothing recorded yet";
    return;
  }

  const resultStatus = lastResult.status ? `[${lastResult.status}] ` : "";
  queueLastResult.textContent = `${resultStatus}${lastResult.message || "No message"}`;
}

function renderPublicCollectionStatus(settings = {}) {
  publicCollectionMode.textContent = settings.enabled ? "Enabled" : "Disabled";
  publicCollectionCadence.textContent = settings.enabled
    ? `Every ${settings.poll_seconds || "?"} second${settings.poll_seconds === 1 ? "" : "s"}`
    : "Disabled";
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

queueGrid.addEventListener("click", (event) => {
  const button = event.target.closest(".queue-action");
  if (!button || button.id === "queue-run-next") {
    return;
  }

  runQueueAction(button);
});

queueRunNextButton.addEventListener("click", () => {
  runNextQueuedItem();
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
