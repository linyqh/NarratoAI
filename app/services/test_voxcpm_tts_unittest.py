import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import voice


class FakeResponse:
    def __init__(self, *, status_code=200, content=b"", payload=None):
        self.status_code = status_code
        self.content = content
        self._payload = payload or {}
        self.text = "OK"

    def json(self):
        return self._payload


class VoxCPMTtsTests(unittest.TestCase):
    def setUp(self):
        self.original_config = dict(voice.config.voxcpm_05b)
        self.original_proxy = dict(voice.config.proxy)

    def tearDown(self):
        voice.config.voxcpm_05b.clear()
        voice.config.voxcpm_05b.update(self.original_config)
        voice.config.proxy.clear()
        voice.config.proxy.update(self.original_proxy)

    def test_uploads_prompt_audio_and_downloads_generated_wav(self):
        voice.config.voxcpm_05b.clear()
        voice.config.voxcpm_05b.update({
            "api_url": "http://127.0.0.1:7864/v1/audio/speech",
            "prompt_text": "参考文本",
            "cfg_value": 2.1,
            "inference_timesteps": 12,
            "max_length": 2048,
            "normalize": True,
            "denoise": False,
        })
        voice.config.proxy.clear()

        with tempfile.TemporaryDirectory() as temp_dir:
            reference = Path(temp_dir) / "reference.wav"
            output = Path(temp_dir) / "output.wav"
            reference.write_bytes(b"reference")
            with (
                patch("app.services.voice.requests.post", return_value=FakeResponse(payload={"audio_url": "/outputs/result.wav"})) as post,
                patch("app.services.voice.requests.get", return_value=FakeResponse(content=b"wav-bytes")) as get,
                patch("app.services.voice.get_audio_duration_from_file", return_value=1.5),
            ):
                result = voice.voxcpm_tts("  测试文本。  ", f"voxcpm_05b:{reference}", str(output))

            self.assertIsNotNone(result)
            self.assertEqual(output.read_bytes(), b"wav-bytes")
            self.assertEqual(post.call_args.args[0], "http://127.0.0.1:7864/tts")
            self.assertEqual(post.call_args.kwargs["data"], {
                "text": "测试文本。", "prompt_text": "参考文本", "cfg_value": 2.1,
                "inference_timesteps": 12, "max_length": 2048,
                "normalize": "true", "denoise": "false",
            })
            self.assertIn("prompt_audio", post.call_args.kwargs["files"])
            self.assertEqual(get.call_args.args[0], "http://127.0.0.1:7864/outputs/result.wav")

    def test_default_voice_does_not_upload_audio(self):
        voice.config.voxcpm_05b.clear()
        voice.config.voxcpm_05b.update({"api_url": "http://127.0.0.1:7864"})
        voice.config.proxy.clear()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output.wav"
            with (
                patch("app.services.voice.requests.post", return_value=FakeResponse(payload={"audio_url": "/outputs/result.wav"})) as post,
                patch("app.services.voice.requests.get", return_value=FakeResponse(content=b"wav")),
                patch("app.services.voice.get_audio_duration_from_file", return_value=1.0),
            ):
                result = voice.voxcpm_tts("默认音色", "voxcpm_05b:default", str(output))
        self.assertIsNotNone(result)
        self.assertIsNone(post.call_args.kwargs["files"])


if __name__ == "__main__":
    unittest.main()
