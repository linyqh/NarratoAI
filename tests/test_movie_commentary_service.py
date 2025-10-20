import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services.movie_commentary import MovieCommentaryService


class MovieCommentaryServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.video_path = Path(self.temp_dir.name) / "sample.mp4"
        self.video_path.write_bytes(b"fake video content")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_auto_generate_creates_script_and_invokes_pipeline(self):
        fake_segments = [
            {
                "timestamp": "00:00:00-00:00:05",
                "narration": "开场介绍",
                "picture": "Hero walks into frame",
                "OST": 2,
            },
            {
                "timestamp": "00:00:05-00:00:10",
                "narration": "情节展开",
                "picture": "Action intensifies",
                "OST": 2,
            },
        ]

        generator = AsyncMock()
        generator.generate_script.return_value = fake_segments
        service = MovieCommentaryService(script_generator=generator)

        voice_options = {
            "voice_name": "zh-CN-Example",
            "voice_rate": 1.1,
            "voice_pitch": 0.9,
            "tts_engine": "edge_tts",
        }
        subtitle_options = {
            "enabled": True,
            "font_name": "SimHei",
            "font_size": 42,
            "color": "#FFFFFF",
        }
        mix_options = {
            "tts_volume": 1.2,
            "original_volume": 1.0,
            "bgm_volume": 0.2,
        }

        progress_events = []

        def progress(percent, message):
            progress_events.append((percent, message))

        with patch(
            "app.services.movie_commentary.utils.script_dir",
            side_effect=lambda sub_dir="": self.temp_dir.name,
        ), patch(
            "app.services.movie_commentary.task.start_subclip_unified",
            return_value={"videos": ["/tmp/final.mp4"], "combined_videos": ["/tmp/combined.mp4"]},
        ) as mock_start:
            result = await service.generate_commentary_video(
                str(self.video_path),
                auto_generate=True,
                video_theme="史诗电影",
                custom_prompt="突出动作场面",
                frame_interval=4,
                skip_seconds=1,
                threshold=25,
                vision_batch_size=3,
                vision_provider="gemini",
                voice_options=voice_options,
                subtitle_options=subtitle_options,
                mix_options=mix_options,
                progress_callback=progress,
            )

        generator.generate_script.assert_awaited_once()
        args, kwargs = generator.generate_script.await_args
        self.assertEqual(kwargs["video_path"], str(self.video_path))
        self.assertEqual(kwargs["frame_interval_input"], 4)
        self.assertEqual(kwargs["vision_batch_size"], 3)

        script_path = Path(result["script_path"])
        self.assertTrue(script_path.exists())
        with script_path.open("r", encoding="utf-8") as fh:
            saved_script = json.load(fh)
        self.assertEqual(len(saved_script), 2)
        self.assertEqual(saved_script[0]["_id"], 1)
        self.assertEqual(saved_script[0]["timestamp"], "00:00:00,000-00:00:05,000")
        self.assertEqual(saved_script[1]["timestamp"], "00:00:05,000-00:00:10,000")

        mock_start.assert_called_once()
        _, params = mock_start.call_args[0]
        self.assertEqual(params.video_clip_json_path, str(script_path))
        self.assertEqual(params.video_origin_path, str(self.video_path))
        self.assertEqual(result["videos"], ["/tmp/final.mp4"])
        self.assertTrue(any(p for p, _ in progress_events if p >= 100))

    async def test_user_script_list_normalization(self):
        script_input = [
            {"timestamp": "0:00-0:03", "narration": "第一幕", "OST": "2"},
            {"timestamp": "00:00:03.5-00:00:06", "narration": "", "OST": 1},
        ]

        generator = AsyncMock()
        service = MovieCommentaryService(script_generator=generator)

        with patch(
            "app.services.movie_commentary.utils.script_dir",
            side_effect=lambda sub_dir="": self.temp_dir.name,
        ), patch(
            "app.services.movie_commentary.task.start_subclip_unified",
            return_value={"videos": []},
        ) as mock_start:
            result = await service.generate_commentary_video(
                str(self.video_path),
                script=script_input,
                voice_options={"tts_engine": "edge_tts"},
            )

        generator.generate_script.assert_not_called()

        script_path = Path(result["script_path"])
        with script_path.open("r", encoding="utf-8") as fh:
            saved_script = json.load(fh)

        self.assertEqual(saved_script[0]["timestamp"], "00:00:00,000-00:00:03,000")
        self.assertEqual(saved_script[0]["OST"], 2)
        self.assertEqual(saved_script[1]["timestamp"], "00:00:03,500-00:00:06,000")
        self.assertEqual(saved_script[1]["OST"], 1)
        self.assertEqual(saved_script[1]["narration"], "")
        self.assertEqual([segment["_id"] for segment in saved_script], [1, 2])

        mock_start.assert_called_once()
        _, params = mock_start.call_args[0]
        self.assertEqual(params.video_clip_json_path, str(script_path))
        self.assertEqual(params.video_origin_path, str(self.video_path))

    async def test_requires_script_when_not_auto_generating(self):
        service = MovieCommentaryService(script_generator=AsyncMock())
        with self.assertRaises(ValueError):
            await service.generate_commentary_video(
                str(self.video_path),
                auto_generate=False,
                script=None,
            )


if __name__ == "__main__":
    unittest.main()
