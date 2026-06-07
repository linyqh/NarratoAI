"""
OpenAI 兼容提供商实现

使用 OpenAI 官方 SDK 调用 OpenAI 兼容接口，支持文本和视觉模型。
"""

import asyncio
import io
import base64
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import PIL.Image
from loguru import logger
from openai import (
    APIError as OpenAIAPIError,
    AsyncOpenAI,
    AuthenticationError as OpenAIAuthError,
    BadRequestError as OpenAIBadRequestError,
    RateLimitError as OpenAIRateLimitError,
)

from app.config import config
from app.config.defaults import DEFAULT_LLM_GENERATION_CONFIG, normalize_openai_compatible_model_name
from .base import TextModelProvider, VisionModelProvider
from .exceptions import APICallError, AuthenticationError, ContentFilterError, RateLimitError


def _normalize_model_name(model_name: str) -> str:
    """仅剥离误保存的 openai/ 前缀，保留完整模型名称。"""
    return normalize_openai_compatible_model_name(model_name)


def _is_response_format_error(message: str) -> bool:
    return "response_format" in (message or "").lower()


def _is_content_filter_error(message: str) -> bool:
    lowered = (message or "").lower()
    return "content_filter" in lowered or "safety" in lowered


def _clean_json_output(output: str) -> str:
    """清理 JSON 输出中的 markdown 包裹。"""
    output = re.sub(r"^```json\s*", "", output, flags=re.MULTILINE)
    output = re.sub(r"^```\s*$", "", output, flags=re.MULTILINE)
    output = re.sub(r"^```.*$", "", output, flags=re.MULTILINE)
    return output.strip()


class _OpenAICompatibleBase:
    """OpenAI 兼容 provider 共享逻辑。"""

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def supported_models(self) -> List[str]:
        # 兼容网关模型数量很多，运行时校验由远端完成。
        return []

    def _validate_model_support(self):
        logger.debug(f"OpenAI 兼容模型已配置: {self.model_name}")

    def _initialize(self):
        # SDK client 按请求参数动态构建，这里无需初始化全局状态。
        pass

    def _generation_config_value(self, model_type: str, param_name: str, override: Any = None) -> Any:
        if override is not None:
            return override
        return config.app.get(
            f"{model_type}_openai_{param_name}",
            DEFAULT_LLM_GENERATION_CONFIG[param_name],
        )

    def _build_chat_completion_options(
        self,
        model_type: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Build common OpenAI-compatible generation options from config and overrides."""
        options: Dict[str, Any] = {
            "temperature": float(self._generation_config_value(model_type, "temperature", temperature)),
        }

        top_p = float(self._generation_config_value(model_type, "top_p", kwargs.get("top_p")))
        options["top_p"] = top_p

        configured_max_tokens = self._generation_config_value(model_type, "max_tokens", max_tokens)
        if configured_max_tokens is not None and int(configured_max_tokens) > 0:
            options["max_tokens"] = int(configured_max_tokens)

        extra_body: Dict[str, Any] = {}

        thinking_level = str(
            self._generation_config_value(model_type, "thinking_level", kwargs.get("thinking_level")) or "auto"
        )
        if thinking_level in {"low", "medium", "high"}:
            extra_body["reasoning_effort"] = thinking_level

        if extra_body:
            options["extra_body"] = extra_body

        return options

    def _build_client(
        self,
        api_key_override: Optional[str] = None,
        base_url_override: Optional[str] = None,
        timeout_override: Optional[float] = None,
        max_retries_override: Optional[int] = None,
    ) -> AsyncOpenAI:
        """按请求构建 AsyncOpenAI 客户端，支持动态覆盖 api_key / base_url。"""
        api_key = api_key_override or self.api_key
        base_url = base_url_override or self.base_url or None

        timeout_seconds: float = timeout_override or config.app.get("llm_text_timeout", 180)
        max_retries: int = max_retries_override or config.app.get("llm_max_retries", 3)

        return AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )


class OpenAICompatibleVisionProvider(_OpenAICompatibleBase, VisionModelProvider):
    """OpenAI 兼容视觉模型提供商。"""

    async def analyze_images(
        self,
        images: List[Union[str, Path, PIL.Image.Image]],
        prompt: str,
        batch_size: int = 10,
        max_concurrency: int = 1,
        **kwargs,
    ) -> List[str]:
        logger.info(f"开始使用 OpenAI 兼容接口 ({self.model_name}) 分析 {len(images)} 张图片")

        processed_images = self._prepare_images(images)
        if not processed_images:
            return []

        bounded_concurrency = max(1, int(max_concurrency))
        semaphore = asyncio.Semaphore(bounded_concurrency)
        batches = [
            (index // batch_size, processed_images[index : index + batch_size])
            for index in range(0, len(processed_images), batch_size)
        ]

        async def run_batch(batch_index: int, batch: List[PIL.Image.Image]) -> tuple[int, str]:
            logger.info(f"处理第 {batch_index + 1} 批，共 {len(batch)} 张图片")
            async with semaphore:
                try:
                    result = await self._analyze_batch(batch, prompt, **kwargs)
                    return batch_index, result
                except Exception as exc:
                    logger.error(f"批次 {batch_index + 1} 处理失败: {exc}")
                    return batch_index, f"批次处理失败: {exc}"

        completed = await asyncio.gather(*(run_batch(index, batch) for index, batch in batches))
        completed.sort(key=lambda item: item[0])
        return [result for _, result in completed]

    async def _analyze_batch(self, batch: List[PIL.Image.Image], prompt: str, **kwargs) -> str:
        content = [{"type": "text", "text": prompt}]
        for img in batch:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{self._image_to_base64(img)}"},
                }
            )

        messages = [{"role": "user", "content": content}]
        model_name = _normalize_model_name(self.model_name)

        client = self._build_client(
            api_key_override=kwargs.get("api_key"),
            base_url_override=kwargs.get("api_base"),
            timeout_override=config.app.get("llm_vision_timeout", 120),
        )

        try:
            generation_overrides = dict(kwargs)
            completion_options = self._build_chat_completion_options(
                "vision",
                temperature=generation_overrides.pop("temperature", None),
                max_tokens=generation_overrides.pop("max_tokens", None),
                **generation_overrides,
            )
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                **completion_options,
            )
            if response.choices and response.choices[0].message and response.choices[0].message.content:
                return response.choices[0].message.content
            raise APICallError("OpenAI 兼容接口返回空响应")
        except OpenAIAuthError as exc:
            logger.error(f"OpenAI 兼容接口认证失败: {exc}")
            raise AuthenticationError(str(exc))
        except OpenAIRateLimitError as exc:
            logger.error(f"OpenAI 兼容接口速率限制: {exc}")
            raise RateLimitError(str(exc))
        except OpenAIBadRequestError as exc:
            error_msg = str(exc)
            if _is_content_filter_error(error_msg):
                raise ContentFilterError(f"内容被安全过滤器阻止: {error_msg}")
            raise APICallError(f"请求错误: {error_msg}")
        except OpenAIAPIError as exc:
            logger.error(f"OpenAI 兼容接口 API 错误: {exc}")
            raise APICallError(f"API 错误: {exc}")
        except Exception as exc:
            logger.error(f"OpenAI 兼容接口调用失败: {exc}")
            raise APICallError(f"调用失败: {exc}")

    def _image_to_base64(self, img: PIL.Image.Image) -> str:
        img_buffer = io.BytesIO()
        img.save(img_buffer, format="JPEG", quality=85)
        return base64.b64encode(img_buffer.getvalue()).decode("utf-8")

    async def _make_api_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return payload


class OpenAICompatibleTextProvider(_OpenAICompatibleBase, TextModelProvider):
    """OpenAI 兼容文本模型提供商。"""

    def _build_text_completion_kwargs(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        response_format: Optional[str],
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        model_name = _normalize_model_name(self.model_name)
        generation_kwargs = dict(kwargs)
        temperature_override = generation_kwargs.pop("temperature", None)
        if temperature_override is None and temperature != 1.0:
            temperature_override = temperature

        completion_kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
        }
        completion_kwargs.update(
            self._build_chat_completion_options(
                "text",
                temperature=temperature_override,
                max_tokens=generation_kwargs.pop("max_tokens", max_tokens),
                **generation_kwargs,
            )
        )
        if response_format == "json":
            completion_kwargs["response_format"] = {"type": "json_object"}
        return completion_kwargs

    @staticmethod
    def _emit_stream_chunk(on_chunk, chunk_type: str, text: str):
        if not on_chunk or not text:
            return
        try:
            on_chunk({"type": chunk_type, "text": text})
        except Exception as exc:
            logger.debug(f"流式回调更新失败: {exc}")

    @staticmethod
    def _extract_reasoning_delta(delta: Any) -> str:
        if delta is None:
            return ""
        if hasattr(delta, "reasoning_content"):
            value = getattr(delta, "reasoning_content")
            if value:
                return str(value)
        if hasattr(delta, "model_dump"):
            data = delta.model_dump(exclude_none=True)
            for key in ("reasoning_content", "reasoning", "thinking"):
                value = data.get(key)
                if value:
                    return str(value)
        return ""

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,
        **kwargs,
    ) -> str:
        messages = self._build_messages(prompt, system_prompt)

        client = self._build_client(
            api_key_override=kwargs.get("api_key"),
            base_url_override=kwargs.get("api_base"),
            timeout_override=config.app.get("llm_text_timeout", 180),
        )

        completion_kwargs = self._build_text_completion_kwargs(
            messages,
            temperature,
            max_tokens,
            response_format,
            kwargs,
        )

        try:
            response = await client.chat.completions.create(**completion_kwargs)
            if response.choices and response.choices[0].message and response.choices[0].message.content:
                return response.choices[0].message.content
            raise APICallError("OpenAI 兼容接口返回空响应")

        except OpenAIBadRequestError as exc:
            error_msg = str(exc)
            # 某些网关不支持 response_format，回退到提示词约束模式
            if response_format == "json" and _is_response_format_error(error_msg):
                logger.warning("目标网关不支持 response_format，回退为提示词约束 JSON 输出")
                completion_kwargs.pop("response_format", None)
                messages[-1]["content"] += "\n\n请确保输出严格的JSON格式，不要包含任何其他文字或标记。"

                retry_response = await client.chat.completions.create(**completion_kwargs)
                if retry_response.choices and retry_response.choices[0].message and retry_response.choices[0].message.content:
                    return _clean_json_output(retry_response.choices[0].message.content)
                raise APICallError("OpenAI 兼容接口返回空响应")

            if _is_content_filter_error(error_msg):
                raise ContentFilterError(f"内容被安全过滤器阻止: {error_msg}")
            raise APICallError(f"请求错误: {error_msg}")

        except OpenAIAuthError as exc:
            logger.error(f"OpenAI 兼容接口认证失败: {exc}")
            raise AuthenticationError(str(exc))
        except OpenAIRateLimitError as exc:
            logger.error(f"OpenAI 兼容接口速率限制: {exc}")
            raise RateLimitError(str(exc))
        except OpenAIAPIError as exc:
            logger.error(f"OpenAI 兼容接口 API 错误: {exc}")
            raise APICallError(f"API 错误: {exc}")
        except Exception as exc:
            logger.error(f"OpenAI 兼容接口调用失败: {exc}")
            raise APICallError(f"调用失败: {exc}")

    async def generate_text_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,
        on_chunk=None,
        **kwargs,
    ) -> str:
        messages = self._build_messages(prompt, system_prompt)
        client = self._build_client(
            api_key_override=kwargs.get("api_key"),
            base_url_override=kwargs.get("api_base"),
            timeout_override=config.app.get("llm_text_timeout", 180),
        )
        completion_kwargs = self._build_text_completion_kwargs(
            messages,
            temperature,
            max_tokens,
            response_format,
            kwargs,
        )
        completion_kwargs["stream"] = True

        async def collect_stream() -> str:
            content_parts: List[str] = []
            stream = await client.chat.completions.create(**completion_kwargs)
            async for chunk in stream:
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                reasoning_delta = self._extract_reasoning_delta(delta)
                if reasoning_delta:
                    self._emit_stream_chunk(on_chunk, "reasoning", reasoning_delta)

                content_delta = getattr(delta, "content", None) if delta is not None else None
                if content_delta:
                    content_parts.append(content_delta)
                    self._emit_stream_chunk(on_chunk, "content", content_delta)

            result = "".join(content_parts).strip()
            if result:
                self._emit_stream_chunk(on_chunk, "done", "")
                return result
            raise APICallError("OpenAI 兼容接口返回空响应")

        try:
            return await collect_stream()

        except OpenAIBadRequestError as exc:
            error_msg = str(exc)
            if response_format == "json" and _is_response_format_error(error_msg):
                logger.warning("目标网关不支持流式 response_format，回退为提示词约束 JSON 输出")
                completion_kwargs.pop("response_format", None)
                messages[-1]["content"] += "\n\n请确保输出严格的JSON格式，不要包含任何其他文字或标记。"
                result = await collect_stream()
                return _clean_json_output(result)

            if _is_content_filter_error(error_msg):
                raise ContentFilterError(f"内容被安全过滤器阻止: {error_msg}")
            raise APICallError(f"请求错误: {error_msg}")

        except OpenAIAuthError as exc:
            logger.error(f"OpenAI 兼容接口认证失败: {exc}")
            raise AuthenticationError(str(exc))
        except OpenAIRateLimitError as exc:
            logger.error(f"OpenAI 兼容接口速率限制: {exc}")
            raise RateLimitError(str(exc))
        except OpenAIAPIError as exc:
            logger.error(f"OpenAI 兼容接口 API 错误: {exc}")
            raise APICallError(f"API 错误: {exc}")
        except Exception as exc:
            logger.error(f"OpenAI 兼容接口流式调用失败: {exc}")
            raise APICallError(f"流式调用失败: {exc}")

    async def _make_api_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return payload
