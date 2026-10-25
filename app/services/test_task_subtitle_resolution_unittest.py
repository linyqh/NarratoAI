import tempfile
import time
import unittest
from pathlib import Path

from app.models.schema import VideoClipParams
from app.services import script_subtitle, task


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

    def test_auto_matched_subtitle_keeps_its_video_id_when_earlier_video_has_none(self):
        original_subtitle_dir = task.utils.subtitle_dir

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            first_video = temp_path / "first.mp4"
            second_video = temp_path / "second_20260829010203.mp4"
            second_subtitle = temp_path / "second_fun_asr_20260829010204.srt"
            output_file = temp_path / "script_subtitles.srt"
            second_subtitle.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\n第二个视频的原声字幕。\n",
                encoding="utf-8",
            )

            task.utils.subtitle_dir = lambda: str(temp_path)
            params = VideoClipParams(
                video_origin_paths=[str(first_video), str(second_video)],
            )

            try:
                subtitle_paths = task._get_original_subtitle_paths(params)
            finally:
                task.utils.subtitle_dir = original_subtitle_dir

            result = script_subtitle.create_script_subtitle_file(
                task_id="partial-multi-video-subtitles",
                list_script=[
                    {
                        "_id": 1,
                        "video_id": 2,
                        "video_name": second_video.name,
                        "OST": 1,
                        "sourceTimeRange": "00:00:01,000-00:00:03,000",
                        "editedTimeRange": "00:00:00-00:00:02",
                        "duration": 2,
                    }
                ],
                output_file=str(output_file),
                original_subtitle_paths=subtitle_paths,
                video_origin_paths=[str(first_video), str(second_video)],
            )
            self.assertEqual(str(output_file), result)
            content = output_file.read_text(encoding="utf-8")

        self.assertIn("第二个视频的原声字幕", content)
        self.assertEqual(["", str(second_subtitle)], subtitle_paths)


if __name__ == "__main__":
    unittest.main()
