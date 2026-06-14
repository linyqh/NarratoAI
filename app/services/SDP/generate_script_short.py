"""
视频脚本生成pipeline，串联各个处理步骤
"""
import json
import os
from typing import Any, Dict, Optional
from loguru import logger

from .utils.step1_subtitle_analyzer_openai import analyze_subtitle
from .utils.step5_merge_script import merge_script
from app.services.upload_validation import InputValidationError, resolve_subtitle_input


def generate_script_result(
    api_key: str,
    model_name: str,
    output_path: str,
    base_url: str = None,
    custom_clips: int = 5,
    provider: str = None,
    video_paths=None,
    plot_analysis: Optional[str] = None,
    short_name: str = "",
    drama_genre: str = "",
    *,
    srt_path: Optional[str] = None,
    subtitle_content: Optional[str] = None,
    subtitle_file_path: Optional[str] = None,
) -> Dict[str, Any]:
    """生成视频混剪脚本（安全版本，返回结果字典）

    Args:
        api_key: API密钥
        model_name: 模型名称
        output_path: 输出文件路径
        base_url: API基础URL，可选
        custom_clips: 自定义片段数量，默认5
        provider: LLM服务提供商，可选
        video_paths: 原始视频路径列表，用于生成 video_id/video_name
        plot_analysis: 已完成的剧情理解文本，提供时会跳过混剪内部剧情理解
        short_name: 短剧名称
        drama_genre: 短剧类型
        srt_path: 字幕文件路径（向后兼容）
        subtitle_content: 字幕文本内容
        subtitle_file_path: 字幕文件路径（推荐）

    Returns:
        Dict[str, Any]:
            成功: {"status": "success", "script": [...]}
            失败: {"status": "error", "message": "错误信息"}
    """
    try:
        # 解析字幕输入源（支持内容或文件路径）
        resolved_content, resolved_path = resolve_subtitle_input(
            subtitle_content=subtitle_content,
            subtitle_file_path=subtitle_file_path,
            srt_path=srt_path,
        )

        logger.info("开始分析字幕内容...")
        openai_analysis = analyze_subtitle(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
            custom_clips=custom_clips,
            provider=provider,
            srt_path=resolved_path,
            subtitle_content=resolved_content,
            plot_analysis=plot_analysis,
            video_paths=video_paths,
            short_name=short_name,
            drama_genre=drama_genre,
        )

        if openai_analysis.get("script_items"):
            final_script = openai_analysis["script_items"]
            if not output_path or not str(output_path).strip():
                raise ValueError("output_path不能为空")
            os.makedirs(os.path.dirname(str(output_path)) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(final_script, f, ensure_ascii=False, indent=4)
            logger.info(f"短剧混剪脚本生成完成：{output_path}")
        else:
            adjusted_results = openai_analysis['plot_points']
            final_script = merge_script(adjusted_results, output_path, video_paths=video_paths)

        return {"status": "success", "script": final_script}

    except InputValidationError as e:
        logger.error(f"输入验证失败: {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.exception(f"SDP 脚本生成失败: {e}")
        return {"status": "error", "message": f"生成脚本失败: {str(e)}"}


def generate_script(
    srt_path: Optional[str] = None,
    api_key: str = None,
    model_name: str = None,
    output_path: str = None,
    base_url: str = None,
    custom_clips: int = 5,
    provider: str = None,
    video_paths=None,
    plot_analysis: Optional[str] = None,
    short_name: str = "",
    drama_genre: str = "",
    *,
    subtitle_content: Optional[str] = None,
    subtitle_file_path: Optional[str] = None,
):
    """生成视频混剪脚本（向后兼容版本）

    Args:
        srt_path: 字幕文件路径（向后兼容参数，可选）
        api_key: API密钥
        model_name: 模型名称
        output_path: 输出文件路径
        base_url: API基础URL，可选
        custom_clips: 自定义片段数量，默认5
        provider: LLM服务提供商，可选
        video_paths: 原始视频路径列表，用于生成 video_id/video_name
        plot_analysis: 已完成的剧情理解文本
        short_name: 短剧名称
        drama_genre: 短剧类型
        subtitle_content: 字幕文本内容（可选）
        subtitle_file_path: 字幕文件路径（推荐使用，可选）

    Returns:
        str: 生成的脚本内容

    Raises:
        FileNotFoundError: 字幕文件不存在（向后兼容）
        ValueError: 输入验证失败或脚本生成失败
    """
    result = generate_script_result(
        api_key=api_key,
        model_name=model_name,
        output_path=output_path,
        base_url=base_url,
        custom_clips=custom_clips,
        provider=provider,
        video_paths=video_paths,
        plot_analysis=plot_analysis,
        short_name=short_name,
        drama_genre=drama_genre,
        srt_path=srt_path,
        subtitle_content=subtitle_content,
        subtitle_file_path=subtitle_file_path,
    )

    if result.get("status") != "success":
        error_message = result.get("message", "生成脚本失败")
        # 保持向后兼容：如果是文件不存在错误，抛出 FileNotFoundError
        if "不存在" in error_message and (srt_path or subtitle_file_path):
            raise FileNotFoundError(error_message)
        raise ValueError(error_message)

    return result["script"]
