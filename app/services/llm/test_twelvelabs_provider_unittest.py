"""TwelveLabs Pegasus 视觉 provider 的最小回归测试。

- 无网络单元测试：mock SDK 与 ffmpeg，校验 provider 把关键帧批次转成 Pegasus 文本，
  并正确执行 max_tokens 下限、批次降级与 Asset 清理。
- 可选 live 测试：仅在设置 TWELVELABS_API_KEY 时运行，验证真实 SDK 契约。
"""

import asyncio
import os
import unittest
from unittest.mock import MagicMock, patch

import PIL.Image

from app.config import config
from app.services.llm.manager import LLMServiceManager
from app.services.llm.providers import register_all_providers
from app.services.llm.twelvelabs_provider import TwelveLabsVisionProvider


def _make_provider() -> TwelveLabsVisionProvider:
    # _resolve_ffmpeg 在 _initialize 中执行，patch shutil.which 让其在无 ffmpeg 环境也可构建。
    with patch("app.services.llm.twelvelabs_provider.shutil.which", return_value="/usr/bin/ffmpeg"):
        return TwelveLabsVisionProvider(api_key="test-key", model_name="pegasus1.5")


class TwelveLabsProviderUnitTests(unittest.TestCase):
    def test_registered_as_vision_provider(self):
        LLMServiceManager._vision_providers.clear()
        LLMServiceManager._text_providers.clear()
        register_all_providers()
        self.assertIn("twelvelabs", LLMServiceManager.list_vision_providers())

    def test_resolve_max_tokens_enforces_floor(self):
        provider = _make_provider()
        # 低于 Pegasus 下限 512 时被抬到 512。
        self.assertEqual(512, provider._resolve_max_tokens(10))
        self.assertEqual(2048, provider._resolve_max_tokens(2048))

    def test_analyze_images_returns_pegasus_text(self):
        provider = _make_provider()

        # 伪造 SDK client：上传 -> ready -> analyze 返回文本。
        fake_client = MagicMock()
        fake_client.assets.create.return_value = MagicMock(id="asset-1")
        fake_client.assets.retrieve.return_value = MagicMock(status="ready")
        fake_client.analyze.return_value = MagicMock(data="A red frame fades to blue.", finish_reason="stop")

        img = PIL.Image.new("RGB", (64, 64), (200, 30, 30))

        with patch.object(provider, "_build_client", return_value=fake_client), \
             patch.object(provider, "_frames_to_clip", return_value="/tmp/clip.mp4"), \
             patch("app.services.llm.twelvelabs_provider.os.path.getsize", return_value=1234), \
             patch("builtins.open", MagicMock()):
            results = asyncio.run(provider.analyze_images(images=[img, img], prompt="describe", batch_size=10))

        self.assertEqual(["A red frame fades to blue."], results)
        fake_client.analyze.assert_called_once()
        # 调用使用配置的模型与 >=512 的 max_tokens。
        _, kwargs = fake_client.analyze.call_args
        self.assertEqual("pegasus1.5", kwargs["model_name"])
        self.assertGreaterEqual(kwargs["max_tokens"], 512)
        # 远端 Asset 被清理。
        fake_client.assets.delete.assert_called_once_with(asset_id="asset-1")

    def test_analyze_images_degrades_on_batch_error(self):
        provider = _make_provider()
        with patch.object(provider, "_analyze_batch_sync", side_effect=RuntimeError("boom")):
            img = PIL.Image.new("RGB", (64, 64), (0, 0, 0))
            results = asyncio.run(provider.analyze_images(images=[img], prompt="p", batch_size=10))
        self.assertEqual(1, len(results))
        self.assertIn("批次处理失败", results[0])


class TwelveLabsProviderLiveTests(unittest.TestCase):
    """需要真实 API Key 与 ffmpeg；未配置时跳过。"""

    @unittest.skipUnless(os.getenv("TWELVELABS_API_KEY"), "TWELVELABS_API_KEY 未设置，跳过 live 测试")
    def test_live_keyframe_analysis_returns_text(self):
        provider = TwelveLabsVisionProvider(
            api_key=os.environ["TWELVELABS_API_KEY"], model_name="pegasus1.5"
        )
        frames = [PIL.Image.new("RGB", (640, 360), c) for c in [(220, 40, 40), (40, 180, 60), (40, 80, 220)]]
        results = asyncio.run(provider.analyze_images(images=frames, prompt="Describe what is shown.", batch_size=10))
        self.assertEqual(1, len(results))
        self.assertTrue(results[0].strip())
        self.assertNotIn("批次处理失败", results[0])


if __name__ == "__main__":
    unittest.main()
