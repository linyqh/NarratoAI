import tempfile
import unittest
from pathlib import Path

from app.services import script_subtitle


class ScriptSubtitleTests(unittest.TestCase):
    def test_split_narration_prefers_punctuation_boundaries(self):
        chunks = script_subtitle.split_narration(
            "她终于意识到，这场婚姻不是爱情，而是一场交易。",
            max_chars=12,
        )

        self.assertEqual(
            ["她终于意识到", "这场婚姻不是爱情", "而是一场交易"],
            chunks,
        )

    def test_time_range_parsing_supports_milliseconds(self):
        start, end = script_subtitle.parse_time_range("00:00:01,500-00:00:03,250")

        self.assertAlmostEqual(1.5, start)
        self.assertAlmostEqual(3.25, end)

    def test_create_script_subtitle_file_skips_original_audio_segments(self):
        list_script = [
            {
                "_id": 1,
                "OST": 0,
                "narration": "第一句解说。第二句解说。",
                "editedTimeRange": "00:00:00-00:00:04",
                "duration": 4,
            },
            {
                "_id": 2,
                "OST": 1,
                "narration": "这句是原声，不应该默认生成。",
                "editedTimeRange": "00:00:04-00:00:08",
                "duration": 4,
            },
            {
                "_id": 3,
                "OST": 2,
                "narration": "混合片段也保留解说字幕。",
                "editedTimeRange": "00:00:08-00:00:12",
                "duration": 4,
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "script_subtitles.srt"
            result = script_subtitle.create_script_subtitle_file(
                task_id="test",
                list_script=list_script,
                output_file=str(output_file),
                max_chars=16,
            )

            self.assertEqual(str(output_file), result)
            content = output_file.read_text(encoding="utf-8")

        self.assertIn("00:00:00,000 -->", content)
        self.assertIn("第一句解说", content)
        self.assertIn("混合片段也保留解说字幕", content)
        self.assertNotIn("这句是原声", content)
        self.assertNotIn("。", content)
        self.assertNotIn("，", content)

    def test_create_script_subtitle_file_uses_duration_when_edited_range_missing(self):
        list_script = [
            {
                "_id": 1,
                "OST": 0,
                "narration": "没有 editedTimeRange 时使用 duration。",
                "duration": 3,
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "script_subtitles.srt"
            script_subtitle.create_script_subtitle_file(
                task_id="test",
                list_script=list_script,
                output_file=str(output_file),
            )
            content = output_file.read_text(encoding="utf-8")

        self.assertIn("00:00:00,000 -->", content)
        self.assertIn("--> 00:00:03,000", content)


if __name__ == "__main__":
    unittest.main()
