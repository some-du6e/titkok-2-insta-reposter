from __future__ import annotations

import threading
from datetime import datetime, timezone

from src.components.pipeline import QueuePipelineError, QueueValidationError, enqueue_tiktok_url
from src.components import queue_store
from src.components.video_logic.tiktok_collection import (
    CollectionFetchResult,
    PublicCollectionError,
    fetch_public_collection,
    normalize_collection_url,
)


PUBLIC_COLLECTION_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_error_message(exc: Exception) -> str:
    return str(exc)[:512]


def get_public_collection_status() -> dict:
    settings = queue_store.get_settings()
    return {
        "enabled": settings.get("publicCollectionEnabled", False),
        "url": settings.get("publicCollectionUrl"),
        "poll_seconds": settings.get("publicCollectionPollSeconds"),
        "last_cursor": settings.get("publicCollectionLastCursor"),
        "seen_ids": settings.get("publicCollectionSeenIds", []),
        "last_status": settings.get("publicCollectionLastStatus"),
        "last_error": settings.get("publicCollectionLastError"),
        "last_items_found": settings.get("publicCollectionLastItemsFound"),
        "last_items_queued": settings.get("publicCollectionLastItemsQueued"),
        "last_extract_strategy": settings.get("publicCollectionLastExtractStrategy"),
        "last_checked_at": settings.get("publicCollectionLastCheckedAt"),
    }


def _update_public_collection_settings(updates: dict) -> dict:
    settings = queue_store.get_settings()
    merged = dict(settings)
    merged.update(updates)
    return queue_store.save_settings(merged)


def test_public_collection_url(url: str) -> dict:
    try:
        normalized = normalize_collection_url(url)
        result = fetch_public_collection(normalized)
        return {
            "fetch_ok": result.error is None,
            "extract_strategy": result.strategy,
            "items_found": len(result.items),
            "sample_items": [item.url for item in result.items[:5]],
            "error": result.error,
            "normalized_url": normalized,
            "metadata": result.metadata or {},
        }
    except Exception as exc:
        return {
            "fetch_ok": False,
            "extract_strategy": "none",
            "items_found": 0,
            "sample_items": [],
            "error": _safe_error_message(exc),
            "normalized_url": None,
            "metadata": {},
        }


def _sync_result_payload(
    *,
    status: str,
    fetch_result: CollectionFetchResult | None = None,
    items_queued: int = 0,
    duplicates: int = 0,
    baseline_seeded: bool = False,
    error: str | None = None,
) -> dict:
    return {
        "status": status,
        "items_found": len(fetch_result.items) if fetch_result else 0,
        "items_queued": items_queued,
        "duplicates": duplicates,
        "baseline_seeded": baseline_seeded,
        "extract_strategy": fetch_result.strategy if fetch_result else "none",
        "sample_items": [item.url for item in (fetch_result.items[:5] if fetch_result else [])],
        "error": error or (fetch_result.error if fetch_result else None),
        "metadata": fetch_result.metadata if fetch_result else {},
    }


def sync_public_collection(*, override_url: str | None = None) -> dict:
    with PUBLIC_COLLECTION_LOCK:
        settings = queue_store.get_settings()
        configured_url = override_url or settings.get("publicCollectionUrl")
        normalized_url = normalize_collection_url(configured_url)

        fetch_result = fetch_public_collection(normalized_url)
        checked_at = _now_iso()

        if fetch_result.error:
            _update_public_collection_settings(
                {
                    "publicCollectionUrl": normalized_url,
                    "publicCollectionLastStatus": "parse_error",
                    "publicCollectionLastError": fetch_result.error,
                    "publicCollectionLastItemsFound": 0,
                    "publicCollectionLastItemsQueued": 0,
                    "publicCollectionLastExtractStrategy": fetch_result.strategy,
                    "publicCollectionLastCheckedAt": checked_at,
                }
            )
            return _sync_result_payload(status="parse_error", fetch_result=fetch_result, error=fetch_result.error)

        seen_ids = list(settings.get("publicCollectionSeenIds", []))
        seen_set = set(seen_ids)
        incoming_ids = [item.id or item.url for item in fetch_result.items]
        baseline_ready = settings.get("publicCollectionLastStatus") == "baseline_ready"

        if not baseline_ready and not seen_ids:
            _update_public_collection_settings(
                {
                    "publicCollectionUrl": normalized_url,
                    "publicCollectionSeenIds": incoming_ids,
                    "publicCollectionLastStatus": "baseline_ready",
                    "publicCollectionLastError": "",
                    "publicCollectionLastItemsFound": len(fetch_result.items),
                    "publicCollectionLastItemsQueued": 0,
                    "publicCollectionLastExtractStrategy": fetch_result.strategy,
                    "publicCollectionLastCheckedAt": checked_at,
                }
            )
            return _sync_result_payload(status="baseline_ready", fetch_result=fetch_result, baseline_seeded=True)

        items_queued = 0
        duplicates = 0

        for item in fetch_result.items:
            item_key = item.id or item.url
            if item_key in seen_set:
                continue

            try:
                enqueue_status, _queue_item = enqueue_tiktok_url(
                    item.url,
                    source_kind="public_collection_monitor",
                    discovered_at=checked_at,
                    ingestion_metadata={
                        "client": "server_public_collection_monitor",
                        "collection_url": normalized_url,
                        "extract_strategy": fetch_result.strategy,
                        "collection_metadata": fetch_result.metadata or {},
                    },
                )
            except QueueValidationError as exc:
                raise QueuePipelineError(str(exc)) from exc

            if enqueue_status == "queued":
                items_queued += 1
            elif enqueue_status == "duplicate":
                duplicates += 1

            seen_set.add(item_key)

        final_status = "idle"
        if items_queued:
            final_status = "queued"
        elif duplicates:
            final_status = "duplicate_only"

        _update_public_collection_settings(
            {
                "publicCollectionUrl": normalized_url,
                "publicCollectionSeenIds": list(seen_set),
                "publicCollectionLastStatus": final_status,
                "publicCollectionLastError": "",
                "publicCollectionLastItemsFound": len(fetch_result.items),
                "publicCollectionLastItemsQueued": items_queued,
                "publicCollectionLastExtractStrategy": fetch_result.strategy,
                "publicCollectionLastCheckedAt": checked_at,
            }
        )

        return _sync_result_payload(
            status=final_status,
            fetch_result=fetch_result,
            items_queued=items_queued,
            duplicates=duplicates,
        )
