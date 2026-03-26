const ALARM_NAME = "favorites-monitor-scan";
const DEFAULT_SETTINGS = {
  monitorEnabled: false,
  serverBaseUrl: "http://localhost:6767",
  pollIntervalSeconds: 60,
};
const MAX_SEEN_ITEMS = 500;

function normalizeBaseUrl(url) {
  return (url || DEFAULT_SETTINGS.serverBaseUrl).trim().replace(/\/+$/, "") || DEFAULT_SETTINGS.serverBaseUrl;
}

async function getMonitorState() {
  const data = await chrome.storage.local.get([
    "monitorEnabled",
    "serverBaseUrl",
    "pollIntervalSeconds",
    "seenFavoriteIds",
    "seenFavoriteUrls",
    "favoritesTabId",
    "lastScanAt",
    "lastScanStatus",
    "lastScanError",
    "lastItemsFound",
    "lastItemsQueued",
    "baselineSeeded",
  ]);

  return {
    ...DEFAULT_SETTINGS,
    ...data,
    serverBaseUrl: normalizeBaseUrl(data.serverBaseUrl),
    seenFavoriteIds: Array.isArray(data.seenFavoriteIds) ? data.seenFavoriteIds : [],
    seenFavoriteUrls: Array.isArray(data.seenFavoriteUrls) ? data.seenFavoriteUrls : [],
    baselineSeeded: Boolean(data.baselineSeeded),
  };
}

async function setRuntimeStatus(updates) {
  await chrome.storage.local.set({
    ...updates,
    lastScanAt: updates.lastScanAt || new Date().toISOString(),
  });
}

async function syncAlarm() {
  const state = await getMonitorState();
  await chrome.alarms.clear(ALARM_NAME);

  if (!state.monitorEnabled) {
    await setRuntimeStatus({
      lastScanStatus: "idle",
      lastScanError: "",
      lastItemsFound: 0,
      lastItemsQueued: 0,
    });
    return;
  }

  const intervalMinutes = Math.max(1, Number(state.pollIntervalSeconds || DEFAULT_SETTINGS.pollIntervalSeconds) / 60);
  await chrome.alarms.create(ALARM_NAME, { periodInMinutes: intervalMinutes });
}

async function findFavoritesTab() {
  const tabs = await chrome.tabs.query({ url: "*://*.tiktok.com/*" });
  return tabs.find((tab) => {
    const url = (tab.url || "").toLowerCase();
    return url.includes("/favorites") || url.includes("/favourite");
  }) || null;
}

async function scanFavoritesTab(tab) {
  if (!tab?.id) {
    return { ok: false, pageType: "unknown", items: [], error: "Favorites tab is missing an id." };
  }

  await chrome.tabs.reload(tab.id, { bypassCache: true });
  await waitForTabComplete(tab.id, 15000);
  await new Promise((resolve) => setTimeout(resolve, 2500));

  return chrome.tabs.sendMessage(tab.id, { type: "scanFavorites" });
}

function waitForTabComplete(tabId, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    let finished = false;

    const cleanup = () => {
      if (finished) {
        return;
      }
      finished = true;
      chrome.tabs.onUpdated.removeListener(handleUpdated);
      clearTimeout(timeoutId);
    };

    const handleUpdated = (updatedTabId, changeInfo) => {
      if (updatedTabId !== tabId) {
        return;
      }

      if (changeInfo.status === "complete") {
        cleanup();
        resolve();
      }
    };

    const timeoutId = setTimeout(() => {
      cleanup();
      reject(new Error("Timed out waiting for TikTok favorites page refresh."));
    }, timeoutMs);

    chrome.tabs.onUpdated.addListener(handleUpdated);
  });
}

async function findScannableFavoritesTab() {
  const tabs = await chrome.tabs.query({ url: "*://*.tiktok.com/*" });

  for (const tab of tabs) {
    try {
      const result = await chrome.tabs.sendMessage(tab.id, { type: "scanFavorites" });
      if (result?.pageType === "favorites") {
        return { tab, result };
      }
    } catch (_error) {
      continue;
    }
  }

  return { tab: null, result: null };
}

async function sendToServer(url, state, tab) {
  const payload = new URLSearchParams();
  payload.set("url", url);
  payload.set("source_kind", "favorites_monitor");
  payload.set("client", "chrome_extension");
  payload.set("discovered_at", new Date().toISOString());
  if (tab?.url) {
    payload.set("monitor_tab_url", tab.url);
  }

  const response = await fetch(`${state.serverBaseUrl}/api/get_tiktok_link`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: payload.toString(),
  });

  let data = null;
  try {
    data = await response.json();
  } catch (_error) {
    data = null;
  }

  if (!response.ok) {
    throw new Error(data?.error || `Server returned ${response.status}`);
  }

  return data;
}

function trimSeenItems(items) {
  return items.slice(Math.max(0, items.length - MAX_SEEN_ITEMS));
}

async function persistSeenItems(state, items) {
  const seenIds = new Set(state.seenFavoriteIds);
  const seenUrls = new Set(state.seenFavoriteUrls);

  for (const item of items) {
    if (item.id) {
      seenIds.add(item.id);
    }
    if (item.url) {
      seenUrls.add(item.url);
    }
  }

  await chrome.storage.local.set({
    seenFavoriteIds: trimSeenItems([...seenIds]),
    seenFavoriteUrls: trimSeenItems([...seenUrls]),
  });
}

function filterUnseenItems(items, state) {
  const seenIds = new Set(state.seenFavoriteIds);
  const seenUrls = new Set(state.seenFavoriteUrls);
  return items.filter((item) => !seenIds.has(item.id) && !seenUrls.has(item.url));
}

async function runMonitorScan() {
  const state = await getMonitorState();
  if (!state.monitorEnabled) {
    return;
  }

  await setRuntimeStatus({
    lastScanStatus: "scanning",
    lastScanError: "",
    lastItemsFound: 0,
    lastItemsQueued: 0,
  });

  const discovered = await findScannableFavoritesTab();
  const tab = discovered.tab || await findFavoritesTab();
  if (!tab?.id) {
    await setRuntimeStatus({
      lastScanStatus: "waiting_for_tab",
      lastScanError: "",
      lastItemsFound: 0,
      lastItemsQueued: 0,
      favoritesTabId: null,
    });
    return;
  }

  await chrome.storage.local.set({ favoritesTabId: tab.id });

  let result = null;
  try {
    result = await scanFavoritesTab(tab);
  } catch (error) {
    await setRuntimeStatus({
      lastScanStatus: "parse_error",
      lastScanError: chrome.runtime.lastError?.message || error?.message || String(error),
      lastItemsFound: 0,
      lastItemsQueued: 0,
    });
    return;
  }

  if (result.pageType !== "favorites") {
    await setRuntimeStatus({
      lastScanStatus: "wrong_page",
      lastScanError: "",
      lastItemsFound: 0,
      lastItemsQueued: 0,
    });
    return;
  }

  if (!result.ok) {
    await setRuntimeStatus({
      lastScanStatus: "parse_error",
      lastScanError: result.error || "Unable to scan favorites page.",
      lastItemsFound: 0,
      lastItemsQueued: 0,
    });
    return;
  }

  const items = Array.isArray(result.items) ? result.items : [];
  if (!state.baselineSeeded) {
    await persistSeenItems(state, items);
    await chrome.storage.local.set({ baselineSeeded: true });
    await setRuntimeStatus({
      lastScanStatus: "baseline_ready",
      lastScanError: "",
      lastItemsFound: items.length,
      lastItemsQueued: 0,
    });
    return;
  }

  const unseenItems = filterUnseenItems(items, state);
  let queuedCount = 0;
  let sawNewItem = false;

  for (const item of unseenItems) {
    try {
      const response = await sendToServer(item.url, state, tab);
      if (response?.status === "queued") {
        queuedCount += 1;
      }
      if (response?.status === "queued" || response?.status === "duplicate") {
        sawNewItem = true;
        await persistSeenItems(await getMonitorState(), [item]);
      }
    } catch (error) {
      await setRuntimeStatus({
        lastScanStatus: "server_error",
        lastScanError: error?.message || String(error),
        lastItemsFound: items.length,
        lastItemsQueued: queuedCount,
      });
      return;
    }
  }

  await setRuntimeStatus({
    lastScanStatus: queuedCount > 0 ? "queued" : (sawNewItem ? "duplicate_only" : "idle"),
    lastScanError: "",
    lastItemsFound: items.length,
    lastItemsQueued: queuedCount,
  });
}

async function sendCurrentTabToServer() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !(tab.url || "").includes("tiktok.com")) {
    return;
  }

  const state = await getMonitorState();
  const payload = new URLSearchParams();
  payload.set("url", tab.url);
  payload.set("source_kind", "manual");
  payload.set("client", "chrome_extension");

  await fetch(`${state.serverBaseUrl}/api/get_tiktok_link`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: payload.toString(),
  });
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(["monitorEnabled", "serverBaseUrl", "pollIntervalSeconds", "baselineSeeded"], (stored) => {
    chrome.storage.local.set(
      {
        monitorEnabled: typeof stored.monitorEnabled === "boolean" ? stored.monitorEnabled : DEFAULT_SETTINGS.monitorEnabled,
        serverBaseUrl: stored.serverBaseUrl || DEFAULT_SETTINGS.serverBaseUrl,
        pollIntervalSeconds: stored.pollIntervalSeconds || DEFAULT_SETTINGS.pollIntervalSeconds,
        baselineSeeded: Boolean(stored.baselineSeeded),
      },
      () => {
        syncAlarm().catch((error) => console.error("Failed to sync monitor alarm:", error));
      }
    );
  });
});

chrome.runtime.onStartup.addListener(() => {
  syncAlarm().catch((error) => console.error("Failed to sync monitor alarm:", error));
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== ALARM_NAME) {
    return;
  }

  runMonitorScan().catch((error) => {
    setRuntimeStatus({
      lastScanStatus: "server_error",
      lastScanError: error?.message || String(error),
      lastItemsFound: 0,
      lastItemsQueued: 0,
    }).catch(() => {});
  });
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "monitorSettingsUpdated") {
    return false;
  }

  syncAlarm()
    .then(async () => {
      const state = await getMonitorState();
      if (state.monitorEnabled) {
        await runMonitorScan();
      }
      sendResponse({ ok: true });
    })
    .catch((error) => sendResponse({ ok: false, error: error?.message || String(error) }));

  return true;
});

chrome.commands.onCommand.addListener((command) => {
  if (command !== "send-tt") {
    return;
  }

  sendCurrentTabToServer().catch((error) => {
    console.error("Manual TikTok send failed:", error);
  });
});

