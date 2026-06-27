"""
TwelveLabs 视觉模型提供商实现

使用 TwelveLabs 官方 Python SDK 调用 Pegasus 视频理解模型。

与其它视觉提供商（OpenAI 兼容接口）不同，Pegasus 是一个原生的*视频*理解模型，
而非逐帧图像模型。为了在不改动现有调用方（关键帧批次 -> 文本描述）的前提下接入，
本提供商把每个关键帧批次用 ffmpeg 组装成一段短视频片段，上传为 TwelveLabs Asset，
再调用 Pegasus 进行分析，返回与其它视觉提供商一致的文本结果。

这是一个**可选**的视觉提供商：仅当 `vision_llm_provider = "twelvelabs"` 时才会启用，
默认行为保持不变。未配置 TwelveLabs API Key 时，整套流程与之前完全一致。
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import PIL.Image
from loguru import logger

from app.config import config
from .base import VisionModelProvider
from .exceptions import APICallError, AuthenticationError, ConfigurationError, RateLimitError

# Pegasus 对分析窗口的硬性要求：最短 4 秒。
_MIN_CLIP_SECONDS = 4
# Pegasus 1.5 同步分析对 max_tokens 的有效区间为 [512, 98304]。
_MIN_MAX_TOKENS = 512
# 本地直传 Asset 的体积上限（method="direct"，约 200MB）。关键帧拼接的短片远小于此值。
_DIRECT_UPLOAD_LIMIT_BYTES = 200 * 1024 * 1024


class TwelveLabsVisionProvider(VisionModelProvider):
    """TwelveLabs Pegasus 视频理解提供商。"""

    @property
    def provider_name(self) -> str:
        return "twelvelabs"

    @property
    def supported_models(self) -> List[str]:
        return ["pegasus1.5", "pegasus1.2"]

    def _validate_model_support(self):
        # Pegasus 模型列表稳定，保持宽松校验（与基类一致，仅记录警告）。
        if self.model_name not in self.supported_models:
            logger.warning(
                f"模型 {self.model_name} 不在 TwelveLabs 预定义列表中，"
                f"将按原样传递给 API。支持的模型: {self.supported_models}"
            )

    def _initialize(self):
        # SDK client 按请求构建，这里仅校验 ffmpeg 可用性（拼接关键帧片段需要）。
        self._ffmpeg_bin = self._resolve_ffmpeg()

    @staticmethod
    def _resolve_ffmpeg() -> str:
        configured = (config.app.get("ffmpeg_path") or "").strip()
        if configured:
            return configured
        found = shutil.which("ffmpeg")
        if not found:
            raise ConfigurationError(
                "TwelveLabs 提供商需要 ffmpeg 将关键帧拼接为视频片段，但未找到 ffmpeg。"
                "请安装 ffmpeg 或在配置中设置 ffmpeg_path。",
                "ffmpeg_path",
            )
        return found

    def _build_client(self):
        try:
            from twelvelabs import TwelveLabs
        except ImportError as exc:  # pragma: no cover - 仅在缺少可选依赖时触发
            raise ConfigurationError(
                "未安装 twelvelabs SDK。请运行 `pip install twelvelabs>=1.2.8` 后重试。",
                "twelvelabs",
            ) from exc
        return TwelveLabs(api_key=self.api_key)

    async def analyze_images(
        self,
        images: List[Union[str, Path, PIL.Image.Image]],
        prompt: str,
        batch_size: int = 10,
        max_concurrency: int = 1,
        **kwargs,
    ) -> List[str]:
        logger.info(
            f"开始使用 TwelveLabs Pegasus ({self.model_name}) 分析 {len(images)} 张关键帧"
        )

        processed_images = self._prepare_images(images)
        if not processed_images:
            return []

        bounded_concurrency = max(1, int(max_concurrency))
        semaphore = asyncio.Semaphore(bounded_concurrency)
        batches = [
            (index // batch_size, processed_images[index : index + batch_size])
            for index in range(0, len(processed_images), batch_size)
        ]

        max_tokens = self._resolve_max_tokens(kwargs.get("max_tokens"))

        async def run_batch(batch_index: int, batch: List[PIL.Image.Image]) -> tuple[int, str]:
            logger.info(f"处理第 {batch_index + 1} 批，共 {len(batch)} 张关键帧")
            async with semaphore:
                try:
                    # SDK 为同步实现，放到线程池中执行以免阻塞事件循环。
                    result = await asyncio.to_thread(
                        self._analyze_batch_sync, batch, prompt, max_tokens
                    )
                    return batch_index, result
                except Exception as exc:  # 与其它 provider 保持一致：批次级降级，不整体失败。
                    logger.error(f"批次 {batch_index + 1} 处理失败: {exc}")
                    return batch_index, f"批次处理失败: {exc}"

        completed = await asyncio.gather(
            *(run_batch(index, batch) for index, batch in batches)
        )
        completed.sort(key=lambda item: item[0])
        return [result for _, result in completed]

    def _resolve_max_tokens(self, override: Any) -> int:
        configured = override if override is not None else config.app.get(
            "vision_twelvelabs_max_tokens", 1024
        )
        try:
            value = int(configured)
        except (TypeError, ValueError):
            value = 1024
        return max(_MIN_MAX_TOKENS, value)

    def _analyze_batch_sync(
        self, batch: List[PIL.Image.Image], prompt: str, max_tokens: int
    ) -> str:
        """把一批关键帧拼成短视频，上传为 Asset，调用 Pegasus 分析后返回文本。"""
        from twelvelabs.types.video_context import VideoContext_AssetId
        from twelvelabs.errors import (
            BadRequestError,
            ForbiddenError,
            TooManyRequestsError,
        )

        client = self._build_client()
        asset_id: Optional[str] = None

        with tempfile.TemporaryDirectory(prefix="tl_pegasus_") as tmp_dir:
            clip_path = self._frames_to_clip(batch, tmp_dir)
            size = os.path.getsize(clip_path)
            if size > _DIRECT_UPLOAD_LIMIT_BYTES:
                raise APICallError(
                    f"拼接片段过大（{size} 字节），超过直传上限 {_DIRECT_UPLOAD_LIMIT_BYTES} 字节。"
                    "请减小 vision_batch_size 或降低关键帧分辨率。"
                )

            try:
                with open(clip_path, "rb") as fh:
                    asset = client.assets.create(
                        method="direct", file=fh, filename="keyframes.mp4"
                    )
                asset_id = asset.id
                self._wait_for_asset_ready(client, asset_id)

                response = client.analyze(
                    model_name=self.model_name,
                    video=VideoContext_AssetId(asset_id=asset_id),
                    prompt=prompt,
                    max_tokens=max_tokens,
                )
                text = (response.data or "").strip()
                if not text:
                    raise APICallError("TwelveLabs Pegasus 返回空响应")
                return text
            except ForbiddenError as exc:
                raise AuthenticationError(str(exc))
            except TooManyRequestsError as exc:
                raise RateLimitError(str(exc))
            except BadRequestError as exc:
                raise APICallError(f"请求错误: {getattr(exc, 'body', exc)}")
            finally:
                # 尽力清理远端 Asset，避免占用配额。
                if asset_id:
                    try:
                        client.assets.delete(asset_id=asset_id)
                    except Exception as exc:  # pragma: no cover - 清理失败不影响结果
                        logger.debug(f"清理 TwelveLabs Asset 失败 {asset_id}: {exc}")

    def _frames_to_clip(self, batch: List[PIL.Image.Image], tmp_dir: str) -> str:
        """用 ffmpeg 把关键帧序列拼成 >= 4s 的视频片段（满足 Pegasus 最短窗口要求）。"""
        frame_paths: List[str] = []
        for idx, img in enumerate(batch):
            frame_path = os.path.join(tmp_dir, f"frame_{idx:04d}.jpg")
            img.convert("RGB").save(frame_path, format="JPEG", quality=85)
            frame_paths.append(frame_path)

        # 每帧停留时长，保证总时长不少于 _MIN_CLIP_SECONDS。
        per_frame_seconds = max(1.0, _MIN_CLIP_SECONDS / max(1, len(frame_paths)))
        list_file = os.path.join(tmp_dir, "frames.txt")
        with open(list_file, "w", encoding="utf-8") as fh:
            for frame_path in frame_paths:
                fh.write(f"file '{frame_path}'\n")
                fh.write(f"duration {per_frame_seconds}\n")
            # concat demuxer 需要重复最后一帧才能让其显示完整时长。
            fh.write(f"file '{frame_paths[-1]}'\n")

        clip_path = os.path.join(tmp_dir, "clip.mp4")
        cmd = [
            self._ffmpeg_bin,
            "-y",
            "-loglevel", "error",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            # 强制偶数尺寸 + yuv420p，保证 H.264 兼容。
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-pix_fmt", "yuv420p",
            "-r", "24",
            "-c:v", "libx264",
            clip_path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        except subprocess.CalledProcessError as exc:
            raise APICallError(f"ffmpeg 拼接关键帧失败: {exc.stderr or exc}")
        except subprocess.TimeoutExpired:
            raise APICallError("ffmpeg 拼接关键帧超时")
        return clip_path

    @staticmethod
    def _wait_for_asset_ready(client, asset_id: str, timeout_seconds: int = 180) -> None:
        """轮询等待上传的 Asset 进入 ready 状态。"""
        import time

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            asset = client.assets.retrieve(asset_id=asset_id)
            status = (asset.status or "").lower()
            if status == "ready":
                return
            if status == "failed":
                raise APICallError(f"TwelveLabs Asset 处理失败: {asset_id}")
            time.sleep(3)
        raise APICallError(f"等待 TwelveLabs Asset 就绪超时: {asset_id}")

    async def _make_api_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # 本提供商直接使用官方 SDK，不走通用 payload 通道。
        return payload
