from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.components import captions as captions_store
from src.components import queue_store
from src.components.queue_store import QueueItemNotFoundError
from src.components.video_logic.tiktok import TikTokDownloadError, download_tiktok_video
from src.components.video_logic.uploadvideo import InstagramUploader


class QueuePipelineError(RuntimeError):
    """Raised for queue orchestration failures."""


class QueueValidationError(QueuePipelineError):
    """Raised for user-fixable queue input errors."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _choose_caption() -> str:
    captions = [caption.strip() for caption in captions_store.load_captions() if caption.strip()]
    if not captions:
        raise QueueValidationError("No saved captions available")
    return random.choice(captions)


def enqueue_tiktok_url(url: str) -> dict:
    if not isinstance(url, str) or not url.strip():
        raise QueueValidationError("Missing TikTok URL")

    try:
        download_result = download_tiktok_video(url)
    except TikTokDownloadError as exc:
        message = str(exc)
        if "valid TikTok link" in message:
            raise QueueValidationError(message) from exc
        raise QueuePipelineError(message) from exc

    timestamp = _now_iso()
    item = {
        "id": str(uuid.uuid4()),
        "source_url": url,
        "video_path": str(Path(download_result["video_path"]).resolve()),
        "video_filename": download_result["video_filename"],
        "caption": _choose_caption(),
        "media_type": "REELS",
        "status": "queued",
        "created_at": timestamp,
        "updated_at": timestamp,
        "published_at": None,
        "instagram_media_id": None,
        "container_id": None,
        "download": download_result["download"],
        "last_error": None,
    }
    return queue_store.append_item(item)


def list_queue_items() -> list[dict]:
    return queue_store.list_items()


def _mark_item(item_id: str, **updates) -> dict:
    updates["updated_at"] = _now_iso()
    return queue_store.update_item(item_id, updates)


def publish_queue_item(item_id: str) -> dict:
    try:
        item = queue_store.get_item(item_id)
    except QueueItemNotFoundError as exc:
        raise QueuePipelineError("Queue item not found") from exc

    if item.get("status") == "published":
        raise QueueValidationError("Queue item is already published")

    video_path = Path(item.get("video_path", ""))
    if not video_path.exists():
        raise QueueValidationError("Queued video file is missing")

    _mark_item(item_id, status="publishing", last_error=None)

    try:
        result = InstagramUploader().upload_video(
            video_path=str(video_path),
            caption=item.get("caption", ""),
            media_type=item.get("media_type", "REELS"),
        )
    except Exception as exc:
        return _mark_item(item_id, status="failed", last_error=str(exc))

    return _mark_item(
        item_id,
        status="published",
        published_at=_now_iso(),
        instagram_media_id=result.get("media_id"),
        container_id=result.get("container_id"),
        last_error=None,
    )


def retry_queue_item(item_id: str) -> dict:
    try:
        item = queue_store.get_item(item_id)
    except QueueItemNotFoundError as exc:
        raise QueuePipelineError("Queue item not found") from exc

    if item.get("status") != "failed":
        raise QueueValidationError("Only failed queue items can be retried")

    return publish_queue_item(item_id)
