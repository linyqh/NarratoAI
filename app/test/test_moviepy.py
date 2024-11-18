"""
使用 moviepy 库剪辑指定时间戳视频
"""

from moviepy.editor import VideoFileClip
from datetime import datetime


def time_str_to_seconds(time_str: str) -> float:
    """
    将时间字符串转换为秒数
    参数:
        time_str: 格式为"MM:SS"的时间字符串
    返回:
        转换后的秒数
    """
    time_obj = datetime.strptime(time_str, "%M:%S")
    return time_obj.minute * 60 + time_obj.second


def format_duration(seconds: float) -> str:
    """
    将秒数转换为可读的时间格式
    参数:
        seconds: 秒数
    返回:
        格式化的时间字符串 (MM:SS)
    """
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    return f"{minutes:02d}:{remaining_seconds:02d}"


def cut_video(video_path: str, start_time: str, end_time: str, output_path: str) -> None:
    """
    剪辑视频
    参数:
        video_path: 视频文件路径
        start_time: 开始时间 (格式: "MM:SS")
        end_time: 结束时间 (格式: "MM:SS")
    """
    # 转换时间字符串为秒数
    start_seconds = time_str_to_seconds(start_time)
    end_seconds = time_str_to_seconds(end_time)
    
    # 加载视频文件
    video = VideoFileClip(video_path)
    
    # 计算剪辑时长
    clip_duration = end_seconds - start_seconds
    print(f"原视频总长度: {format_duration(video.duration)}")
    print(f"剪辑时长: {format_duration(clip_duration)}")
    
    # 剪辑视频
    video = video.subclip(start_seconds, end_seconds)
    video.write_videofile("../../resource/videos/cut_video3.mp4")
    
    # 释放资源
    video.close()


if __name__ == "__main__":
    # cut_video("E:\\NarratoAI_v0.3.5_cuda\\NarratoAI\storage\\tasks\ca4fee22-350b-47f9-bb2f-802ad96774f7\\final-2.mp4", "00:00", "07:00", "E:\\NarratoAI_v0.3.5_cuda\\NarratoAI\storage\\tasks\\yyjx2-1")
    # cut_video("E:\\NarratoAI_v0.3.5_cuda\\NarratoAI\storage\\tasks\ca4fee22-350b-47f9-bb2f-802ad96774f7\\final-2.mp4", "07:00", "14:00", "E:\\NarratoAI_v0.3.5_cuda\\NarratoAI\storage\\tasks\\yyjx2-2")
    cut_video("E:\\NarratoAI_v0.3.5_cuda\\NarratoAI\storage\\tasks\ca4fee22-350b-47f9-bb2f-802ad96774f7\\final-2.mp4", "14:00", "22:00", "E:\\NarratoAI_v0.3.5_cuda\\NarratoAI\storage\\tasks\\yyjx2-3")
