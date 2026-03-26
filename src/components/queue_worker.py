from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

from src.components.public_collection import sync_public_collection
from src.components.pipeline import publish_next_queued_item
from src.components.queue_store import get_settings


LOGGER = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 5
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()


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


def _is_due(settings: dict) -> bool:
    if not settings.get("auto_post_enabled"):
        return False

    next_run = _parse_iso(settings.get("next_auto_post_at"))
    if next_run is None:
        return True

    return next_run <= datetime.now(timezone.utc)


def _collection_is_due(settings: dict) -> bool:
    if not settings.get("publicCollectionEnabled"):
        return False
    if not settings.get("publicCollectionUrl"):
        return False

    last_checked = _parse_iso(settings.get("publicCollectionLastCheckedAt"))
    if last_checked is None:
        return True

    interval_seconds = max(1, int(settings.get("publicCollectionPollSeconds") or 300))
    return (datetime.now(timezone.utc) - last_checked).total_seconds() >= interval_seconds


def _worker_loop() -> None:
    while True:
        try:
            settings = get_settings()
            if _is_due(settings):
                publish_next_queued_item(is_auto=True)
            if _collection_is_due(settings):
                sync_public_collection()
        except Exception:
            LOGGER.exception("Automatic queue worker failed during a polling cycle")

        time.sleep(POLL_INTERVAL_SECONDS)


def should_start_worker(debug: bool) -> bool:
    if not debug:
        return True
    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def start_queue_worker(debug: bool = False) -> None:
    global _worker_thread

    if not should_start_worker(debug):
        return

    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return

        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="queue-auto-post-worker",
            daemon=True,
        )
        _worker_thread.start()
