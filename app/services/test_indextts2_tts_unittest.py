import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import voice


class FakeResponse:
    def __init__(self, *, status_code=200, content=b"", payload=None, content_type="application/json"):
        self.status_code = status_code
        self.content = content
        self._payload = payload or {}
        self.headers = {"content-type": content_type}
        self.text = "OK"

    def json(self):
        return self._payload


class IndexTTS2TtsTests(unittest.TestCase):
    def setUp(self):
        self.original_indextts2 = dict(voice.config.indextts2)
        self.original_proxy = dict(voice.config.proxy)

    def tearDown(self):
        voice.config.indextts2.clear()
        voice.config.indextts2.update(self.original_indextts2)
        voice.config.proxy.clear()
        voice.config.proxy.update(self.original_proxy)

    def test_uploads_reference_audio_and_downloads_pack_output_url(self):
        voice.config.indextts2.clear()
        voice.config.indextts2.update(
            {
                "api_url": "http://127.0.0.1:7860",
                "emotion": "happy:0.7,calm:0.3",
                "emo_alpha": 0.6,
                "speed": 1.15,
                "seed": 20260713,
                "max_mel_tokens": 1500,
                "max_text_tokens_per_segment": 120,
                "interval_silence": 200,
                "temperature": 0.8,
                "top_p": 0.8,
                "top_k": 30,
                "repetition_penalty": 10.0,
                "diffusion_steps": 25,
                "cfg_rate": 0.7,
                "segment_overlap_ms": 50,
            }
        )
        voice.config.proxy.clear()

        generation_response = FakeResponse(
            payload={"output": {"url": "/outputs/audio/speech.wav"}}
        )
        download_response = FakeResponse(content=b"wav-bytes", content_type="audio/wav")

        with tempfile.TemporaryDirectory() as temp_dir:
            reference_audio = Path(temp_dir) / "reference.wav"
            output_file = Path(temp_dir) / "output.wav"
            reference_audio.write_bytes(b"reference-wav")

            with (
                patch("app.services.voice.requests.post", return_value=generation_response) as post,
                patch("app.services.voice.requests.get", return_value=download_response) as get,
                patch("app.services.voice.get_audio_duration_from_file", return_value=1.25),
            ):
                result = voice.indextts2_tts(
                    text="  新版接口测试。  ",
                    voice_name=f"indextts2:{reference_audio}",
                    voice_file=str(output_file),
                )

            output_bytes = output_file.read_bytes() if output_file.exists() else b""

        self.assertIsNotNone(result)
        self.assertEqual(output_bytes, b"wav-bytes")
        self.assertEqual(
            post.call_args.args[0],
            "http://127.0.0.1:7860/v1/audio/speech/upload",
        )
        self.assertEqual(
            post.call_args.kwargs["data"],
            {
                "text": "新版接口测试。",
                "emotion": "happy:0.7,calm:0.3",
                "emo_alpha": 0.6,
                "speed": 1.15,
                "seed": 20260713,
                "max_mel_tokens": 1500,
                "max_text_tokens_per_segment": 120,
                "interval_silence": 200,
                "temperature": 0.8,
                "top_p": 0.8,
                "top_k": 30,
                "repetition_penalty": 10.0,
                "diffusion_steps": 25,
                "cfg_rate": 0.7,
                "segment_overlap_ms": 50,
            },
        )
        self.assertIn("reference_audio", post.call_args.kwargs["files"])
        self.assertEqual(
            get.call_args.args[0],
            "http://127.0.0.1:7860/outputs/audio/speech.wav",
        )

    def test_maps_legacy_vector_settings_to_pack_emotion_and_endpoint(self):
        voice.config.indextts2.clear()
        voice.config.indextts2.update(
            {
                "api_url": "http://127.0.0.1:7860/tts",
                "emotion_mode": "vector",
                "emotion_alpha": 0.65,
                "vec_happy": 0.3,
                "vec_calm": 0.7,
            }
        )
        voice.config.proxy.clear()

        generation_response = FakeResponse(content=b"wav-bytes", content_type="audio/wav")

        with tempfile.TemporaryDirectory() as temp_dir:
            reference_audio = Path(temp_dir) / "reference.wav"
            output_file = Path(temp_dir) / "output.wav"
            reference_audio.write_bytes(b"reference-wav")

            with (
                patch("app.services.voice.requests.post", return_value=generation_response) as post,
                patch("app.services.voice.get_audio_duration_from_file", return_value=1.0),
            ):
                result = voice.indextts2_tts(
                    text="旧配置兼容测试。",
                    voice_name=f"indextts2:{reference_audio}",
                    voice_file=str(output_file),
                )

        self.assertIsNotNone(result)
        self.assertEqual(
            post.call_args.args[0],
            "http://127.0.0.1:7860/v1/audio/speech/upload",
        )
        self.assertEqual(post.call_args.kwargs["data"]["emotion"], "happy:0.3,calm:0.7")
        self.assertEqual(post.call_args.kwargs["data"]["emo_alpha"], 0.65)
        self.assertNotIn("emotion_mode", post.call_args.kwargs["data"])
        self.assertNotIn("vec_happy", post.call_args.kwargs["data"])

    def test_normalizes_saved_values_to_pack_request_ranges(self):
        voice.config.indextts2.clear()
        voice.config.indextts2.update(
            {
                "api_url": "http://127.0.0.1:7860",
                "emo_alpha": 2.0,
                "speed": 0.1,
                "max_mel_tokens": 50,
                "max_text_tokens_per_segment": 1,
                "interval_silence": -10,
                "temperature": 0.0,
                "top_p": 0.0,
                "top_k": 0,
                "repetition_penalty": 0.1,
                "diffusion_steps": 0,
                "cfg_rate": -1.0,
                "segment_overlap_ms": -5,
                "seed": "not-an-integer",
            }
        )
        voice.config.proxy.clear()

        generation_response = FakeResponse(content=b"wav-bytes", content_type="audio/wav")

        with tempfile.TemporaryDirectory() as temp_dir:
            reference_audio = Path(temp_dir) / "reference.wav"
            output_file = Path(temp_dir) / "output.wav"
            reference_audio.write_bytes(b"reference-wav")

            with (
                patch("app.services.voice.requests.post", return_value=generation_response) as post,
                patch("app.services.voice.get_audio_duration_from_file", return_value=1.0),
            ):
                result = voice.indextts2_tts(
                    text="参数范围测试。",
                    voice_name=f"indextts2:{reference_audio}",
                    voice_file=str(output_file),
                )

        self.assertIsNotNone(result)
        self.assertEqual(
            post.call_args.kwargs["data"],
            {
                "text": "参数范围测试。",
                "emo_alpha": 1.0,
                "speed": 0.5,
                "max_mel_tokens": 64,
                "max_text_tokens_per_segment": 20,
                "interval_silence": 0,
                "temperature": 0.05,
                "top_p": 0.05,
                "top_k": 1,
                "repetition_penalty": 1.0,
                "diffusion_steps": 1,
                "cfg_rate": 0.0,
                "segment_overlap_ms": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
