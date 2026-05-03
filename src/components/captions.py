from __future__ import annotations

import json
import os
from pathlib import Path


class CaptionPayloadError(ValueError):
    """Raised when caption payloads do not match the expected schema."""


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(PROJECT_ROOT))).resolve()
CAPTIONS_PATH = DATA_DIR / "captions.json"


def normalize_captions(raw) -> list[str]:
    if raw is None:
        return []

    if not isinstance(raw, list):
        raise CaptionPayloadError("captions must be an array of strings")

    normalized = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, str):
            raise CaptionPayloadError(
                f"captions[{index}] must be a string"
            )
        normalized.append(entry)

    return normalized


def load_captions() -> list[str]:
    if not CAPTIONS_PATH.exists():
        return []

    try:
        raw_content = CAPTIONS_PATH.read_text(encoding="utf-8")
    except OSError:
        raise

    if not raw_content.strip():
        return []

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        return []

    try:
        return normalize_captions(parsed)
    except CaptionPayloadError:
        return []


def save_captions(captions: list[str]) -> list[str]:
    normalized = normalize_captions(captions)

    CAPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    temp_path = CAPTIONS_PATH.with_suffix(".json.tmp")
    temp_path.write_text(payload, encoding="utf-8")
    temp_path.replace(CAPTIONS_PATH)

    return normalized
