import os
import json
import subprocess
import edge_tts
from edge_tts import submaker
from pydub import AudioSegment
from typing import List, Dict
from loguru import logger
from app.utils import utils


def check_ffmpeg():
    """检查FFmpeg是否已安装"""
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False


def merge_audio_files(task_id: str, audio_file_paths: List[str], total_duration: int, video_script: list):
    """
    合并多个音频文件到一个指定总时长的音频文件中，并生成相应的字幕
    :param task_id: 任务ID
    :param audio_file_paths: 音频文件路径列表
    :param total_duration: 最终音频文件的总时长（秒）
    :param video_script: JSON格式的视频脚本
    """
    output_dir = utils.task_dir(task_id)

    if not check_ffmpeg():
        logger.error("错误：FFmpeg未安装。请安装FFmpeg后再运行此脚本。")
        return None, None

    # 创建一个总时长为total_duration的空白音频
    blank_audio = AudioSegment.silent(duration=total_duration * 1000)  # pydub使用毫秒

    for audio_path in audio_file_paths:
        if not os.path.exists(audio_path):
            logger.info(f"警告：文件 {audio_path} 不存在，已跳过。")
            continue

        # 从文件名中提取时间戳
        filename = os.path.basename(audio_path)
        start_time, end_time = extract_timestamp(filename)

        # 读取音频文件
        try:
            audio = AudioSegment.from_mp3(audio_path)
        except Exception as e:
            logger.error(f"错误：无法读取文件 {audio_path}。错误信息：{str(e)}")
            continue
        
        # 将音频插入到空白音频的指定位置
        blank_audio = blank_audio.overlay(audio, position=start_time * 1000)

    # 尝试导出为WAV格式
    try:
        output_file = os.path.join(output_dir, "audio.wav")
        blank_audio.export(output_file, format="wav")
        logger.info(f"音频合并完成，已保存为 {output_file}")
    except Exception as e:
        logger.info(f"导出为WAV格式失败，尝试使用MP3格式：{str(e)}")
        try:
            output_file = os.path.join(output_dir, "audio.mp3")
            blank_audio.export(output_file, format="mp3", codec="libmp3lame")
            logger.info(f"音频合并完成，已保存为 {output_file}")
        except Exception as e:
            logger.error(f"导出音频失败：{str(e)}")
            return None, None

    return output_file

def parse_timestamp(timestamp: str):
    """解析时间戳字符串为秒数"""
    # start, end = timestamp.split('-')
    return time_to_seconds(timestamp)

def extract_timestamp(filename):
    """从文件名中提取开始和结束时间戳"""
    time_part = filename.split('_')[1].split('.')[0]
    times = time_part.split('-')

    # 将时间戳转换为秒
    start_seconds = time_to_seconds(times[0])
    end_seconds = time_to_seconds(times[1])

    return start_seconds, end_seconds


def time_to_seconds(times):
    """将 “00:06” 转换为总秒数 """
    times = times.split(':')
    return int(times[0]) * 60 + int(times[1])


if __name__ == "__main__":
    # 示例用法
    audio_files =[
        "/Users/apple/Desktop/home/NarratoAI/storage/tasks/test456/audio_00:06-00:24.mp3",
        "/Users/apple/Desktop/home/NarratoAI/storage/tasks/test456/audio_00:32-00:38.mp3",
        "/Users/apple/Desktop/home/NarratoAI/storage/tasks/test456/audio_00:43-00:52.mp3",
        "/Users/apple/Desktop/home/NarratoAI/storage/tasks/test456/audio_00:52-01:09.mp3",
        "/Users/apple/Desktop/home/NarratoAI/storage/tasks/test456/audio_01:13-01:15.mp3",
    ]
    total_duration = 38
    video_script_path = "/Users/apple/Desktop/home/NarratoAI/resource/scripts/test003.json"
    with open(video_script_path, "r", encoding="utf-8") as f:
        video_script = json.load(f)

    output_file = merge_audio_files("test456", audio_files, total_duration, video_script)
    print(output_file)
