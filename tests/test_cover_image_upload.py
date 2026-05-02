from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from src.components.api import app


class CoverImageUploadApiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_upload_cover_image_saves_coverrrr_jpg(self):
        image_bytes = io.BytesIO()
        Image.new("RGBA", (4, 4), color=(0, 128, 255, 200)).save(image_bytes, format="PNG")
        image_bytes.seek(0)

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.components.api.PROJECT_ROOT", Path(temp_dir)):
                response = self.client.post(
                    "/api/cover-image",
                    data={"cover_image": (image_bytes, "cover.png")},
                    content_type="multipart/form-data",
                )

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertTrue(payload["saved"])
            self.assertEqual(payload["filename"], "coverrrr.jpg")
            saved_path = Path(temp_dir) / "coverrrr.jpg"
            self.assertTrue(saved_path.exists())
            with Image.open(saved_path) as converted:
                self.assertEqual(converted.format, "JPEG")

    def test_upload_cover_image_requires_file(self):
        response = self.client.post("/api/cover-image", data={}, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIn("Missing cover_image file", payload["error"])


class CoverImageFromUrlApiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_from_url_returns_saved_cover(self):
        fake_path = Path("/tmp/fake/coverrrr.jpg")
        with patch(
            "src.components.video_logic.tiktok.fetch_video_cover_image",
            return_value=fake_path,
        ):
            response = self.client.post(
                "/api/cover-image/from-url",
                json={"url": "https://www.tiktok.com/@user/video/123"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["saved"])
        self.assertEqual(payload["filename"], "coverrrr.jpg")
        self.assertEqual(payload["path"], str(fake_path))

    def test_from_url_requires_url_field(self):
        response = self.client.post("/api/cover-image/from-url", json={})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIn("Missing url parameter", payload["error"])

    def test_from_url_requires_json_body(self):
        response = self.client.post(
            "/api/cover-image/from-url",
            data="not-json",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIn("JSON object", payload["error"])

    def test_from_url_propagates_download_error(self):
        from src.components.video_logic.tiktok import TikTokDownloadError

        with patch(
            "src.components.video_logic.tiktok.fetch_video_cover_image",
            side_effect=TikTokDownloadError("No cover image found for the given video URL"),
        ):
            response = self.client.post(
                "/api/cover-image/from-url",
                json={"url": "https://www.tiktok.com/@user/video/999"},
            )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIn("No cover image found", payload["error"])


if __name__ == "__main__":
    unittest.main()
