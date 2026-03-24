from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[3]
VIDEOS_DIR = PROJECT_ROOT / "videos"
LOCAL_YT_DLP = PROJECT_ROOT / "yt-dlp.exe"


class TikTokDownloadError(RuntimeError):
    """Raised when downloading a TikTok URL fails."""


def is_tiktok_url(url: str) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        return False

    hostname = (parsed.hostname or "").lower()
    return hostname == "tiktok.com" or hostname.endswith(".tiktok.com")


def get_yt_dlp_command() -> list[str]:
    if LOCAL_YT_DLP.exists():
        return [str(LOCAL_YT_DLP)]
    return ["yt-dlp"]


def download_tiktok_video(url: str) -> dict:
    if not is_tiktok_url(url):
        raise TikTokDownloadError("URL must be a valid TikTok link")

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    output_template = str(VIDEOS_DIR / "%(uploader_id|creator|unknown)s__%(id)s.%(ext)s")

    metadata_command = [
        *get_yt_dlp_command(),
        "--print-json",
        "--no-warnings",
        "--skip-download",
        url,
    ]
    metadata_result = subprocess.run(
        metadata_command,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    if metadata_result.returncode != 0:
        raise TikTokDownloadError(
            metadata_result.stderr.strip() or "Failed to fetch TikTok metadata"
        )

    try:
        metadata = json.loads(metadata_result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise TikTokDownloadError("yt-dlp returned unreadable metadata") from exc

    download_command = [
        *get_yt_dlp_command(),
        "--no-warnings",
        "--no-progress",
        "--restrict-filenames",
        "--merge-output-format",
        "mp4",
        "--output",
        output_template,
        url,
    ]
    download_result = subprocess.run(
        download_command,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    if download_result.returncode != 0:
        raise TikTokDownloadError(
            download_result.stderr.strip() or "Failed to download TikTok video"
        )

    requested_downloads = metadata.get("requested_downloads") or []
    relative_path = None
    filepath = metadata.get("_filename")
    if isinstance(filepath, str) and filepath:
        relative_path = Path(filepath)
    elif requested_downloads:
        path_value = requested_downloads[0].get("filepath")
        if isinstance(path_value, str) and path_value:
            relative_path = Path(path_value)

    if relative_path is None:
        matching_files = sorted(VIDEOS_DIR.glob(f"*__{metadata.get('id', '')}.*"))
        if not matching_files:
            raise TikTokDownloadError("Downloaded file could not be located")
        relative_path = matching_files[-1]

    video_path = None
    if relative_path is not None:
        candidate_path = Path(relative_path)
        if not candidate_path.is_absolute():
            candidate_path = (PROJECT_ROOT / candidate_path).resolve()
        if candidate_path.exists():
            video_path = candidate_path

    if video_path is None:
        matching_files = sorted(VIDEOS_DIR.glob(f"*__{metadata.get('id', '')}.*"))
        if not matching_files:
            raise TikTokDownloadError("Downloaded file is missing on disk")
        video_path = matching_files[-1].resolve()

    return {
        "video_path": str(video_path),
        "video_filename": video_path.name,
        "download": {
            "extractor": "yt-dlp",
            "source_id": metadata.get("id"),
            "title": metadata.get("title"),
        },
    }
