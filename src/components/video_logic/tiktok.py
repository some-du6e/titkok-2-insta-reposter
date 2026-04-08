from __future__ import annotations

import json
import mimetypes
import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from src.components.video_logic.render import (
    COVER_IMAGE_PATH,
    RenderError,
    prepend_cover_intro_frame,
    render_photo_reel,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
VIDEOS_DIR = PROJECT_ROOT / "videos"
LOCAL_YT_DLP = PROJECT_ROOT / "yt-dlp.exe"
REQUEST_TIMEOUT_SECONDS = 60
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}
FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


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


def extract_tiktok_username(url: str) -> str | None:
    if not is_tiktok_url(url):
        return None

    path_parts = [part for part in urlparse(url.strip()).path.split("/") if part]
    if not path_parts:
        return None

    candidate = path_parts[0]
    if not candidate.startswith("@") or len(candidate) == 1:
        return None

    return candidate[1:]


def extract_tiktok_video_id(url: str) -> str | None:
    if not is_tiktok_url(url):
        return None

    path_parts = [part for part in urlparse(url.strip()).path.split("/") if part]
    if "video" not in path_parts:
        return None

    video_index = path_parts.index("video")
    if video_index + 1 >= len(path_parts):
        return None

    candidate = path_parts[video_index + 1].strip()
    if not candidate.isdigit():
        return None

    return candidate


def normalize_tiktok_url(url: str) -> str:
    if not is_tiktok_url(url):
        raise TikTokDownloadError("URL must be a valid TikTok link")

    parsed = urlparse(url.strip())
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if not key.startswith("utm_")
    ]
    normalized_query = urlencode(query_pairs, doseq=True)
    normalized_path = parsed.path.rstrip("/") or "/"

    return urlunparse(
        (
            parsed.scheme.lower() or "https",
            (parsed.netloc or "").lower(),
            normalized_path,
            "",
            normalized_query,
            "",
        )
    )


def fetch_tiktok_metadata(url: str) -> dict:
    if not is_tiktok_url(url):
        raise TikTokDownloadError("URL must be a valid TikTok link")

    command = [
        *get_yt_dlp_command(),
        "--print-json",
        "--no-warnings",
        "--skip-download",
        url,
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise TikTokDownloadError(result.stderr.strip() or "Failed to fetch TikTok metadata")

    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise TikTokDownloadError("yt-dlp returned unreadable metadata") from exc


def _sanitize_filename_part(value: str | None, fallback: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback
    normalized = FILENAME_SAFE_RE.sub("_", value.strip())
    normalized = normalized.strip("._-")
    return normalized or fallback


def _build_base_stem(metadata: dict) -> str:
    creator = (
        metadata.get("uploader_id")
        or metadata.get("creator")
        or metadata.get("channel_id")
        or metadata.get("uploader")
    )
    source_id = metadata.get("id")
    return (
        f"{_sanitize_filename_part(str(creator) if creator is not None else None, 'unknown')}"
        f"__{_sanitize_filename_part(str(source_id) if source_id is not None else None, 'unknown')}"
    )


def _looks_like_music_cdn(url: str | None) -> bool:
    if not isinstance(url, str):
        return False
    hostname = (urlparse(url).hostname or "").lower()
    return "music" in hostname and "tiktokcdn.com" in hostname


def _is_real_video_format(fmt: dict) -> bool:
    if not isinstance(fmt, dict):
        return False
    vcodec = fmt.get("vcodec")
    if not isinstance(vcodec, str) or vcodec == "none":
        return False
    width = fmt.get("width")
    height = fmt.get("height")
    if isinstance(width, int) and width > 0 and isinstance(height, int) and height > 0:
        return True
    return False


def _is_audio_like_format(fmt: dict) -> bool:
    if not isinstance(fmt, dict):
        return False
    acodec = fmt.get("acodec")
    if not isinstance(acodec, str) or acodec == "none":
        return False
    if fmt.get("vcodec") == "none":
        return True
    width = fmt.get("width")
    height = fmt.get("height")
    url = fmt.get("url")
    return (
        ((width in (0, None)) and (height in (0, None)))
        or _looks_like_music_cdn(url)
    )


def _extract_image_candidates(metadata: dict) -> list[str]:
    candidates: list[str] = []

    def _extend_from_container(value: object) -> None:
        if isinstance(value, str) and value:
            candidates.append(value)
            return
        if isinstance(value, list):
            for item in value:
                _extend_from_container(item)
            return
        if not isinstance(value, dict):
            return

        for key in ("url", "image_url", "display_image_url", "video_url"):
            _extend_from_container(value.get(key))
        _extend_from_container(value.get("url_list"))
        _extend_from_container(value.get("urlList"))
        _extend_from_container(value.get("play_addr"))
        _extend_from_container(value.get("playAddr"))
        _extend_from_container(value.get("images"))

    for key in ("images", "image_post", "image_post_info"):
        raw = metadata.get(key)
        if isinstance(raw, list):
            for item in raw:
                _extend_from_container(item)
        elif isinstance(raw, dict):
            _extend_from_container(raw)

    thumbnails = metadata.get("thumbnails")
    if isinstance(thumbnails, list) and not candidates:
        sorted_thumbnails = sorted(
            (
                item for item in thumbnails
                if isinstance(item, dict) and isinstance(item.get("url"), str) and item.get("url")
            ),
            key=lambda item: (item.get("width") or 0) * (item.get("height") or 0),
            reverse=True,
        )
        candidates.extend(item["url"] for item in sorted_thumbnails)

    deduped: list[str] = []
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def _select_audio_format(metadata: dict) -> dict | None:
    formats = metadata.get("formats")
    if not isinstance(formats, list):
        return None

    candidates = [fmt for fmt in formats if _is_audio_like_format(fmt)]
    if not candidates:
        return None

    def _score(fmt: dict) -> tuple[float, float]:
        abr = fmt.get("abr")
        filesize = fmt.get("filesize") or fmt.get("filesize_approx") or 0
        return (
            float(abr) if isinstance(abr, (int, float)) else 0.0,
            float(filesize) if isinstance(filesize, (int, float)) else 0.0,
        )

    return max(candidates, key=_score)


def _detect_media_kind(metadata: dict) -> str:
    if any(_is_real_video_format(fmt) for fmt in metadata.get("formats") or []):
        return "video"

    if _extract_image_candidates(metadata):
        return "photo_post"

    if _select_audio_format(metadata) is not None:
        return "photo_post"

    return "video"


def _download_command(url: str, output_template: str) -> list[str]:
    return [
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


def _resolve_downloaded_video_path(metadata: dict) -> Path:
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

    candidate_path = Path(relative_path)
    if not candidate_path.is_absolute():
        candidate_path = (PROJECT_ROOT / candidate_path).resolve()
    if candidate_path.exists():
        return candidate_path

    matching_files = sorted(VIDEOS_DIR.glob(f"*__{metadata.get('id', '')}.*"))
    if not matching_files:
        raise TikTokDownloadError("Downloaded file is missing on disk")
    return matching_files[-1].resolve()


def _guess_extension(url: str, content_type: str | None, fallback: str) -> str:
    parsed = Path(urlparse(url).path)
    suffix = parsed.suffix.lower()
    if suffix:
        return suffix
    if isinstance(content_type, str) and content_type:
        stripped = content_type.strip().lower()
        if stripped.startswith("."):
            return stripped
        if "/" not in stripped and stripped.replace("-", "").replace("_", "").isalnum():
            return f".{stripped}"
    if isinstance(content_type, str) and content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return guessed
    return fallback


def _download_binary(url: str, destination: Path) -> Path:
    try:
        with requests.get(
            url,
            stream=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers=REQUEST_HEADERS,
        ) as response:
            response.raise_for_status()
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp_path = destination.with_name(f"{destination.stem}.tmp{destination.suffix}")
            if temp_path.exists():
                temp_path.unlink()
            with temp_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        handle.write(chunk)
            temp_path.replace(destination)
            return destination
    except requests.RequestException as exc:
        raise TikTokDownloadError(f"Failed to download media asset: {exc}") from exc


def _prepare_video_media(url: str, metadata: dict, *, prepend_cover_intro: bool = False) -> dict:
    output_template = str(VIDEOS_DIR / "%(uploader_id|creator|unknown)s__%(id)s.%(ext)s")
    result = subprocess.run(
        _download_command(url, output_template),
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise TikTokDownloadError(result.stderr.strip() or "Failed to download TikTok video")

    video_path = _resolve_downloaded_video_path(metadata)
    cover_intro_applied = False
    cover_intro_source_path = None
    if prepend_cover_intro:
        try:
            video_path = prepend_cover_intro_frame(video_path, COVER_IMAGE_PATH, video_path)
        except RenderError as exc:
            raise TikTokDownloadError(str(exc)) from exc
        cover_intro_applied = True
        cover_intro_source_path = str(COVER_IMAGE_PATH.resolve())

    return {
        "media_kind": "video",
        "video_path": str(video_path),
        "video_filename": video_path.name,
        "download": {
            "extractor": "yt-dlp",
            "source_id": metadata.get("id"),
            "title": metadata.get("title"),
            "source_media_kind": "video",
            "audio_path": None,
            "image_path": None,
            "audio_duration_seconds": None,
            "rendered_from_photo": False,
            "cover_intro_applied": cover_intro_applied,
            "cover_intro_source_path": cover_intro_source_path,
        },
    }


def _prepare_photo_media(metadata: dict, *, prepend_cover_intro: bool = False) -> dict:
    image_candidates = _extract_image_candidates(metadata)
    if not image_candidates:
        raise TikTokDownloadError("TikTok photo post image could not be found")

    audio_format = _select_audio_format(metadata)
    if audio_format is None:
        raise TikTokDownloadError("TikTok photo post audio could not be found")

    audio_url = audio_format.get("url")
    if not isinstance(audio_url, str) or not audio_url:
        raise TikTokDownloadError("TikTok photo post audio URL is missing")

    base_stem = _build_base_stem(metadata)
    downloaded_image_paths: list[Path] = []
    for index, image_url in enumerate(image_candidates, start=1):
        image_ext = _guess_extension(image_url, None, ".jpg")
        image_path = VIDEOS_DIR / f"{base_stem}__photo_{index:02d}{image_ext}"
        _download_binary(image_url, image_path)
        downloaded_image_paths.append(image_path)

    audio_ext = _guess_extension(
        audio_url,
        audio_format.get("ext") if isinstance(audio_format.get("ext"), str) else None,
        ".m4a",
    )
    audio_path = VIDEOS_DIR / f"{base_stem}__audio{audio_ext}"
    video_path = VIDEOS_DIR / f"{base_stem}.mp4"

    _download_binary(audio_url, audio_path)

    try:
        render_result = render_photo_reel(downloaded_image_paths, audio_path, video_path)
    except RenderError as exc:
        raise TikTokDownloadError(str(exc)) from exc

    final_video_path = Path(render_result["video_path"])
    cover_intro_applied = False
    cover_intro_source_path = None
    if prepend_cover_intro:
        try:
            final_video_path = prepend_cover_intro_frame(
                final_video_path,
                COVER_IMAGE_PATH,
                final_video_path,
            )
        except RenderError as exc:
            raise TikTokDownloadError(str(exc)) from exc
        cover_intro_applied = True
        cover_intro_source_path = str(COVER_IMAGE_PATH.resolve())

    return {
        "media_kind": "photo_post",
        "video_path": str(final_video_path),
        "video_filename": final_video_path.name,
        "download": {
            "extractor": "yt-dlp",
            "source_id": metadata.get("id"),
            "title": metadata.get("title"),
            "source_media_kind": "photo_post",
            "audio_path": str(audio_path.resolve()),
            "image_path": str(downloaded_image_paths[0].resolve()),
            "image_paths": [str(path.resolve()) for path in downloaded_image_paths],
            "audio_duration_seconds": render_result["audio_duration_seconds"],
            "rendered_from_photo": True,
            "cover_intro_applied": cover_intro_applied,
            "cover_intro_source_path": cover_intro_source_path,
        },
    }


def prepare_tiktok_media(url: str, *, prepend_cover_intro: bool = False) -> dict:
    if not is_tiktok_url(url):
        raise TikTokDownloadError("URL must be a valid TikTok link")

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    metadata = fetch_tiktok_metadata(url)
    media_kind = _detect_media_kind(metadata)

    if media_kind == "photo_post":
        return _prepare_photo_media(metadata, prepend_cover_intro=prepend_cover_intro)

    return _prepare_video_media(url, metadata, prepend_cover_intro=prepend_cover_intro)


def fetch_video_cover_image(url: str) -> Path:
    """Download the cover/thumbnail of any yt-dlp-supported video URL and save it as the cover image.

    Fetches video metadata via yt-dlp, selects the best available thumbnail, downloads
    it, and saves it to ``COVER_IMAGE_PATH`` (``coverrrr.png`` in the project root).

    Args:
        url: A publicly accessible video URL (TikTok or any yt-dlp-supported site).

    Returns:
        The :class:`~pathlib.Path` where the cover image was saved.

    Raises:
        TikTokDownloadError: If the URL is empty, metadata cannot be fetched, no
            thumbnail is available, or the download fails.
    """
    if not isinstance(url, str) or not url.strip():
        raise TikTokDownloadError("URL must not be empty")

    parsed_url = urlparse(url.strip())
    if parsed_url.scheme not in {"http", "https"}:
        raise TikTokDownloadError("URL must use http or https")

    command = [
        *get_yt_dlp_command(),
        "--print-json",
        "--no-warnings",
        "--skip-download",
        url.strip(),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise TikTokDownloadError(result.stderr.strip() or "Failed to fetch video metadata")

    stdout = result.stdout.strip()
    if not stdout:
        raise TikTokDownloadError("yt-dlp returned no metadata")

    try:
        metadata = json.loads(stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise TikTokDownloadError("yt-dlp returned unreadable metadata") from exc

    image_candidates = _extract_image_candidates(metadata)
    if not image_candidates:
        raise TikTokDownloadError("No cover image found for the given video URL")

    COVER_IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _download_binary(image_candidates[0], COVER_IMAGE_PATH)
    return COVER_IMAGE_PATH


def download_tiktok_video(url: str) -> dict:
    """Backward-compatible alias for the older video-only downloader name."""
    return prepare_tiktok_media(url)
