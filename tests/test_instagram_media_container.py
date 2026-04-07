from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.components.video_logic import api


class InstagramMediaContainerPayloadTestCase(unittest.TestCase):
    @patch("src.components.video_logic.api.requests.post")
    def test_create_media_container_includes_cover_url_and_ignores_thumb_offset(self, mock_post):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"id": "container-1"}
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        container_id = api.create_media_container(
            video_url="https://example.com/video.mp4",
            caption="cap",
            media_type="REELS",
            cover_url="https://example.com/cover.jpg",
            thumb_offset=250,
            share_to_feed=True,
        )

        self.assertEqual(container_id, "container-1")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["cover_url"], "https://example.com/cover.jpg")
        self.assertNotIn("thumb_offset", payload)
        self.assertTrue(payload["share_to_feed"])

    @patch("src.components.video_logic.api.requests.post")
    def test_create_media_container_uses_thumb_offset_when_cover_url_missing(self, mock_post):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"id": "container-2"}
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        api.create_media_container(
            video_url="https://example.com/video.mp4",
            media_type="REELS",
            thumb_offset=1200,
        )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["thumb_offset"], 1200)
        self.assertNotIn("cover_url", payload)


if __name__ == "__main__":
    unittest.main()
