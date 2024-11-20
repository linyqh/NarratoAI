"""
使用 moviepy 库剪辑指定时间戳视频，支持时分秒毫秒精度
"""

from moviepy.editor import VideoFileClip
from datetime import datetime
import os


def time_str_to_seconds(time_str: str) -> float:
    """
    将时间字符串转换为秒数
    参数:
        time_str: 格式为"HH:MM:SS,mmm"的时间字符串，例如"00:01:23,456"
    返回:
        转换后的秒数(float)
    """
    try:
        # 分离时间和毫秒
        time_part, ms_part = time_str.split(',')
        # 转换时分秒
        time_obj = datetime.strptime(time_part, "%H:%M:%S")
        # 计算总秒数
        total_seconds = time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second
        # 添加毫秒部分
        total_seconds += int(ms_part) / 1000
        return total_seconds
    except ValueError as e:
        raise ValueError("时间格式错误，请使用 HH:MM:SS,mmm 格式，例如 00:01:23,456") from e


def format_duration(seconds: float) -> str:
    """
    将秒数转换为可读的时间格式
    参数:
        seconds: 秒数
    返回:
        格式化的时间字符串 (HH:MM:SS,mmm)
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds_remain = seconds % 60
    whole_seconds = int(seconds_remain)
    milliseconds = int((seconds_remain - whole_seconds) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def cut_video(video_path: str, start_time: str, end_time: str, output_path: str) -> None:
    """
    剪辑视频
    参数:
        video_path: 视频文件路径
        start_time: 开始时间 (格式: "HH:MM:SS,mmm")
        end_time: 结束时间 (格式: "HH:MM:SS,mmm")
        output_path: 输出文件路径
    """
    try:
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # 如果输出文件已存在，先尝试删除
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except PermissionError:
                print(f"无法删除已存在的文件：{output_path}，请确保文件未被其他程序占用")
                return
        
        # 转换时间字符串为秒数
        start_seconds = time_str_to_seconds(start_time)
        end_seconds = time_str_to_seconds(end_time)
        
        # 加载视频文件
        video = VideoFileClip(video_path)
        
        # 验证时间范围
        if start_seconds >= video.duration or end_seconds > video.duration:
            raise ValueError(f"剪辑时间超出视频长度！视频总长度为: {format_duration(video.duration)}")
        
        if start_seconds >= end_seconds:
            raise ValueError("结束时间必须大于开始时间！")
        
        # 计算剪辑时长
        clip_duration = end_seconds - start_seconds
        print(f"原视频总长度: {format_duration(video.duration)}")
        print(f"剪辑时长: {format_duration(clip_duration)}")
        print(f"剪辑区间: {start_time} -> {end_time}")
        
        # 剪辑视频
        video = video.subclip(start_seconds, end_seconds)
        
        # 添加错误处理的写入过程
        try:
            video.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile='temp-audio.m4a',
                remove_temp=True
            )
        except IOError as e:
            print(f"写入视频文件时发生错误：{str(e)}")
            raise
        finally:
            # 确保资源被释放
            video.close()
            
    except Exception as e:
        print(f"视频剪辑过程中发生错误：{str(e)}")
        raise


if __name__ == "__main__":
    cut_video(
        video_path="/Users/apple/Desktop/NarratoAI/resource/videos/duanju_yuansp.mp4",
        start_time="00:00:00,789",
        end_time="00:02:00,123",
        output_path="/Users/apple/Desktop/NarratoAI/resource/videos/duanju_yuansp_cut3.mp4"
    )
