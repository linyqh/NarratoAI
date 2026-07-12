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


class IndexTTSMacOSTtsTests(unittest.TestCase):
    def setUp(self):
        self.original_config = dict(voice.config.indextts_macos)
        self.original_proxy = dict(voice.config.proxy)

    def tearDown(self):
        voice.config.indextts_macos.clear()
        voice.config.indextts_macos.update(self.original_config)
        voice.config.proxy.clear()
        voice.config.proxy.update(self.original_proxy)

    def test_uploads_reference_audio_and_downloads_pack_output_url(self):
        voice.config.indextts_macos.clear()
        voice.config.indextts_macos.update(
            {
                "api_url": "http://127.0.0.1:7866",
                "speed": 1.1,
                "seed": 42,
                "max_mel_tokens": 800,
                "max_text_tokens_per_segment": 120,
                "interval_silence": 200,
                "temperature": 1.0,
                "top_p": 0.8,
                "top_k": 30,
                "repetition_penalty": 10.0,
                "segment_overlap_ms": 50,
            }
        )
        voice.config.proxy.clear()

        generation_response = FakeResponse(payload={"output_url": "/outputs/speech.wav"})
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
                result = voice.indextts_macos_tts(
                    text="  macOS 接口测试。  ",
                    voice_name=f"indextts_macos:{reference_audio}",
                    voice_file=str(output_file),
                )

            output_bytes = output_file.read_bytes() if output_file.exists() else b""

        self.assertIsNotNone(result)
        self.assertEqual(output_bytes, b"wav-bytes")
        self.assertEqual(
            post.call_args.args[0],
            "http://127.0.0.1:7866/v1/audio/speech/upload",
        )
        self.assertEqual(
            post.call_args.kwargs["data"],
            {
                "text": "macOS 接口测试。",
                "speed": 1.1,
                "seed": 42,
                "max_mel_tokens": 800,
                "max_text_tokens_per_segment": 120,
                "interval_silence": 200,
                "temperature": 1.0,
                "top_p": 0.8,
                "top_k": 30,
                "repetition_penalty": 10.0,
                "segment_overlap_ms": 50,
            },
        )
        self.assertIn("reference_audio", post.call_args.kwargs["files"])
        self.assertEqual(
            get.call_args.args[0],
            "http://127.0.0.1:7866/outputs/speech.wav",
        )


if __name__ == "__main__":
    unittest.main()
