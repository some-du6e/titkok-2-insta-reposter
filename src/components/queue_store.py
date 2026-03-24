from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUEUE_PATH = PROJECT_ROOT / "queue.json"


class QueueItemNotFoundError(KeyError):
    """Raised when a queue item cannot be found."""


def _normalize_items(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []

    return [item for item in raw if isinstance(item, dict)]


def load_queue() -> dict:
    if not QUEUE_PATH.exists():
        return {"items": []}

    raw_content = QUEUE_PATH.read_text(encoding="utf-8").strip()
    if not raw_content:
        return {"items": []}

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        return {"items": []}

    if not isinstance(parsed, dict):
        return {"items": []}

    return {"items": _normalize_items(parsed.get("items", []))}


def save_queue(queue: dict) -> dict:
    payload = {"items": _normalize_items(queue.get("items", []))}
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
