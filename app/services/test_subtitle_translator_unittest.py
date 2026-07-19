import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.services import subtitle_translator as translator


SAMPLE_SRT = """1
00:00:01,000 --> 00:00:03,000
Hello, everyone.

2
00:00:04,000 --> 00:00:06,000
We are going to Beijing.
"""

BATCH_SAMPLE_SRT = """1
00:00:01,000 --> 00:00:02,000
Line one.

2
00:00:02,000 --> 00:00:03,000
Line two.

3
00:00:03,000 --> 00:00:04,000
Line three.

4
00:00:04,000 --> 00:00:05,000
Line four.

5
00:00:05,000 --> 00:00:06,000
Line five.
"""


class SubtitleTranslatorTests(unittest.TestCase):
    def test_translate_srt_content_preserves_timecodes_and_rebuilds_text(self):
        llm_output = {
            "items": [
                {"id": 1, "text": "大家好。"},
                {"id": 2, "text": "我们要去北京。"},
            ]
        }

        with (
            mock.patch.dict(
                translator.config.app,
                {
                    "text_openai_model_name": "reasoning-model",
                    "text_openai_fast_model_name": "fast-subtitle-model",
                },
                clear=False,
            ),
            mock.patch("app.services.subtitle_translator._ensure_llm_providers_registered"),
            mock.patch(
                "app.services.subtitle_translator._run_async_safely",
                return_value=json.dumps(llm_output, ensure_ascii=False),
            ) as run_llm,
        ):
            translated = translator.translate_srt_content(
                SAMPLE_SRT,
                target_language="中文",
                provider="openai",
                api_key="sk-test",
                base_url="https://llm.example/v1",
            )

        self.assertIn("00:00:01,000 --> 00:00:03,000", translated)
        self.assertIn("大家好。", translated)
        self.assertIn("我们要去北京。", translated)
        self.assertNotIn("Hello, everyone.", translated)

        call_kwargs = run_llm.call_args.kwargs
        self.assertEqual("openai", call_kwargs["provider"])
        self.assertEqual("sk-test", call_kwargs["api_key"])
        self.assertEqual("https://llm.example/v1", call_kwargs["api_base"])
        self.assertEqual("fast-subtitle-model", call_kwargs["model"])
        self.assertEqual("off", call_kwargs["thinking_level"])
        self.assertEqual("json", call_kwargs["response_format"])
        self.assertIn("专业字幕翻译员", call_kwargs["system_prompt"])
        self.assertIn("翻译为中文", call_kwargs["prompt"])

    def test_translate_srt_content_rejects_missing_items(self):
        llm_output = {"items": [{"id": 1, "text": "大家好。"}]}

        with (
            mock.patch("app.services.subtitle_translator._ensure_llm_providers_registered"),
            mock.patch(
                "app.services.subtitle_translator._run_async_safely",
                return_value=json.dumps(llm_output, ensure_ascii=False),
            ),
        ):
            with self.assertRaises(translator.SubtitleTranslationError):
                translator.translate_srt_content(SAMPLE_SRT, provider="openai")

    def test_translate_subtitle_file_writes_translated_srt(self):
        llm_output = {
            "items": [
                {"id": 1, "text": "大家好。"},
                {"id": 2, "text": "我们要去北京。"},
            ]
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "input.srt"
            output_file = Path(tmp_dir) / "output.srt"
            input_file.write_text(SAMPLE_SRT, encoding="utf-8")

            with (
                mock.patch("app.services.subtitle_translator._ensure_llm_providers_registered"),
                mock.patch(
                    "app.services.subtitle_translator._run_async_safely",
                    return_value=json.dumps(llm_output, ensure_ascii=False),
                ),
            ):
                result_path = translator.translate_subtitle_file(
                    str(input_file),
                    str(output_file),
                    target_language="中文",
                    provider="openai",
                )

            self.assertEqual(str(output_file), result_path)
            self.assertIn("大家好。", output_file.read_text(encoding="utf-8"))

    def test_translate_srt_content_batches_requests_and_reports_progress(self):
        progress_events = []

        def fake_run_llm(*args, **kwargs):
            payload_text = kwargs["prompt"].rsplit("待翻译字幕条目：", 1)[1].strip()
            payload = json.loads(payload_text)
            translated = {key: f"译文{key}" for key in payload}
            return json.dumps(translated, ensure_ascii=False)

        with (
            mock.patch("app.services.subtitle_translator._ensure_llm_providers_registered"),
            mock.patch(
                "app.services.subtitle_translator._run_async_safely",
                side_effect=fake_run_llm,
            ) as run_llm,
        ):
            translated = translator.translate_srt_content(
                BATCH_SAMPLE_SRT,
                target_language="中文",
                provider="openai",
                batch_size=2,
                max_workers=1,
                progress_callback=lambda completed, total, message: progress_events.append(
                    (completed, total, message)
                ),
            )

        self.assertEqual(3, run_llm.call_count)
        self.assertIn("译文1", translated)
        self.assertIn("译文5", translated)
        self.assertEqual((0, 5), progress_events[0][:2])
        self.assertEqual((5, 5), progress_events[-1][:2])
        self.assertTrue(any("完成批次" in event[2] for event in progress_events))


if __name__ == "__main__":
    unittest.main()
