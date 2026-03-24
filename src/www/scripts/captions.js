const captionCloudList = document.querySelector("#caption-cloud-list");
const addCaptionCloudButton = document.querySelector("#add-caption-cloud");
const captionCloudTemplate = document.querySelector("#caption-cloud-template");
const captionCloudTotal = document.querySelector("#caption-cloud-total");
const captionCharacterTotal = document.querySelector("#caption-character-total");
const captionSaveStatus = document.querySelector("#caption-save-status");

const INITIAL_CLOUD_COUNT = 3;
const COPY_RESET_DELAY_MS = 1400;
const AUTOSAVE_DELAY_MS = 300;
const CAPTIONS_API_URL = "/api/captions";

let hasLoadedWorkspace = false;
let saveTimerId = null;
let isSaving = false;
let hasQueuedSave = false;
let lastSaveFailed = false;

function formatCharacterCount(value) {
  return `${value} character${value === 1 ? "" : "s"}`;
}

function setSaveStatus(state, text) {
  captionSaveStatus.dataset.state = state;
  captionSaveStatus.textContent = text;
}

function createCaptionCloud(initialValue = "") {
  const fragment = captionCloudTemplate.content.cloneNode(true);
  const cloud = fragment.querySelector(".caption-cloud");
  const input = cloud.querySelector(".caption-cloud__input");

  input.value = initialValue;

  return cloud;
}

function getCaptionClouds() {
  return Array.from(captionCloudList.querySelectorAll(".caption-cloud"));
}

function serializeCaptions() {
  return getCaptionClouds().map((cloud) => cloud.querySelector(".caption-cloud__input").value);
}

function updateCloudState(cloud, index) {
  const title = cloud.querySelector(".caption-cloud__title");
  const input = cloud.querySelector(".caption-cloud__input");
  const count = cloud.querySelector(".caption-cloud__count");
  const removeButton = cloud.querySelector('[data-action="remove"]');

  title.textContent = `Caption ${index + 1}`;
  input.setAttribute("aria-label", `Caption ${index + 1} text`);
  count.textContent = formatCharacterCount(input.value.length);
  removeButton.disabled = getCaptionClouds().length === 1;
}

function updateWorkspaceState() {
  const clouds = getCaptionClouds();
  let totalCharacters = 0;

  clouds.forEach((cloud, index) => {
    updateCloudState(cloud, index);
    totalCharacters += cloud.querySelector(".caption-cloud__input").value.length;
  });

  captionCloudTotal.textContent = String(clouds.length);
  captionCharacterTotal.textContent = String(totalCharacters);
}

function renderWorkspace(captions) {
  captionCloudList.replaceChildren();

  captions.forEach((caption) => {
    captionCloudList.append(createCaptionCloud(caption));
  });

  updateWorkspaceState();
}

function ensureMinimumWorkspace() {
  const fallbackCaptions = Array.from({ length: INITIAL_CLOUD_COUNT }, () => "");
  renderWorkspace(fallbackCaptions);
}

async function postCaptions() {
  const payload = { captions: serializeCaptions() };

  isSaving = true;
  setSaveStatus("saving", "Saving...");

  try {
    const response = await fetch(CAPTIONS_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.error || "Failed to save captions");
    }

    lastSaveFailed = false;
    setSaveStatus("saved", "Saved");
  } catch (error) {
    lastSaveFailed = true;
    setSaveStatus("error", "Save failed");
  } finally {
    isSaving = false;

    if (hasQueuedSave) {
      hasQueuedSave = false;
      queueSave({ immediate: true });
    }
  }
}

function queueSave(options = {}) {
  if (!hasLoadedWorkspace) {
    return;
  }

  if (saveTimerId !== null) {
    window.clearTimeout(saveTimerId);
    saveTimerId = null;
  }

  if (isSaving) {
    hasQueuedSave = true;
    return;
  }

  if (!options.immediate) {
    setSaveStatus(lastSaveFailed ? "error" : "saving", lastSaveFailed ? "Retrying..." : "Saving...");
  }

  const delay = options.immediate ? 0 : AUTOSAVE_DELAY_MS;
  saveTimerId = window.setTimeout(() => {
    saveTimerId = null;
    postCaptions();
  }, delay);
}

function addCaptionCloud(options = {}) {
  const cloud = createCaptionCloud(options.value || "");
  captionCloudList.append(cloud);
  updateWorkspaceState();

  if (options.focusInput) {
    cloud.querySelector(".caption-cloud__input").focus();
  }

  if (options.persist !== false) {
    queueSave();
  }
}

function clearCloud(cloud) {
  const input = cloud.querySelector(".caption-cloud__input");
  if (!input.value) {
    return;
  }

  input.value = "";
  updateWorkspaceState();
  input.focus();
  queueSave();
}

async function copyCloud(cloud, button) {
  const input = cloud.querySelector(".caption-cloud__input");
  const value = input.value;
  const originalText = button.textContent;

  if (!value) {
    button.textContent = "Nothing to copy";
    window.setTimeout(() => {
      button.textContent = originalText;
    }, COPY_RESET_DELAY_MS);
    return;
  }

  try {
    await navigator.clipboard.writeText(value);
    button.textContent = "Copied";
  } catch (error) {
    button.textContent = "Copy failed";
  }

  window.setTimeout(() => {
    button.textContent = originalText;
  }, COPY_RESET_DELAY_MS);
}

function removeCloud(cloud) {
  if (getCaptionClouds().length === 1) {
    clearCloud(cloud);
    return;
  }

  cloud.remove();
  updateWorkspaceState();
  queueSave();
}

async function loadWorkspace() {
  setSaveStatus("loading", "Loading drafts...");

  try {
    const response = await fetch(CAPTIONS_API_URL);
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.error || "Failed to load captions");
    }

    if (Array.isArray(data.captions) && data.captions.length > 0) {
      renderWorkspace(data.captions);
      hasLoadedWorkspace = true;
      setSaveStatus("saved", "Saved");
      return;
    }

    ensureMinimumWorkspace();
    hasLoadedWorkspace = true;
    queueSave();
  } catch (error) {
    ensureMinimumWorkspace();
    hasLoadedWorkspace = true;
    lastSaveFailed = true;
    setSaveStatus("error", "Load failed");
  }
}

addCaptionCloudButton.addEventListener("click", () => {
  addCaptionCloud({ focusInput: true });
});

captionCloudList.addEventListener("input", (event) => {
  if (!event.target.matches(".caption-cloud__input")) {
    return;
  }

  updateWorkspaceState();
  queueSave();
});

captionCloudList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) {
    return;
  }

  const cloud = button.closest(".caption-cloud");
  if (!cloud) {
    return;
  }

  const action = button.dataset.action;

  if (action === "copy") {
    copyCloud(cloud, button);
    return;
  }

  if (action === "clear") {
    clearCloud(cloud);
    return;
  }

  if (action === "remove") {
    removeCloud(cloud);
  }
});

loadWorkspace();
