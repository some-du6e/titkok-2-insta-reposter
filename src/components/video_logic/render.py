from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
FRAME_RATE = 30


class RenderError(RuntimeError):
    """Raised when ffmpeg-based media rendering fails."""


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RenderError(f"{name} is not installed")
    return path


def get_media_duration(media_path: str | Path) -> float:
    ffprobe = _require_binary("ffprobe")
    path = Path(media_path)

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise RenderError(result.stderr.strip() or "ffprobe failed to read media duration")

    try:
        payload = json.loads(result.stdout or "{}")
        raw_duration = payload.get("format", {}).get("duration")
        duration = float(raw_duration)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RenderError("ffprobe returned unreadable media duration") from exc

    if duration <= 0:
        raise RenderError("Media duration must be greater than zero")

    return duration


def render_photo_reel(
    image_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
) -> dict:
    ffmpeg = _require_binary("ffmpeg")
    image = Path(image_path)
    audio = Path(audio_path)
    output = Path(output_path)

    if not image.exists():
        raise RenderError("Photo post image is missing on disk")
    if not audio.exists():
        raise RenderError("Photo post audio is missing on disk")

    duration = get_media_duration(audio)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_name(f"{output.stem}.tmp{output.suffix}")
    if temp_output.exists():
        temp_output.unlink()

    filter_graph = (
        f"[0:v]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},boxblur=20:10[bg];"
        f"[0:v]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
    )

    command = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(FRAME_RATE),
        "-i",
        str(image),
        "-i",
        str(audio),
        "-t",
        f"{duration:.3f}",
        "-filter_complex",
        filter_graph,
        "-map",
        "[v]",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        "-shortest",
        str(temp_output),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    if result.returncode != 0 or not temp_output.exists():
        if temp_output.exists():
            temp_output.unlink()
        raise RenderError(result.stderr.strip() or "ffmpeg failed to render photo reel")

    temp_output.replace(output)
    return {
        "video_path": str(output.resolve()),
        "video_filename": output.name,
        "audio_duration_seconds": duration,
    }
