from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.components import queue_store
from src.components.queue_store import QueueItemNotFoundError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(PROJECT_ROOT))).resolve()
PREVIEWS_DIR = DATA_DIR / "videos" / "previews"
PREVIEW_WIDTH = 360
PREVIEW_FORMAT = "jpg"


class PreviewGenerationError(RuntimeError):
    """Raised when a cached preview cannot be created."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_preview(preview: dict | None) -> dict:
    raw = preview if isinstance(preview, dict) else {}
    return {
        "status": raw.get("status") if isinstance(raw.get("status"), str) else "missing",
        "image_path": raw.get("image_path") if isinstance(raw.get("image_path"), str) else None,
        "updated_at": raw.get("updated_at") if isinstance(raw.get("updated_at"), str) else None,
        "width": raw.get("width") if isinstance(raw.get("width"), int) else None,
        "height": raw.get("height") if isinstance(raw.get("height"), int) else None,
        "error": raw.get("error") if isinstance(raw.get("error"), str) else None,
    }


def get_preview_path(item_id: str) -> Path:
    return PREVIEWS_DIR / f"{item_id}.{PREVIEW_FORMAT}"


def _read_dimensions(image_path: Path) -> tuple[int | None, int | None]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None, None

    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(image_path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    if result.returncode != 0:
        return None, None

    try:
        payload = json.loads(result.stdout or "{}")
        stream = (payload.get("streams") or [{}])[0]
    except (json.JSONDecodeError, IndexError):
        return None, None

    width = stream.get("width")
    height = stream.get("height")
    return width if isinstance(width, int) else None, height if isinstance(height, int) else None


def _build_preview_update(
    *,
    status: str,
    image_path: Path | None,
    error: str | None,
    width: int | None = None,
    height: int | None = None,
) -> dict:
    return {
        "preview": {
            "status": status,
            "image_path": str(image_path.resolve()) if image_path else None,
            "updated_at": _now_iso(),
            "width": width,
            "height": height,
            "error": error,
        }
    }


def _save_preview_state(item_id: str, **kwargs) -> dict:
    return queue_store.update_item(item_id, _build_preview_update(**kwargs))


def _run_ffmpeg(video_path: Path, output_path: Path, seek_seconds: float) -> str | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "ffmpeg is not installed"

    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    if temp_path.exists():
        temp_path.unlink()

    command = [
        ffmpeg,
        "-y",
        "-ss",
        str(seek_seconds),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        f"scale={PREVIEW_WIDTH}:-1:flags=lanczos",
        str(temp_path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    if result.returncode != 0 or not temp_path.exists():
        if temp_path.exists():
            temp_path.unlink()
        return result.stderr.strip() or "ffmpeg failed to create preview image"

    temp_path.replace(output_path)
    return None


def _generate_preview(item: dict) -> Path:
    item_id = item.get("id")
    if not item_id:
        raise PreviewGenerationError("Queue item is missing an id")

    video_path = Path(item.get("video_path", ""))
    if not video_path.exists():
        _save_preview_state(
            item_id,
            status="failed",
            image_path=None,
            error="Queued video file is missing",
        )
        raise FileNotFoundError("Queued video file is missing")

    output_path = get_preview_path(item_id)
    first_error = _run_ffmpeg(video_path, output_path, 1.0)
    if first_error and output_path.exists():
        output_path.unlink()

    if first_error:
        second_error = _run_ffmpeg(video_path, output_path, 0.0)
        if second_error:
            _save_preview_state(
                item_id,
                status="failed",
                image_path=None,
                error=second_error or first_error,
            )
            raise PreviewGenerationError(second_error or first_error)

    width, height = _read_dimensions(output_path)
    _save_preview_state(
        item_id,
        status="ready",
        image_path=output_path,
        width=width,
        height=height,
        error=None,
    )
    return output_path


def ensure_queue_item_preview(item: dict) -> dict:
    item_id = item.get("id")
    if not item_id:
        raise PreviewGenerationError("Queue item is missing an id")

    current_item = queue_store.get_item(item_id)
    preview = _normalize_preview(current_item.get("preview"))
    image_path = Path(preview["image_path"]).resolve() if preview.get("image_path") else None

    if preview["status"] == "ready" and image_path and image_path.exists():
        if preview.get("width") is None or preview.get("height") is None:
            width, height = _read_dimensions(image_path)
            return _save_preview_state(
                item_id,
                status="ready",
                image_path=image_path,
                width=width,
                height=height,
                error=None,
            )
        return current_item

    if preview["status"] == "failed" and not (image_path and image_path.exists()):
        raise PreviewGenerationError(preview.get("error") or "Preview generation previously failed")

    if image_path and not image_path.exists():
        preview["status"] = "missing"

    _generate_preview(current_item)
    return queue_store.get_item(item_id)


def build_preview_response(item_id: str) -> tuple[Path, dict]:
    try:
        item = queue_store.get_item(item_id)
    except QueueItemNotFoundError as exc:
        raise QueueItemNotFoundError(item_id) from exc

    current_item = ensure_queue_item_preview(item)
    preview = _normalize_preview(current_item.get("preview"))
    image_path = preview.get("image_path")
    if not image_path:
        raise PreviewGenerationError("Preview image path is missing")

    resolved_path = Path(image_path).resolve()
    if not resolved_path.exists():
        raise PreviewGenerationError("Preview image is missing on disk")

    return resolved_path, current_item
