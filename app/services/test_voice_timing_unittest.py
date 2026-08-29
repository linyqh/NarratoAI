"""Regression tests for TTS-driven video timing."""

import unittest
from unittest.mock import patch

from app.services import voice


class TtsTimingTests(unittest.TestCase):
    def test_tts_multiple_uses_actual_audio_duration_for_edge_tts(self):
        item = {
            "_id": 1,
            "timestamp": "00:00:00,000-00:00:03,000",
            "narration": "一段配音文本",
            "OST": 0,
        }

        with (
            patch.object(voice.config, "normalize_tts_engine_name", return_value="edge_tts"),
            patch.object(voice.config, "normalize_indextts_voice_prefix", side_effect=lambda value: value),
            patch.object(voice.utils, "task_dir", return_value="task-dir"),
            patch.object(voice, "tts", return_value=object()),
            patch.object(voice, "create_subtitle", return_value=("subtitle.srt", 3.0)),
            patch.object(voice, "get_audio_duration_from_file", return_value=4.5),
        ):
            results = voice.tts_multiple(
                task_id="task-id",
                list_script=[item],
                voice_name="zh-CN-YunjianNeural-Male",
                voice_rate=1.0,
                voice_pitch=0.0,
                tts_engine="edge_tts",
            )

        self.assertEqual(4.5, results[0]["duration"])

