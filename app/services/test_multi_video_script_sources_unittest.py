import json
import os
import tempfile
import unittest
from unittest import mock

from app.services import clip_video
from app.utils import check_script


class TestMultiVideoScriptSources(unittest.TestCase):
    def test_check_format_accepts_optional_video_source_fields(self):
        script = [
            {
                "_id": 1,
                "video_id": 2,
                "video_name": "2.mp4",
                "timestamp": "00:00:00,000-00:00:03,000",
                "picture": "画面",
                "narration": "解说",
                "OST": 0,
            }
        ]

        result = check_script.check_format(json.dumps(script, ensure_ascii=False))

        self.assertTrue(result["success"])

    def test_clip_video_unified_resolves_source_by_video_id_and_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_1 = os.path.join(temp_dir, "1.mp4")
            video_2 = os.path.join(temp_dir, "2.mp4")
            for video_path in [video_1, video_2]:
                with open(video_path, "wb") as file:
                    file.write(b"video")

            output_dir = os.path.join(temp_dir, "clips")
            used_sources = []

            def fake_process(source_video_path, script_item, output_dir_arg, *_args):
                used_sources.append(source_video_path)
                output_path = os.path.join(output_dir_arg, f"{script_item['_id']}.mp4")
                with open(output_path, "wb") as file:
                    file.write(b"clip")
                return output_path

            script_list = [
                {
                    "_id": 1,
                    "video_id": 2,
                    "timestamp": "00:00:00,000-00:00:03,000",
                    "picture": "视频2画面",
                    "narration": "播放原片1",
                    "OST": 1,
                },
                {
                    "_id": 2,
                    "video_name": "1.mp4",
                    "timestamp": "00:00:03,000-00:00:06,000",
                    "picture": "视频1画面",
                    "narration": "播放原片2",
                    "OST": 1,
                },
            ]

            with (
                mock.patch.object(clip_video, "check_hardware_acceleration", return_value=None),
                mock.patch.object(clip_video, "_process_original_audio_segment", side_effect=fake_process),
            ):
                result = clip_video.clip_video_unified(
                    video_origin_path=video_1,
                    video_origin_paths=[video_1, video_2],
                    script_list=script_list,
                    tts_results=[],
                    output_dir=output_dir,
                    task_id="multi-video-test",
                )

            self.assertEqual([video_2, video_1], used_sources)
            self.assertEqual({1, 2}, set(result.keys()))


if __name__ == "__main__":
    unittest.main()
