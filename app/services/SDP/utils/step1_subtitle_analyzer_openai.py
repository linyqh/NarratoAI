"""
使用统一LLM服务，分析字幕文件，返回剧情梗概和爆点
"""
import traceback
import json
import asyncio
from loguru import logger

from .utils import load_srt
# 导入新的提示词管理系统
from app.services.prompts import PromptManager
# 导入统一LLM服务
from app.services.llm.unified_service import UnifiedLLMService
# 导入安全的异步执行函数
from app.services.llm.migration_adapter import _run_async_safely


def analyze_subtitle(
    srt_path: str,
    model_name: str,
    api_key: str = None,
    base_url: str = None,
    custom_clips: int = 5,
    provider: str = None
) -> dict:
    """分析字幕内容，返回完整的分析结果

    Args:
        srt_path (str): SRT字幕文件路径
        model_name (str): 大模型名称
        api_key (str, optional): 大模型API密钥. Defaults to None.
        base_url (str, optional): 大模型API基础URL. Defaults to None.
        custom_clips (int): 需要提取的片段数量. Defaults to 5.
        provider (str, optional): LLM服务提供商. Defaults to None.

    Returns:
        dict: 包含剧情梗概和结构化的时间段分析的字典
    """
    try:
        # 加载字幕文件
        subtitles = load_srt(srt_path)
        subtitle_content = "\n".join([f"{sub['timestamp']}\n{sub['text']}" for sub in subtitles])

        # 初始化统一LLM服务
        llm_service = UnifiedLLMService()

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
        from webui.tools.generate_short_summary import parse_and_fix_json
        summary_data = parse_and_fix_json(response)

        if not summary_data:
            raise Exception("无法解析LLM返回的JSON数据")

        logger.info(f"字幕分析完成，找到 {len(summary_data.get('plot_titles', []))} 个关键情节")
        print(json.dumps(summary_data, indent=4, ensure_ascii=False))

        # 构建爆点标题列表
        plot_titles_text = ""
        print(f"找到 {len(summary_data['plot_titles'])} 个片段")
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

