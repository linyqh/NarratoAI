#!/usr/bin/env python
# -*- coding: UTF-8 -*-

'''
@Project: NarratoAI
@File   : clip_video
@Author : 小林同学
@Date   : 2025/5/6 下午6:14 
'''

import os
import subprocess
import json
import hashlib
import logging
from typing import Dict, List, Optional
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def parse_timestamp(timestamp: str) -> tuple:
    """
    解析时间戳字符串，返回开始和结束时间
    
    Args:
        timestamp: 格式为'HH:MM:SS-HH:MM:SS'的时间戳字符串
        
    Returns:
        tuple: (开始时间, 结束时间) 格式为'HH:MM:SS'
    """
    start_time, end_time = timestamp.split('-')
    return start_time, end_time


def calculate_end_time(start_time: str, duration: float, extra_seconds: float = 1.0) -> str:
    """
    根据开始时间和持续时间计算结束时间
    
    Args:
        start_time: 开始时间，格式为'HH:MM:SS'
        duration: 持续时间，单位为秒
        extra_seconds: 额外添加的秒数，默认为1秒
        
    Returns:
        str: 计算后的结束时间，格式为'HH:MM:SS'
    """
    h, m, s = map(int, start_time.split(':'))
    total_seconds = h * 3600 + m * 60 + s + duration + extra_seconds

    h_new = int(total_seconds // 3600)
    m_new = int((total_seconds % 3600) // 60)
    s_new = int(total_seconds % 60)

    return f"{h_new:02d}:{m_new:02d}:{s_new:02d}"


def check_hardware_acceleration() -> Optional[str]:
    """
    检查系统支持的硬件加速选项
    
    Returns:
        Optional[str]: 硬件加速参数，如果不支持则返回None
    """
    # 检查NVIDIA GPU支持
    try:
        nvidia_check = subprocess.run(
            ["ffmpeg", "-hwaccel", "cuda", "-i", "/dev/null", "-f", "null", "-"],
            stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, check=False
        )
        if nvidia_check.returncode == 0:
            return "cuda"
    except Exception:
        pass

    # 检查MacOS videotoolbox支持
    try:
        videotoolbox_check = subprocess.run(
            ["ffmpeg", "-hwaccel", "videotoolbox", "-i", "/dev/null", "-f", "null", "-"],
            stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, check=False
        )
        if videotoolbox_check.returncode == 0:
            return "videotoolbox"
    except Exception:
        pass

    # 检查Intel Quick Sync支持
    try:
        qsv_check = subprocess.run(
            ["ffmpeg", "-hwaccel", "qsv", "-i", "/dev/null", "-f", "null", "-"],
            stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, check=False
        )
        if qsv_check.returncode == 0:
            return "qsv"
    except Exception:
        pass

    return None


def clip_video(
        video_origin_path: str,
        tts_result: List[Dict],
        output_dir: Optional[str] = None,
        task_id: Optional[str] = None
) -> Dict[str, str]:
    """
    根据时间戳裁剪视频
    
    Args:
        video_origin_path: 原始视频的路径
        tts_result: 包含时间戳和持续时间信息的列表
        output_dir: 输出目录路径，默认为None时会自动生成
        task_id: 任务ID，用于生成唯一的输出目录，默认为None时会自动生成
        
    Returns:
        Dict[str, str]: 时间戳到裁剪后视频路径的映射
    """
    # 检查视频文件是否存在
    if not os.path.exists(video_origin_path):
        raise FileNotFoundError(f"视频文件不存在: {video_origin_path}")

    # 如果未提供task_id，则根据输入生成一个唯一ID
    if task_id is None:
        content_for_hash = f"{video_origin_path}_{json.dumps(tts_result)}"
        task_id = hashlib.md5(content_for_hash.encode()).hexdigest()

    # 设置输出目录
    if output_dir is None:
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "storage", "temp", "clip_video", task_id
        )

    # 确保输出目录存在
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 检查硬件加速支持
    hwaccel = check_hardware_acceleration()
    hwaccel_args = []
    if hwaccel:
        hwaccel_args = ["-hwaccel", hwaccel]
        logger.info(f"使用硬件加速: {hwaccel}")

    # 存储裁剪结果
    result = {}

    for item in tts_result:
        timestamp = item["timestamp"]
        start_time, _ = parse_timestamp(timestamp)

        # 根据持续时间计算真正的结束时间（加上1秒余量）
        duration = item["duration"]
        calculated_end_time = calculate_end_time(start_time, duration)

        # 格式化输出文件名
        output_filename = f"vid-{start_time.replace(':', '-')}-{calculated_end_time.replace(':', '-')}.mp4"
        output_path = os.path.join(output_dir, output_filename)

        # 构建FFmpeg命令
        ffmpeg_cmd = [
            "ffmpeg", "-y", *hwaccel_args,
            "-i", video_origin_path,
            "-ss", start_time,
            "-to", calculated_end_time,
            "-c:v", "h264_videotoolbox" if hwaccel == "videotoolbox" else "libx264",
            "-c:a", "aac",
            "-strict", "experimental",
            output_path
        ]

        # 执行FFmpeg命令
        try:
            logger.info(f"裁剪视频片段: {timestamp} -> {start_time}到{calculated_end_time}")
            logger.debug(f"执行命令: {' '.join(ffmpeg_cmd)}")

            process = subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )

            result[timestamp] = output_path
            logger.info(f"成功裁剪视频片段: {timestamp} -> {output_path}")

        except subprocess.CalledProcessError as e:
            logger.error(f"裁剪视频片段失败: {timestamp}")
            logger.error(f"错误信息: {e.stderr}")
            raise RuntimeError(f"视频裁剪失败: {e.stderr}")

    return result


if __name__ == "__main__":
    video_origin_path = "/Users/apple/Desktop/home/NarratoAI/resource/videos/qyn2-2无片头片尾.mp4"

    tts_result = [{'timestamp': '00:00:00-00:01:15',
                   'audio_file': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_00_00-00_01_15.mp3',
                   'subtitle_file': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_00_00-00_01_15.srt',
                   'duration': 25.55,
                   'text': '好的各位，欢迎回到我的频道！《庆余年 2》刚开播就给了我们一个王炸！范闲在北齐"死"了？这怎么可能！上集片尾那个巨大的悬念，这一集就立刻揭晓了！范闲假死归来，他面临的第一个，也是最大的难关，就是如何面对他最敬爱的，同时也是最可怕的那个人——庆帝！'},
                  {'timestamp': '00:01:15-00:04:40',
                   'audio_file': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_01_15-00_04_40.mp3',
                   'subtitle_file': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_01_15-00_04_40.srt',
                   'duration': 13.488,
                   'text': '但我们都知道，他绝不可能就这么轻易退场！第二集一开场，范闲就已经秘密回到了京都。他的生死传闻，可不像我们想象中那样只是小范围流传，而是…'},
                  {'timestamp': '00:04:58-00:05:45',
                   'audio_file': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_04_58-00_05_45.mp3',
                   'subtitle_file': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_04_58-00_05_45.srt',
                   'duration': 21.363,
                   'text': '"欺君之罪"！在封建王朝，这可是抄家灭族的大罪！搁一般人，肯定脚底抹油溜之大吉了。但范闲是谁啊？他偏要反其道而行之！他竟然决定，直接去见庆帝！冒着天大的风险，用"假死"这个事实去赌庆帝的态度！'},
                  {'timestamp': '00:05:45-00:06:00',
                   'audio_file': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_05_45-00_06_00.mp3',
                   'subtitle_file': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_05_45-00_06_00.srt',
                   'duration': 7.675, 'text': '但想见庆帝，哪有那么容易？范闲艺高人胆大，竟然选择了最激进的方式——闯宫！'}]

    # 使用方法示例
    try:
        result = clip_video(video_origin_path, tts_result)
        print("裁剪结果:")
        print(json.dumps(result, indent=4, ensure_ascii=False))
    except Exception as e:
        print(f"发生错误: {e}")
