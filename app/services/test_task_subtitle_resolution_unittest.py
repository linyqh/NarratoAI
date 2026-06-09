import tempfile
import time
import unittest
from pathlib import Path

from app.models.schema import VideoClipParams
from app.services import task


class TaskSubtitleResolutionTests(unittest.TestCase):
    def test_get_original_subtitle_paths_falls_back_to_matching_video_name(self):
        original_subtitle_dir = task.utils.subtitle_dir

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            older = temp_path / "01_1080p_fun_asr.srt"
            newer = temp_path / "01_1080p_fun_asr_20260608010240.srt"
            unrelated = temp_path / "other_fun_asr.srt"
            older.write_text("older", encoding="utf-8")
            unrelated.write_text("other", encoding="utf-8")
            time.sleep(0.01)
            newer.write_text("newer", encoding="utf-8")

            task.utils.subtitle_dir = lambda: str(temp_path)
            params = VideoClipParams(
                video_origin_path="/tmp/01_1080p_20260608113314.mp4",
            )

            try:
                subtitle_paths = task._get_original_subtitle_paths(params)
            finally:
                task.utils.subtitle_dir = original_subtitle_dir

        self.assertEqual([str(newer)], subtitle_paths)

    def test_get_original_subtitle_paths_keeps_explicit_params(self):
        params = VideoClipParams(
            video_origin_path="/tmp/01_1080p_20260608113314.mp4",
            original_subtitle_paths=["/tmp/provided.srt"],
        )

        self.assertEqual(["/tmp/provided.srt"], task._get_original_subtitle_paths(params))


if __name__ == "__main__":
    unittest.main()
