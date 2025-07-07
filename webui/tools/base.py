import os
import requests
import streamlit as st
from loguru import logger
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import config
# 导入新的LLM服务模块 - 确保提供商被注册
import app.services.llm  # 这会触发提供商注册
from app.services.llm.migration_adapter import create_vision_analyzer as create_vision_analyzer_new
# 保留旧的导入以确保向后兼容
from app.utils import gemini_analyzer, qwenvl_analyzer


def create_vision_analyzer(provider, api_key, model, base_url):
    """
    创建视觉分析器实例 - 已重构为使用新的LLM服务架构

    Args:
        provider: 提供商名称 ('gemini', 'gemini(openai)', 'qwenvl', 'siliconflow')
        api_key: API密钥
        model: 模型名称
        base_url: API基础URL

    Returns:
        视觉分析器实例
    """
    try:
        # 优先使用新的LLM服务架构
        return create_vision_analyzer_new(provider, api_key, model, base_url)
    except Exception as e:
        logger.warning(f"使用新LLM服务失败，回退到旧实现: {str(e)}")

        # 回退到旧的实现以确保兼容性
        if provider == 'gemini':
            return gemini_analyzer.VisionAnalyzer(model_name=model, api_key=api_key, base_url=base_url)
        elif provider == 'gemini(openai)':
            from app.utils.gemini_openai_analyzer import GeminiOpenAIAnalyzer
            return GeminiOpenAIAnalyzer(model_name=model, api_key=api_key, base_url=base_url)
        else:
            # 只传入必要的参数
            return qwenvl_analyzer.QwenAnalyzer(
                model_name=model,
                api_key=api_key,
                base_url=base_url
            )


def get_batch_timestamps(batch_files, prev_batch_files=None):
    """
    解析一批文件的时间戳范围,支持毫秒级精度

    Args:
        batch_files: 当前批次的文件列表
        prev_batch_files: 上一个批次的文件列表,用于处理单张图片的情况

    Returns:
        tuple: (first_timestamp, last_timestamp, timestamp_range)
        时间戳格式: HH:MM:SS,mmm (时:分:秒,毫秒)
        例如: 00:00:50,100 表示50秒100毫秒

    示例文件名格式:
        keyframe_001253_000050100.jpg
        其中 000050100 表示 00:00:50,100 (50秒100毫秒)
    """
    if not batch_files:
        logger.warning("Empty batch files")
        return "00:00:00,000", "00:00:00,000", "00:00:00,000-00:00:00,000"

    def get_frame_files():
        """获取首帧和尾帧文件名"""
        if len(batch_files) == 1 and prev_batch_files and prev_batch_files:
            # 单张图片情况:使用上一批次最后一帧作为首帧
            first = os.path.basename(prev_batch_files[-1])
            last = os.path.basename(batch_files[0])
            logger.debug(f"单张图片批次,使用上一批次最后一帧作为首帧: {first}")
        else:
            first = os.path.basename(batch_files[0])
            last = os.path.basename(batch_files[-1])
        return first, last

    def extract_time(filename):
        """从文件名提取时间信息"""
        try:
            # 提取类似 000050100 的时间戳部分
            time_str = filename.split('_')[2].replace('.jpg', '')
            if len(time_str) < 9:  # 处理旧格式
                time_str = time_str.ljust(9, '0')
            return time_str
        except (IndexError, AttributeError) as e:
            logger.warning(f"Invalid filename format: {filename}, error: {e}")
            return "000000000"

    def format_timestamp(time_str):
        """
        将时间字符串转换为 HH:MM:SS,mmm 格式

        Args:
            time_str: 9位数字字符串,格式为 HHMMSSMMM
                     例如: 000010000 表示 00时00分10秒000毫秒
                          000043039 表示 00时00分43秒039毫秒

        Returns:
            str: HH:MM:SS,mmm 格式的时间戳
        """
        try:
            if len(time_str) < 9:
                logger.warning(f"Invalid timestamp format: {time_str}")
                return "00:00:00,000"

            # 从时间戳中提取时、分、秒和毫秒
            hours = int(time_str[0:2])  # 前2位作为小时
            minutes = int(time_str[2:4])  # 第3-4位作为分钟
            seconds = int(time_str[4:6])  # 第5-6位作为秒数
            milliseconds = int(time_str[6:])  # 最后3位作为毫秒

            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

        except ValueError as e:
            logger.warning(f"时间戳格式转换失败: {time_str}, error: {e}")
            return "00:00:00,000"

    # 获取首帧和尾帧文件名
    first_frame, last_frame = get_frame_files()

    # 从文件名中提取时间信息
    first_time = extract_time(first_frame)
    last_time = extract_time(last_frame)

    # 转换为标准时间戳格式
    first_timestamp = format_timestamp(first_time)
    last_timestamp = format_timestamp(last_time)
    timestamp_range = f"{first_timestamp}-{last_timestamp}"

    # logger.debug(f"解析时间戳: {first_frame} -> {first_timestamp}, {last_frame} -> {last_timestamp}")
    return first_timestamp, last_timestamp, timestamp_range
