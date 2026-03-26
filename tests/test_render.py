from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.components.video_logic.render import RenderError, get_media_duration, render_photo_reel


class RenderHelpersTestCase(unittest.TestCase):
    @patch("src.components.video_logic.render.shutil.which", return_value="C:/bin/ffprobe.exe")
    @patch("src.components.video_logic.render.subprocess.run")
    def test_get_media_duration_reads_ffprobe_output(self, mock_run, _mock_which):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout='{"format":{"duration":"12.345"}}',
            stderr="",
        )

        duration = get_media_duration("audio.m4a")

        self.assertAlmostEqual(duration, 12.345)
        command = mock_run.call_args.args[0]
        self.assertIn("ffprobe", command[0])
        self.assertIn("audio.m4a", command)

    @patch("src.components.video_logic.render.shutil.which", side_effect=lambda name: f"C:/bin/{name}.exe")
    @patch("src.components.video_logic.render.get_media_duration", return_value=7.25)
    @patch("src.components.video_logic.render.subprocess.run")
    def test_render_photo_reel_builds_expected_ffmpeg_command(
        self,
        mock_run,
        _mock_duration,
        _mock_which,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "photo.jpg"
            audio_path = Path(temp_dir) / "audio.m4a"
            output_path = Path(temp_dir) / "rendered.mp4"
            image_path.write_bytes(b"image")
            audio_path.write_bytes(b"audio")

            def _run_side_effect(command, **_kwargs):
                Path(command[-1]).write_bytes(b"video")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            mock_run.side_effect = _run_side_effect

            result = render_photo_reel(image_path, audio_path, output_path)

            self.assertEqual(result["video_filename"], "rendered.mp4")
            self.assertAlmostEqual(result["audio_duration_seconds"], 7.25)
            self.assertTrue(output_path.exists())

            command = mock_run.call_args.args[0]
            self.assertEqual(command[0], "C:/bin/ffmpeg.exe")
            self.assertIn("-loop", command)
            self.assertIn("-filter_complex", command)
            self.assertIn("7.250", command)
            self.assertIn(str(image_path), command)
            self.assertIn(str(audio_path), command)

    @patch("src.components.video_logic.render.shutil.which", side_effect=lambda name: f"C:/bin/{name}.exe")
    @patch("src.components.video_logic.render.get_media_duration", return_value=3.0)
    @patch("src.components.video_logic.render.subprocess.run")
    def test_render_photo_reel_raises_on_ffmpeg_failure(
        self,
        mock_run,
        _mock_duration,
        _mock_which,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "photo.jpg"
            audio_path = Path(temp_dir) / "audio.m4a"
            output_path = Path(temp_dir) / "rendered.mp4"
            image_path.write_bytes(b"image")
            audio_path.write_bytes(b"audio")
            mock_run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="boom")

            with self.assertRaises(RenderError):
                render_photo_reel(image_path, audio_path, output_path)


if __name__ == "__main__":
    unittest.main()
