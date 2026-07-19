"""LLM-powered SRT subtitle correction."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.config import config
from app.config.defaults import resolve_text_model_name
from app.services.llm.manager import LLMServiceManager
from app.services.llm.migration_adapter import _run_async_safely
from app.services.llm.unified_service import UnifiedLLMService
from app.services.subtitle_text import has_timecodes, normalize_subtitle_text, read_subtitle_text
from app.utils import utils


class SubtitleCorrectionError(RuntimeError):
    """Raised when subtitle correction cannot produce a valid SRT."""


_TIME_LINE_RE = re.compile(
    r"^\s*\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}(?:\s+.*)?$"
)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class SubtitleBlock:
    order: int
    index_line: str
    time_line: str
    text: str


def _ensure_llm_providers_registered() -> None:
    if LLMServiceManager.is_registered():
        return
    from app.services.llm.providers import register_all_providers

    register_all_providers()


def parse_srt_blocks(srt_content: str) -> list[SubtitleBlock]:
    normalized = normalize_subtitle_text(srt_content)
    if not normalized or not has_timecodes(normalized):
        raise SubtitleCorrectionError("字幕内容为空或未检测到有效 SRT 时间轴")

    blocks: list[SubtitleBlock] = []
    raw_blocks = re.split(r"\n\s*\n", normalized)
    for raw_block in raw_blocks:
        lines = [line.rstrip() for line in raw_block.splitlines() if line.strip()]
        if not lines:
            continue

        if len(lines) >= 2 and _TIME_LINE_RE.match(lines[1]):
            index_line = lines[0].strip()
            time_line = lines[1].strip()
            text = "\n".join(lines[2:]).strip()
        elif _TIME_LINE_RE.match(lines[0]):
            index_line = str(len(blocks) + 1)
            time_line = lines[0].strip()
            text = "\n".join(lines[1:]).strip()
        else:
            raise SubtitleCorrectionError(f"无法解析字幕块: {raw_block[:80]}")

        blocks.append(
            SubtitleBlock(
                order=len(blocks) + 1,
                index_line=index_line,
                time_line=time_line,
                text=text,
            )
        )

    if not blocks:
        raise SubtitleCorrectionError("字幕内容为空或未检测到有效字幕块")
    return blocks


def _build_correction_prompt(blocks: list[SubtitleBlock]) -> str:
    payload = [
        {
            "id": block.order,
            "time": block.time_line,
            "text": block.text,
        }
        for block in blocks
    ]
    return f"""
请校准以下 SRT 字幕文本中的明显语音识别错误。字幕可能是中文、英文、日文、韩文或其他语言，也可能包含多语言混合内容。

校准要求：
1. 先结合全部字幕内容识别原语言和语境，保持原语言输出；多语言混合内容也要保持原有语言混合方式。
2. 只纠正明显的 ASR 错字、拼写错误、同音或近音误识别、词形误识别、专有名词前后不一致。
3. 不要润色、扩写、改写句意，不要翻译，不要增删剧情信息。
4. 不要修改时间轴、序号、条目数量或条目顺序。
5. 不确定的内容保持原样。
6. 保留必要的说话人标记、标点和换行。

只输出严格 JSON，不要输出 Markdown 或解释文字。格式必须为：
{{"items":[{{"id":1,"text":"校准后的字幕文本"}}]}}

待校准字幕条目：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def _extract_json_text(raw_output: str) -> str:
    text = str(raw_output or "").strip()
    block_match = _JSON_BLOCK_RE.search(text)
    if block_match:
        return block_match.group(1).strip()

    if not text.startswith(("{", "[")):
        starts = [pos for pos in (text.find("{"), text.find("[")) if pos >= 0]
        if starts:
            start = min(starts)
            end = max(text.rfind("}"), text.rfind("]"))
            if end > start:
                return text[start:end + 1]
    return text


def _parse_corrections(raw_output: str, expected_ids: set[int]) -> dict[int, str]:
    json_text = _extract_json_text(raw_output)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise SubtitleCorrectionError("LLM 未返回有效 JSON 字幕校准结果") from exc

    if isinstance(data, dict) and "items" in data:
        items = data["items"]
    elif isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [{"id": key, "text": value} for key, value in data.items()]
    else:
        raise SubtitleCorrectionError("LLM 字幕校准结果格式无效")

    corrections: dict[int, str] = {}
    if not isinstance(items, list):
        raise SubtitleCorrectionError("LLM 字幕校准结果缺少 items 列表")

    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            item_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if item_id in expected_ids:
            corrections[item_id] = str(item.get("text") or "").strip()

    missing_ids = sorted(expected_ids - set(corrections.keys()))
    if missing_ids:
        raise SubtitleCorrectionError(f"LLM 字幕校准结果缺少字幕条目: {missing_ids[:10]}")
    return corrections


def _render_srt(blocks: list[SubtitleBlock], corrections: dict[int, str]) -> str:
    rendered_blocks = []
    for block in blocks:
        corrected_text = corrections.get(block.order, "").strip() or block.text
        rendered_blocks.append(f"{block.index_line}\n{block.time_line}\n{corrected_text}")
    return "\n\n".join(rendered_blocks).rstrip() + "\n"


def correct_srt_content(
    srt_content: str,
    *,
    provider: str = "",
    api_key: str = "",
    base_url: str = "",
    model_name: str = "",
    temperature: float = 0.1,
) -> str:
    blocks = parse_srt_blocks(srt_content)
    _ensure_llm_providers_registered()

    resolved_model_name = str(
        model_name or resolve_text_model_name(config.app, provider, prefer_fast=True)
    ).strip()
    logger.info(f"开始使用高效率模型 {resolved_model_name} 校准字幕，共 {len(blocks)} 条")
    prompt = _build_correction_prompt(blocks)
    raw_output = _run_async_safely(
        UnifiedLLMService.generate_text,
        prompt=prompt,
        system_prompt="你是一位专业的多语言字幕校对员，擅长修正 ASR 语音识别造成的明显错字、拼写错误、同音或近音误识别，同时严格保留字幕结构和原语言。",
        provider=provider,
        temperature=temperature,
        response_format="json",
        api_key=api_key,
        api_base=base_url,
        model=resolved_model_name,
        thinking_level="off",
    )
    corrections = _parse_corrections(raw_output, {block.order for block in blocks})
    corrected_srt = _render_srt(blocks, corrections)
    logger.info("字幕校准完成")
    return corrected_srt


def write_srt_file(srt_content: str, subtitle_file: str = "") -> str:
    if not subtitle_file:
        subtitle_file = os.path.join(utils.subtitle_dir(), "subtitle_corrected.srt")
    parent = os.path.dirname(subtitle_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(subtitle_file, "w", encoding="utf-8") as f:
        f.write(srt_content)
    return subtitle_file


def correct_subtitle_file(
    subtitle_file: str,
    output_file: str = "",
    *,
    provider: str = "",
    api_key: str = "",
    base_url: str = "",
    model_name: str = "",
    temperature: float = 0.1,
) -> str:
    if not subtitle_file or not os.path.isfile(subtitle_file):
        raise SubtitleCorrectionError(f"字幕文件不存在: {subtitle_file}")

    decoded = read_subtitle_text(subtitle_file)
    corrected_srt = correct_srt_content(
        decoded.text,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        temperature=temperature,
    )
    return write_srt_file(corrected_srt, output_file)
