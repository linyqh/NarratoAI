import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import voice


class FakeDoubaoResponse:
    status_code = 200
    text = "OK"

    def json(self):
        return {
            "code": 3000,
            "data": base64.b64encode(b"mp3-bytes").decode("ascii"),
        }


class DoubaoTtsTests(unittest.TestCase):
    def setUp(self):
        self.original_doubaotts = dict(voice.config.doubaotts)
        self.original_proxy = dict(voice.config.proxy)

    def tearDown(self):
        voice.config.doubaotts.clear()
        voice.config.doubaotts.update(self.original_doubaotts)
        voice.config.proxy.clear()
        voice.config.proxy.update(self.original_proxy)

    def test_api_key_auth_does_not_require_legacy_appid_or_token(self):
        voice.config.doubaotts.clear()
        voice.config.doubaotts.update(
            {
                "api_key": "db-api-key",
                "cluster": "volcano_tts",
                "volume": 1.2,
                "pitch": 0.9,
                "silence_duration": 0.25,
            }
        )
        voice.config.proxy.clear()
        voice.config.proxy.update({"enabled": False})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "doubao.mp3"
            sub_maker = object()

            with patch("requests.post", return_value=FakeDoubaoResponse()) as post, patch(
                "app.services.voice.new_sub_maker", return_value=sub_maker
            ):
                result = voice.doubaotts_tts(
                    text=" 你好，豆包新版鉴权。 ",
                    voice_name="BV700_V2_streaming",
                    voice_file=str(output_file),
                    speed=1.25,
                )
            output_bytes = output_file.read_bytes() if output_file.exists() else b""

        self.assertIs(result, sub_maker)
        self.assertEqual(output_bytes, b"mp3-bytes")

        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["X-Api-Key"], "db-api-key")
        self.assertNotIn("Authorization", kwargs["headers"])
        self.assertEqual(kwargs["json"]["app"], {"cluster": "volcano_tts"})
        self.assertEqual(kwargs["json"]["request"]["text"], "你好，豆包新版鉴权。")
        self.assertEqual(kwargs["json"]["audio"]["voice_type"], "BV700_V2_streaming")
        self.assertEqual(kwargs["json"]["audio"]["speed_ratio"], 1.25)
        self.assertEqual(kwargs["json"]["audio"]["volume_ratio"], 1.2)
        self.assertEqual(kwargs["json"]["audio"]["pitch_ratio"], 0.9)
        self.assertEqual(kwargs["json"]["audio"]["silence_duration"], 0.25)

    def test_legacy_token_auth_still_sends_appid_and_token(self):
        voice.config.doubaotts.clear()
        voice.config.doubaotts.update(
            {
                "appid": "legacy-appid",
                "token": "legacy-token",
                "cluster": "volcano_tts",
            }
        )
        voice.config.proxy.clear()
        voice.config.proxy.update({"enabled": False})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "doubao.mp3"

            with patch("requests.post", return_value=FakeDoubaoResponse()) as post:
                result = voice.doubaotts_tts(
                    text="旧版鉴权仍然可用",
                    voice_name="BV700_streaming",
                    voice_file=str(output_file),
                    speed=1.0,
                )
            output_bytes = output_file.read_bytes()

        self.assertIsNotNone(result)
        self.assertEqual(output_bytes, b"mp3-bytes")

        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer;legacy-token")
        self.assertNotIn("X-Api-Key", kwargs["headers"])
        self.assertEqual(
            kwargs["json"]["app"],
            {
                "appid": "legacy-appid",
                "token": "legacy-token",
                "cluster": "volcano_tts",
            },
        )


if __name__ == "__main__":
    unittest.main()
