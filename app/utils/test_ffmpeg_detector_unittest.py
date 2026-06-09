import os
import tempfile
import unittest
from pathlib import Path

from app.utils import ffmpeg_detector


class FFmpegDetectorTests(unittest.TestCase):
    def _write_fake_binary(self, path: Path, first_line: str) -> None:
        path.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"-version\" ]; then\n"
            f"  echo \"{first_line}\"\n"
            "  exit 0\n"
            "fi\n"
            "if [ \"$2\" = \"-hwaccels\" ]; then\n"
            "  echo \"Hardware acceleration methods:\"\n"
            "  echo \"videotoolbox\"\n"
            "  exit 0\n"
            "fi\n"
            "if [ \"$2\" = \"-encoders\" ]; then\n"
            "  echo \" V....D h264_videotoolbox Apple VideoToolbox H.264\"\n"
            "  echo \" V....D h264_nvenc NVIDIA NVENC H.264\"\n"
            "  echo \" V....D h264_qsv Intel QSV H.264\"\n"
            "  echo \" V....D libx264 libx264 H.264\"\n"
            "  exit 0\n"
            "fi\n"
            "if [ \"$2\" = \"-filters\" ]; then\n"
            "  echo \" ... subtitles V->V Render text subtitles\"\n"
            "  echo \" ... drawtext V->V Draw text\"\n"
            "  echo \" ... overlay VV->V Overlay video\"\n"
            "  exit 0\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        path.chmod(0o755)

    @unittest.skipIf(os.name == "nt", "shell fake binaries are POSIX-only")
    def test_discover_includes_configured_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ffmpeg_path = Path(tmp_dir) / "ffmpeg"
            ffprobe_path = Path(tmp_dir) / "ffprobe"
            self._write_fake_binary(ffmpeg_path, "ffmpeg version fake-1.0")
            self._write_fake_binary(ffprobe_path, "ffprobe version fake-1.0")

            engines = ffmpeg_detector.discover_ffmpeg_engines(
                configured_path=str(ffmpeg_path),
                root_dir=tmp_dir,
                include_system=False,
            )

            self.assertEqual(engines[0]["path"], str(ffmpeg_path.resolve()))
            self.assertEqual(engines[0]["ffprobe_path"], str(ffprobe_path.resolve()))
            self.assertTrue(engines[0]["available"])

    @unittest.skipIf(os.name == "nt", "shell fake binaries are POSIX-only")
    def test_validate_reports_hardware_and_subtitle_support(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ffmpeg_path = Path(tmp_dir) / "ffmpeg"
            ffprobe_path = Path(tmp_dir) / "ffprobe"
            self._write_fake_binary(ffmpeg_path, "ffmpeg version fake-1.0")
            self._write_fake_binary(ffprobe_path, "ffprobe version fake-1.0")

            report = ffmpeg_detector.validate_ffmpeg_engine(str(ffmpeg_path))

            self.assertTrue(report["ffmpeg_available"])
            self.assertTrue(report["ffprobe_available"])
            self.assertTrue(report["hardware_acceleration"]["available"])
            self.assertTrue(report["subtitle_burn"]["available"])
            self.assertEqual(report["subtitle_burn"]["method"], "subtitles")


if __name__ == "__main__":
    unittest.main()
