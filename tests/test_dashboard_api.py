from __future__ import annotations

import unittest
from unittest.mock import patch

from src.components.api import app


class DashboardApiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch("src.components.api.captions_store.load_captions")
    @patch("src.components.api.get_public_collection_status")
    @patch("src.components.api.get_queue_state")
    def test_dashboard_endpoint_returns_live_summary(
        self,
        mock_get_queue_state,
        mock_get_public_collection_status,
        mock_load_captions,
    ):
        mock_get_queue_state.return_value = {
            "items": [
                {
                    "id": "queued-1",
                    "status": "queued",
                    "created_at": "2026-04-07T20:00:00+00:00",
                    "updated_at": "2026-04-07T20:10:00+00:00",
                    "published_at": None,
                    "source_url": "https://www.tiktok.com/@foo/video/1",
                    "video_filename": "queued.mp4",
                    "download": {"title": "Queued clip"},
                    "last_error": None,
                },
                {
                    "id": "failed-1",
                    "status": "failed",
                    "created_at": "2026-04-07T18:00:00+00:00",
                    "updated_at": "2026-04-07T20:20:00+00:00",
                    "published_at": None,
                    "source_url": "https://www.tiktok.com/@foo/video/2",
                    "video_filename": "failed.mp4",
                    "download": {"title": "Failed clip"},
                    "last_error": "Upload failed",
                },
                {
                    "id": "published-1",
                    "status": "published",
                    "created_at": "2026-04-07T16:00:00+00:00",
                    "updated_at": "2026-04-07T19:10:00+00:00",
                    "published_at": "2026-04-07T19:10:00+00:00",
                    "source_url": "https://www.tiktok.com/@foo/video/3",
                    "video_filename": "published.mp4",
                    "download": {"title": "Published clip"},
                    "last_error": None,
                },
            ],
            "settings": {
                "auto_post_enabled": True,
                "auto_post_interval_minutes": 15,
                "next_auto_post_at": "2026-04-07T20:30:00+00:00",
                "last_auto_post_attempt_at": "2026-04-07T20:15:00+00:00",
                "last_auto_post_result": {
                    "item_id": "published-1",
                    "status": "published",
                    "message": "Published successfully",
                    "attempted_at": "2026-04-07T20:15:00+00:00",
                },
                "prependCoverIntroEnabled": True,
            },
        }
        mock_get_public_collection_status.return_value = {
            "enabled": True,
            "last_status": "queued",
            "last_items_found": 5,
            "last_items_queued": 2,
            "last_error": "",
            "last_checked_at": "2026-04-07T20:12:00+00:00",
        }
        mock_load_captions.return_value = ["Caption one", "", "Caption three"]

        response = self.client.get("/api/dashboard")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["queue"]["queued"], 1)
        self.assertEqual(payload["queue"]["failed"], 1)
        self.assertEqual(payload["queue"]["published"], 1)
        self.assertEqual(payload["queue"]["next_item"]["id"], "queued-1")
        self.assertEqual(payload["queue"]["latest_published"]["id"], "published-1")
        self.assertEqual(payload["captions"]["total_clouds"], 3)
        self.assertEqual(payload["captions"]["filled_clouds"], 2)
        self.assertEqual(payload["automation"]["interval_minutes"], 15)
        self.assertTrue(payload["public_collection"]["enabled"])
        self.assertEqual(payload["activity"][0]["id"], "failed-1")


if __name__ == "__main__":
    unittest.main()
