"""OpenAI 兼容 provider 的最小回归测试。"""

import asyncio
import unittest
from unittest.mock import patch

from app.config import config
from app.services.llm.base import TextModelProvider
from app.services.llm.exceptions import ConfigurationError
from app.services.llm.manager import LLMServiceManager
from app.services.llm.migration_adapter import LegacyLLMAdapter, VisionAnalyzerAdapter
from app.services.llm.openai_compatible_provider import (
    OpenAICompatibleTextProvider,
    OpenAICompatibleVisionProvider,
    is_trusted_openai_compatible_base_url,
    validate_openai_compatible_base_url,
)
from app.services.llm.providers import register_all_providers
from app.utils.openai_base_url_security import openai_compatible_base_url_warning


class DummyOpenAITextProvider(TextModelProvider):
    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def supported_models(self) -> list[str]:
        return []

    async def generate_text(self, prompt: str, **kwargs) -> str:
        return prompt

    async def _make_api_call(self, payload: dict) -> dict:
        return payload


def _reset_manager_state():
    LLMServiceManager._vision_providers.clear()
    LLMServiceManager._text_providers.clear()
    LLMServiceManager._vision_instance_cache.clear()
    LLMServiceManager._text_instance_cache.clear()


class OpenAICompatManagerTests(unittest.TestCase):
    def setUp(self):
        _reset_manager_state()
        self._original_app = dict(config.app)

    def tearDown(self):
        _reset_manager_state()
        config.app.clear()
        config.app.update(self._original_app)

    def test_register_all_providers_registers_expected_providers(self):
        register_all_providers()

        # 文本仅 OpenAI 兼容；视觉额外提供可选的 TwelveLabs Pegasus。
        self.assertEqual({"openai"}, set(LLMServiceManager.list_text_providers()))
        self.assertEqual({"openai", "twelvelabs"}, set(LLMServiceManager.list_vision_providers()))

    def test_get_text_provider_uses_openai_keys(self):
        LLMServiceManager.register_text_provider("openai", DummyOpenAITextProvider)

        config.app["text_llm_provider"] = "openai"
        config.app["text_openai_api_key"] = "new-key"
        config.app["text_openai_model_name"] = "new-model"
        config.app["text_openai_base_url"] = "https://new.example/v1"

        provider = LLMServiceManager.get_text_provider()

        self.assertIsInstance(provider, DummyOpenAITextProvider)
        self.assertEqual("new-key", provider.api_key)
        self.assertEqual("new-model", provider.model_name)
        self.assertEqual("https://new.example/v1", provider.base_url)


class OpenAICompatVisionConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_analyze_images_keeps_batch_order_when_running_concurrently(self):
        provider = OpenAICompatibleVisionProvider(api_key="k", model_name="m")
        provider._prepare_images = lambda images: list(images)

        async def fake_analyze_batch(batch, prompt, **kwargs):
            delays = {"a": 0.03, "c": 0.01, "e": 0.0}
            await asyncio.sleep(delays[batch[0]])
            return f"batch-{batch[0]}"

        provider._analyze_batch = fake_analyze_batch

        result = await provider.analyze_images(
            images=["a", "b", "c", "d", "e", "f"],
            prompt="prompt",
            batch_size=2,
            max_concurrency=2,
        )

        self.assertEqual(["batch-a", "batch-c", "batch-e"], result)

    async def test_analyze_images_respects_max_concurrency_limit(self):
        provider = OpenAICompatibleVisionProvider(api_key="k", model_name="m")
        provider._prepare_images = lambda images: list(images)

        in_flight = 0
        max_in_flight = 0

        async def fake_analyze_batch(batch, prompt, **kwargs):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1
            return f"batch-{batch[0]}"

        provider._analyze_batch = fake_analyze_batch

        result = await provider.analyze_images(
            images=["a", "b", "c", "d", "e", "f"],
            prompt="prompt",
            batch_size=1,
            max_concurrency=2,
        )

        self.assertEqual(6, len(result))
        self.assertEqual(2, max_in_flight)


class OpenAICompatGenerationOptionTests(unittest.TestCase):
    def setUp(self):
        self._original_app = dict(config.app)

    def tearDown(self):
        config.app.clear()
        config.app.update(self._original_app)

    def test_build_options_uses_generation_defaults(self):
        provider = OpenAICompatibleTextProvider(api_key="k", model_name="m")
        for key in (
            "text_openai_temperature",
            "text_openai_top_p",
            "text_openai_max_tokens",
            "text_openai_thinking_level",
        ):
            config.app.pop(key, None)

        options = provider._build_chat_completion_options("text")

        self.assertEqual(1.0, options["temperature"])
        self.assertEqual(0.95, options["top_p"])
        self.assertEqual(65536, options["max_tokens"])
        self.assertNotIn("extra_body", options)

    def test_build_options_uses_per_model_generation_config(self):
        provider = OpenAICompatibleTextProvider(api_key="k", model_name="m")
        config.app.update(
            {
                "text_openai_temperature": 0.3,
                "text_openai_top_p": 0.8,
                "text_openai_max_tokens": 2048,
                "text_openai_thinking_level": "high",
            }
        )

        options = provider._build_chat_completion_options("text")

        self.assertEqual(0.3, options["temperature"])
        self.assertEqual(0.8, options["top_p"])
        self.assertEqual(2048, options["max_tokens"])
        self.assertEqual({"reasoning_effort": "high"}, options["extra_body"])

    def test_explicit_generation_options_override_config(self):
        provider = OpenAICompatibleTextProvider(api_key="k", model_name="m")
        config.app["text_openai_temperature"] = 0.3

        options = provider._build_chat_completion_options("text", temperature=0.9, max_tokens=512)

        self.assertEqual(0.9, options["temperature"])
        self.assertEqual(512, options["max_tokens"])


class OpenAICompatBaseURLValidationTests(unittest.TestCase):
    def setUp(self):
        self._original_app = dict(config.app)

    def tearDown(self):
        config.app.clear()
        config.app.update(self._original_app)

    def test_known_providers_and_local_ollama_are_trusted(self):
        trusted_urls = [
            "https://api.openai.com/v1",
            "https://api.siliconflow.cn/v1",
            "https://openrouter.ai/api/v1",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "https://example.openai.azure.com/openai/deployments/demo",
            "http://localhost:11434/v1",
            "http://127.0.0.1:11434/v1",
        ]

        for url in trusted_urls:
            with self.subTest(url=url):
                self.assertTrue(is_trusted_openai_compatible_base_url(url))

    def test_unrecognized_or_unsafe_base_urls_are_not_trusted(self):
        untrusted_urls = [
            "https://attacker.example/v1",
            "http://api.openai.com/v1",
            "https://user@api.openai.com/v1",
            "https://127.0.0.1:9999/v1",
            "not-a-url",
        ]

        for url in untrusted_urls:
            with self.subTest(url=url):
                self.assertFalse(is_trusted_openai_compatible_base_url(url))

    def test_build_client_allows_well_formed_custom_base_url_by_default(self):
        provider = OpenAICompatibleTextProvider(
            api_key="test-key",
            model_name="test-model",
            base_url="https://custom.example/v1",
        )

        with patch("app.services.llm.openai_compatible_provider.AsyncOpenAI") as async_openai:
            provider._build_client()

        self.assertEqual("https://custom.example/v1", async_openai.call_args.kwargs["base_url"])

    def test_custom_base_url_validation_returns_normalized_url(self):
        self.assertEqual(
            "https://custom.example/v1",
            validate_openai_compatible_base_url(" https://custom.example/v1 "),
        )

    def test_custom_base_url_warning_only_for_untrusted_well_formed_urls(self):
        warning = openai_compatible_base_url_warning("https://custom.example/v1")
        self.assertIn("custom.example", warning)
        self.assertEqual("", openai_compatible_base_url_warning("https://api.openai.com/v1"))
        self.assertEqual("", openai_compatible_base_url_warning(""))

    def test_custom_base_url_validation_rejects_malformed_urls(self):
        provider = OpenAICompatibleTextProvider(
            api_key="test-key",
            model_name="test-model",
            base_url="https://user@custom.example/v1",
        )

        with self.assertRaises(ConfigurationError):
            provider._build_client()


class ExplicitVisionAdapterSettingsTests(unittest.IsolatedAsyncioTestCase):
    class _CapturingVisionProvider:
        last_init: tuple[str, str, str | None] | None = None
        last_call_kwargs: dict | None = None

        def __init__(self, api_key: str, model_name: str, base_url: str | None = None):
            self.api_key = api_key
            self.model_name = model_name
            self.base_url = base_url
            ExplicitVisionAdapterSettingsTests._CapturingVisionProvider.last_init = (api_key, model_name, base_url)

        async def analyze_images(self, images, prompt, batch_size=10, max_concurrency=1, **kwargs):
            ExplicitVisionAdapterSettingsTests._CapturingVisionProvider.last_call_kwargs = dict(kwargs)
            return [f"{self.model_name}|{self.api_key}|{self.base_url}"]

    def setUp(self):
        _reset_manager_state()
        self._original_app = dict(config.app)

    def tearDown(self):
        _reset_manager_state()
        config.app.clear()
        config.app.update(self._original_app)

    async def test_adapter_uses_explicit_settings_instead_of_global_config(self):
        LLMServiceManager.register_vision_provider("openai", self._CapturingVisionProvider)
        config.app["vision_openai_api_key"] = "config-key"
        config.app["vision_openai_model_name"] = "config-model"
        config.app["vision_openai_base_url"] = "https://config.example/v1"

        adapter = VisionAnalyzerAdapter(
            provider="openai",
            api_key="explicit-key",
            model="explicit-model",
            base_url="https://explicit.example/v1",
        )
        result = await adapter.analyze_images(
            images=["/tmp/keyframe_000001_000000100.jpg"],
            prompt="描述画面",
            batch_size=1,
            max_concurrency=1,
        )

        self.assertEqual(
            ("explicit-key", "explicit-model", "https://explicit.example/v1"),
            self._CapturingVisionProvider.last_init,
        )
        self.assertEqual("explicit-key", self._CapturingVisionProvider.last_call_kwargs["api_key"])
        self.assertEqual("https://explicit.example/v1", self._CapturingVisionProvider.last_call_kwargs["api_base"])
        self.assertEqual("explicit-model|explicit-key|https://explicit.example/v1", result[0]["response"])


class LegacyNarrationAdapterBehaviorTests(unittest.TestCase):
    def test_generate_narration_returns_raw_unrecoverable_payload_without_fabrication(self):
        raw_payload = "not-json-at-all ::: ???"

        with patch(
            "app.services.llm.migration_adapter.PromptManager.get_prompt",
            return_value="prompt",
        ), patch(
            "app.services.llm.migration_adapter._run_async_safely",
            return_value=raw_payload,
        ):
            result = LegacyLLMAdapter.generate_narration(
                markdown_content="markdown",
                api_key="test-key",
                base_url="https://example.com/v1",
                model="test-model",
            )

        self.assertEqual(raw_payload, result)
        self.assertNotIn('"items"', result)


if __name__ == "__main__":
    unittest.main()
