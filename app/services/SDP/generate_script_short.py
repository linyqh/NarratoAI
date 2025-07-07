"""
视频脚本生成pipeline，串联各个处理步骤
"""
import os
from .utils.step1_subtitle_analyzer_openai import analyze_subtitle
from .utils.step5_merge_script import merge_script


def generate_script(srt_path: str, api_key: str, model_name: str, output_path: str, base_url: str = None, custom_clips: int = 5, provider: str = None):
    """生成视频混剪脚本

    Args:
        srt_path: 字幕文件路径
        api_key: API密钥
        model_name: 模型名称
        output_path: 输出文件路径，可选
        base_url: API基础URL
        custom_clips: 自定义片段数量
        provider: LLM服务提供商

    Returns:
        str: 生成的脚本内容
    """
    # 验证输入文件
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"字幕文件不存在: {srt_path}")

    # 分析字幕
    print("开始分析...")
    openai_analysis = analyze_subtitle(
        srt_path=srt_path,
        api_key=api_key,
        model_name=model_name,
        base_url=base_url,
        custom_clips=custom_clips,
        provider=provider
    )

    # 合并生成最终脚本
    adjusted_results = openai_analysis['plot_points']
    final_script = merge_script(adjusted_results, output_path)

    return final_script
