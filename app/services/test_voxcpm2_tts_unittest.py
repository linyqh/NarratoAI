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


class VoxCPM2TtsTests(unittest.TestCase):
    def setUp(self):
        self.original_config = dict(voice.config.voxcpm_2b)
        self.original_proxy = dict(voice.config.proxy)

    def tearDown(self):
        voice.config.voxcpm_2b.clear()
        voice.config.voxcpm_2b.update(self.original_config)
        voice.config.proxy.clear()
        voice.config.proxy.update(self.original_proxy)

    def test_voice_design_sends_control_and_downloads_wav(self):
        voice.config.voxcpm_2b.clear()
        voice.config.voxcpm_2b.update({
            "api_url": "http://127.0.0.1:7863/v1/audio/speech",
            "mode": "design", "control": "温暖自然的年轻女声",
            "cfg_value": 2.0, "inference_timesteps": 10,
            "normalize": True, "denoise": False, "output_48k": True,
            "context_aware": True, "streaming": False,
        })
        voice.config.proxy.clear()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "output.wav"
            with (
                patch("app.services.voice.requests.post", return_value=FakeResponse(payload={"downloads": {"wav": "/download/result.wav"}})) as post,
                patch("app.services.voice.requests.get", return_value=FakeResponse(content=b"wav-2b")) as get,
                patch("app.services.voice.get_audio_duration_from_file", return_value=2.0),
            ):
                result = voice.voxcpm2_tts("  高质量旁白。 ", "voxcpm_2b:design", str(output))
            self.assertIsNotNone(result)
            self.assertEqual(output.read_bytes(), b"wav-2b")
            self.assertEqual(post.call_args.args[0], "http://127.0.0.1:7863/tts")
            self.assertIsNone(post.call_args.kwargs["files"])
            self.assertEqual(post.call_args.kwargs["data"]["control"], "温暖自然的年轻女声")
            self.assertEqual(post.call_args.kwargs["data"]["output_48k"], "true")
            self.assertEqual(get.call_args.args[0], "http://127.0.0.1:7863/download/result.wav")

    def test_clone_uploads_reference_audio(self):
        voice.config.voxcpm_2b.clear()
        voice.config.voxcpm_2b.update({
            "api_url": "http://127.0.0.1:7863/tts/batch",
            "mode": "clone", "prompt_text": "参考音频文本",
        })
        voice.config.proxy.clear()
        with tempfile.TemporaryDirectory() as temp_dir:
            reference = Path(temp_dir) / "reference.wav"
            output = Path(temp_dir) / "output.wav"
            reference.write_bytes(b"reference")
            with (
                patch("app.services.voice.requests.post", return_value=FakeResponse(payload={"downloads": {"wav": "/download/result.wav"}})) as post,
                patch("app.services.voice.requests.get", return_value=FakeResponse(content=b"wav")),
                patch("app.services.voice.get_audio_duration_from_file", return_value=1.0),
            ):
                result = voice.voxcpm2_tts("克隆测试", f"voxcpm_2b:{reference}", str(output))
        self.assertIsNotNone(result)
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:7863/tts")
        self.assertIn("reference_audio", post.call_args.kwargs["files"])
        self.assertEqual(post.call_args.kwargs["data"]["prompt_text"], "参考音频文本")


if __name__ == "__main__":
    unittest.main()
