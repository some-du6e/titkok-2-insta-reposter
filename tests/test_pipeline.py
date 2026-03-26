from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.components import queue_store
from src.components.pipeline import QueuePipelineError, enqueue_tiktok_url, publish_queue_item
from src.components.video_logic.tiktok import TikTokDownloadError


class PipelinePhotoSupportTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_queue_path = queue_store.QUEUE_PATH
        queue_store.QUEUE_PATH = Path(self.temp_dir.name) / "queue.json"
        self.addCleanup(self._restore_queue_path)

    def _restore_queue_path(self):
        queue_store.QUEUE_PATH = self.original_queue_path

    @patch("src.components.pipeline.captions_store.load_captions", return_value=["Caption"])
    @patch("src.components.pipeline.prepare_tiktok_media")
    def test_enqueue_standard_video_item_preserves_video_contract(
        self,
        mock_prepare_media,
        _mock_captions,
    ):
        video_path = Path(self.temp_dir.name) / "clip.mp4"
        video_path.write_bytes(b"video")
        mock_prepare_media.return_value = {
            "media_kind": "video",
            "video_path": str(video_path),
            "video_filename": video_path.name,
            "download": {
                "extractor": "yt-dlp",
                "source_id": "123",
                "title": "Clip",
                "source_media_kind": "video",
                "audio_path": None,
                "image_path": None,
                "audio_duration_seconds": None,
                "rendered_from_photo": False,
            },
        }

        status, item = enqueue_tiktok_url("https://www.tiktok.com/@creator/video/123")

        self.assertEqual(status, "queued")
        self.assertEqual(item["source_media_kind"], "video")
        self.assertFalse(item["rendered_from_photo"])
        self.assertEqual(item["source_assets"]["audio_path"], None)

    @patch("src.components.pipeline.captions_store.load_captions", return_value=["Caption"])
    @patch("src.components.pipeline.prepare_tiktok_media")
    def test_enqueue_photo_post_stores_rendered_video_and_source_assets(
        self,
        mock_prepare_media,
        _mock_captions,
    ):
        video_path = Path(self.temp_dir.name) / "photo-post.mp4"
        video_path.write_bytes(b"video")
        mock_prepare_media.return_value = {
            "media_kind": "photo_post",
            "video_path": str(video_path),
            "video_filename": video_path.name,
            "download": {
                "extractor": "yt-dlp",
                "source_id": "456",
                "title": "Photo post",
                "source_media_kind": "photo_post",
                "audio_path": str(Path(self.temp_dir.name) / "audio.m4a"),
                "image_path": str(Path(self.temp_dir.name) / "photo.jpg"),
                "audio_duration_seconds": 8.4,
                "rendered_from_photo": True,
            },
        }

        status, item = enqueue_tiktok_url("https://www.tiktok.com/@creator/video/456")

        self.assertEqual(status, "queued")
        self.assertEqual(item["source_media_kind"], "photo_post")
        self.assertTrue(item["rendered_from_photo"])
        self.assertEqual(item["video_path"], str(video_path.resolve()))
        self.assertEqual(item["source_assets"]["audio_duration_seconds"], 8.4)

    @patch("src.components.pipeline.captions_store.load_captions", return_value=["Caption"])
    @patch("src.components.pipeline.prepare_tiktok_media")
    def test_duplicate_detection_still_works_for_photo_posts(
        self,
        mock_prepare_media,
        _mock_captions,
    ):
        video_path = Path(self.temp_dir.name) / "photo-post.mp4"
        video_path.write_bytes(b"video")
        mock_prepare_media.return_value = {
            "media_kind": "photo_post",
            "video_path": str(video_path),
            "video_filename": video_path.name,
            "download": {
                "extractor": "yt-dlp",
                "source_id": "456",
                "title": "Photo post",
                "source_media_kind": "photo_post",
                "audio_path": None,
                "image_path": None,
                "audio_duration_seconds": 3.1,
                "rendered_from_photo": True,
            },
        }

        first_status, first_item = enqueue_tiktok_url("https://www.tiktok.com/@creator/video/456")
        second_status, second_item = enqueue_tiktok_url("https://www.tiktok.com/@creator/video/456?utm_source=test")

        self.assertEqual(first_status, "queued")
        self.assertEqual(second_status, "duplicate")
        self.assertEqual(second_item["id"], first_item["id"])
        self.assertEqual(mock_prepare_media.call_count, 1)

    @patch("src.components.pipeline.InstagramUploader")
    def test_publish_path_still_uses_rendered_local_mp4_for_photo_posts(self, mock_uploader):
        video_path = Path(self.temp_dir.name) / "photo-post.mp4"
        video_path.write_bytes(b"video")
        queue_store.append_item(
            {
                "id": "item-1",
                "source_url": "https://www.tiktok.com/@creator/video/456",
                "source_url_normalized": "https://www.tiktok.com/@creator/video/456",
                "source_kind": "manual",
                "source_id": "456",
                "video_path": str(video_path.resolve()),
                "video_filename": video_path.name,
                "source_media_kind": "photo_post",
                "rendered_from_photo": True,
                "source_assets": {
                    "image_path": "photo.jpg",
                    "audio_path": "audio.m4a",
                    "audio_duration_seconds": 8.4,
                },
                "caption": "Caption",
                "media_type": "REELS",
                "status": "queued",
                "created_at": "2026-03-24T00:00:00+00:00",
                "updated_at": "2026-03-24T00:00:00+00:00",
                "published_at": None,
                "instagram_media_id": None,
                "container_id": None,
                "download": {"title": "Photo post", "rendered_from_photo": True},
                "preview": {
                    "status": "missing",
                    "image_path": None,
                    "updated_at": "2026-03-24T00:00:00+00:00",
                    "width": None,
                    "height": None,
                    "error": None,
                },
                "last_error": None,
            }
        )
        mock_uploader.return_value.upload_video.return_value = {
            "media_id": "ig-1",
            "container_id": "container-1",
        }

        result = publish_queue_item("item-1")

        self.assertEqual(result["status"], "published")
        mock_uploader.return_value.upload_video.assert_called_once_with(
            video_path=str(video_path.resolve()),
            caption="Caption",
            media_type="REELS",
        )

    @patch("src.components.pipeline.traceback.print_exc")
    @patch("src.components.pipeline.InstagramUploader")
    def test_publish_failure_persists_detailed_error_message(self, mock_uploader, mock_print_exc):
        video_path = Path(self.temp_dir.name) / "broken.mp4"
        video_path.write_bytes(b"video")
        queue_store.append_item(
            {
                "id": "item-fail",
                "source_url": "https://www.tiktok.com/@creator/video/999",
                "source_url_normalized": "https://www.tiktok.com/@creator/video/999",
                "source_kind": "manual",
                "source_id": "999",
                "video_path": str(video_path.resolve()),
                "video_filename": video_path.name,
                "source_media_kind": "video",
                "rendered_from_photo": False,
                "source_assets": {
                    "image_path": None,
                    "audio_path": None,
                    "audio_duration_seconds": None,
                },
                "caption": "Caption",
                "media_type": "REELS",
                "status": "queued",
                "created_at": "2026-03-24T00:00:00+00:00",
                "updated_at": "2026-03-24T00:00:00+00:00",
                "published_at": None,
                "instagram_media_id": None,
                "container_id": None,
                "download": {"title": "Broken post", "rendered_from_photo": False},
                "preview": {
                    "status": "missing",
                    "image_path": None,
                    "updated_at": "2026-03-24T00:00:00+00:00",
                    "width": None,
                    "height": None,
                    "error": None,
                },
                "last_error": None,
            }
        )
        mock_uploader.return_value.upload_video.side_effect = RuntimeError(
            "Instagram media publish failed: status=400 body={'error': {'message': 'Bad request'}}"
        )

        result = publish_queue_item("item-fail")

        self.assertEqual(result["status"], "failed")
        self.assertIn("Instagram media publish failed", result["last_error"])
        mock_print_exc.assert_called_once()

    @patch("src.components.pipeline.captions_store.load_captions", return_value=["Caption"])
    @patch("src.components.pipeline.prepare_tiktok_media", side_effect=TikTokDownloadError("Photo post image is missing"))
    def test_prepare_failure_does_not_append_partial_queue_item(
        self,
        _mock_prepare_media,
        _mock_captions,
    ):
        with self.assertRaises(QueuePipelineError):
            enqueue_tiktok_url("https://www.tiktok.com/@creator/video/456")

        payload = json.loads(queue_store.QUEUE_PATH.read_text(encoding="utf-8")) if queue_store.QUEUE_PATH.exists() else {"items": []}
        self.assertEqual(payload["items"], [])


if __name__ == "__main__":
    unittest.main()
