from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from src.components.api import app
from src.components.public_collection import sync_public_collection
from src.components.video_logic.tiktok_collection import (
    CollectionFetchResult,
    CollectionItem,
    extract_embedded_json_items,
    extract_html_items,
    normalize_collection_url,
)


class PublicCollectionHelpersTestCase(unittest.TestCase):
    def test_normalize_collection_url_strips_tracking(self):
        normalized = normalize_collection_url(
            "https://www.tiktok.com/@commenter495/collection/To%20ig-7620160651285695252/?utm_source=test"
        )
        self.assertEqual(
            normalized,
            "https://www.tiktok.com/@commenter495/collection/To%20ig-7620160651285695252",
        )

    def test_extract_html_items_finds_canonical_video_urls(self):
        html = """
        <html>
          <body>
            <a href="/@sweetnsaucii/video/7598284820724206855?foo=bar">One</a>
            <a href="https://www.tiktok.com/@imaan.sal/video/7619296655703067925">Two</a>
          </body>
        </html>
        """

        items = extract_html_items(html)

        self.assertEqual(
            [item.url for item in items],
            [
                "https://www.tiktok.com/@sweetnsaucii/video/7598284820724206855",
                "https://www.tiktok.com/@imaan.sal/video/7619296655703067925",
            ],
        )

    def test_extract_embedded_json_items_builds_urls_from_author_and_id(self):
        payload = {
            "__DEFAULT_SCOPE__": {
                "collection": {
                    "items": [
                        {"author": "sweetnsaucii", "id": "7598284820724206855"},
                        {"authorName": "@imaan.sal", "videoId": "7619296655703067925"},
                    ]
                }
            }
        }

        items = extract_embedded_json_items(payload)

        self.assertEqual(
            [item.url for item in items],
            [
                "https://www.tiktok.com/@sweetnsaucii/video/7598284820724206855",
                "https://www.tiktok.com/@imaan.sal/video/7619296655703067925",
            ],
        )


class PublicCollectionSyncTestCase(unittest.TestCase):
    @patch("src.components.public_collection._update_public_collection_settings")
    @patch("src.components.public_collection.fetch_public_collection")
    @patch("src.components.public_collection.queue_store.get_settings")
    def test_first_sync_seeds_baseline_without_queueing(
        self,
        mock_get_settings,
        mock_fetch_public_collection,
        mock_update_settings,
    ):
        mock_get_settings.return_value = {
            "publicCollectionUrl": "https://www.tiktok.com/@commenter495/collection/To%20ig-7620160651285695252",
            "publicCollectionSeenIds": [],
            "publicCollectionLastStatus": "idle",
        }
        mock_fetch_public_collection.return_value = CollectionFetchResult(
            items=[
                CollectionItem(
                    id="7598284820724206855",
                    url="https://www.tiktok.com/@sweetnsaucii/video/7598284820724206855",
                )
            ],
            strategy="undocumented_api",
        )

        with patch("src.components.public_collection.enqueue_tiktok_url") as mock_enqueue:
            result = sync_public_collection()

        self.assertEqual(result["status"], "baseline_ready")
        self.assertTrue(result["baseline_seeded"])
        mock_enqueue.assert_not_called()
        mock_update_settings.assert_called_once()

    @patch("src.components.public_collection._update_public_collection_settings")
    @patch("src.components.public_collection.fetch_public_collection")
    @patch("src.components.public_collection.queue_store.get_settings")
    def test_sync_only_queues_unseen_items(
        self,
        mock_get_settings,
        mock_fetch_public_collection,
        mock_update_settings,
    ):
        mock_get_settings.return_value = {
            "publicCollectionUrl": "https://www.tiktok.com/@commenter495/collection/To%20ig-7620160651285695252",
            "publicCollectionSeenIds": ["7598284820724206855"],
            "publicCollectionLastStatus": "baseline_ready",
        }
        mock_fetch_public_collection.return_value = CollectionFetchResult(
            items=[
                CollectionItem(
                    id="7598284820724206855",
                    url="https://www.tiktok.com/@sweetnsaucii/video/7598284820724206855",
                ),
                CollectionItem(
                    id="7619296655703067925",
                    url="https://www.tiktok.com/@imaan.sal/video/7619296655703067925",
                ),
            ],
            strategy="undocumented_api",
        )

        with patch("src.components.public_collection.enqueue_tiktok_url") as mock_enqueue:
            mock_enqueue.return_value = ("queued", {"id": "queue-item"})
            result = sync_public_collection()

        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["items_queued"], 1)
        mock_enqueue.assert_called_once_with(
            "https://www.tiktok.com/@imaan.sal/video/7619296655703067925",
            source_kind="public_collection_monitor",
            discovered_at=unittest.mock.ANY,
            ingestion_metadata=unittest.mock.ANY,
        )
        mock_update_settings.assert_called_once()


class PublicCollectionApiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch("src.components.api.test_public_collection_url")
    def test_test_endpoint_returns_collection_probe_result(self, mock_test_public_collection_url):
        mock_test_public_collection_url.return_value = {
            "fetch_ok": True,
            "extract_strategy": "html_embedded",
            "items_found": 2,
            "sample_items": ["https://www.tiktok.com/@foo/video/1"],
            "error": None,
            "normalized_url": "https://www.tiktok.com/@foo/collection/bar-1",
            "metadata": {},
        }

        response = self.client.post(
            "/api/public-collection/test",
            data=json.dumps({"url": "https://www.tiktok.com/@foo/collection/bar-1"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["items_found"], 2)
        self.assertEqual(payload["extract_strategy"], "html_embedded")

    @patch("src.components.api.sync_public_collection")
    def test_sync_endpoint_returns_sync_summary(self, mock_sync_public_collection):
        mock_sync_public_collection.return_value = {
            "status": "queued",
            "items_found": 3,
            "items_queued": 1,
            "duplicates": 2,
            "baseline_seeded": False,
            "extract_strategy": "undocumented_api",
            "sample_items": [],
            "error": None,
            "metadata": {},
        }

        response = self.client.post(
            "/api/public-collection/sync",
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["items_queued"], 1)

    @patch("src.components.api.get_public_collection_status")
    def test_status_endpoint_returns_monitor_state(self, mock_get_public_collection_status):
        mock_get_public_collection_status.return_value = {
            "enabled": True,
            "url": "https://www.tiktok.com/@foo/collection/bar-1",
            "poll_seconds": 300,
            "last_cursor": None,
            "seen_ids": ["1"],
            "last_status": "queued",
            "last_error": "",
            "last_items_found": 3,
            "last_items_queued": 1,
            "last_extract_strategy": "undocumented_api",
            "last_checked_at": "2026-03-24T00:00:00+00:00",
        }

        response = self.client.get("/api/public-collection/status")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["last_extract_strategy"], "undocumented_api")


if __name__ == "__main__":
    unittest.main()
