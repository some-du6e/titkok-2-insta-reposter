from __future__ import annotations

import unittest
from unittest.mock import patch

from src.components.video_logic.tiktok import (
    TikTokDownloadError,
    _build_base_stem,
    _extract_image_candidates,
    prepare_tiktok_media,
)


class TikTokMediaPrepTestCase(unittest.TestCase):
    @patch("src.components.video_logic.tiktok._prepare_video_media")
    @patch("src.components.video_logic.tiktok.fetch_tiktok_metadata")
    def test_standard_video_metadata_routes_to_video_preparation(
        self,
        mock_fetch_metadata,
        mock_prepare_video,
    ):
        mock_fetch_metadata.return_value = {
            "id": "123",
            "title": "Video",
            "formats": [
                {"vcodec": "h264", "acodec": "aac", "width": 720, "height": 1280, "url": "https://v.example/video.mp4"}
            ],
        }
        mock_prepare_video.return_value = {"media_kind": "video"}

        result = prepare_tiktok_media("https://www.tiktok.com/@creator/video/123")

        self.assertEqual(result["media_kind"], "video")
        mock_prepare_video.assert_called_once()
        self.assertEqual(mock_prepare_video.call_args.kwargs["prepend_cover_intro"], False)

    @patch("src.components.video_logic.tiktok._prepare_photo_media")
    @patch("src.components.video_logic.tiktok.fetch_tiktok_metadata")
    def test_photo_post_metadata_with_images_routes_to_photo_preparation(
        self,
        mock_fetch_metadata,
        mock_prepare_photo,
    ):
        mock_fetch_metadata.return_value = {
            "id": "456",
            "title": "Photo post",
            "images": [{"url": "https://img.example/photo.jpg"}],
            "formats": [
                {
                    "vcodec": "h264",
                    "acodec": "aac",
                    "width": 0,
                    "height": 0,
                    "url": "https://sf16-ies-music-va.tiktokcdn.com/audio",
                }
            ],
        }
        mock_prepare_photo.return_value = {"media_kind": "photo_post"}

        result = prepare_tiktok_media("https://www.tiktok.com/@creator/video/456")

        self.assertEqual(result["media_kind"], "photo_post")
        mock_prepare_photo.assert_called_once()
        self.assertEqual(mock_prepare_photo.call_args.kwargs["prepend_cover_intro"], False)

    @patch("src.components.video_logic.tiktok._prepare_photo_media")
    @patch("src.components.video_logic.tiktok.fetch_tiktok_metadata")
    def test_audio_only_disguised_as_video_routes_to_photo_preparation(
        self,
        mock_fetch_metadata,
        mock_prepare_photo,
    ):
        mock_fetch_metadata.return_value = {
            "id": "789",
            "formats": [
                {
                    "vcodec": "h264",
                    "acodec": "aac",
                    "width": 0,
                    "height": 0,
                    "url": "https://sf16-ies-music-va.tiktokcdn.com/obj/audio-track",
                }
            ],
            "thumbnails": [{"url": "https://img.example/post.jpg", "width": 1080, "height": 1920}],
        }
        mock_prepare_photo.return_value = {"media_kind": "photo_post"}

        result = prepare_tiktok_media("https://www.tiktok.com/@creator/video/789")

        self.assertEqual(result["media_kind"], "photo_post")
        mock_prepare_photo.assert_called_once()
        self.assertEqual(mock_prepare_photo.call_args.kwargs["prepend_cover_intro"], False)

    @patch("src.components.video_logic.tiktok._prepare_video_media")
    @patch("src.components.video_logic.tiktok.fetch_tiktok_metadata")
    def test_prepare_tiktok_media_passes_cover_intro_flag_for_videos(
        self,
        mock_fetch_metadata,
        mock_prepare_video,
    ):
        mock_fetch_metadata.return_value = {
            "id": "123",
            "formats": [{"vcodec": "h264", "acodec": "aac", "width": 720, "height": 1280}],
        }
        mock_prepare_video.return_value = {
            "media_kind": "video",
            "download": {"cover_intro_applied": True},
        }

        result = prepare_tiktok_media(
            "https://www.tiktok.com/@creator/video/123",
            prepend_cover_intro=True,
        )

        self.assertTrue(result["download"]["cover_intro_applied"])
        self.assertEqual(mock_prepare_video.call_args.kwargs["prepend_cover_intro"], True)

    @patch("src.components.video_logic.tiktok._prepare_photo_media")
    @patch("src.components.video_logic.tiktok.fetch_tiktok_metadata")
    def test_prepare_tiktok_media_passes_cover_intro_flag_for_photo_posts(
        self,
        mock_fetch_metadata,
        mock_prepare_photo,
    ):
        mock_fetch_metadata.return_value = {
            "id": "456",
            "images": [{"url": "https://img.example/photo.jpg"}],
            "formats": [
                {
                    "vcodec": "h264",
                    "acodec": "aac",
                    "width": 0,
                    "height": 0,
                    "url": "https://sf16-ies-music-va.tiktokcdn.com/audio",
                }
            ],
        }
        mock_prepare_photo.return_value = {
            "media_kind": "photo_post",
            "download": {"cover_intro_applied": True},
        }

        result = prepare_tiktok_media(
            "https://www.tiktok.com/@creator/video/456",
            prepend_cover_intro=True,
        )

        self.assertTrue(result["download"]["cover_intro_applied"])
        self.assertEqual(mock_prepare_photo.call_args.kwargs["prepend_cover_intro"], True)

    def test_build_base_stem_uses_stable_fallbacks(self):
        stem = _build_base_stem({"uploader_id": None, "id": None, "title": None})

        self.assertEqual(stem, "unknown__unknown")

    def test_invalid_url_raises_validation_error(self):
        with self.assertRaises(TikTokDownloadError):
            prepare_tiktok_media("https://example.com/not-tiktok")

    def test_extract_image_candidates_reads_slideshow_images_from_image_post_info(self):
        metadata = {
            "image_post_info": {
                "images": [
                    {"image_url": {"url_list": ["https://img.example/one.jpg"]}},
                    {"image_url": {"url_list": ["https://img.example/two.jpg"]}},
                ]
            },
            "thumbnails": [
                {
                    "url": "https://img.example/thumb.jpg",
                    "width": 1080,
                    "height": 1920,
                }
            ],
        }

        image_urls = _extract_image_candidates(metadata)

        self.assertEqual(
            image_urls,
            ["https://img.example/one.jpg", "https://img.example/two.jpg"],
        )


if __name__ == "__main__":
    unittest.main()
