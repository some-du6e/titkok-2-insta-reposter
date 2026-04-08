from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.components.api import app


class CoverImageUploadApiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_upload_cover_image_saves_coverrrr_png(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.components.api.PROJECT_ROOT", Path(temp_dir)):
                response = self.client.post(
                    "/api/cover-image",
                    data={"cover_image": (io.BytesIO(b"fake-png-bytes"), "cover.png")},
                    content_type="multipart/form-data",
                )

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertTrue(payload["saved"])
            self.assertEqual(payload["filename"], "coverrrr.png")
            self.assertTrue((Path(temp_dir) / "coverrrr.png").exists())

    def test_upload_cover_image_requires_file(self):
        response = self.client.post("/api/cover-image", data={}, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIn("Missing cover_image file", payload["error"])


if __name__ == "__main__":
    unittest.main()
