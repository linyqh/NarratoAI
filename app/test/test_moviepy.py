"""
使用 moviepy 库剪辑指定时间戳视频
"""

from moviepy.editor import VideoFileClip
from datetime import datetime
import os


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
        
        # 计算剪辑时长
        clip_duration = end_seconds - start_seconds
        print(f"原视频总长度: {format_duration(video.duration)}")
        print(f"剪辑时长: {format_duration(clip_duration)}")
        
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
    # cut_video("E:\\NarratoAI_v0.3.5_cuda\\NarratoAI\storage\\tasks\ca4fee22-350b-47f9-bb2f-802ad96774f7\\final-2.mp4", "00:00", "07:00", "E:\\NarratoAI_v0.3.5_cuda\\NarratoAI\storage\\tasks\\yyjx2-1")
    # cut_video("E:\\NarratoAI_v0.3.5_cuda\\NarratoAI\storage\\tasks\ca4fee22-350b-47f9-bb2f-802ad96774f7\\final-2.mp4", "07:00", "14:00", "E:\\NarratoAI_v0.3.5_cuda\\NarratoAI\storage\\tasks\\yyjx2-2")
    cut_video("E:\\NarratoAI_v0.3.5_cuda\\NarratoAI\storage\\tasks\ca4fee22-350b-47f9-bb2f-802ad96774f7\\final-2.mp4", "14:00", "22:00", "E:\\NarratoAI_v0.3.5_cuda\\NarratoAI\storage\\tasks\\yyjx2-3")
