#!/usr/bin/env python
# -*- coding: UTF-8 -*-

'''
@Project: NarratoAI
@File   : clip_video
@Author : Viccy同学
@Date   : 2025/5/6 下午6:14
'''

import os
import subprocess
import json
import hashlib
from loguru import logger
from typing import Dict, List, Optional
from pathlib import Path

from app.utils import ffmpeg_utils

def parse_timestamp(timestamp: str) -> tuple:
    """
    解析时间戳字符串，返回开始和结束时间

    Args:
        timestamp: 格式为'HH:MM:SS-HH:MM:SS'或'HH:MM:SS,sss-HH:MM:SS,sss'的时间戳字符串

    Returns:
        tuple: (开始时间, 结束时间) 格式为'HH:MM:SS'或'HH:MM:SS,sss'
    """
    start_time, end_time = timestamp.split('-')
    return start_time, end_time


def _ffmpeg_time_to_seconds(time_value: str) -> float:
    normalized_time = str(time_value).strip().replace(",", ".")
    parts = normalized_time.split(":")

    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    return float(normalized_time)


def _calculate_ffmpeg_duration(start_time: str, end_time: str) -> str:
    duration = _ffmpeg_time_to_seconds(end_time) - _ffmpeg_time_to_seconds(start_time)
    if duration <= 0:
        raise ValueError(f"无效的视频裁剪时间范围: {start_time} -> {end_time}")

    return f"{duration:.3f}".rstrip("0").rstrip(".")


def _append_fast_seek_input(cmd: List[str], input_path: str, start_time: str, end_time: str) -> None:
    duration = _calculate_ffmpeg_duration(start_time, end_time)
    cmd.extend(["-ss", start_time, "-i", input_path, "-t", duration])


def _normalize_video_origin_paths(
    video_origin_path: str,
    video_origin_paths: Optional[List[str]] = None,
) -> List[str]:
    paths = []
    if video_origin_paths:
        paths.extend(video_origin_paths)
    if video_origin_path:
        paths.insert(0, video_origin_path)

    normalized_paths = []
    seen = set()
    for item in paths:
        if not isinstance(item, str):
            continue
        item = item.strip()
        if not item or item in seen:
            continue
        normalized_paths.append(item)
        seen.add(item)
    return normalized_paths


def _coerce_video_id(value) -> Optional[int]:
    try:
        video_id = int(value)
    except (TypeError, ValueError):
        return None
    return video_id if video_id > 0 else None


def _match_video_id_by_name(video_name: str, video_origin_paths: List[str]) -> Optional[int]:
    video_name = str(video_name or "").strip()
    if not video_name:
        return None

    expected_name = os.path.basename(video_name)
    for index, video_path in enumerate(video_origin_paths, start=1):
        if os.path.basename(video_path) == expected_name:
            return index
    return None


def _resolve_script_video_path(script_item: Dict, video_origin_paths: List[str]) -> str:
    explicit_path = (
        script_item.get("source_video_path")
        or script_item.get("video_origin_path")
        or script_item.get("origin_video_path")
    )
    if explicit_path and os.path.exists(explicit_path):
        return explicit_path

    video_id = _coerce_video_id(script_item.get("video_id") or script_item.get("video_index"))
    matched_video_id = _match_video_id_by_name(
        script_item.get("video_name") or script_item.get("source_video"),
        video_origin_paths,
    )
    if matched_video_id:
        video_id = matched_video_id

    if video_id is not None:
        if video_id <= len(video_origin_paths):
            return video_origin_paths[video_id - 1]
        logger.warning(
            f"片段 {script_item.get('_id')} 的 video_id={video_id} 超出视频数量 "
            f"{len(video_origin_paths)}，默认使用第一个视频"
        )

    return video_origin_paths[0]


def _safe_output_id(value) -> str:
    safe_value = str(value if value is not None else "unknown")
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in safe_value)


def calculate_end_time(start_time: str, duration: float, extra_seconds: float = 1.0) -> str:
    """
    根据开始时间和持续时间计算结束时间

    Args:
        start_time: 开始时间，格式为'HH:MM:SS'或'HH:MM:SS,sss'(带毫秒)
        duration: 持续时间，单位为秒
        extra_seconds: 额外添加的秒数，默认为1秒

    Returns:
        str: 计算后的结束时间，格式与输入格式相同
    """
    # 检查是否包含毫秒
    has_milliseconds = ',' in start_time
    milliseconds = 0

    if has_milliseconds:
        time_part, ms_part = start_time.split(',')
        h, m, s = map(int, time_part.split(':'))
        milliseconds = int(ms_part)
    else:
        h, m, s = map(int, start_time.split(':'))

    # 转换为总毫秒数
    total_milliseconds = ((h * 3600 + m * 60 + s) * 1000 + milliseconds +
                          int((duration + extra_seconds) * 1000))

    # 计算新的时、分、秒、毫秒
    ms_new = total_milliseconds % 1000
    total_seconds = total_milliseconds // 1000
    h_new = int(total_seconds // 3600)
    m_new = int((total_seconds % 3600) // 60)
    s_new = int(total_seconds % 60)

    # 返回与输入格式一致的时间字符串
    if has_milliseconds:
        return f"{h_new:02d}:{m_new:02d}:{s_new:02d},{ms_new:03d}"
    else:
        return f"{h_new:02d}:{m_new:02d}:{s_new:02d}"


def check_hardware_acceleration() -> Optional[str]:
    """
    检查系统支持的硬件加速选项

    Returns:
        Optional[str]: 硬件加速参数，如果不支持则返回None
    """
    # 使用集中式硬件加速检测
    return ffmpeg_utils.get_ffmpeg_hwaccel_type()


def get_safe_encoder_config(hwaccel_type: Optional[str] = None) -> Dict[str, str]:
    """
    获取安全的编码器配置，基于ffmpeg_demo.py成功方案优化
    
    Args:
        hwaccel_type: 硬件加速类型
        
    Returns:
        Dict[str, str]: 编码器配置字典
    """
    # 基础配置 - 参考ffmpeg_demo.py的成功方案
    config = {
        "video_codec": "libx264",
        "audio_codec": "aac",
        "pixel_format": "yuv420p",
        "preset": "medium",
        "quality_param": "crf",  # 质量参数类型
        "quality_value": "23"    # 质量值
    }
    
    # 根据硬件加速类型调整配置（简化版本）
    if hwaccel_type in ["nvenc_pure", "nvenc_software", "cuda_careful", "nvenc", "cuda", "cuda_decode"]:
        # NVIDIA硬件加速 - 使用ffmpeg_demo.py中验证有效的参数
        config["video_codec"] = "h264_nvenc"
        config["preset"] = "medium"
        config["quality_param"] = "cq"  # CQ质量控制，而不是CRF
        config["quality_value"] = "23"
        config["pixel_format"] = "yuv420p"
    elif hwaccel_type == "amf":
        # AMD AMF编码器
        config["video_codec"] = "h264_amf"
        config["preset"] = "balanced"
        config["quality_param"] = "qp_i"
        config["quality_value"] = "23"
    elif hwaccel_type == "qsv":
        # Intel QSV编码器
        config["video_codec"] = "h264_qsv"
        config["preset"] = "medium"
        config["quality_param"] = "global_quality"
        config["quality_value"] = "23"
    elif hwaccel_type == "videotoolbox":
        # macOS VideoToolbox编码器
        config["video_codec"] = "h264_videotoolbox"
        config["preset"] = "medium"
        config["quality_param"] = "b:v"
        config["quality_value"] = "5M"
    else:
        # 软件编码（默认）
        config["video_codec"] = "libx264"
        config["preset"] = "medium"
        config["quality_param"] = "crf"
        config["quality_value"] = "23"
    
    return config


def build_ffmpeg_command(
    input_path: str, 
    output_path: str, 
    start_time: str, 
    end_time: str,
    encoder_config: Dict[str, str],
    hwaccel_args: List[str] = None
) -> List[str]:
    """
    构建优化的ffmpeg命令，基于测试结果使用正确的硬件加速方案
    
    重要发现：对于视频裁剪场景，CUDA硬件解码会导致滤镜链错误，
    应该使用纯NVENC编码器（无硬件解码）来获得最佳兼容性
    
    Args:
        input_path: 输入视频路径
        output_path: 输出视频路径
        start_time: 开始时间
        end_time: 结束时间
        encoder_config: 编码器配置
        hwaccel_args: 硬件加速参数
        
    Returns:
        List[str]: ffmpeg命令列表
    """
    cmd = ["ffmpeg", "-y"]
    
    # 关键修正：对于视频裁剪，不使用CUDA硬件解码，只使用NVENC编码器
    # 这样能避免滤镜链格式转换错误，同时保持编码性能优势
    if encoder_config["video_codec"] == "h264_nvenc":
        # 不添加硬件解码参数，让FFmpeg自动处理
        # 这避免了 "Impossible to convert between the formats" 错误
        pass
    elif hwaccel_args:
        # 对于其他编码器，可以使用硬件解码参数
        cmd.extend(hwaccel_args)
    
    # 快速定位输入文件，避免长视频从头解码到目标片段
    _append_fast_seek_input(cmd, input_path, start_time, end_time)
    
    # 编码器设置
    cmd.extend(["-c:v", encoder_config["video_codec"]])
    cmd.extend(["-c:a", encoder_config["audio_codec"]])
    
    # 像素格式
    cmd.extend(["-pix_fmt", encoder_config["pixel_format"]])
    
    # 质量和预设参数 - 针对NVENC优化
    if encoder_config["video_codec"] == "h264_nvenc":
        # 纯NVENC编码器配置（无硬件解码，兼容性最佳）
        cmd.extend(["-preset", encoder_config["preset"]])
        cmd.extend(["-cq", encoder_config["quality_value"]])
        cmd.extend(["-profile:v", "main"])  # 提高兼容性
        logger.debug("使用纯NVENC编码器（无硬件解码，避免滤镜链问题）")
    elif encoder_config["video_codec"] == "h264_amf":
        # AMD AMF编码器
        cmd.extend(["-quality", encoder_config["preset"]])
        cmd.extend(["-qp_i", encoder_config["quality_value"]])
    elif encoder_config["video_codec"] == "h264_qsv":
        # Intel QSV编码器
        cmd.extend(["-preset", encoder_config["preset"]])
        cmd.extend(["-global_quality", encoder_config["quality_value"]])
    elif encoder_config["video_codec"] == "h264_videotoolbox":
        # macOS VideoToolbox编码器
        cmd.extend(["-profile:v", "high"])
        cmd.extend(["-b:v", encoder_config["quality_value"]])
    else:
        # 软件编码器（libx264）
        cmd.extend(["-preset", encoder_config["preset"]])
        cmd.extend(["-crf", encoder_config["quality_value"]])
    
    # 音频设置
    cmd.extend(["-ar", "44100", "-ac", "2"])
    
    # 优化参数
    cmd.extend(["-avoid_negative_ts", "make_zero"])
    cmd.extend(["-movflags", "+faststart"])
    
    # 输出文件
    cmd.append(output_path)
    
    return cmd


def execute_ffmpeg_with_fallback(
    cmd: List[str], 
    timestamp: str,
    input_path: str,
    output_path: str,
    start_time: str,
    end_time: str
) -> bool:
    """
    执行ffmpeg命令，带有智能fallback机制
    
    Args:
        cmd: 主要的ffmpeg命令
        timestamp: 时间戳（用于日志）
        input_path: 输入路径
        output_path: 输出路径
        start_time: 开始时间
        end_time: 结束时间
        
    Returns:
        bool: 是否成功
    """
    try:
        # logger.debug(f"执行ffmpeg命令: {' '.join(cmd)}")
        
        # 在Windows系统上使用UTF-8编码处理输出
        is_windows = os.name == 'nt'
        process_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "check": True
        }
        
        if is_windows:
            process_kwargs["encoding"] = 'utf-8'
        
        result = subprocess.run(cmd, **process_kwargs)
        
        # 验证输出文件
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            # logger.info(f"✓ 视频裁剪成功: {timestamp}")
            return True
        else:
            logger.warning(f"输出文件无效: {output_path}")
            return False
            
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logger.warning(f"主要命令失败: {error_msg}")
        
        # 智能错误分析
        error_type = analyze_ffmpeg_error(error_msg)
        logger.debug(f"错误类型分析: {error_type}")
        
        # 根据错误类型选择fallback策略
        if error_type == "filter_chain_error":
            logger.info(f"检测到滤镜链错误，尝试兼容性模式: {timestamp}")
            return try_compatibility_fallback(input_path, output_path, start_time, end_time, timestamp)
        elif error_type == "hardware_error":
            logger.info(f"检测到硬件加速错误，尝试软件编码: {timestamp}")
            return try_software_fallback(input_path, output_path, start_time, end_time, timestamp)
        elif error_type == "encoder_error":
            logger.info(f"检测到编码器错误，尝试基本编码: {timestamp}")
            return try_basic_fallback(input_path, output_path, start_time, end_time, timestamp)
        else:
            logger.info(f"尝试通用fallback方案: {timestamp}")
            return try_fallback_encoding(input_path, output_path, start_time, end_time, timestamp)
            
    except Exception as e:
        logger.error(f"执行ffmpeg命令时发生异常: {str(e)}")
        return False


def analyze_ffmpeg_error(error_msg: str) -> str:
    """
    分析ffmpeg错误信息，返回错误类型
    
    Args:
        error_msg: 错误信息
        
    Returns:
        str: 错误类型
    """
    error_msg_lower = error_msg.lower()
    
    # 滤镜链错误
    if any(keyword in error_msg_lower for keyword in [
        "impossible to convert", "filter", "format", "scale", "auto_scale",
        "null", "parsed_null", "reinitializing filters"
    ]):
        return "filter_chain_error"
    
    # 硬件加速错误
    if any(keyword in error_msg_lower for keyword in [
        "cuda", "nvenc", "amf", "qsv", "d3d11va", "dxva2", "videotoolbox",
        "hardware", "hwaccel", "gpu", "device"
    ]):
        return "hardware_error"
    
    # 编码器错误
    if any(keyword in error_msg_lower for keyword in [
        "encoder", "codec", "h264", "libx264", "bitrate", "preset"
    ]):
        return "encoder_error"
    
    # 文件访问错误
    if any(keyword in error_msg_lower for keyword in [
        "no such file", "permission denied", "access denied", "file not found"
    ]):
        return "file_error"
    
    return "unknown_error"


def try_compatibility_fallback(
    input_path: str,
    output_path: str,
    start_time: str,
    end_time: str,
    timestamp: str
) -> bool:
    """
    尝试兼容性fallback方案（解决滤镜链问题）
    
    Args:
        input_path: 输入路径
        output_path: 输出路径
        start_time: 开始时间
        end_time: 结束时间
        timestamp: 时间戳
        
    Returns:
        bool: 是否成功
    """
    # 兼容性模式：避免所有可能的滤镜链问题
    duration = _calculate_ffmpeg_duration(start_time, end_time)
    fallback_cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", start_time,
        "-i", input_path,
        "-t", duration,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",  # 明确指定像素格式
        "-preset", "fast",
        "-crf", "23",
        "-ar", "44100", "-ac", "2",  # 标准化音频
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        "-max_muxing_queue_size", "1024",  # 增加缓冲区大小
        output_path
    ]
    
    return execute_simple_command(fallback_cmd, timestamp, "兼容性模式")


def try_software_fallback(
    input_path: str,
    output_path: str,
    start_time: str,
    end_time: str,
    timestamp: str
) -> bool:
    """
    尝试软件编码fallback方案
    
    Args:
        input_path: 输入路径
        output_path: 输出路径
        start_time: 开始时间
        end_time: 结束时间
        timestamp: 时间戳
        
    Returns:
        bool: 是否成功
    """
    # 纯软件编码
    duration = _calculate_ffmpeg_duration(start_time, end_time)
    fallback_cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", start_time,
        "-i", input_path,
        "-t", duration,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "23",
        "-ar", "44100", "-ac", "2",
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        output_path
    ]
    
    return execute_simple_command(fallback_cmd, timestamp, "软件编码")


def try_basic_fallback(
    input_path: str,
    output_path: str,
    start_time: str,
    end_time: str,
    timestamp: str
) -> bool:
    """
    尝试基本编码fallback方案
    
    Args:
        input_path: 输入路径
        output_path: 输出路径
        start_time: 开始时间
        end_time: 结束时间
        timestamp: 时间戳
        
    Returns:
        bool: 是否成功
    """
    # 最基本的编码参数
    duration = _calculate_ffmpeg_duration(start_time, end_time)
    fallback_cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", start_time,
        "-i", input_path,
        "-t", duration,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        "-preset", "ultrafast",  # 最快速度
        "-crf", "28",  # 稍微降低质量
        "-avoid_negative_ts", "make_zero",
        output_path
    ]
    
    return execute_simple_command(fallback_cmd, timestamp, "基本编码")


def execute_simple_command(cmd: List[str], timestamp: str, method_name: str) -> bool:
    """
    执行简单的ffmpeg命令
    
    Args:
        cmd: 命令列表
        timestamp: 时间戳
        method_name: 方法名称
        
    Returns:
        bool: 是否成功
    """
    try:
        logger.debug(f"执行{method_name}命令: {' '.join(cmd)}")
        
        is_windows = os.name == 'nt'
        process_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "check": True
        }
        
        if is_windows:
            process_kwargs["encoding"] = 'utf-8'
        
        subprocess.run(cmd, **process_kwargs)
        
        output_path = cmd[-1]  # 输出路径总是最后一个参数
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(f"✓ {method_name}成功: {timestamp}")
            return True
        else:
            logger.error(f"{method_name}失败，输出文件无效: {output_path}")
            return False
            
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logger.error(f"{method_name}失败: {error_msg}")
        return False
    except Exception as e:
        logger.error(f"{method_name}异常: {str(e)}")
        return False


def try_fallback_encoding(
    input_path: str,
    output_path: str,
    start_time: str,
    end_time: str,
    timestamp: str
) -> bool:
    """
    尝试fallback编码方案（通用方案）
    
    Args:
        input_path: 输入路径
        output_path: 输出路径
        start_time: 开始时间
        end_time: 结束时间
        timestamp: 时间戳
        
    Returns:
        bool: 是否成功
    """
    # 最简单的软件编码命令
    duration = _calculate_ffmpeg_duration(start_time, end_time)
    fallback_cmd = [
        "ffmpeg", "-y",
        "-ss", start_time,
        "-i", input_path,
        "-t", duration,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        "-preset", "ultrafast",  # 最快速度
        "-crf", "28",  # 稍微降低质量以提高兼容性
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        output_path
    ]
    
    return execute_simple_command(fallback_cmd, timestamp, "通用Fallback")


def _process_narration_only_segment(
    video_origin_path: str,
    script_item: Dict,
    tts_map: Dict,
    output_dir: str,
    encoder_config: Dict,
    hwaccel_args: List[str]
) -> Optional[str]:
    """
    处理OST=0的纯解说片段
    - 根据TTS音频时长动态裁剪
    - 移除原声，生成静音视频
    """
    _id = script_item["_id"]
    timestamp = script_item["timestamp"]

    # 获取对应的TTS结果
    tts_item = tts_map.get(_id)
    if not tts_item:
        logger.error(f"未找到片段 {_id} 的TTS结果")
        return None

    # 解析起始时间，使用TTS音频时长计算结束时间
    start_time, _ = parse_timestamp(timestamp)
    duration = tts_item["duration"]
    calculated_end_time = calculate_end_time(start_time, duration, extra_seconds=0)

    # 转换为FFmpeg兼容的时间格式
    ffmpeg_start_time = start_time.replace(',', '.')
    ffmpeg_end_time = calculated_end_time.replace(',', '.')

    # 生成输出文件名
    safe_start_time = start_time.replace(':', '-').replace(',', '-')
    safe_end_time = calculated_end_time.replace(':', '-').replace(',', '-')
    output_filename = f"ost0_{_safe_output_id(_id)}_vid_{safe_start_time}@{safe_end_time}.mp4"
    output_path = os.path.join(output_dir, output_filename)

    # 构建FFmpeg命令 - 移除音频
    cmd = _build_ffmpeg_command_with_audio_control(
        video_origin_path, output_path, ffmpeg_start_time, ffmpeg_end_time,
        encoder_config, hwaccel_args, remove_audio=True
    )

    # 执行命令
    success = execute_ffmpeg_with_fallback(
        cmd, timestamp, video_origin_path, output_path,
        ffmpeg_start_time, ffmpeg_end_time
    )

    return output_path if success else None


def _process_original_audio_segment(
    video_origin_path: str,
    script_item: Dict,
    output_dir: str,
    encoder_config: Dict,
    hwaccel_args: List[str]
) -> Optional[str]:
    """
    处理OST=1的纯原声片段
    - 严格按照脚本timestamp精确裁剪
    - 保持原声不变
    """
    _id = script_item["_id"]
    timestamp = script_item["timestamp"]

    # 严格按照timestamp进行裁剪
    start_time, end_time = parse_timestamp(timestamp)

    # 转换为FFmpeg兼容的时间格式
    ffmpeg_start_time = start_time.replace(',', '.')
    ffmpeg_end_time = end_time.replace(',', '.')

    # 生成输出文件名
    safe_start_time = start_time.replace(':', '-').replace(',', '-')
    safe_end_time = end_time.replace(':', '-').replace(',', '-')
    output_filename = f"ost1_{_safe_output_id(_id)}_vid_{safe_start_time}@{safe_end_time}.mp4"
    output_path = os.path.join(output_dir, output_filename)

    # 构建FFmpeg命令 - 保持原声
    cmd = _build_ffmpeg_command_with_audio_control(
        video_origin_path, output_path, ffmpeg_start_time, ffmpeg_end_time,
        encoder_config, hwaccel_args, remove_audio=False
    )

    # 执行命令
    success = execute_ffmpeg_with_fallback(
        cmd, timestamp, video_origin_path, output_path,
        ffmpeg_start_time, ffmpeg_end_time
    )

    return output_path if success else None


def _process_mixed_segment(
    video_origin_path: str,
    script_item: Dict,
    tts_map: Dict,
    output_dir: str,
    encoder_config: Dict,
    hwaccel_args: List[str]
) -> Optional[str]:
    """
    处理OST=2的解说+原声混合片段
    - 根据TTS音频时长动态裁剪
    - 保持原声，确保视频时长等于TTS音频时长
    """
    _id = script_item["_id"]
    timestamp = script_item["timestamp"]

    # 获取对应的TTS结果
    tts_item = tts_map.get(_id)
    if not tts_item:
        logger.error(f"未找到片段 {_id} 的TTS结果")
        return None

    # 解析起始时间，使用TTS音频时长计算结束时间
    start_time, _ = parse_timestamp(timestamp)
    duration = tts_item["duration"]
    calculated_end_time = calculate_end_time(start_time, duration, extra_seconds=0)

    # 转换为FFmpeg兼容的时间格式
    ffmpeg_start_time = start_time.replace(',', '.')
    ffmpeg_end_time = calculated_end_time.replace(',', '.')

    # 生成输出文件名
    safe_start_time = start_time.replace(':', '-').replace(',', '-')
    safe_end_time = calculated_end_time.replace(':', '-').replace(',', '-')
    output_filename = f"ost2_{_safe_output_id(_id)}_vid_{safe_start_time}@{safe_end_time}.mp4"
    output_path = os.path.join(output_dir, output_filename)

    # 构建FFmpeg命令 - 保持原声
    cmd = _build_ffmpeg_command_with_audio_control(
        video_origin_path, output_path, ffmpeg_start_time, ffmpeg_end_time,
        encoder_config, hwaccel_args, remove_audio=False
    )

    # 执行命令
    success = execute_ffmpeg_with_fallback(
        cmd, timestamp, video_origin_path, output_path,
        ffmpeg_start_time, ffmpeg_end_time
    )

    return output_path if success else None


def _build_ffmpeg_command_with_audio_control(
    input_path: str,
    output_path: str,
    start_time: str,
    end_time: str,
    encoder_config: Dict[str, str],
    hwaccel_args: List[str] = None,
    remove_audio: bool = False
) -> List[str]:
    """
    构建支持音频控制的FFmpeg命令

    Args:
        input_path: 输入视频路径
        output_path: 输出视频路径
        start_time: 开始时间
        end_time: 结束时间
        encoder_config: 编码器配置
        hwaccel_args: 硬件加速参数
        remove_audio: 是否移除音频（OST=0时为True）

    Returns:
        List[str]: ffmpeg命令列表
    """
    cmd = ["ffmpeg", "-y"]

    # 硬件加速设置（参考原有逻辑）
    if encoder_config["video_codec"] == "h264_nvenc":
        # 对于NVENC，不使用硬件解码以避免滤镜链问题
        pass
    elif hwaccel_args:
        cmd.extend(hwaccel_args)

    # 快速定位输入文件，避免长视频从头解码到目标片段
    _append_fast_seek_input(cmd, input_path, start_time, end_time)

    # 视频编码器设置
    cmd.extend(["-c:v", encoder_config["video_codec"]])

    # 音频处理
    if remove_audio:
        # OST=0: 移除音频
        cmd.extend(["-an"])  # -an 表示不包含音频流
        logger.debug("OST=0: 移除音频流")
    else:
        # OST=1,2: 保持原声
        cmd.extend(["-c:a", encoder_config["audio_codec"]])
        cmd.extend(["-ar", "44100", "-ac", "2"])
        logger.debug("OST=1/2: 保持原声")

    # 像素格式
    cmd.extend(["-pix_fmt", encoder_config["pixel_format"]])

    # 质量和预设参数（参考原有逻辑）
    if encoder_config["video_codec"] == "h264_nvenc":
        cmd.extend(["-preset", encoder_config["preset"]])
        cmd.extend(["-cq", encoder_config["quality_value"]])
        cmd.extend(["-profile:v", "main"])
    elif encoder_config["video_codec"] == "h264_amf":
        cmd.extend(["-quality", encoder_config["preset"]])
        cmd.extend(["-qp_i", encoder_config["quality_value"]])
    elif encoder_config["video_codec"] == "h264_qsv":
        cmd.extend(["-preset", encoder_config["preset"]])
        cmd.extend(["-global_quality", encoder_config["quality_value"]])
    elif encoder_config["video_codec"] == "h264_videotoolbox":
        cmd.extend(["-profile:v", "high"])
        cmd.extend(["-b:v", encoder_config["quality_value"]])
    else:
        # 软件编码器（libx264）
        cmd.extend(["-preset", encoder_config["preset"]])
        cmd.extend(["-crf", encoder_config["quality_value"]])

    # 优化参数
    cmd.extend(["-avoid_negative_ts", "make_zero"])
    cmd.extend(["-movflags", "+faststart"])

    # 输出文件
    cmd.append(output_path)

    return cmd


def clip_video_unified(
        video_origin_path: str,
        script_list: List[Dict],
        tts_results: List[Dict],
        output_dir: Optional[str] = None,
        task_id: Optional[str] = None,
        video_origin_paths: Optional[List[str]] = None
) -> Dict[str, str]:
    """
    基于OST类型的统一视频裁剪策略 - 消除双重裁剪问题

    Args:
        video_origin_path: 原始视频的路径；旧脚本或无 video_id 片段默认使用该视频
        script_list: 完整的脚本列表，包含所有片段信息
        tts_results: TTS结果列表，仅包含OST=0和OST=2的片段
        output_dir: 输出目录路径，默认为None时会自动生成
        task_id: 任务ID，用于生成唯一的输出目录，默认为None时会自动生成
        video_origin_paths: 多个原始视频路径，脚本片段可用 video_id/video_name 指定来源

    Returns:
        Dict[str, str]: 片段ID到裁剪后视频路径的映射
    """
    video_source_paths = _normalize_video_origin_paths(video_origin_path, video_origin_paths)
    if not video_source_paths:
        raise FileNotFoundError("视频文件不存在: 未提供原始视频路径")

    missing_video_paths = [item for item in video_source_paths if not os.path.exists(item)]
    if missing_video_paths:
        raise FileNotFoundError(f"视频文件不存在: {', '.join(missing_video_paths)}")

    # 如果未提供task_id，则根据输入生成一个唯一ID
    if task_id is None:
        content_for_hash = f"{json.dumps(video_source_paths, ensure_ascii=False)}_{json.dumps(script_list, ensure_ascii=False)}"
        task_id = hashlib.md5(content_for_hash.encode()).hexdigest()

    # 设置输出目录
    if output_dir is None:
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "storage", "temp", "clip_video_unified", task_id
        )

    # 确保输出目录存在
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 创建TTS结果的快速查找映射
    tts_map = {item['_id']: item for item in tts_results}

    # 获取硬件加速支持
    hwaccel_type = check_hardware_acceleration()
    hwaccel_args = []

    if hwaccel_type:
        hwaccel_args = ffmpeg_utils.get_ffmpeg_hwaccel_args()
        hwaccel_info = ffmpeg_utils.get_ffmpeg_hwaccel_info()
        logger.info(f"🚀 使用硬件加速: {hwaccel_type} ({hwaccel_info.get('message', '')})")
    else:
        logger.info("🔧 使用软件编码")

    # 获取编码器配置
    encoder_config = get_safe_encoder_config(hwaccel_type)
    logger.debug(f"编码器配置: {encoder_config}")

    # 统计信息
    total_clips = len(script_list)
    result = {}
    failed_clips = []
    success_count = 0

    logger.info(f"📹 开始统一视频裁剪，总共{total_clips}个片段，源视频{len(video_source_paths)}个")

    for i, script_item in enumerate(script_list, 1):
        _id = script_item.get("_id")
        ost = script_item.get("OST", 0)
        timestamp = script_item["timestamp"]
        source_video_path = _resolve_script_video_path(script_item, video_source_paths)

        logger.info(
            f"📹 [{i}/{total_clips}] 处理片段 ID:{_id}, OST:{ost}, "
            f"视频:{os.path.basename(source_video_path)}, 时间戳:{timestamp}"
        )

        try:
            if ost == 0:  # 纯解说片段
                output_path = _process_narration_only_segment(
                    source_video_path, script_item, tts_map, output_dir,
                    encoder_config, hwaccel_args
                )
            elif ost == 1:  # 纯原声片段
                output_path = _process_original_audio_segment(
                    source_video_path, script_item, output_dir,
                    encoder_config, hwaccel_args
                )
            elif ost == 2:  # 解说+原声混合片段
                output_path = _process_mixed_segment(
                    source_video_path, script_item, tts_map, output_dir,
                    encoder_config, hwaccel_args
                )
            else:
                logger.warning(f"未知的OST类型: {ost}，跳过片段 {_id}")
                continue

            if output_path and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                result[_id] = output_path
                success_count += 1
                logger.info(f"✅ [{i}/{total_clips}] 片段处理成功: OST={ost}, ID={_id}")
            else:
                failed_clips.append(f"ID:{_id}, OST:{ost}")
                logger.error(f"❌ [{i}/{total_clips}] 片段处理失败: OST={ost}, ID={_id}")

        except Exception as e:
            failed_clips.append(f"ID:{_id}, OST:{ost}")
            logger.error(f"❌ [{i}/{total_clips}] 片段处理异常: OST={ost}, ID={_id}, 错误: {str(e)}")

    # 最终统计
    logger.info(f"📊 统一视频裁剪完成: 成功 {success_count}/{total_clips}, 失败 {len(failed_clips)}")

    # 检查是否有失败的片段
    if failed_clips:
        logger.warning(f"⚠️  以下片段处理失败: {failed_clips}")
        if len(failed_clips) == total_clips:
            raise RuntimeError("所有视频片段处理都失败了，请检查视频文件和ffmpeg配置")
        elif len(failed_clips) > total_clips / 2:
            logger.warning(f"⚠️  超过一半的片段处理失败 ({len(failed_clips)}/{total_clips})，请检查硬件加速配置")

    if success_count > 0:
        logger.info(f"🎉 统一视频裁剪任务完成! 输出目录: {output_dir}")

    return result


def clip_video(
        video_origin_path: str,
        tts_result: List[Dict],
        output_dir: Optional[str] = None,
        task_id: Optional[str] = None
) -> Dict[str, str]:
    """
    根据时间戳裁剪视频 - 优化版本，增强Windows兼容性和错误处理

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

    # 获取硬件加速支持
    hwaccel_type = check_hardware_acceleration()
    hwaccel_args = []
    
    if hwaccel_type:
        hwaccel_args = ffmpeg_utils.get_ffmpeg_hwaccel_args()
        hwaccel_info = ffmpeg_utils.get_ffmpeg_hwaccel_info()
        logger.info(f"🚀 使用硬件加速: {hwaccel_type} ({hwaccel_info.get('message', '')})")
    else:
        logger.info("🔧 使用软件编码")

    # 获取编码器配置
    encoder_config = get_safe_encoder_config(hwaccel_type)
    logger.debug(f"编码器配置: {encoder_config}")

    # 统计信息
    total_clips = len(tts_result)
    result = {}
    failed_clips = []
    success_count = 0

    logger.info(f"📹 开始裁剪视频，总共{total_clips}个片段")

    for i, item in enumerate(tts_result, 1):
        _id = item.get("_id", item.get("timestamp", "unknown"))
        timestamp = item["timestamp"]
        start_time, _ = parse_timestamp(timestamp)

        # 根据持续时间计算真正的结束时间（加上1秒余量）
        duration = item["duration"]

        # 时长合理性检查和修正
        if duration <= 0 or duration > 300:  # 超过5分钟认为不合理
            logger.warning(f"检测到异常时长 {duration}秒，片段: {timestamp}")

            # 尝试从时间戳计算实际时长
            try:
                start_time_str, end_time_str = timestamp.split('-')

                # 解析开始时间
                if ',' in start_time_str:
                    time_part, ms_part = start_time_str.split(',')
                    h1, m1, s1 = map(int, time_part.split(':'))
                    ms1 = int(ms_part)
                else:
                    h1, m1, s1 = map(int, start_time_str.split(':'))
                    ms1 = 0

                # 解析结束时间
                if ',' in end_time_str:
                    time_part, ms_part = end_time_str.split(',')
                    h2, m2, s2 = map(int, time_part.split(':'))
                    ms2 = int(ms_part)
                else:
                    h2, m2, s2 = map(int, end_time_str.split(':'))
                    ms2 = 0

                # 计算实际时长
                start_total_ms = (h1 * 3600 + m1 * 60 + s1) * 1000 + ms1
                end_total_ms = (h2 * 3600 + m2 * 60 + s2) * 1000 + ms2
                actual_duration = (end_total_ms - start_total_ms) / 1000.0

                if actual_duration > 0 and actual_duration <= 300:
                    duration = actual_duration
                    logger.info(f"使用时间戳计算的实际时长: {duration:.3f}秒")
                else:
                    duration = 5.0  # 默认5秒
                    logger.warning(f"时间戳计算也异常，使用默认时长: {duration}秒")

            except Exception as e:
                duration = 5.0  # 默认5秒
                logger.warning(f"时长修正失败，使用默认时长: {duration}秒, 错误: {str(e)}")

        calculated_end_time = calculate_end_time(start_time, duration)

        # 转换为FFmpeg兼容的时间格式（逗号替换为点）
        ffmpeg_start_time = start_time.replace(',', '.')
        ffmpeg_end_time = calculated_end_time.replace(',', '.')

        # 格式化输出文件名（使用连字符替代冒号和逗号）
        safe_start_time = start_time.replace(':', '-').replace(',', '-')
        safe_end_time = calculated_end_time.replace(':', '-').replace(',', '-')
        output_filename = f"vid_{safe_start_time}@{safe_end_time}.mp4"
        output_path = os.path.join(output_dir, output_filename)

        # 构建FFmpeg命令
        ffmpeg_cmd = build_ffmpeg_command(
            video_origin_path, 
            output_path, 
            ffmpeg_start_time, 
            ffmpeg_end_time,
            encoder_config,
            hwaccel_args
        )

        # 执行FFmpeg命令
        logger.info(f"📹 [{i}/{total_clips}] 裁剪视频片段: {timestamp} -> {ffmpeg_start_time}到{ffmpeg_end_time}")
        
        success = execute_ffmpeg_with_fallback(
            ffmpeg_cmd, 
            timestamp,
            video_origin_path,
            output_path,
            ffmpeg_start_time,
            ffmpeg_end_time
        )
        
        if success:
            result[_id] = output_path
            success_count += 1
            logger.info(f"✅ [{i}/{total_clips}] 片段裁剪成功: {timestamp}")
        else:
            failed_clips.append(timestamp)
            logger.error(f"❌ [{i}/{total_clips}] 片段裁剪失败: {timestamp}")

    # 最终统计
    logger.info(f"📊 视频裁剪完成: 成功 {success_count}/{total_clips}, 失败 {len(failed_clips)}")
    
    # 检查是否有失败的片段
    if failed_clips:
        logger.warning(f"⚠️  以下片段裁剪失败: {failed_clips}")
        if len(failed_clips) == total_clips:
            raise RuntimeError("所有视频片段裁剪都失败了，请检查视频文件和ffmpeg配置")
        elif len(failed_clips) > total_clips / 2:
            logger.warning(f"⚠️  超过一半的片段裁剪失败 ({len(failed_clips)}/{total_clips})，请检查硬件加速配置")

    if success_count > 0:
        logger.info(f"🎉 视频裁剪任务完成! 输出目录: {output_dir}")
        
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
    subclip_path_videos = {
        '00:00:00-00:01:15': '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-00-00-00-01-15.mp4',
        '00:01:15-00:04:40': '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-01-15-00-04-40.mp4',
        '00:04:41-00:04:58': '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-04-41-00-04-58.mp4',
        '00:04:58-00:05:45': '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-04-58-00-05-45.mp4',
        '00:05:45-00:06:00': '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-05-45-00-06-00.mp4',
        '00:06:00-00:06:03': '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-06-00-00-06-03.mp4',
    }

    # 使用方法示例
    try:
        result = clip_video(video_origin_path, tts_result, subclip_path_videos)
        print("裁剪结果:")
        print(json.dumps(result, indent=4, ensure_ascii=False))
    except Exception as e:
        print(f"发生错误: {e}")
