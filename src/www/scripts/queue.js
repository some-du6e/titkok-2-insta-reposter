const queueGrid = document.querySelector("#queue-grid");
const queueCardTemplate = document.querySelector("#queue-card-template");
const queueReadyCount = document.querySelector("#queue-ready-count");
const queueEmptyState = document.querySelector("#queue-empty-state");
const queueFeedback = document.querySelector("#queue-feedback");

const QUEUE_API_URL = "/api/queue";
const TONES = ["berry", "rose", "violet", "peach", "gold", "plum"];

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

function getStatusLine(item) {
  if (item.status === "published" && item.published_at) {
    return `Published ${new Date(item.published_at).toLocaleString()}`;
  }

  if (item.status === "failed" && item.last_error) {
    return "Retry after checking the error below";
  }

  return item.download?.title || item.video_filename || "Queued video";
}

function truncateText(text, maxLength = 120) {
  if (!text) {
    return "";
  }

  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength - 1)}…`;
}

function formatSourceLabel(url) {
  try {
    const parsed = new URL(url);
    return `${parsed.hostname}${parsed.pathname}`;
  } catch (error) {
    return url;
  }
}

function formatCreatedAt(value) {
  if (!value) {
    return "Unknown";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
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

function renderQueue(items) {
  const readyItems = items.filter((item) => item.status === "queued");
  queueReadyCount.textContent = `${readyItems.length} video${readyItems.length === 1 ? "" : "s"} ready`;

  queueEmptyState.hidden = items.length > 0;
  queueGrid.replaceChildren();

  if (!items.length) {
    return;
  }

  items.forEach((item, index) => {
    const fragment = queueCardTemplate.content.cloneNode(true);
    const card = fragment.querySelector(".queue-card");
    const actionButton = fragment.querySelector("[data-action='publish']");
    const errorWrap = fragment.querySelector("[data-role='error-wrap']");
    const statusPill = fragment.querySelector("[data-field='status-pill']");
    const statusLabel = getStatusLabel(item.status);
    const action = getActionConfig(item.status);

    card.dataset.tone = TONES[index % TONES.length];
    card.dataset.status = item.status || "queued";
    fragment.querySelector("[data-field='title']").textContent =
      item.download?.title || item.video_filename || "Queued video";
    fragment.querySelector("[data-field='status-line']").textContent = getStatusLine(item);
    fragment.querySelector("[data-field='caption']").textContent = truncateText(item.caption, 180);
    fragment.querySelector("[data-field='created-at']").textContent = formatCreatedAt(item.created_at);
    fragment.querySelector("[data-field='filename']").textContent = item.video_filename || "Unknown";
    fragment.querySelector("[data-field='status']").textContent = statusLabel;
    fragment.querySelector("[data-field='index-pill']").textContent = `#${index + 1}`;

    const sourceLink = fragment.querySelector("[data-field='source-url']");
    sourceLink.href = item.source_url;
    sourceLink.textContent = formatSourceLabel(item.source_url);

    if (item.last_error) {
      errorWrap.hidden = false;
      fragment.querySelector("[data-field='last-error']").textContent = item.last_error;
    }

    statusPill.dataset.status = item.status || "queued";
    actionButton.textContent = action.label;
    actionButton.disabled = action.disabled;
    actionButton.dataset.id = item.id;
    actionButton.dataset.endpoint = action.endpoint;

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

  renderQueue(Array.isArray(data.items) ? data.items : []);
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
      setFeedback("Queue updated.");
    }

    await loadQueue({ preserveFeedback: true });
  } catch (error) {
    setFeedback(error.message, true);
    button.disabled = false;
    button.textContent = previousText;
  }
}

queueGrid.addEventListener("click", (event) => {
  const button = event.target.closest(".queue-action");
  if (!button) {
    return;
  }

  runQueueAction(button);
});

loadQueue().catch((error) => {
  setFeedback(error.message, true);
  renderQueue([]);
});
