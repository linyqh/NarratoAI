import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.services import subtitle_corrector as corrector


SAMPLE_SRT = """1
00:00:01,000 --> 00:00:03,000
今天我们来看张三的顾是

2
00:00:04,000 --> 00:00:06,000
他来到北精找李四
"""


class SubtitleCorrectorTests(unittest.TestCase):
    def test_correct_srt_content_preserves_timecodes_and_rebuilds_text(self):
        llm_output = {
            "items": [
                {"id": 1, "text": "今天我们来看张三的故事"},
                {"id": 2, "text": "他来到北京找李四"},
            ]
        }

        with (
            mock.patch("app.services.subtitle_corrector._ensure_llm_providers_registered"),
            mock.patch(
                "app.services.subtitle_corrector._run_async_safely",
                return_value=json.dumps(llm_output, ensure_ascii=False),
            ) as run_llm,
        ):
            corrected = corrector.correct_srt_content(
                SAMPLE_SRT,
                provider="openai",
                api_key="sk-test",
                base_url="https://llm.example/v1",
            )

        self.assertIn("00:00:01,000 --> 00:00:03,000", corrected)
        self.assertIn("今天我们来看张三的故事", corrected)
        self.assertIn("他来到北京找李四", corrected)
        self.assertNotIn("顾是", corrected)

        call_kwargs = run_llm.call_args.kwargs
        self.assertEqual("openai", call_kwargs["provider"])
        self.assertEqual("sk-test", call_kwargs["api_key"])
        self.assertEqual("https://llm.example/v1", call_kwargs["api_base"])
        self.assertEqual("json", call_kwargs["response_format"])
        self.assertIn("多语言字幕校对员", call_kwargs["system_prompt"])
        self.assertIn("保持原语言", call_kwargs["prompt"])

    def test_correct_srt_content_rejects_missing_items(self):
        llm_output = {"items": [{"id": 1, "text": "今天我们来看张三的故事"}]}

        with (
            mock.patch("app.services.subtitle_corrector._ensure_llm_providers_registered"),
            mock.patch(
                "app.services.subtitle_corrector._run_async_safely",
                return_value=json.dumps(llm_output, ensure_ascii=False),
            ),
        ):
            with self.assertRaises(corrector.SubtitleCorrectionError):
                corrector.correct_srt_content(SAMPLE_SRT, provider="openai")

    def test_correct_subtitle_file_writes_corrected_srt(self):
        llm_output = {
            "items": [
                {"id": 1, "text": "今天我们来看张三的故事"},
                {"id": 2, "text": "他来到北京找李四"},
            ]
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "input.srt"
            output_file = Path(tmp_dir) / "output.srt"
            input_file.write_text(SAMPLE_SRT, encoding="utf-8")

            with (
                mock.patch("app.services.subtitle_corrector._ensure_llm_providers_registered"),
                mock.patch(
                    "app.services.subtitle_corrector._run_async_safely",
                    return_value=json.dumps(llm_output, ensure_ascii=False),
                ),
            ):
                result_path = corrector.correct_subtitle_file(
                    str(input_file),
                    str(output_file),
                    provider="openai",
                )

            self.assertEqual(str(output_file), result_path)
            self.assertIn("北京", output_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
