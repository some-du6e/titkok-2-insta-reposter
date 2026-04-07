from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
FRAME_RATE = 30
COVER_IMAGE_PATH = PROJECT_ROOT / "coverrrr.png"
INTRO_DURATION_SECONDS = 0.1
PHOTO_FRAME_DURATION_SECONDS = 5.0


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


def _build_cover_image_filter(input_label: str, output_label: str) -> str:
    return (
        f"[{input_label}]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},boxblur=20:10[coverbg];"
        f"[{input_label}]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease[coverfg];"
        f"[coverbg][coverfg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[{output_label}]"
    )


def _build_reel_video_filter(input_label: str, output_label: str) -> str:
    return (
        f"[{input_label}]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,format=yuv420p[{output_label}]"
    )


def render_photo_reel(
    image_path: str | Path | list[str | Path],
    audio_path: str | Path,
    output_path: str | Path,
) -> dict:
    ffmpeg = _require_binary("ffmpeg")
    if isinstance(image_path, (list, tuple)):
        images = [Path(item) for item in image_path]
    else:
        images = [Path(image_path)]
    audio = Path(audio_path)
    output = Path(output_path)

    if not images:
        raise RenderError("Photo post image is missing on disk")
    for image in images:
        if not image.exists():
            raise RenderError("Photo post image is missing on disk")
    if not audio.exists():
        raise RenderError("Photo post audio is missing on disk")

    duration = get_media_duration(audio)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_name(f"{output.stem}.tmp{output.suffix}")
    concat_manifest = output.with_name(f"{output.stem}.images.ffconcat")
    if temp_output.exists():
        temp_output.unlink()
    if concat_manifest.exists():
        concat_manifest.unlink()

    sequence_duration = len(images) * PHOTO_FRAME_DURATION_SECONDS
    repeat_count = max(1, math.ceil(duration / sequence_duration))
    rendered_images = images * repeat_count

    def _escape_manifest_path(path: Path) -> str:
        return str(path.resolve()).replace("\\", "\\\\").replace("'", "\\'")

    manifest_lines = ["ffconcat version 1.0"]
    for image in rendered_images:
        manifest_lines.append(f"file '{_escape_manifest_path(image)}'")
        manifest_lines.append(f"duration {PHOTO_FRAME_DURATION_SECONDS:.3f}")
    manifest_lines.append(f"file '{_escape_manifest_path(rendered_images[-1])}'")
    concat_manifest.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    filter_graph = _build_cover_image_filter("0:v", "v")

    command = [
        ffmpeg,
        "-y",
        "-safe",
        "0",
        "-f",
        "concat",
        "-i",
        str(concat_manifest),
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
        "-r",
        str(FRAME_RATE),
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
    if concat_manifest.exists():
        concat_manifest.unlink()
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


def prepend_cover_intro_frame(
    video_path: str | Path,
    cover_image_path: str | Path,
    output_path: str | Path,
    *,
    intro_duration_seconds: float = INTRO_DURATION_SECONDS,
    frame_rate: int = FRAME_RATE,
    delay_audio: bool = True,
) -> Path:
    ffmpeg = _require_binary("ffmpeg")
    video = Path(video_path)
    cover = Path(cover_image_path)
    output = Path(output_path)

    if not video.exists():
        raise RenderError("Video is missing on disk")
    if not cover.exists():
        raise RenderError("Cover intro image is missing on disk")
    if intro_duration_seconds <= 0:
        raise RenderError("Intro duration must be greater than zero")
    if frame_rate <= 0:
        raise RenderError("Frame rate must be greater than zero")

    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_name(f"{output.stem}.tmp{output.suffix}")
    if temp_output.exists():
        temp_output.unlink()

    filter_parts = [
        _build_cover_image_filter("0:v", "coverv"),
        _build_reel_video_filter("1:v", "mainv"),
        "[coverv][mainv]concat=n=2:v=1:a=0[v]",
    ]
    command = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(frame_rate),
        "-t",
        f"{intro_duration_seconds:.3f}",
        "-i",
        str(cover),
        "-i",
        str(video),
    ]

    if delay_audio:
        filter_parts.append("[2:a][1:a:0]concat=n=2:v=0:a=1[a]")
        command.extend(
            [
                "-f",
                "lavfi",
                "-t",
                f"{intro_duration_seconds:.3f}",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
    else:
        filter_parts.append("[1:a:0]anull[a]")

    command.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(frame_rate),
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
            str(temp_output),
        ]
    )
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
        raise RenderError(result.stderr.strip() or "ffmpeg failed to prepend cover intro frame")

    temp_output.replace(output)
    return output.resolve()
