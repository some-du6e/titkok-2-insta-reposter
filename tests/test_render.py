from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.components.video_logic.render import (
    RenderError,
    _should_loop_visual_input_as_stream,
    get_media_duration,
    prepend_cover_intro_frame,
    render_photo_reel,
)


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

    @patch("src.components.video_logic.render.shutil.which", return_value="C:/bin/ffprobe.exe")
    @patch("src.components.video_logic.render.subprocess.run")
    def test_should_loop_visual_animated_by_packet_count(self, mock_run, _mock_which):
        """Inputs with more than one video packet are classified as stream-loop."""
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout='{"streams":[{"nb_read_packets":"30","duration":"1.0"}]}',
            stderr="",
        )
        self.assertTrue(_should_loop_visual_input_as_stream("animation.gif"))

    @patch("src.components.video_logic.render.shutil.which", return_value="C:/bin/ffprobe.exe")
    @patch("src.components.video_logic.render.subprocess.run")
    def test_should_loop_visual_animated_by_duration(self, mock_run, _mock_which):
        """Single-packet inputs whose duration exceeds the threshold are stream-loop."""
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout='{"streams":[{"nb_read_packets":"1","duration":"0.5"}]}',
            stderr="",
        )
        self.assertTrue(_should_loop_visual_input_as_stream("photo.jpg"))

    @patch("src.components.video_logic.render.shutil.which", return_value="C:/bin/ffprobe.exe")
    @patch("src.components.video_logic.render.subprocess.run")
    def test_should_loop_visual_static_image(self, mock_run, _mock_which):
        """A truly static image (1 packet, tiny duration) is not stream-looped."""
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout='{"streams":[{"nb_read_packets":"1","duration":"0.0"}]}',
            stderr="",
        )
        self.assertFalse(_should_loop_visual_input_as_stream("photo.jpg"))

    @patch("src.components.video_logic.render.shutil.which", return_value="C:/bin/ffprobe.exe")
    @patch("src.components.video_logic.render.subprocess.run")
    def test_should_loop_visual_empty_streams(self, mock_run, _mock_which):
        """An empty streams list results in False (no stream-loop)."""
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout='{"streams":[]}',
            stderr="",
        )
        self.assertFalse(_should_loop_visual_input_as_stream("photo.jpg"))

    @patch("src.components.video_logic.render.shutil.which", return_value="C:/bin/ffprobe.exe")
    @patch("src.components.video_logic.render.subprocess.run")
    def test_should_loop_visual_probe_fails_video_extension(self, mock_run, _mock_which):
        """When ffprobe fails, video extensions (.mp4, .webp) default to stream-loop."""
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="error")
        self.assertTrue(_should_loop_visual_input_as_stream("live.mp4"))
        self.assertTrue(_should_loop_visual_input_as_stream("live.webp"))

    @patch("src.components.video_logic.render.shutil.which", return_value="C:/bin/ffprobe.exe")
    @patch("src.components.video_logic.render.subprocess.run")
    def test_should_loop_visual_probe_fails_static_extension(self, mock_run, _mock_which):
        """When ffprobe fails, non-animated extensions (.jpg, .png) default to False."""
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="error")
        self.assertFalse(_should_loop_visual_input_as_stream("photo.jpg"))
        self.assertFalse(_should_loop_visual_input_as_stream("photo.png"))

    @patch("src.components.video_logic.render.shutil.which", return_value="C:/bin/ffprobe.exe")
    @patch("src.components.video_logic.render.subprocess.run")
    def test_should_loop_visual_bad_json_fallback(self, mock_run, _mock_which):
        """Unparseable ffprobe output falls back to extension-based detection."""
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="not-json", stderr="")
        self.assertTrue(_should_loop_visual_input_as_stream("clip.webm"))
        self.assertFalse(_should_loop_visual_input_as_stream("photo.png"))

    @patch("src.components.video_logic.render.shutil.which", return_value="C:/bin/ffprobe.exe")
    @patch("src.components.video_logic.render.subprocess.run")
    def test_should_loop_visual_missing_fields_treated_as_zero(self, mock_run, _mock_which):
        """Missing nb_read_packets/duration are treated as 0 and checked against thresholds."""
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout='{"streams":[{}]}',
            stderr="",
        )
        self.assertFalse(_should_loop_visual_input_as_stream("photo.jpg"))

    @patch("src.components.video_logic.render.shutil.which", side_effect=lambda name: f"C:/bin/{name}.exe")
    @patch("src.components.video_logic.render._should_loop_visual_input_as_stream", return_value=False)
    @patch("src.components.video_logic.render.get_media_duration", return_value=7.25)
    @patch("src.components.video_logic.render.subprocess.run")
    def test_render_photo_reel_builds_expected_ffmpeg_command(
        self,
        mock_run,
        _mock_duration,
        _mock_loop_mode,
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
    @patch("src.components.video_logic.render._should_loop_visual_input_as_stream", return_value=True)
    @patch("src.components.video_logic.render.get_media_duration", return_value=4.5)
    @patch("src.components.video_logic.render.subprocess.run")
    def test_render_photo_reel_uses_stream_loop_for_live_images(
        self,
        mock_run,
        _mock_duration,
        _mock_loop_mode,
        _mock_which,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "photo.webp"
            audio_path = Path(temp_dir) / "audio.m4a"
            output_path = Path(temp_dir) / "rendered.mp4"
            image_path.write_bytes(b"image")
            audio_path.write_bytes(b"audio")

            def _run_side_effect(command, **_kwargs):
                Path(command[-1]).write_bytes(b"video")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            mock_run.side_effect = _run_side_effect

            render_photo_reel(image_path, audio_path, output_path)

            command = mock_run.call_args.args[0]
            self.assertIn("-stream_loop", command)
            self.assertNotIn("-framerate", command)

    @patch("src.components.video_logic.render.shutil.which", side_effect=lambda name: f"C:/bin/{name}.exe")
    @patch("src.components.video_logic.render._should_loop_visual_input_as_stream", return_value=False)
    @patch("src.components.video_logic.render.get_media_duration", return_value=3.0)
    @patch("src.components.video_logic.render.subprocess.run")
    def test_render_photo_reel_raises_on_ffmpeg_failure(
        self,
        mock_run,
        _mock_duration,
        _mock_loop_mode,
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

    @patch("src.components.video_logic.render.shutil.which", side_effect=lambda name: f"C:/bin/{name}.exe")
    @patch("src.components.video_logic.render.subprocess.run")
    def test_prepend_cover_intro_frame_builds_expected_ffmpeg_command(
        self,
        mock_run,
        _mock_which,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "input.mp4"
            cover_path = Path(temp_dir) / "coverrrr.png"
            output_path = Path(temp_dir) / "output.mp4"
            video_path.write_bytes(b"video")
            cover_path.write_bytes(b"image")

            def _run_side_effect(command, **_kwargs):
                Path(command[-1]).write_bytes(b"video")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            mock_run.side_effect = _run_side_effect

            result = prepend_cover_intro_frame(video_path, cover_path, output_path)

            self.assertEqual(result, output_path.resolve())
            self.assertTrue(output_path.exists())
            command = mock_run.call_args.args[0]
            self.assertEqual(command[0], "C:/bin/ffmpeg.exe")
            self.assertIn("-loop", command)
            self.assertIn(str(cover_path), command)
            self.assertIn("anullsrc=channel_layout=stereo:sample_rate=48000", command)
            self.assertIn("0.100", command)
            self.assertIn("-filter_complex", command)
            filter_graph = command[command.index("-filter_complex") + 1]
            self.assertIn("[coverv][mainv]concat=n=2:v=1:a=0[v]", filter_graph)
            self.assertIn("[2:a][1:a:0]concat=n=2:v=0:a=1[a]", filter_graph)

    @patch("src.components.video_logic.render.shutil.which", side_effect=lambda name: f"C:/bin/{name}.exe")
    @patch("src.components.video_logic.render.subprocess.run")
    def test_prepend_cover_intro_frame_raises_on_ffmpeg_failure(
        self,
        mock_run,
        _mock_which,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "input.mp4"
            cover_path = Path(temp_dir) / "coverrrr.png"
            output_path = Path(temp_dir) / "output.mp4"
            video_path.write_bytes(b"video")
            cover_path.write_bytes(b"image")
            mock_run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="boom")

            with self.assertRaises(RenderError):
                prepend_cover_intro_frame(video_path, cover_path, output_path)


if __name__ == "__main__":
    unittest.main()
