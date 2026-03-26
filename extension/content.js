function normalizeTikTokUrl(url) {
  try {
    const parsed = new URL(url, window.location.origin);
    parsed.hash = "";

    for (const key of [...parsed.searchParams.keys()]) {
      if (key.startsWith("utm_")) {
        parsed.searchParams.delete(key);
      }
    }

    parsed.pathname = parsed.pathname.replace(/\/+$/, "") || "/";
    return parsed.toString();
  } catch (_error) {
    return null;
  }
}

function extractVideoIdFromUrl(url) {
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.split("/").filter(Boolean);
    const videoIndex = parts.indexOf("video");
    if (videoIndex === -1 || videoIndex + 1 >= parts.length) {
      return null;
    }

    const candidate = parts[videoIndex + 1];
    return /^\d+$/.test(candidate) ? candidate : null;
  } catch (_error) {
    return null;
  }
}

function isFavoritesPage() {
  const path = window.location.pathname.toLowerCase();
  return (
    path.includes("/favorites")
    || path.includes("/favourite")
    || Boolean(document.querySelector("#main-content-collection"))
    || Boolean(document.querySelector('[data-e2e="collection-item-list"]'))
  );
}

function collectFavoriteItems() {
  const collectionItems = document.querySelectorAll('[data-e2e="collection-item"]');
  const preferredLinks = [...collectionItems]
    .map((item) => item.querySelector('a[href*="/video/"]'))
    .filter(Boolean);
  const links = preferredLinks.length ? preferredLinks : [...document.querySelectorAll('a[href*="/video/"]')];
  const itemsByKey = new Map();

  for (const link of links) {
    const normalizedUrl = normalizeTikTokUrl(link.href);
    if (!normalizedUrl || !normalizedUrl.includes("/video/")) {
      continue;
    }

    const id = extractVideoIdFromUrl(normalizedUrl);
    const key = id || normalizedUrl;
    if (!itemsByKey.has(key)) {
      itemsByKey.set(key, { id, url: normalizedUrl });
    }
  }

  return [...itemsByKey.values()];
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "scanFavorites") {
    return false;
  }

  try {
    if (!isFavoritesPage()) {
      sendResponse({
        ok: true,
        pageType: "other",
        items: [],
      });
      return false;
    }

    const items = collectFavoriteItems();
    if (!items.length) {
      sendResponse({
        ok: false,
        pageType: "favorites",
        items: [],
        error: "No favorite video links were visible on the page.",
      });
      return false;
    }

    sendResponse({
      ok: true,
      pageType: "favorites",
      items,
    });
  } catch (error) {
    sendResponse({
      ok: false,
      pageType: isFavoritesPage() ? "favorites" : "unknown",
      items: [],
      error: error?.message || String(error),
    });
  }

  return false;
});
