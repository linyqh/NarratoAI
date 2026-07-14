"""
使用统一LLM服务，分析字幕文件，返回剧情梗概和爆点
"""
import os
import traceback
import json
from loguru import logger

from app.services.subtitle_text import has_timecodes, normalize_subtitle_text, read_subtitle_text
from app.services.short_drama_narration_validation import (
    build_subtitle_index,
    parse_script_timestamp_range,
)
# 导入新的提示词管理系统
from app.services.prompts import PromptManager
# 导入统一LLM服务
from app.services.llm.unified_service import UnifiedLLMService
# 导入安全的异步执行函数
from app.services.llm.migration_adapter import _run_async_safely
from app.utils.json_utils import parse_and_fix_json


def _normalize_paths(paths):
    if isinstance(paths, str):
        paths = [paths]
    if not paths:
        return []

    normalized_paths = []
    seen = set()
    for path in paths:
        if not isinstance(path, str):
            continue
        path = path.strip()
        if not path or path in seen:
            continue
        normalized_paths.append(path)
        seen.add(path)
    return normalized_paths


def _coerce_positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _match_video_id_by_name(video_name, video_paths):
    video_name = os.path.basename(str(video_name or "").strip())
    if not video_name:
        return None

    for index, video_path in enumerate(video_paths, start=1):
        if os.path.basename(video_path) == video_name:
            return index
    return None


def _default_video_name(video_id, video_paths):
    if 1 <= video_id <= len(video_paths):
        return os.path.basename(video_paths[video_id - 1])
    return ""


def _normalize_short_mix_items(items, video_paths, subtitle_content):
    if not isinstance(items, list) or not items:
        raise ValueError("短剧混剪脚本 items 必须是非空数组")

    normalized_video_paths = _normalize_paths(video_paths)
    subtitle_index = build_subtitle_index(subtitle_content, normalized_video_paths)
    available_video_ids = {cue.video_id for cue in subtitle_index}
    if normalized_video_paths:
        available_video_ids.update(range(1, len(normalized_video_paths) + 1))

    normalized_items = []
    ranges_by_video = {}
    for index, raw_item in enumerate(items, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError(f"第 {index} 个混剪片段必须是对象")

        item_id = index
        video_id = (
            _match_video_id_by_name(raw_item.get("video_name") or raw_item.get("source_video"), normalized_video_paths)
            or _coerce_positive_int(raw_item.get("video_id") or raw_item.get("video_index"))
            or 1
        )
        if available_video_ids and video_id not in available_video_ids:
            raise ValueError(f"片段 {item_id} 的 video_id={video_id} 不在已选视频范围内")

        try:
            start_ms, end_ms, timestamp = parse_script_timestamp_range(raw_item.get("timestamp", ""))
        except ValueError as exc:
            raise ValueError(f"片段 {item_id}: {exc}") from exc
        if start_ms >= end_ms:
            raise ValueError(f"片段 {item_id} 的开始时间必须早于结束时间")

        video_cues = [cue for cue in subtitle_index if cue.video_id == video_id]
        if video_cues:
            min_start = min(cue.start_ms for cue in video_cues)
            max_end = max(cue.end_ms for cue in video_cues)
            if start_ms < min_start or end_ms > max_end:
                raise ValueError(f"片段 {item_id} 的时间戳不在视频 {video_id} 的字幕范围内")
            if not any(start_ms < cue.end_ms and end_ms > cue.start_ms for cue in video_cues):
                raise ValueError(f"片段 {item_id} 的时间戳没有命中视频 {video_id} 的字幕内容")

        picture = str(
            raw_item.get("picture")
            or raw_item.get("title")
            or raw_item.get("narrative_function")
            or raw_item.get("intent")
            or raw_item.get("story_role")
            or ""
        ).strip()
        if not picture:
            raise ValueError(f"片段 {item_id} 的 picture 不能为空")

        video_name = str(raw_item.get("video_name") or "").strip()
        if normalized_video_paths:
            video_name = _default_video_name(video_id, normalized_video_paths)

        normalized_items.append(
            {
                "_id": item_id,
                "video_id": video_id,
                "video_name": video_name,
                "timestamp": timestamp,
                "picture": picture,
                "narration": f"播放原片{item_id}",
                "OST": 1,
            }
        )
        ranges_by_video.setdefault(video_id, []).append((start_ms, end_ms, item_id))

    for video_id, ranges in ranges_by_video.items():
        ranges = sorted(ranges, key=lambda item: (item[0], item[1], item[2]))
        previous_start, previous_end, previous_id = ranges[0]
        for start_ms, end_ms, item_id in ranges[1:]:
            if start_ms < previous_end:
                raise ValueError(f"视频 {video_id} 的片段 {item_id} 与片段 {previous_id} 时间戳重叠")
            if end_ms > previous_end:
                previous_start, previous_end, previous_id = start_ms, end_ms, item_id

    return normalized_items


def _generate_short_mix_script(
    *,
    subtitle_content,
    plot_analysis,
    custom_clips,
    provider,
    model_name,
    api_key,
    base_url,
    video_paths=None,
    short_name="",
    drama_genre="",
):
    script_generation_prompt = PromptManager.get_prompt(
        category="short_drama_editing",
        name="script_generation",
        parameters={
            "drama_name": short_name or "短剧",
            "drama_genre": drama_genre or "短剧",
            "plot_analysis": plot_analysis,
            "subtitle_content": subtitle_content,
            "custom_clips": int(custom_clips or 5),
        },
    )

    response = _run_async_safely(
        UnifiedLLMService.generate_text,
        prompt=script_generation_prompt,
        provider=provider,
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,
        max_tokens=4000,
    )

    script_data = parse_and_fix_json(response)
    if not script_data:
        raise ValueError("无法解析短剧混剪脚本JSON")

    script_items = script_data.get("items") or script_data.get("segments") or script_data.get("plot_points")
    return _normalize_short_mix_items(script_items, video_paths, subtitle_content)


def analyze_subtitle(
    model_name: str,
    api_key: str = None,
    base_url: str = None,
    custom_clips: int = 5,
    provider: str = None,
    srt_path: str = None,
    subtitle_content: str = None,
    plot_analysis: str = None,
    video_paths=None,
    short_name: str = "",
    drama_genre: str = "",
) -> dict:
    """分析字幕内容，返回完整的分析结果

    Args:
        model_name (str): 大模型名称
        api_key (str, optional): 大模型API密钥. Defaults to None.
        base_url (str, optional): 大模型API基础URL. Defaults to None.
        custom_clips (int): 需要提取的片段数量. Defaults to 5.
        provider (str, optional): LLM服务提供商. Defaults to None.
        srt_path (str, optional): SRT字幕文件路径（与subtitle_content二选一）
        subtitle_content (str, optional): SRT字幕文本内容（与srt_path二选一）
        plot_analysis (str, optional): 已审核/缓存的剧情理解文本，提供时直接进入混剪脚本生成
        video_paths (list, optional): 原始视频路径列表，用于补齐 video_id/video_name
        short_name (str, optional): 短剧名称
        drama_genre (str, optional): 短剧类型

    Returns:
        dict: 包含剧情梗概和结构化的时间段分析的字典
    """
    try:
        # 读取并规范化字幕文本（不依赖结构化 SRT 解析，提升兼容性）
        if subtitle_content and str(subtitle_content).strip():
            normalized_subtitle_text = normalize_subtitle_text(subtitle_content)
            source_label = "字幕内容（直接传入）"
        elif srt_path:
            decoded = read_subtitle_text(srt_path)
            normalized_subtitle_text = decoded.text
            source_label = f"字幕文件: {srt_path} (encoding: {decoded.encoding})"
        else:
            raise ValueError("必须提供 srt_path 或 subtitle_content 参数")

        # 基础校验：必须有内容且包含可用于定位的时间码
        if not normalized_subtitle_text or len(normalized_subtitle_text.strip()) < 10:
            error_msg = (
                f"字幕来源 [{source_label}] 内容为空或过短。\n"
                f"请检查：\n"
                f"1. 文件格式是否为标准 SRT\n"
                f"2. 文件编码是否为 UTF-8、UTF-16、GBK 或 GB2312\n"
                f"3. 文件内容是否为空"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not has_timecodes(normalized_subtitle_text):
            error_msg = (
                f"字幕来源 [{source_label}] 未检测到有效时间码，无法进行时间段定位。\n"
                f"请确保字幕包含类似以下格式的时间轴：\n"
                f"00:00:01,000 --> 00:00:02,000\n"
                f"（若毫秒分隔符为'.'，系统会自动规范化为','）"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"成功加载字幕来源 [{source_label}]，字符数: {len(normalized_subtitle_text)}")
        subtitle_content = normalized_subtitle_text

        # 如果没有指定provider，根据model_name推断
        if not provider:
            if "deepseek" in model_name.lower():
                provider = "deepseek"
            elif "gpt" in model_name.lower():
                provider = "openai"
            elif "gemini" in model_name.lower():
                provider = "gemini"
            else:
                provider = "openai"  # 默认使用openai

        logger.info(f"使用LLM服务分析字幕，提供商: {provider}, 模型: {model_name}")

        if plot_analysis and str(plot_analysis).strip():
            logger.info("使用已有剧情理解直接生成短剧混剪脚本")
            script_items = _generate_short_mix_script(
                subtitle_content=subtitle_content,
                plot_analysis=str(plot_analysis).strip(),
                custom_clips=custom_clips,
                provider=provider,
                model_name=model_name,
                api_key=api_key,
                base_url=base_url,
                video_paths=video_paths,
                short_name=short_name,
                drama_genre=drama_genre,
            )
            return {
                "summary": str(plot_analysis).strip(),
                "plot_titles": [],
                "plot_points": [],
                "script_items": script_items,
            }

        # 使用新的提示词管理系统
        subtitle_analysis_prompt = PromptManager.get_prompt(
            category="short_drama_editing",
            name="subtitle_analysis",
            parameters={
                "subtitle_content": subtitle_content,
                "custom_clips": custom_clips
            }
        )

        # 使用统一LLM服务生成文本
        logger.info("开始分析字幕内容...")
        response = _run_async_safely(
            UnifiedLLMService.generate_text,
            prompt=subtitle_analysis_prompt,
            provider=provider,
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0.1,  # 使用较低的温度以获得更稳定的结果
            max_tokens=4000
        )

        # 解析JSON响应
        summary_data = parse_and_fix_json(response)

        if not summary_data:
            raise Exception("无法解析LLM返回的JSON数据")

        logger.info(f"字幕分析完成，找到 {len(summary_data.get('plot_titles', []))} 个关键情节")
        logger.debug(json.dumps(summary_data, indent=4, ensure_ascii=False))

        try:
            script_items = _generate_short_mix_script(
                subtitle_content=subtitle_content,
                plot_analysis=json.dumps(summary_data, ensure_ascii=False, indent=2),
                custom_clips=custom_clips,
                provider=provider,
                model_name=model_name,
                api_key=api_key,
                base_url=base_url,
                video_paths=video_paths,
                short_name=short_name,
                drama_genre=drama_genre,
            )
            return {
                "summary": summary_data.get("summary", ""),
                "plot_titles": summary_data.get("plot_titles", []),
                "plot_points": [],
                "script_items": script_items,
            }
        except Exception as direct_script_error:
            logger.warning(f"直接生成短剧混剪脚本失败，回退到时间段定位: {direct_script_error}")

        # 构建爆点标题列表
        plot_titles_text = ""
        logger.info(f"找到 {len(summary_data.get('plot_titles', []))} 个片段")
        for i, point in enumerate(summary_data['plot_titles'], 1):
            plot_titles_text += f"{i}. {point}\n"

        # 使用新的提示词管理系统
        plot_extraction_prompt = PromptManager.get_prompt(
            category="short_drama_editing",
            name="plot_extraction",
            parameters={
                "subtitle_content": subtitle_content,
                "plot_summary": summary_data['summary'],
                "plot_titles": plot_titles_text
            }
        )

        # 使用统一LLM服务进行爆点时间段分析
        logger.info("开始分析爆点时间段...")
        response = _run_async_safely(
            UnifiedLLMService.generate_text,
            prompt=plot_extraction_prompt,
            provider=provider,
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0.1,
            max_tokens=4000
        )

        # 解析JSON响应
        plot_data = parse_and_fix_json(response)

        if not plot_data:
            raise Exception("无法解析爆点分析的JSON数据")

        logger.info(f"爆点分析完成，找到 {len(plot_data.get('plot_points', []))} 个时间段")

        # 合并结果
        result = {
            "summary": summary_data.get("summary", ""),
            "plot_titles": summary_data.get("plot_titles", []),
            "plot_points": plot_data.get("plot_points", [])
        }

        return result

    except Exception as e:
        logger.error(f"分析字幕时发生错误: {str(e)}")
        raise Exception(f"分析字幕时发生错误：{str(e)}\n{traceback.format_exc()}")
