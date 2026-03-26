from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUEUE_PATH = PROJECT_ROOT / "queue.json"
DEFAULT_AUTO_POST_ENABLED = False
DEFAULT_AUTO_POST_INTERVAL_MINUTES = 15
DEFAULT_PUBLIC_COLLECTION_ENABLED = False
DEFAULT_PUBLIC_COLLECTION_POLL_SECONDS = 300


class QueueItemNotFoundError(KeyError):
    """Raised when a queue item cannot be found."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_bool(value, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return fallback


def _parse_int(value, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 1 else fallback


def _parse_iso(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_last_result(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None

    result = {}
    for key in ("item_id", "status", "message", "attempted_at"):
        value = raw.get(key)
        if value is None or isinstance(value, str):
            result[key] = value

    return result or None


def _normalize_items(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []

    normalized_items = []
    for item in raw:
        if not isinstance(item, dict):
            continue

        normalized_item = dict(item)
        normalized_item.setdefault("source_kind", None)
        normalized_item.setdefault("source_id", None)
        normalized_item.setdefault("source_url_normalized", None)
        normalized_item.setdefault("discovered_at", None)
        normalized_item.setdefault("ingestion_metadata", None)
        normalized_item.setdefault("source_media_kind", "video")
        normalized_item.setdefault("rendered_from_photo", False)
        normalized_item.setdefault(
            "source_assets",
            {
                "image_path": None,
                "audio_path": None,
                "audio_duration_seconds": None,
            },
        )
        normalized_items.append(normalized_item)

    return normalized_items


def get_env_default_settings() -> dict:
    return {
        "auto_post_enabled": _parse_bool(
            os.getenv("AUTO_POST_ENABLED"),
            DEFAULT_AUTO_POST_ENABLED,
        ),
        "auto_post_interval_minutes": _parse_int(
            os.getenv("AUTO_POST_INTERVAL_MINUTES"),
            DEFAULT_AUTO_POST_INTERVAL_MINUTES,
        ),
    }


def build_next_auto_post_at(interval_minutes: int, now: datetime | None = None) -> str:
    base = now or _now()
    return (base + timedelta(minutes=interval_minutes)).isoformat()


def normalize_settings(raw, *, persist_existing_schedule: bool = True) -> dict:
    env_defaults = get_env_default_settings()
    auto_post_enabled = env_defaults["auto_post_enabled"]
    interval_minutes = env_defaults["auto_post_interval_minutes"]
    next_auto_post_at = None
    last_auto_post_attempt_at = None
    last_auto_post_result = None
    public_collection_enabled = DEFAULT_PUBLIC_COLLECTION_ENABLED
    public_collection_url = None
    public_collection_poll_seconds = DEFAULT_PUBLIC_COLLECTION_POLL_SECONDS
    public_collection_last_cursor = None
    public_collection_seen_ids = []
    public_collection_last_status = "idle"
    public_collection_last_error = ""
    public_collection_last_items_found = 0
    public_collection_last_items_queued = 0
    public_collection_last_extract_strategy = "none"
    public_collection_last_checked_at = None

    if isinstance(raw, dict):
        auto_post_enabled = _parse_bool(raw.get("auto_post_enabled"), auto_post_enabled)
        interval_minutes = _parse_int(raw.get("auto_post_interval_minutes"), interval_minutes)
        next_auto_post_at = raw.get("next_auto_post_at")
        last_auto_post_attempt_at = raw.get("last_auto_post_attempt_at")
        last_auto_post_result = _normalize_last_result(raw.get("last_auto_post_result"))
        public_collection_enabled = _parse_bool(
            raw.get("publicCollectionEnabled"),
            public_collection_enabled,
        )
        public_collection_url = raw.get("publicCollectionUrl")
        public_collection_poll_seconds = _parse_int(
            raw.get("publicCollectionPollSeconds"),
            public_collection_poll_seconds,
        )
        public_collection_last_cursor = raw.get("publicCollectionLastCursor")
        public_collection_seen_ids = raw.get("publicCollectionSeenIds", [])
        public_collection_last_status = raw.get("publicCollectionLastStatus", public_collection_last_status)
        public_collection_last_error = raw.get("publicCollectionLastError", public_collection_last_error)
        public_collection_last_items_found = raw.get("publicCollectionLastItemsFound", public_collection_last_items_found)
        public_collection_last_items_queued = raw.get("publicCollectionLastItemsQueued", public_collection_last_items_queued)
        public_collection_last_extract_strategy = raw.get(
            "publicCollectionLastExtractStrategy",
            public_collection_last_extract_strategy,
        )
        public_collection_last_checked_at = raw.get("publicCollectionLastCheckedAt")

    parsed_next = _parse_iso(next_auto_post_at)
    parsed_last_attempt = _parse_iso(last_auto_post_attempt_at)
    parsed_public_checked_at = _parse_iso(public_collection_last_checked_at)

    if auto_post_enabled:
        if parsed_next is None:
            parsed_next = _now() if not persist_existing_schedule else _now() + timedelta(minutes=interval_minutes)
    else:
        parsed_next = None

    if not isinstance(public_collection_url, str) or not public_collection_url.strip():
        public_collection_url = None
    else:
        public_collection_url = public_collection_url.strip()

    if not isinstance(public_collection_last_cursor, str) or not public_collection_last_cursor.strip():
        public_collection_last_cursor = None

    if not isinstance(public_collection_seen_ids, list):
        public_collection_seen_ids = []
    else:
        public_collection_seen_ids = [
            value for value in public_collection_seen_ids if isinstance(value, str) and value.strip()
        ][-1000:]

    if not isinstance(public_collection_last_status, str) or not public_collection_last_status.strip():
        public_collection_last_status = "idle"

    if not isinstance(public_collection_last_error, str):
        public_collection_last_error = ""

    public_collection_last_items_found = _parse_int(
        public_collection_last_items_found,
        0,
    ) if public_collection_last_items_found is not None else 0
    public_collection_last_items_queued = _parse_int(
        public_collection_last_items_queued,
        0,
    ) if public_collection_last_items_queued is not None else 0

    if not isinstance(public_collection_last_extract_strategy, str) or not public_collection_last_extract_strategy.strip():
        public_collection_last_extract_strategy = "none"

    return {
        "auto_post_enabled": auto_post_enabled,
        "auto_post_interval_minutes": interval_minutes,
        "next_auto_post_at": parsed_next.isoformat() if parsed_next else None,
        "last_auto_post_attempt_at": parsed_last_attempt.isoformat() if parsed_last_attempt else None,
        "last_auto_post_result": last_auto_post_result,
        "publicCollectionEnabled": public_collection_enabled,
        "publicCollectionUrl": public_collection_url,
        "publicCollectionPollSeconds": public_collection_poll_seconds,
        "publicCollectionLastCursor": public_collection_last_cursor,
        "publicCollectionSeenIds": public_collection_seen_ids,
        "publicCollectionLastStatus": public_collection_last_status,
        "publicCollectionLastError": public_collection_last_error,
        "publicCollectionLastItemsFound": public_collection_last_items_found,
        "publicCollectionLastItemsQueued": public_collection_last_items_queued,
        "publicCollectionLastExtractStrategy": public_collection_last_extract_strategy,
        "publicCollectionLastCheckedAt": parsed_public_checked_at.isoformat() if parsed_public_checked_at else None,
    }


def load_queue() -> dict:
    if not QUEUE_PATH.exists():
        return {"items": [], "settings": normalize_settings(None, persist_existing_schedule=False)}

    raw_content = QUEUE_PATH.read_text(encoding="utf-8").strip()
    if not raw_content:
        return {"items": [], "settings": normalize_settings(None, persist_existing_schedule=False)}

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        return {"items": [], "settings": normalize_settings(None, persist_existing_schedule=False)}

    if not isinstance(parsed, dict):
        return {"items": [], "settings": normalize_settings(None, persist_existing_schedule=False)}

    raw_settings = parsed.get("settings")
    return {
        "items": _normalize_items(parsed.get("items", [])),
        "settings": normalize_settings(
            raw_settings,
            persist_existing_schedule=isinstance(raw_settings, dict),
        ),
    }


def save_queue(queue: dict) -> dict:
    payload = {
        "items": _normalize_items(queue.get("items", [])),
        "settings": normalize_settings(queue.get("settings")),
    }
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = QUEUE_PATH.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(QUEUE_PATH)
    return payload


def list_items() -> list[dict]:
    return load_queue()["items"]


def get_settings() -> dict:
    return load_queue()["settings"]


def save_settings(settings: dict) -> dict:
    queue = load_queue()
    queue["settings"] = normalize_settings(settings)
    save_queue(queue)
    return queue["settings"]


def update_settings(updates: dict) -> dict:
    queue = load_queue()
    merged = dict(queue.get("settings", {}))
    merged.update(updates)
    queue["settings"] = normalize_settings(merged)
    save_queue(queue)
    return queue["settings"]


def append_item(item: dict) -> dict:
    queue = load_queue()
    queue["items"].append(item)
    save_queue(queue)
    return item


def get_item(item_id: str) -> dict:
    for item in list_items():
        if item.get("id") == item_id:
            return item

    raise QueueItemNotFoundError(item_id)


def get_oldest_queued_item() -> dict | None:
    queued_items = [item for item in list_items() if item.get("status") == "queued"]
    if not queued_items:
        return None

    return min(queued_items, key=lambda item: item.get("created_at") or "")


def update_item(item_id: str, updates: dict) -> dict:
    queue = load_queue()

    for index, item in enumerate(queue["items"]):
        if item.get("id") != item_id:
            continue

        updated = dict(item)
        updated.update(updates)
        queue["items"][index] = updated
        save_queue(queue)
        return updated

    raise QueueItemNotFoundError(item_id)
