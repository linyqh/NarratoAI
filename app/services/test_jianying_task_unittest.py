import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.models.schema import VideoClipParams
from app.services import jianying_task


class JianyingTaskTests(unittest.TestCase):
    def test_normalize_indextts2_uses_valid_param_reference(self):
        with tempfile.NamedTemporaryFile(suffix=".wav") as ref:
            params = VideoClipParams(tts_engine="indextts2", voice_name=ref.name)

            jianying_task._normalize_indextts2_reference_audio(params)

            self.assertEqual(f"indextts2:{ref.name}", params.voice_name)

    def test_normalize_indextts2_uses_config_reference_when_param_is_stale(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ref_path = Path(temp_dir) / "reference.wav"
            ref_path.write_bytes(b"fake wav")
            params = VideoClipParams(tts_engine="indextts2", voice_name="zh-CN-YunjianNeural")

            with patch.dict(jianying_task.config.indextts2, {"reference_audio": str(ref_path)}, clear=False):
                jianying_task._normalize_indextts2_reference_audio(params)

            self.assertEqual(f"indextts2:{ref_path}", params.voice_name)

    def test_normalize_indextts2_requires_existing_reference_audio(self):
        params = VideoClipParams(tts_engine="indextts2", voice_name="zh-CN-YunjianNeural")

        with patch.dict(jianying_task.config.indextts2, {"reference_audio": ""}, clear=False):
            with self.assertRaisesRegex(ValueError, "IndexTTS2 参考音频不存在"):
                jianying_task._normalize_indextts2_reference_audio(params)

    def test_floor_duration_to_milliseconds(self):
        self.assertAlmostEqual(6.997, jianying_task._floor_duration_to_milliseconds(6.997333))
        self.assertAlmostEqual(7.0, jianying_task._floor_duration_to_milliseconds(7.000999))


if __name__ == "__main__":
    unittest.main()
