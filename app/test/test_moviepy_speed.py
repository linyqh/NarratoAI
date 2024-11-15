"""
使用 moviepy 优化视频处理速度的示例
包含：视频加速、多核处理、预设参数优化等
"""

from moviepy.editor import VideoFileClip
from moviepy.video.fx.speedx import speedx
import multiprocessing as mp
import time


class VideoSpeedProcessor:
    """视频速度处理器"""

    def __init__(self, input_path: str, output_path: str):
        self.input_path = input_path
        self.output_path = output_path
        # 获取CPU核心数
        self.cpu_cores = mp.cpu_count()

    def process_with_optimization(self, speed_factor: float = 1.0) -> None:
        """
        使用优化参数处理视频
        参数:
            speed_factor: 速度倍数 (1.0 为原速, 2.0 为双倍速)
        """
        start_time = time.time()
        
        # 加载视频时使用优化参数
        video = VideoFileClip(
            self.input_path,
            audio=True,  # 如果不需要音频可以设为False
            target_resolution=(720, None),  # 可以降低分辨率加快处理
            resize_algorithm='fast_bilinear'  # 使用快速的重置算法
        )

        # 应用速度变化
        if speed_factor != 1.0:
            video = speedx(video, factor=speed_factor)

        # 使用优化参数导出视频
        video.write_videofile(
            self.output_path,
            codec='libx264',  # 使用h264编码
            audio_codec='aac',  # 音频编码
            temp_audiofile='temp-audio.m4a',  # 临时音频文件
            remove_temp=True,  # 处理完成后删除临时文件
            write_logfile=False,  # 关闭日志文件
            threads=self.cpu_cores,  # 使用多核处理
            preset='ultrafast',  # 使用最快的编码预设
            ffmpeg_params=[
                '-brand', 'mp42',
                '-crf', '23',  # 压缩率，范围0-51，数值越大压缩率越高
            ]
        )

        # 释放资源
        video.close()

        end_time = time.time()
        print(f"处理完成！用时: {end_time - start_time:.2f} 秒")

    def batch_process_segments(self, segment_times: list, speed_factor: float = 1.0) -> None:
        """
        批量处理视频片段（并行处理）
        参数:
            segment_times: 列表，包含多个(start, end)时间元组
            speed_factor: 速度倍数
        """
        start_time = time.time()
        
        # 创建进程池
        with mp.Pool(processes=self.cpu_cores) as pool:
            # 准备参数
            args = [(self.input_path, start, end, speed_factor, i) 
                   for i, (start, end) in enumerate(segment_times)]
            
            # 并行处理片段
            pool.starmap(self._process_segment, args)

        end_time = time.time()
        print(f"批量处理完成！总用时: {end_time - start_time:.2f} 秒")

    @staticmethod
    def _process_segment(video_path: str, start: str, end: str, 
                        speed_factor: float, index: int) -> None:
        """处理单个视频片段"""
        # 转换时间格式
        start_sec = VideoSpeedProcessor._time_to_seconds(start)
        end_sec = VideoSpeedProcessor._time_to_seconds(end)
        
        # 加载并处理视频片段
        video = VideoFileClip(
            video_path,
            audio=True,
            target_resolution=(720, None)
        ).subclip(start_sec, end_sec)

        # 应用速度变化
        if speed_factor != 1.0:
            video = speedx(video, factor=speed_factor)

        # 保存处理后的片段
        output_path = f"../../resource/videos/segment_{index}.mp4"
        video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            preset='ultrafast',
            threads=2  # 每个进程使用的线程数
        )
        
        video.close()

    @staticmethod
    def _time_to_seconds(time_str: str) -> float:
        """将时间字符串(MM:SS)转换为秒数"""
        minutes, seconds = map(int, time_str.split(':'))
        return minutes * 60 + seconds


def test_video_speed():
    """测试视频加速处理"""
    processor = VideoSpeedProcessor(
        "../../resource/videos/best.mp4",
        "../../resource/videos/speed_up.mp4"
    )
    
    # 测试1：简单加速
    processor.process_with_optimization(speed_factor=1.5)  # 1.5倍速
    
    # 测试2：并行处理多个片段
    segments = [
        ("00:00", "01:00"),
        ("01:00", "02:00"),
        ("02:00", "03:00")
    ]
    processor.batch_process_segments(segments, speed_factor=2.0)  # 2倍速


if __name__ == "__main__":
    test_video_speed()
