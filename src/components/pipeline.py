from __future__ import annotations

import random
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
import traceback

from src.components import captions as captions_store
from src.components import queue_store
from src.components.queue_store import QueueItemNotFoundError
from src.components.video_logic.tiktok import (
    TikTokDownloadError,
    prepare_tiktok_media,
    extract_tiktok_username,
    extract_tiktok_video_id,
    normalize_tiktok_url,
)
from src.components.video_logic.uploadvideo import InstagramUploader


class QueuePipelineError(RuntimeError):
    """Raised for queue orchestration failures."""


class QueueValidationError(QueuePipelineError):
    """Raised for user-fixable queue input errors."""


PUBLISH_LOCK = threading.RLock()
COVER_IMAGE_PATH = queue_store.PROJECT_ROOT / "coverrrr.jpg"
CAPTION_TAG_SUFFIX = "🌱✨🇯🇵👉🇭🇷🙈💧🇵🇱🇸🇬🌳🌍☀️🇺🇸 #japao #inovacao #sustentabilidade #tecnologia"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _choose_caption() -> str:
    captions = [caption.strip() for caption in captions_store.load_captions() if caption.strip()]
    if not captions:
        raise QueueValidationError("No saved captions available")
    return random.choice(captions)


def _build_caption(url: str) -> str:
    caption = _choose_caption()
    if not caption.endswith(CAPTION_TAG_SUFFIX):
        caption = f"{caption} {CAPTION_TAG_SUFFIX}"

    username = extract_tiktok_username(url)
    if not username:
        return caption

    suffix = f"(📸/tt/{username})"
    if caption.endswith(suffix):
        return caption

    return f"{caption} {suffix}"


def _mark_item(item_id: str, **updates) -> dict:
    updates["updated_at"] = _now_iso()
    return queue_store.update_item(item_id, updates)


def _resolve_prepend_cover_intro_enabled() -> bool:
    settings = queue_store.get_settings()
    enabled = bool(settings.get("prependCoverIntroEnabled"))
    if not enabled:
        return False

    if COVER_IMAGE_PATH.exists():
        return True

    print(
        "[queue.prepare] Disabling prependCoverIntroEnabled because "
        f"cover image is missing at {COVER_IMAGE_PATH}"
    )
    queue_store.update_settings({"prependCoverIntroEnabled": False})
    return False


def _find_duplicate_item(*, source_id: str | None, normalized_url: str) -> dict | None:
    for item in queue_store.list_items():
        item_source_id = item.get("source_id")
        item_normalized_url = item.get("source_url_normalized")

        if source_id and item_source_id and item_source_id == source_id:
            return item
        if item_normalized_url and item_normalized_url == normalized_url:
            return item
        if not item_normalized_url and item.get("source_url") == normalized_url:
            return item

    return None


def _schedule_next_auto_post(now: datetime | None = None) -> dict:
    settings = queue_store.get_settings()
    if not settings.get("auto_post_enabled"):
        return settings

    next_run = queue_store.build_next_auto_post_at(
        settings.get("auto_post_interval_minutes", queue_store.DEFAULT_AUTO_POST_INTERVAL_MINUTES),
        now=now,
    )
    return queue_store.update_settings({"next_auto_post_at": next_run})


def _record_auto_post_result(*, item_id: str | None, status: str, message: str, attempted_at: str | None = None) -> dict:
    attempt_time = attempted_at or _now_iso()
    return queue_store.update_settings(
        {
            "last_auto_post_attempt_at": attempt_time,
            "last_auto_post_result": {
                "item_id": item_id,
                "status": status,
                "message": message,
                "attempted_at": attempt_time,
            },
        }
    )


def _publish_selected_item(item: dict) -> dict:
    item_id = item.get("id")
    if not item_id:
        raise QueuePipelineError("Queue item is missing an id")

    current_item = queue_store.get_item(item_id)
    status = current_item.get("status")
    if status == "published":
        raise QueueValidationError("Queue item is already published")
    if status == "publishing":
        raise QueueValidationError("Queue item is already publishing")

    video_path = Path(current_item.get("video_path", ""))
    if not video_path.exists():
        return _mark_item(item_id, status="failed", last_error="Queued video file is missing")

    _mark_item(item_id, status="publishing", last_error=None)
    print(
        f"[queue.publish] Starting publish for item={item_id} "
        f"video_path={video_path} media_type={current_item.get('media_type', 'REELS')}"
    )

    try:
        result = InstagramUploader().upload_video(
            video_path=str(video_path),
            caption=current_item.get("caption", ""),
            media_type=current_item.get("media_type", "REELS"),
        )
    except Exception as exc:
        error_message = str(exc).strip() or exc.__class__.__name__
        print(f"[queue.publish] Publish failed for item={item_id}: {error_message}")
        traceback.print_exc()
        return _mark_item(item_id, status="failed", last_error=error_message)

    print(
        f"[queue.publish] Publish completed for item={item_id} "
        f"container_id={result.get('container_id')} media_id={result.get('media_id')}"
    )
    return _mark_item(
        item_id,
        status="published",
        published_at=_now_iso(),
        instagram_media_id=result.get("media_id"),
        container_id=result.get("container_id"),
        last_error=None,
    )


def enqueue_tiktok_url(
    url: str,
    *,
    source_kind: str = "manual",
    discovered_at: str | None = None,
    ingestion_metadata: dict | None = None,
) -> tuple[str, dict]:
    if not isinstance(url, str) or not url.strip():
        raise QueueValidationError("Missing TikTok URL")

    try:
        normalized_url = normalize_tiktok_url(url)
    except TikTokDownloadError as exc:
        raise QueueValidationError(str(exc)) from exc

    source_id = extract_tiktok_video_id(normalized_url)
    duplicate = _find_duplicate_item(source_id=source_id, normalized_url=normalized_url)
    if duplicate is not None:
        return "duplicate", duplicate

    try:
        download_result = prepare_tiktok_media(
            normalized_url,
            prepend_cover_intro=_resolve_prepend_cover_intro_enabled(),
        )
    except TikTokDownloadError as exc:
        message = str(exc)
        if "valid TikTok link" in message:
            raise QueueValidationError(message) from exc
        raise QueuePipelineError(message) from exc

    timestamp = _now_iso()
    item = {
        "id": str(uuid.uuid4()),
        "source_url": normalized_url,
        "source_kind": source_kind,
        "source_id": source_id or download_result.get("download", {}).get("source_id"),
        "source_url_normalized": normalized_url,
        "discovered_at": discovered_at,
        "ingestion_metadata": ingestion_metadata if isinstance(ingestion_metadata, dict) else None,
        "video_path": str(Path(download_result["video_path"]).resolve()),
        "video_filename": download_result["video_filename"],
        "source_media_kind": download_result.get("media_kind", "video"),
        "rendered_from_photo": bool(download_result.get("download", {}).get("rendered_from_photo")),
        "source_assets": {
            "image_path": download_result.get("download", {}).get("image_path"),
            "audio_path": download_result.get("download", {}).get("audio_path"),
            "audio_duration_seconds": download_result.get("download", {}).get("audio_duration_seconds"),
        },
        "caption": _build_caption(normalized_url),
        "media_type": "REELS",
        "status": "queued",
        "created_at": timestamp,
        "updated_at": timestamp,
        "published_at": None,
        "instagram_media_id": None,
        "container_id": None,
        "download": download_result["download"],
        "preview": {
            "status": "missing",
            "image_path": None,
            "updated_at": timestamp,
            "width": None,
            "height": None,
            "error": None,
        },
        "last_error": None,
    }
    return "queued", queue_store.append_item(item)


def get_queue_state() -> dict:
    return queue_store.load_queue()


def list_queue_items() -> list[dict]:
    return get_queue_state()["items"]


def get_queue_settings() -> dict:
    return get_queue_state()["settings"]


def update_queue_settings(updates: dict) -> dict:
    if not isinstance(updates, dict):
        raise QueueValidationError("Settings payload must be a JSON object")

    normalized_updates = {}

    if "auto_post_enabled" in updates:
        value = updates["auto_post_enabled"]
        if not isinstance(value, bool):
            raise QueueValidationError("auto_post_enabled must be a boolean")
        normalized_updates["auto_post_enabled"] = value

    if "auto_post_interval_minutes" in updates:
        value = updates["auto_post_interval_minutes"]
        try:
            interval = int(value)
        except (TypeError, ValueError) as exc:
            raise QueueValidationError("auto_post_interval_minutes must be an integer") from exc
        if interval < 1:
            raise QueueValidationError("auto_post_interval_minutes must be at least 1")
        normalized_updates["auto_post_interval_minutes"] = interval

    if "publicCollectionEnabled" in updates:
        value = updates["publicCollectionEnabled"]
        if not isinstance(value, bool):
            raise QueueValidationError("publicCollectionEnabled must be a boolean")
        normalized_updates["publicCollectionEnabled"] = value

    if "publicCollectionUrl" in updates:
        value = updates["publicCollectionUrl"]
        if value is not None and not isinstance(value, str):
            raise QueueValidationError("publicCollectionUrl must be a string or null")
        normalized_updates["publicCollectionUrl"] = value.strip() if isinstance(value, str) else None

    if "publicCollectionPollSeconds" in updates:
        value = updates["publicCollectionPollSeconds"]
        try:
            interval = int(value)
        except (TypeError, ValueError) as exc:
            raise QueueValidationError("publicCollectionPollSeconds must be an integer") from exc
        if interval < 1:
            raise QueueValidationError("publicCollectionPollSeconds must be at least 1")
        normalized_updates["publicCollectionPollSeconds"] = interval

    if "prependCoverIntroEnabled" in updates:
        value = updates["prependCoverIntroEnabled"]
        if not isinstance(value, bool):
            raise QueueValidationError("prependCoverIntroEnabled must be a boolean")
        normalized_updates["prependCoverIntroEnabled"] = value

    if not normalized_updates:
        raise QueueValidationError("No supported queue settings were provided")

    with PUBLISH_LOCK:
        current = queue_store.get_settings()
        merged = dict(current)
        merged.update(normalized_updates)

        if "auto_post_enabled" in normalized_updates and not merged["auto_post_enabled"]:
            merged["next_auto_post_at"] = None
        elif (
            "auto_post_enabled" in normalized_updates
            or "auto_post_interval_minutes" in normalized_updates
        ) and merged["auto_post_enabled"]:
            merged["next_auto_post_at"] = queue_store.build_next_auto_post_at(
                merged["auto_post_interval_minutes"]
            )

        return queue_store.save_settings(merged)


def publish_queue_item(item_id: str) -> dict:
    with PUBLISH_LOCK:
        try:
            item = queue_store.get_item(item_id)
        except QueueItemNotFoundError as exc:
            raise QueuePipelineError("Queue item not found") from exc

        return _publish_selected_item(item)


def publish_next_queued_item(*, is_auto: bool = False) -> dict:
    attempt_time = _now_iso()

    with PUBLISH_LOCK:
        item = queue_store.get_oldest_queued_item()
        if item is None:
            if is_auto:
                _record_auto_post_result(
                    item_id=None,
                    status="idle",
                    message="No queued items were ready to publish.",
                    attempted_at=attempt_time,
                )
                _schedule_next_auto_post(now=_now())
            return {"attempted": False, "item": None, "message": "No queued items available"}

        result = _publish_selected_item(item)

        if is_auto:
            result_status = result.get("status") or "unknown"
            message = "Published successfully" if result_status == "published" else (
                result.get("last_error") or "Publishing failed"
            )
            _record_auto_post_result(
                item_id=result.get("id"),
                status=result_status,
                message=message,
                attempted_at=attempt_time,
            )
            _schedule_next_auto_post(now=_now())

        return {
            "attempted": True,
            "item": result,
            "message": "Queue item processed",
        }


def retry_queue_item(item_id: str) -> dict:
    with PUBLISH_LOCK:
        try:
            item = queue_store.get_item(item_id)
        except QueueItemNotFoundError as exc:
            raise QueuePipelineError("Queue item not found") from exc

        if item.get("status") != "failed":
            raise QueueValidationError("Only failed queue items can be retried")

        return _publish_selected_item(item)
