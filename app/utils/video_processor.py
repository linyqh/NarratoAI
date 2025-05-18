"""
视频帧提取工具

这个模块提供了简单高效的视频帧提取功能。主要特点：
1. 使用ffmpeg进行视频处理，支持硬件加速
2. 按指定时间间隔提取视频关键帧
3. 支持多种视频格式
4. 支持高清视频帧输出
5. 直接从原视频提取高质量关键帧

不依赖OpenCV和sklearn等库，只使用ffmpeg作为外部依赖，降低了安装和使用的复杂度。
"""

import os
import re
import time
import subprocess
from typing import List, Dict
from loguru import logger
from tqdm import tqdm

from app.utils import ffmpeg_utils


class VideoProcessor:
    def __init__(self, video_path: str):
        """
        初始化视频处理器

        Args:
            video_path: 视频文件路径
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        self.video_path = video_path
        self.video_info = self._get_video_info()
        self.fps = float(self.video_info.get('fps', 25))
        self.duration = float(self.video_info.get('duration', 0))
        self.width = int(self.video_info.get('width', 0))
        self.height = int(self.video_info.get('height', 0))
        self.total_frames = int(self.fps * self.duration)

    def _get_video_info(self) -> Dict[str, str]:
        """
        使用ffprobe获取视频信息

        Returns:
            Dict[str, str]: 包含视频基本信息的字典
        """
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,duration",
            "-of", "default=noprint_wrappers=1:nokey=0",
            self.video_path
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split('\n')
            info = {}
            for line in lines:
                if '=' in line:
                    key, value = line.split('=', 1)
                    info[key] = value

            # 处理帧率（可能是分数形式）
            if 'r_frame_rate' in info:
                try:
                    num, den = map(int, info['r_frame_rate'].split('/'))
                    info['fps'] = str(num / den)
                except ValueError:
                    info['fps'] = info.get('r_frame_rate', '25')

            return info

        except subprocess.CalledProcessError as e:
            logger.error(f"获取视频信息失败: {e.stderr}")
            return {
                'width': '1280',
                'height': '720',
                'fps': '25',
                'duration': '0'
            }

    def extract_frames_by_interval(self, output_dir: str, interval_seconds: float = 5.0,
                                  use_hw_accel: bool = True) -> List[int]:
        """
        按指定时间间隔提取视频帧

        Args:
            output_dir: 输出目录
            interval_seconds: 帧提取间隔（秒）
            use_hw_accel: 是否使用硬件加速

        Returns:
            List[int]: 提取的帧号列表
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # 计算起始时间和帧提取点
        start_time = 0
        end_time = self.duration
        extraction_times = []

        current_time = start_time
        while current_time < end_time:
            extraction_times.append(current_time)
            current_time += interval_seconds

        if not extraction_times:
            logger.warning("未找到需要提取的帧")
            return []

        # 确定硬件加速器选项
        hw_accel = []
        if use_hw_accel and ffmpeg_utils.is_ffmpeg_hwaccel_available():
            hw_accel = ffmpeg_utils.get_ffmpeg_hwaccel_args()

        # 提取帧
        frame_numbers = []
        for i, timestamp in enumerate(tqdm(extraction_times, desc="提取视频帧")):
            frame_number = int(timestamp * self.fps)
            frame_numbers.append(frame_number)

            # 格式化时间戳字符串 (HHMMSSmmm)
            hours = int(timestamp // 3600)
            minutes = int((timestamp % 3600) // 60)
            seconds = int(timestamp % 60)
            milliseconds = int((timestamp % 1) * 1000)
            time_str = f"{hours:02d}{minutes:02d}{seconds:02d}{milliseconds:03d}"

            output_path = os.path.join(output_dir, f"keyframe_{frame_number:06d}_{time_str}.jpg")

            # 使用ffmpeg提取单帧
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
            ]

            # 添加硬件加速参数
            cmd.extend(hw_accel)

            cmd.extend([
                "-ss", str(timestamp),
                "-i", self.video_path,
                "-vframes", "1",
                "-q:v", "1",  # 最高质量
                "-y",
                output_path
            ])

            try:
                subprocess.run(cmd, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                logger.warning(f"提取帧 {frame_number} 失败: {e.stderr}")

        logger.info(f"成功提取了 {len(frame_numbers)} 个视频帧")
        return frame_numbers

    def _detect_hw_accelerator(self) -> List[str]:
        """
        检测系统可用的硬件加速器

        Returns:
            List[str]: 硬件加速器ffmpeg命令参数
        """
        # 使用集中式硬件加速检测
        if ffmpeg_utils.is_ffmpeg_hwaccel_available():
            return ffmpeg_utils.get_ffmpeg_hwaccel_args()
        return []

    def process_video_pipeline(self,
                              output_dir: str,
                              interval_seconds: float = 5.0,  # 帧提取间隔（秒）
                              use_hw_accel: bool = True) -> None:
        """
        执行简化的视频处理流程，直接从原视频按固定时间间隔提取帧

        Args:
            output_dir: 输出目录
            interval_seconds: 帧提取间隔（秒）
            use_hw_accel: 是否使用硬件加速
        """
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)

        try:
            # 直接从原视频提取关键帧
            logger.info(f"从视频间隔 {interval_seconds} 秒提取关键帧...")
            self.extract_frames_by_interval(
                output_dir,
                interval_seconds=interval_seconds,
                use_hw_accel=use_hw_accel
            )

            logger.info(f"处理完成！视频帧已保存在: {output_dir}")

        except Exception as e:
            import traceback
            logger.error(f"视频处理失败: \n{traceback.format_exc()}")
            raise


if __name__ == "__main__":
    import time

    start_time = time.time()

    # 使用示例
    processor = VideoProcessor("./resource/videos/test.mp4")

    # 设置间隔为3秒提取帧
    processor.process_video_pipeline(
        output_dir="output",
        interval_seconds=3.0,
        use_hw_accel=True
    )

    end_time = time.time()
    print(f"处理完成！总耗时: {end_time - start_time:.2f} 秒")
