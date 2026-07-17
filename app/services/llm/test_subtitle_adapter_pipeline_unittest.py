import json
import unittest
from unittest import mock

from app.services.llm.migration_adapter import SubtitleAnalyzerAdapter
from app.services.llm.unified_service import UnifiedLLMService
from app.services.prompts import PromptManager


class SubtitleAnalyzerAdapterPipelineTests(unittest.TestCase):
    def test_generate_narration_copy_uses_plain_text_prompt_with_selected_type(self):
        adapter = SubtitleAnalyzerAdapter(
            api_key="sk-test",
            model="test-model",
            base_url="https://example.test/v1",
            provider="openai",
        )

        with mock.patch.object(adapter, "_run_async_safely", return_value="她被家人逼到绝路，反击从这一刻开始。") as call:
            result = adapter.generate_narration_copy(
                short_name="测试短剧",
                plot_analysis="女主被家人误会后反击。",
                subtitle_content="# 视频 1: 1.mp4\n00:00:01,000 --> 00:00:04,000\n女主被误会。",
                temperature=0.7,
                narration_language="简体中文（中国）",
                drama_genre="家庭伦理",
                narration_word_count=800,
            )

        self.assertEqual("success", result["status"])
        self.assertIn("反击", result["narration_copy"])
        self.assertIn("家庭伦理", call.call_args.kwargs["prompt"])
        self.assertIn("800", call.call_args.kwargs["prompt"])
        self.assertNotIn("300-650", call.call_args.kwargs["prompt"])
        self.assertNotIn("response_format", call.call_args.kwargs)

    def test_generate_narration_copy_can_use_film_tv_prompt_category(self):
        self.assertTrue(PromptManager.exists("film_tv_narration", "narration_copy"))
        adapter = SubtitleAnalyzerAdapter(
            api_key="sk-test",
            model="test-model",
            base_url="https://example.test/v1",
            provider="openai",
            prompt_category="film_tv_narration",
        )

        with mock.patch.object(adapter, "_run_async_safely", return_value="他发现证据不对，真正的凶手另有其人。") as call:
            result = adapter.generate_narration_copy(
                short_name="测试电影",
                plot_analysis="主角发现证据疑点。",
                subtitle_content="# 视频 1: 1.mp4\n00:00:01,000 --> 00:00:04,000\n证据不对。",
                temperature=0.7,
                narration_language="简体中文（中国）",
                drama_genre="悬疑/犯罪",
                narration_word_count=1200,
            )

        self.assertEqual("success", result["status"])
        self.assertIn("影视解说正文创作任务", call.call_args.kwargs["prompt"])
        self.assertIn("用户选择的影视类型", call.call_args.kwargs["prompt"])
        self.assertIn("1200", call.call_args.kwargs["prompt"])
        self.assertNotIn("350-750", call.call_args.kwargs["prompt"])
        self.assertNotIn("短剧解说正文创作任务", call.call_args.kwargs["prompt"])

    def test_film_tv_script_prompts_exclude_intro_outro_and_ads(self):
        base_parameters = {
            "drama_name": "测试电影",
            "drama_genre": "悬疑/犯罪",
            "plot_analysis": "主角发现证据疑点。",
            "subtitle_content": "# 视频 1: 1.mp4\n00:00:01,000 --> 00:00:04,000\n证据不对。",
            "narration_language": "简体中文（中国）",
        }
        prompt_parameters = {
            "segment_planning": base_parameters,
            "script_matching": {
                **base_parameters,
                "narration_copy": "他发现证据不对，真正的凶手另有其人。",
                "original_sound_ratio": 30,
            },
            "script_generation": {
                **base_parameters,
                "segment_plan": '{"segments": []}',
            },
            "script_repair": {
                **base_parameters,
                "invalid_script": '{"items": []}',
                "validation_errors": "片段包含广告",
            },
        }

        for prompt_name, parameters in prompt_parameters.items():
            with self.subTest(prompt_name=prompt_name):
                prompt = PromptManager.get_prompt(
                    category="film_tv_narration",
                    name=prompt_name,
                    parameters=parameters,
                )
                self.assertIn("片头", prompt)
                self.assertIn("片尾", prompt)
                self.assertIn("广告", prompt)
                self.assertIn("绝对不能", prompt)

    def test_match_narration_copy_to_script_uses_json_prompt_with_selected_type(self):
        adapter = SubtitleAnalyzerAdapter(
            api_key="sk-test",
            model="test-model",
            base_url="https://example.test/v1",
            provider="openai",
        )
        matched = json.dumps(
            {
                "items": [
                    {
                        "_id": 1,
                        "video_id": 1,
                        "video_name": "1.mp4",
                        "timestamp": "00:00:01,000-00:00:04,000",
                        "picture": "女主被家人误会",
                        "narration": "她被家人逼到绝路，反击从这一刻开始。",
                        "OST": 0,
                    }
                ]
            },
            ensure_ascii=False,
        )

        with mock.patch.object(adapter, "_run_async_safely", return_value=matched) as call:
            result = adapter.match_narration_copy_to_script(
                short_name="测试短剧",
                plot_analysis="女主被家人误会后反击。",
                subtitle_content="# 视频 1: 1.mp4\n00:00:01,000 --> 00:00:04,000\n女主被误会。",
                narration_copy="她被家人逼到绝路，反击从这一刻开始。",
                temperature=0.7,
                narration_language="简体中文（中国）",
                drama_genre="家庭伦理",
                original_sound_ratio=60,
            )

        self.assertEqual("success", result["status"])
        self.assertEqual(1, json.loads(result["narration_script"])["items"][0]["_id"])
        self.assertIn("家庭伦理", call.call_args.kwargs["prompt"])
        self.assertIn("60%", call.call_args.kwargs["prompt"])
        self.assertEqual("json", call.call_args.kwargs["response_format"])

    def test_match_narration_copy_to_script_uses_streaming_when_callback_exists(self):
        adapter = SubtitleAnalyzerAdapter(
            api_key="sk-test",
            model="test-model",
            base_url="https://example.test/v1",
            provider="openai",
        )
        matched = json.dumps({"items": []}, ensure_ascii=False)

        with mock.patch.object(adapter, "_run_async_safely", return_value=matched) as call:
            result = adapter.match_narration_copy_to_script(
                short_name="测试短剧",
                plot_analysis="女主被家人误会后反击。",
                subtitle_content="# 视频 1: 1.mp4",
                narration_copy="她被家人逼到绝路，反击从这一刻开始。",
                stream_callback=lambda _event: None,
            )

        self.assertEqual("success", result["status"])
        self.assertIs(UnifiedLLMService.generate_text_stream, call.call_args.args[0])
        self.assertIn("on_chunk", call.call_args.kwargs)

    def test_generate_narration_script_plans_segments_before_copywriting(self):
        adapter = SubtitleAnalyzerAdapter(
            api_key="sk-test",
            model="test-model",
            base_url="https://example.test/v1",
            provider="openai",
        )
        responses = iter(
            [
                json.dumps(
                    {
                        "segments": [
                            {
                                "_id": 1,
                                "video_id": 1,
                                "video_name": "1.mp4",
                                "timestamp": "00:00:01,000-00:00:04,000",
                                "OST": 0,
                                "intent": "开场钩子",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "items": [
                            {
                                "_id": 1,
                                "video_id": 1,
                                "video_name": "1.mp4",
                                "timestamp": "00:00:01,000-00:00:04,000",
                                "picture": "女主被误会",
                                "narration": "她被所有人误会，真正的反击却刚刚开始。",
                                "OST": 0,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            ]
        )

        with mock.patch.object(adapter, "_run_async_safely", side_effect=lambda *_args, **_kwargs: next(responses)) as call:
            result = adapter.generate_narration_script(
                short_name="测试短剧",
                plot_analysis="女主被误会后反击。",
                subtitle_content="# 视频 1: 1.mp4\n00:00:01,000 --> 00:00:04,000\n女主被误会。",
                temperature=0.7,
                narration_language="简体中文（中国）",
            )

        self.assertEqual("success", result["status"])
        self.assertEqual(2, call.call_count)
        self.assertEqual(1, json.loads(result["narration_script"])["items"][0]["_id"])

    def test_repair_narration_script_returns_repaired_json(self):
        adapter = SubtitleAnalyzerAdapter(
            api_key="sk-test",
            model="test-model",
            base_url="https://example.test/v1",
            provider="openai",
        )
        repaired = json.dumps({"items": []}, ensure_ascii=False)

        with mock.patch.object(adapter, "_run_async_safely", return_value=repaired):
            result = adapter.repair_narration_script(
                short_name="测试短剧",
                plot_analysis="",
                subtitle_content="# 视频 1: 1.mp4",
                invalid_script="{bad}",
                validation_errors="时间戳错误",
                narration_language="简体中文（中国）",
            )

        self.assertEqual("success", result["status"])
        self.assertEqual(repaired, result["narration_script"])


if __name__ == "__main__":
    unittest.main()
