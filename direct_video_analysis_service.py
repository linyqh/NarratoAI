"""
直接上传整段影片给「官方原生大模型」一次性分析的服务。

支持两种官方 provider：
  - gemini: 使用 google-generativeai 的 Files API 上传 → Gemini 模型分析
  - qwen:   使用 DashScope MultiModalConversation 上传本地视频 → Qwen-VL 模型分析

输出格式与抽帧链路保持一致（list[dict]，含 timestamp/picture/narration/OST），
方便 WebUI 与下游剪辑流程透明地复用。
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Any, Callable

from loguru import logger

from app.config import config
from app.config.defaults import (
    DEFAULT_DIRECT_VIDEO_GEMINI_MODEL_NAME,
    DEFAULT_DIRECT_VIDEO_PROVIDER,
    DEFAULT_DIRECT_VIDEO_QWEN_MODEL_NAME,
    DIRECT_VIDEO_PROVIDER_GEMINI,
    DIRECT_VIDEO_PROVIDER_QWEN,
)
from app.utils import utils


# 主 Prompt：用中性的「视频内容描述与配音稿」措辞，避免 Google 内部分类过滤误判（block_reason=OTHER）
_DEFAULT_PROMPT = """
请对这段视频进行内容描述并撰写中文配音稿。

任务步骤：
1. 按时间顺序将视频分为若干连续片段，每段约 4-12 秒。
2. 为每个片段提供：
   - timestamp：格式 "HH:MM:SS,mmm-HH:MM:SS,mmm"，毫秒补零至 3 位，对应视频真实时间。
   - picture：客观陈述该片段画面中的主要内容（场景、人物、动作）。
   - narration：根据画面写一句中文配音稿，约 15~25 字，自然口语化。
3. 仅基于视频实际内容撰写，不添加视频中未出现的内容。

${context_block}

输出格式（仅返回 JSON，不要任何额外文字或代码块标记）：
{
  "items": [
    {
      "_id": 1,
      "timestamp": "00:00:00,000-00:00:05,000",
      "picture": "画面内容",
      "narration": "中文配音稿"
    }
  ]
}
""".strip()


# 极简 Fallback Prompt：当主 Prompt 触发 block_reason=OTHER 时退化使用
_FALLBACK_PROMPT = """
请观看视频并以 JSON 输出每个片段的描述与对应中文配音稿。

每个片段包含：
- timestamp: "HH:MM:SS,mmm-HH:MM:SS,mmm" 时间区间
- picture: 画面内容描述
- narration: 一句中文配音稿（15-25 字）

每段时长 4-12 秒，按视频时间顺序排列。仅输出如下 JSON：

{"items":[{"_id":1,"timestamp":"00:00:00,000-00:00:05,000","picture":"...","narration":"..."}]}
""".strip()



# Gemini File API 上传后处理状态轮询
_GEMINI_POLL_INTERVAL_SECONDS = 3
_GEMINI_MAX_PROCESS_WAIT_SECONDS = 600  # 10 分钟

# Gemini generate_content 遇到可恢复错误时的指数退避重试参数
_GEMINI_GENERATE_RETRY_ATTEMPTS = 5
_GEMINI_GENERATE_RETRY_BASE_DELAY = 5  # 秒
# 视为「可重试」的 HTTP 状态码（503 服务超载、429 限流、500 内部错误）
_GEMINI_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}



class DirectVideoAnalysisService:
    """通过 Gemini / Qwen-VL 官方 API 上传完整视频生成解说脚本。

    采用同步 API 设计：直接在调用方所在线程中阻塞执行，便于 progress_callback
    在 Streamlit 主线程中安全地更新 UI 元素。
    """

    def generate_script(
        self,
        *,
        video_path: str,
        video_theme: str = "",
        custom_prompt: str = "",
        provider: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> list[dict[str, Any]]:
        progress = progress_callback or (lambda _p, _m: None)

        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        provider = (provider or config.app.get("direct_video_provider") or DEFAULT_DIRECT_VIDEO_PROVIDER).lower()
        if provider not in (DIRECT_VIDEO_PROVIDER_GEMINI, DIRECT_VIDEO_PROVIDER_QWEN):
            raise ValueError(
                f"未知的 direct_video_provider: {provider}，仅支持: {DIRECT_VIDEO_PROVIDER_GEMINI} / {DIRECT_VIDEO_PROVIDER_QWEN}"
            )

        api_key, model_name = self._resolve_credentials(provider, api_key, model_name)

        prompt = self._build_prompt(video_theme=video_theme, custom_prompt=custom_prompt)

        if provider == DIRECT_VIDEO_PROVIDER_GEMINI:
            raw_text = self._run_gemini(
                video_path=video_path,
                prompt=prompt,
                api_key=api_key,
                model_name=model_name,
                progress=progress,
            )
        else:
            raw_text = self._run_qwen(
                video_path=video_path,
                prompt=prompt,
                api_key=api_key,
                model_name=model_name,
                progress=progress,
            )

        progress(85, "正在解析解说脚本...")
        script_items = self._parse_response_items(raw_text)

        # 保存原始产物，便于排查
        self._save_artifact(
            video_path=video_path,
            provider=provider,
            model_name=model_name,
            raw_text=raw_text,
            script_items=script_items,
        )

        final_script = [{**item, "OST": 2} for item in script_items]
        progress(100, "脚本生成完成")
        return final_script

    # ---------- Provider 配置解析 ----------
    def _resolve_credentials(
        self,
        provider: str,
        api_key: str | None,
        model_name: str | None,
    ) -> tuple[str, str]:
        if provider == DIRECT_VIDEO_PROVIDER_GEMINI:
            api_key = api_key or config.app.get("direct_video_gemini_api_key", "")
            model_name = model_name or config.app.get("direct_video_gemini_model_name") or DEFAULT_DIRECT_VIDEO_GEMINI_MODEL_NAME
            human = "Gemini"
        else:
            api_key = api_key or config.app.get("direct_video_qwen_api_key", "")
            model_name = model_name or config.app.get("direct_video_qwen_model_name") or DEFAULT_DIRECT_VIDEO_QWEN_MODEL_NAME
            human = "Qwen-VL"

        if not api_key:
            raise ValueError(
                f"未配置 {human} 的 API Key，请在「基础设置 → 视频分析模式 → 直接上传分析」中填写"
            )
        if not model_name:
            raise ValueError(f"未配置 {human} 的模型名称")
        return api_key, model_name

    # ---------- Gemini 官方（google-genai 新版 SDK）----------
    def _run_gemini(
        self,
        *,
        video_path: str,
        prompt: str,
        api_key: str,
        model_name: str,
        progress: Callable[[float, str], None],
    ) -> str:
        try:
            from google import genai as google_genai
            from google.genai import types as genai_types
        except ImportError as exc:
            raise RuntimeError(
                "未安装 google-genai，无法使用 Gemini 直接视频分析。"
                "请执行：pip install google-genai"
            ) from exc

        client = google_genai.Client(api_key=api_key)

        progress(15, "正在上传视频到 Gemini File API...")
        upload_name = os.path.basename(video_path)
        try:
            video_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            logger.info(f"待上传视频: {video_path} (大小 {video_size_mb:.2f} MB)")
        except OSError:
            pass
        uploaded = client.files.upload(
            file=video_path,
            config=genai_types.UploadFileConfig(display_name=upload_name),
        )
        uploaded_name = getattr(uploaded, "name", None) or ""
        initial_state = getattr(getattr(uploaded, "state", None), "name", "") or str(
            getattr(uploaded, "state", "")
        )
        logger.info(f"已上传视频到 Gemini: {uploaded_name} ({upload_name}), 初始状态={initial_state or 'UNKNOWN'}")

        progress(35, "等待 Gemini 完成视频预处理（PROCESSING → ACTIVE）...")
        active_file = self._wait_until_active_gemini(client, uploaded_name)
        logger.info(f"Gemini 视频预处理完成，文件状态已变为 ACTIVE: {uploaded_name}")


        progress(60, "Gemini 正在分析视频内容...")
        # 把所有安全分类设为 BLOCK_NONE，避免误判（特别是 block_reason=OTHER）
        safety_settings = self._build_gemini_safety_settings(genai_types)
        gen_config = genai_types.GenerateContentConfig(
            temperature=0.8,
            response_mime_type="application/json",
            # 长视频会产生很多片段，提高输出上限避免被截断
            max_output_tokens=32768,
            safety_settings=safety_settings,
        )

        # 主 prompt 调用
        try:
            response = self._gemini_generate_with_retry(
                client=client,
                model_name=model_name,
                contents=[active_file, prompt],
                generation_config=gen_config,
                progress=progress,
            )
            raw_text = self._extract_gemini_response_text(response)
        except RuntimeError as exc:
            # 主 prompt 触发了 prompt-level 阻挡（block_reason=OTHER 等不可控分类），
            # 自动换成极简中性 prompt 再试一次。
            if not self._is_prompt_block_error(exc):
                raise
            logger.warning(f"主 prompt 被 Gemini 阻挡，自动改用 fallback prompt 重试: {exc}")
            progress(70, "提示词被安全策略阻挡，正在使用极简提示词重试...")
            response = self._gemini_generate_with_retry(
                client=client,
                model_name=model_name,
                contents=[active_file, _FALLBACK_PROMPT],
                generation_config=gen_config,
                progress=progress,
            )
            raw_text = self._extract_gemini_response_text(response)






        # 清理远端文件，避免占用配额（失败不影响主流程）
        try:
            if uploaded_name:
                client.files.delete(name=uploaded_name)
        except Exception as exc:  # pragma: no cover
            logger.warning(f"清理 Gemini 远端文件失败: {exc}")

        return raw_text

    def _wait_until_active_gemini(self, client: Any, file_name: str):
        if not file_name:
            raise RuntimeError("Gemini 上传后未返回 file name，无法继续")

        elapsed = 0
        while elapsed < _GEMINI_MAX_PROCESS_WAIT_SECONDS:
            file_info = client.files.get(name=file_name)
            state = getattr(getattr(file_info, "state", None), "name", "") or str(
                getattr(file_info, "state", "")
            )
            if state.upper() == "ACTIVE":
                return file_info
            if state.upper() == "FAILED":
                raise RuntimeError(f"Gemini 处理视频失败: {file_name}")
            time.sleep(_GEMINI_POLL_INTERVAL_SECONDS)
            elapsed += _GEMINI_POLL_INTERVAL_SECONDS

        raise TimeoutError(
            f"等待 Gemini 处理视频超时（>{_GEMINI_MAX_PROCESS_WAIT_SECONDS}s）: {file_name}"
        )

    def _extract_gemini_response_text(self, response: Any) -> str:
        # 1) 优先用 SDK 提供的 .text 便利属性
        text = getattr(response, "text", None)
        if text:
            return text

        # 2) 退而手动遍历 candidates，把所有 part.text 拼起来（即使被截断也尽量保留）
        candidates = getattr(response, "candidates", None) or []
        finish_reason: str = ""
        collected: list[str] = []
        safety_blocked = False

        for candidate in candidates:
            fr = getattr(candidate, "finish_reason", None)
            if fr is not None:
                finish_reason = getattr(fr, "name", None) or str(fr)

            content = getattr(candidate, "content", None)
            if not content:
                continue
            parts = getattr(content, "parts", None) or []
            for part in parts:
                part_text = getattr(part, "text", "") or ""
                if part_text:
                    collected.append(part_text)

            # 检查 safety ratings 是否触发 BLOCK
            safety_ratings = getattr(candidate, "safety_ratings", None) or []
            for rating in safety_ratings:
                if getattr(rating, "blocked", False):
                    safety_blocked = True

        # 3) 检查 prompt_feedback（可能整段被 prompt 安全策略阻挡）
        prompt_feedback = getattr(response, "prompt_feedback", None)
        block_reason = ""
        if prompt_feedback is not None:
            br = getattr(prompt_feedback, "block_reason", None)
            if br is not None:
                block_reason = getattr(br, "name", None) or str(br)

        if collected:
            joined = "".join(collected)
            if finish_reason and finish_reason.upper() == "MAX_TOKENS":
                logger.warning(
                    "Gemini 输出被 MAX_TOKENS 截断，已保留部分内容尝试解析。"
                    "建议：缩短视频时长、或在模型支持时增加 max_output_tokens。"
                )
            return joined

        # 4) 没有任何 part.text，根据原因抛精准错误
        reason_upper = (finish_reason or "").upper()
        if reason_upper == "MAX_TOKENS":
            raise RuntimeError(
                "Gemini 输出被 MAX_TOKENS 截断且没有任何可解析片段。"
                "请尝试：1) 缩短视频时长 2) 改用更大输出窗口的模型（如 gemini-1.5-pro / gemini-2.5-pro）"
            )
        if reason_upper in {"SAFETY", "RECITATION", "PROHIBITED_CONTENT", "SPII"} or safety_blocked:
            raise RuntimeError(
                f"Gemini 因安全/合规策略未返回内容（finish_reason={finish_reason or 'SAFETY'}）。"
                "请检查视频内容是否触发安全策略，或调整 prompt。"
            )
        if block_reason:
            raise RuntimeError(
                f"Gemini 提示词被安全策略阻挡（block_reason={block_reason}），未生成任何输出。"
            )
        if reason_upper:
            raise RuntimeError(
                f"Gemini 未返回可解析的文本内容（finish_reason={finish_reason}）。"
            )
        raise RuntimeError("Gemini 未返回可解析的文本内容")


    def _gemini_generate_with_retry(
        self,
        *,
        client: Any,
        model_name: str,
        contents: list,
        generation_config: Any,
        progress: Callable[[float, str], None],
    ) -> Any:
        """对 Gemini generate_content 增加指数退避重试，避免被 503/429 类瞬时错误打断。"""
        last_exc: Exception | None = None
        for attempt in range(1, _GEMINI_GENERATE_RETRY_ATTEMPTS + 1):
            try:
                return client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=generation_config,
                )

            except Exception as exc:
                last_exc = exc
                status_code = self._extract_gemini_status_code(exc)
                # 只对可恢复的错误（503/429/500/502/504）重试
                if status_code not in _GEMINI_RETRYABLE_STATUS_CODES:
                    raise
                if attempt >= _GEMINI_GENERATE_RETRY_ATTEMPTS:
                    break

                delay = _GEMINI_GENERATE_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"Gemini generate_content 临时不可用 (status={status_code}, attempt={attempt}/"
                    f"{_GEMINI_GENERATE_RETRY_ATTEMPTS})，{delay}s 后重试: {exc}"
                )
                progress(
                    65,
                    f"Gemini 暂时繁忙（HTTP {status_code}），{delay}s 后自动重试 "
                    f"({attempt}/{_GEMINI_GENERATE_RETRY_ATTEMPTS - 1})...",
                )
                time.sleep(delay)

        # 全部重试都失败
        if last_exc is None:
            raise RuntimeError("Gemini generate_content 重试失败但未捕获到原始异常")
        status_code = self._extract_gemini_status_code(last_exc)
        if status_code == 503:
            raise RuntimeError(
                "Gemini 服务当前需求过高 (503 UNAVAILABLE)，多次重试仍失败。"
                "建议稍后再试，或切换到 Qwen-VL 提供商。"
            ) from last_exc
        if status_code == 429:
            raise RuntimeError(
                "Gemini 调用超出速率限制 (429)，多次重试仍失败。"
                "请稍后再试或检查 API Key 的配额。"
            ) from last_exc
        raise last_exc

    @staticmethod
    def _extract_gemini_status_code(exc: Exception) -> int | None:
        """从 google-genai 抛出的异常中提取 HTTP status code。"""
        # 新版 SDK 的 APIError 直接带 status_code 属性
        code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if isinstance(code, int):
            return code
        # 字符串里通常会带 "503 UNAVAILABLE"，再做一次保底解析
        msg = str(exc)
        match = re.match(r"\s*(\d{3})\s+", msg)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    @staticmethod
    def _is_prompt_block_error(exc: Exception) -> bool:
        """判断异常是否为 prompt-level 阻挡（block_reason=OTHER 等不可控分类）。

        这种错误重试同一个 prompt 不会成功，需要换 fallback prompt。
        """
        msg = str(exc) or ""
        keywords = [
            "block_reason=OTHER",
            "block_reason=BLOCKLIST",
            "block_reason=PROHIBITED",
            "block_reason=SPII",
            "提示词被安全策略阻挡",
            "未生成任何输出",
        ]
        return any(keyword in msg for keyword in keywords)

    @staticmethod
    def _build_gemini_safety_settings(genai_types: Any) -> list[Any]:

        """构造把所有安全分类都设为 BLOCK_NONE 的 safety_settings。

        Gemini 默认的安全过滤偶尔会以 block_reason=OTHER 把整个 prompt 拒绝；
        视频解说脚本生成是创作类用途，把过滤开到最宽即可。
        如果新版 SDK 类型枚举有变动，捕获异常退化为不传 safety_settings。
        """
        try:
            HarmCategory = genai_types.HarmCategory
            HarmBlockThreshold = genai_types.HarmBlockThreshold
            categories = [
                HarmCategory.HARM_CATEGORY_HARASSMENT,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            ]
            # CIVIC_INTEGRITY 在较新版本才有，单独 try
            civic = getattr(HarmCategory, "HARM_CATEGORY_CIVIC_INTEGRITY", None)
            if civic is not None:
                categories.append(civic)
            return [
                genai_types.SafetySetting(
                    category=category,
                    threshold=HarmBlockThreshold.BLOCK_NONE,
                )
                for category in categories
            ]
        except Exception as exc:  # pragma: no cover - SDK 兼容性
            logger.warning(f"无法构造 Gemini safety_settings，将使用默认安全策略: {exc}")
            return []


    # ---------- Qwen-VL（DashScope）----------


    def _run_qwen(
        self,
        *,
        video_path: str,
        prompt: str,
        api_key: str,
        model_name: str,
        progress: Callable[[float, str], None],
    ) -> str:
        try:
            from dashscope import MultiModalConversation
        except ImportError as exc:
            raise RuntimeError(
                "未安装 dashscope，无法使用 Qwen-VL 直接视频分析。"
                "请在 requirements.txt 中保留 dashscope 依赖"
            ) from exc

        progress(20, "正在准备视频文件...")
        # DashScope 支持本地文件 URI: file://<absolute_path>
        absolute_path = os.path.abspath(video_path)
        # 兼容 Windows 路径
        absolute_path_normalized = absolute_path.replace("\\", "/")
        if not absolute_path_normalized.startswith("/"):
            # 例如 D:/video.mp4 → /D:/video.mp4
            absolute_path_normalized = "/" + absolute_path_normalized
        video_uri = f"file://{absolute_path_normalized}"
        logger.info(f"Qwen-VL 视频 URI: {video_uri}")

        messages = [
            {
                "role": "user",
                "content": [
                    {"video": video_uri},
                    {"text": prompt},
                ],
            }
        ]

        progress(45, "Qwen-VL 正在分析视频内容（可能需要数分钟）...")
        response = MultiModalConversation.call(
            api_key=api_key,
            model=model_name,
            messages=messages,
        )
        return self._extract_qwen_response_text(response)

    def _extract_qwen_response_text(self, response: Any) -> str:
        # 失败状态
        status_code = getattr(response, "status_code", None)
        if status_code is not None and status_code != 200:
            err_code = getattr(response, "code", "")
            err_msg = getattr(response, "message", "")
            raise RuntimeError(f"Qwen-VL 调用失败 (status={status_code}, code={err_code}): {err_msg}")

        output = getattr(response, "output", None)
        if not output:
            raise RuntimeError("Qwen-VL 未返回 output")

        # output.choices[0].message.content 可能是字符串或 list[dict]
        choices = output.get("choices") if isinstance(output, dict) else getattr(output, "choices", None)
        if not choices:
            raise RuntimeError("Qwen-VL 返回 output 中没有 choices")

        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else getattr(first, "message", None)
        if not message:
            raise RuntimeError("Qwen-VL 返回的 choice 没有 message")

        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            collected: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    part_text = part.get("text") or ""
                    if part_text:
                        collected.append(str(part_text))
                else:
                    collected.append(str(part))
            text = "".join(collected)
            if text.strip():
                return text
        raise RuntimeError("Qwen-VL 返回内容为空或无法解析")

    # ---------- 通用解析 / 落盘 ----------
    def _build_prompt(self, *, video_theme: str, custom_prompt: str) -> str:
        context_lines: list[str] = []
        if (video_theme or "").strip():
            context_lines.append(f"视频主题：{video_theme.strip()}")
        if (custom_prompt or "").strip():
            context_lines.append(f"补充创作要求：{custom_prompt.strip()}")

        context_block = ""
        if context_lines:
            joined = "\n".join(f"- {line}" for line in context_lines)
            context_block = f"创作上下文：\n{joined}"

        return _DEFAULT_PROMPT.replace("${context_block}", context_block)

    def _parse_response_items(self, raw_text: str) -> list[dict[str, Any]]:
        cleaned = (raw_text or "").strip()
        if not cleaned:
            raise ValueError("模型返回内容为空")

        # 去除 ``` 代码块包裹
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            payload = self._loads_truncated_json(cleaned)
            if payload is None:
                raise ValueError(f"无法解析模型返回的 JSON: {cleaned[:200]}")


        if not isinstance(payload, dict):
            raise ValueError("模型返回 JSON 必须是对象")

        items = payload.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("模型返回的 JSON 缺少非空的 items 数组")

        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            timestamp = str(item.get("timestamp", "")).strip()
            picture = str(item.get("picture", "")).strip()
            narration = str(item.get("narration", "")).strip()
            if not timestamp:
                logger.warning(f"第 {index} 个片段缺少 timestamp，已跳过")
                continue
            normalized.append(
                {
                    "_id": item.get("_id", index),
                    "timestamp": timestamp,
                    "picture": picture,
                    "narration": narration,
                }
            )

        if not normalized:
            raise ValueError("模型返回的 items 中没有有效片段")
        return normalized

    @staticmethod
    def _loads_truncated_json(text: str) -> dict | None:
        """容错解析被 MAX_TOKENS 截断的 JSON：

        策略：
        1. 取从第一个 `{` 开始的子串
        2. 若直接 `json.loads` 失败，逐步剪掉末尾不完整的字符并补齐 `]` `}`
        3. 仍失败则返回 None
        """
        if not text:
            return None
        start = text.find("{")
        if start < 0:
            return None
        body = text[start:]

        # 直接尝试
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            pass

        # 截断到最后一个完整的 `}`（试图回退到一个完整 item）
        for end in range(len(body) - 1, 0, -1):
            ch = body[end]
            if ch != "}":
                continue
            head = body[: end + 1]
            # 计算未闭合的中括号 / 大括号差额，进行补齐
            opens_brace = head.count("{")
            closes_brace = head.count("}")
            opens_bracket = head.count("[")
            closes_bracket = head.count("]")
            patched = head
            patched += "]" * max(0, opens_bracket - closes_bracket)
            patched += "}" * max(0, opens_brace - closes_brace)
            # 去掉常见的尾随逗号
            patched = re.sub(r",\s*([\]}])", r"\1", patched)
            try:
                parsed = json.loads(patched)
                logger.warning(
                    f"模型 JSON 被截断，已通过补齐括号恢复（保留到偏移 {end + 1} / {len(body)}）"
                )
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                continue

        return None

    def _save_artifact(

        self,
        *,
        video_path: str,
        provider: str,
        model_name: str,
        raw_text: str,
        script_items: list[dict[str, Any]],
    ) -> str:
        analysis_dir = os.path.join(utils.storage_dir(), "temp", "analysis")
        os.makedirs(analysis_dir, exist_ok=True)
        filename = f"direct_video_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path = os.path.join(analysis_dir, filename)
        artifact = {
            "artifact_version": "documentary-direct-video-v3",
            "generated_at": datetime.now().isoformat(),
            "video_path": video_path,
            "provider": provider,
            "model_name": model_name,
            "raw_response": raw_text,
            "script_items": script_items,
        }
        try:
            with open(file_path, "w", encoding="utf-8") as fp:
                json.dump(artifact, fp, ensure_ascii=False, indent=2)
            logger.info(f"直接视频分析结果已保存到: {file_path}")
        except Exception as exc:  # pragma: no cover
            logger.warning(f"保存直接视频分析结果失败: {exc}")
        return file_path
