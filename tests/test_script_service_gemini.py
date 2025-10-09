import unittest
from unittest.mock import patch

from app.config import config
from app.services.script_service import ScriptGenerator


class ProcessWithGeminiTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_variant_uses_openai_analyzer(self):
        generator = ScriptGenerator()
        fake_frames = [
            "/tmp/frame_000001_00:00:00,000.jpg",
            "/tmp/frame_000002_00:00:05,000.jpg",
            "/tmp/frame_000003_00:00:10,000.jpg",
        ]

        class DummyAnalyzer:
            instantiated = False

            def __init__(self, model_name, api_key, base_url):
                DummyAnalyzer.instantiated = True
                self.model_name = model_name
                self.api_key = api_key
                self.base_url = base_url

            async def analyze_images(self, images, prompt, batch_size):
                self.images = images
                self.prompt = prompt
                self.batch_size = batch_size
                return [
                    {"batch_index": 0, "response": "analysis"},
                ]

        class DummyProcessor:
            def __init__(self, *args, **kwargs):
                pass

            def process_frames(self, frame_content_list):
                return frame_content_list

        progress_events = []

        def progress_callback(progress, message):
            progress_events.append((progress, message))

        with patch.dict(
            config.app,
            {
                "vision_gemini_api_key": "test-key",
                "vision_gemini_model_name": "test-model",
                "vision_gemini_base_url": "https://vision.example.com",
                "vision_analysis_prompt": "describe",
                "text_llm_provider": "gemini",
                "text_gemini_api_key": "text-key",
                "text_gemini_model_name": "gemini-pro",
                "text_gemini_base_url": "https://text.example.com",
            },
            clear=False,
        ), patch(
            "app.services.script_service.gemini_analyzer.VisionAnalyzer",
            side_effect=AssertionError("Should not instantiate VisionAnalyzer"),
        ), patch(
            "app.utils.gemini_openai_analyzer.GeminiOpenAIAnalyzer",
            DummyAnalyzer,
        ), patch(
            "app.services.script_service.ScriptProcessor",
            DummyProcessor,
        ):
            result = await generator._process_with_gemini(
                keyframe_files=fake_frames,
                video_theme="Adventure",
                custom_prompt="",
                vision_batch_size=2,
                progress_callback=progress_callback,
                vision_provider="gemini(openai)",
            )

        self.assertTrue(DummyAnalyzer.instantiated)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["picture"], "analysis")
        self.assertGreaterEqual(len(progress_events), 3)


if __name__ == "__main__":
    unittest.main()
