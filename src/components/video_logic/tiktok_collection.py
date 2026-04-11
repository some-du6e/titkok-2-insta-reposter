from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from html import unescape
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from src.components.video_logic.tiktok import get_yt_dlp_command, is_tiktok_url


COLLECTION_SCRIPT_ID = "__UNIVERSAL_DATA_FOR_REHYDRATION__"
VIDEO_URL_PATTERN = re.compile(
    r"https://www\.tiktok\.com/@[\w.\-]+/video/\d+",
    re.IGNORECASE,
)
COLLECTION_URL_PATTERN = re.compile(
    r"^https://www\.tiktok\.com/@[\w.\-]+/collection/[^?#]+$",
    re.IGNORECASE,
)
SCRIPT_PATTERN = re.compile(
    r'<script[^>]+id="%s"[^>]*>(.*?)</script>' % COLLECTION_SCRIPT_ID,
    re.IGNORECASE | re.DOTALL,
)
HREF_VIDEO_PATTERN = re.compile(
    r'href=(?:"|\')(?P<value>/@[\w.\-]+/video/\d+[^"\']*)(?:"|\')',
    re.IGNORECASE,
)


class PublicCollectionError(RuntimeError):
    """Raised when a public collection cannot be fetched or parsed."""


@dataclass(slots=True)
class CollectionItem:
    id: str | None
    url: str


@dataclass(slots=True)
class CollectionFetchResult:
    items: list[CollectionItem]
    strategy: str
    error: str | None = None
    metadata: dict | None = None


def normalize_collection_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise PublicCollectionError("Collection URL is required")

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise PublicCollectionError("Collection URL must use http or https")

    hostname = (parsed.netloc or "").lower()
    path = parsed.path.rstrip("/")
    normalized = urlunparse(
        (
            (parsed.scheme or "https").lower(),
            hostname,
            path,
            "",
            urlencode(
                [
                    (key, value)
                    for key, value in parse_qsl(parsed.query, keep_blank_values=False)
                    if not key.startswith("utm_")
                ],
                doseq=True,
            ),
            "",
        )
    )

    if not is_public_collection_url(normalized):
        raise PublicCollectionError("URL must be a valid public TikTok collection link")

    return normalized


def is_public_collection_url(url: str) -> bool:
    if not is_tiktok_url(url):
        return False
    return bool(COLLECTION_URL_PATTERN.match(url.strip()))


def normalize_video_url(url: str) -> str | None:
    if not isinstance(url, str):
        return None

    candidate = unescape(url).strip()
    if candidate.startswith("/"):
        candidate = f"https://www.tiktok.com{candidate}"

    if not is_tiktok_url(candidate):
        return None

    parsed = urlparse(candidate)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or not parts[0].startswith("@") or parts[1] != "video" or not parts[2].isdigit():
        return None

    return urlunparse(
        (
            "https",
            "www.tiktok.com",
            f"/{parts[0]}/video/{parts[2]}",
            "",
            "",
            "",
        )
    )


def extract_video_id(url: str) -> str | None:
    normalized = normalize_video_url(url)
    if not normalized:
        return None

    parts = [part for part in urlparse(normalized).path.split("/") if part]
    return parts[2] if len(parts) >= 3 else None


def _dedupe_items(items: list[CollectionItem]) -> list[CollectionItem]:
    seen: set[str] = set()
    deduped: list[CollectionItem] = []

    for item in items:
        key = item.id or item.url
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped


def _items_from_urls(urls: list[str]) -> list[CollectionItem]:
    items = []
    for url in urls:
        normalized = normalize_video_url(url)
        if not normalized:
            continue
        items.append(CollectionItem(id=extract_video_id(normalized), url=normalized))
    return _dedupe_items(items)


def extract_html_items(html: str) -> list[CollectionItem]:
    urls = []
    for match in HREF_VIDEO_PATTERN.finditer(html or ""):
        urls.append(match.group("value"))
    for match in VIDEO_URL_PATTERN.finditer(html or ""):
        urls.append(match.group(0))
    return _items_from_urls(urls)


def _extract_rehydration_payload(html: str) -> dict | None:
    match = SCRIPT_PATTERN.search(html or "")
    if not match:
        return None
    try:
        return json.loads(unescape(match.group(1)))
    except json.JSONDecodeError:
        return None


def _walk_json_for_items(obj, urls: list[str], author_hints: list[tuple[str, str]]) -> None:
    if isinstance(obj, dict):
        author_value = obj.get("author") or obj.get("authorName") or obj.get("uniqueId") or obj.get("author_id")
        video_id_value = obj.get("id") or obj.get("videoId") or obj.get("aweme_id") or obj.get("itemId")
        if isinstance(author_value, str) and isinstance(video_id_value, (str, int)):
            author = author_value if author_value.startswith("@") else f"@{author_value}"
            author_hints.append((author, str(video_id_value)))

        for key, value in obj.items():
            if isinstance(value, str):
                urls.extend(VIDEO_URL_PATTERN.findall(value))
            _walk_json_for_items(value, urls, author_hints)
        return

    if isinstance(obj, list):
        for value in obj:
            _walk_json_for_items(value, urls, author_hints)
        return

    if isinstance(obj, str):
        urls.extend(VIDEO_URL_PATTERN.findall(obj))


def extract_embedded_json_items(payload: dict | None) -> list[CollectionItem]:
    if not isinstance(payload, dict):
        return []

    urls: list[str] = []
    author_hints: list[tuple[str, str]] = []
    _walk_json_for_items(payload, urls, author_hints)

    for author, video_id in author_hints:
        urls.append(f"https://www.tiktok.com/{author}/video/{video_id}")

    return _items_from_urls(urls)


def _yt_dlp_collection_items(
    url: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> CollectionFetchResult:
    command = [
        *get_yt_dlp_command(),
        "--flat-playlist",
        "--dump-single-json",
        url,
    ]
    result = runner(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PublicCollectionError(result.stderr.strip() or "yt-dlp failed to enumerate the collection")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PublicCollectionError("yt-dlp returned unreadable collection metadata") from exc

    entries = payload.get("entries") or []
    urls = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_url = entry.get("url")
        if isinstance(entry_url, str):
            urls.append(entry_url)

    items = _items_from_urls(urls)
    metadata = {
        "playlist_id": payload.get("id"),
        "playlist_title": payload.get("title"),
        "playlist_count": payload.get("playlist_count"),
        "extractor": payload.get("extractor"),
    }
    return CollectionFetchResult(items=items, strategy="undocumented_api", metadata=metadata)


def fetch_public_collection(
    url: str,
    *,
    session: requests.Session | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    timeout: int = 20,
) -> CollectionFetchResult:
    normalized_url = normalize_collection_url(url)
    _owned_session = session is None
    client = session if session is not None else requests.Session()
    try:
        try:
            response = client.get(
                normalized_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            return CollectionFetchResult(
                items=[],
                strategy="none",
                error=str(exc),
                metadata={"source_url": normalized_url},
            )
        html = response.text

        html_items = extract_html_items(html)
        if html_items:
            return CollectionFetchResult(
                items=html_items,
                strategy="html_embedded",
                metadata={"source_url": normalized_url},
            )

        payload = _extract_rehydration_payload(html)
        json_items = extract_embedded_json_items(payload)
        if json_items:
            return CollectionFetchResult(
                items=json_items,
                strategy="embedded_json",
                metadata={"source_url": normalized_url},
            )

        try:
            fallback_result = _yt_dlp_collection_items(normalized_url, runner=runner)
            fallback_metadata = dict(fallback_result.metadata or {})
            fallback_metadata["source_url"] = normalized_url
            fallback_result.metadata = fallback_metadata
            return fallback_result
        except PublicCollectionError as exc:
            return CollectionFetchResult(
                items=[],
                strategy="none",
                error=str(exc),
                metadata={"source_url": normalized_url},
            )
    finally:
        if _owned_session:
            client.close()
