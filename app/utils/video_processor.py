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
from app.config.ffmpeg_config import FFmpegConfigManager


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

        优化了 Windows 系统兼容性，特别是 N 卡硬件加速的滤镜链问题

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

        # 获取硬件加速信息
        hwaccel_info = ffmpeg_utils.get_ffmpeg_hwaccel_info()
        hwaccel_type = hwaccel_info.get("type", "software")

        # 提取帧 - 使用优化的进度条
        frame_numbers = []
        successful_extractions = 0
        failed_extractions = 0

        logger.info(f"开始提取 {len(extraction_times)} 个关键帧，使用 {hwaccel_type} 加速")

        with tqdm(total=len(extraction_times), desc="🎬 提取视频帧", unit="帧",
                 bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]") as pbar:
            for i, timestamp in enumerate(extraction_times):
                frame_number = int(timestamp * self.fps)
                frame_numbers.append(frame_number)

                # 格式化时间戳字符串 (HHMMSSmmm)
                hours = int(timestamp // 3600)
                minutes = int((timestamp % 3600) // 60)
                seconds = int(timestamp % 60)
                milliseconds = int((timestamp % 1) * 1000)
                time_str = f"{hours:02d}{minutes:02d}{seconds:02d}{milliseconds:03d}"

                output_path = os.path.join(output_dir, f"keyframe_{frame_number:06d}_{time_str}.jpg")

                # 构建 FFmpeg 命令 - 针对 Windows N 卡优化
                success = self._extract_single_frame_optimized(
                    timestamp, output_path, use_hw_accel, hwaccel_type
                )

                if success:
                    successful_extractions += 1
                    pbar.set_postfix({
                        "✅": successful_extractions,
                        "❌": failed_extractions,
                        "时间": f"{timestamp:.1f}s"
                    })
                else:
                    failed_extractions += 1
                    pbar.set_postfix({
                        "✅": successful_extractions,
                        "❌": failed_extractions,
                        "时间": f"{timestamp:.1f}s"
                    })

                pbar.update(1)

        # 统计结果
        total_attempts = len(extraction_times)
        success_rate = (successful_extractions / total_attempts) * 100 if total_attempts > 0 else 0

        logger.info(f"关键帧提取完成: 成功 {successful_extractions}/{total_attempts} 帧 ({success_rate:.1f}%)")

        if failed_extractions > 0:
            logger.warning(f"有 {failed_extractions} 帧提取失败，可能是硬件加速兼容性问题")

        # 验证实际生成的文件
        actual_files = [f for f in os.listdir(output_dir) if f.endswith('.jpg')]
        logger.info(f"实际生成文件数量: {len(actual_files)} 个")

        if len(actual_files) == 0:
            logger.error("未生成任何关键帧文件，可能需要禁用硬件加速")
            raise Exception("关键帧提取完全失败，请检查视频文件和 FFmpeg 配置")

        return frame_numbers

    def _extract_single_frame_optimized(self, timestamp: float, output_path: str,
                                       use_hw_accel: bool, hwaccel_type: str) -> bool:
        """
        优化的单帧提取方法，解决 Windows N 卡硬件加速兼容性问题

        Args:
            timestamp: 时间戳（秒）
            output_path: 输出文件路径
            use_hw_accel: 是否使用硬件加速
            hwaccel_type: 硬件加速类型

        Returns:
            bool: 是否成功提取
        """
        # 策略1: 优先尝试纯编码器方案（避免硬件解码滤镜链问题）
        if use_hw_accel and hwaccel_type in ["nvenc", "cuda"]:
            # 对于 NVIDIA 显卡，优先使用纯软件解码 + NVENC 编码
            if self._try_extract_with_software_decode(timestamp, output_path):
                return True

        # 策略2: 尝试标准硬件加速
        if use_hw_accel and ffmpeg_utils.is_ffmpeg_hwaccel_available():
            hw_accel = ffmpeg_utils.get_ffmpeg_hwaccel_args()
            if self._try_extract_with_hwaccel(timestamp, output_path, hw_accel):
                return True

        # 策略3: 软件方案
        if self._try_extract_with_software(timestamp, output_path):
            return True

        # 策略4: 超级兼容性方案（Windows 特殊处理）
        return self._try_extract_with_ultra_compatibility(timestamp, output_path)

    def _try_extract_with_software_decode(self, timestamp: float, output_path: str) -> bool:
        """
        使用纯软件解码提取帧（推荐用于 Windows N 卡）
        参考 clip_video.py 中的成功实现

        Args:
            timestamp: 时间戳
            output_path: 输出路径

        Returns:
            bool: 是否成功
        """
        # 参考 clip_video.py 中的兼容性方案，专门针对图片输出优化
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(timestamp),  # 先定位时间戳
            "-i", self.video_path,
            "-vframes", "1",  # 只提取一帧
            "-q:v", "2",  # 高质量
            "-pix_fmt", "yuv420p",  # 明确指定像素格式
            "-y",
            output_path
        ]

        return self._execute_ffmpeg_command(cmd, f"软件解码提取帧 {timestamp:.1f}s")

    def _try_extract_with_hwaccel(self, timestamp: float, output_path: str, hw_accel: List[str]) -> bool:
        """
        使用硬件加速提取帧

        Args:
            timestamp: 时间戳
            output_path: 输出路径
            hw_accel: 硬件加速参数

        Returns:
            bool: 是否成功
        """
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
            "-q:v", "2",
            "-pix_fmt", "yuv420p",
            "-y",
            output_path
        ])

        return self._execute_ffmpeg_command(cmd, f"硬件加速提取帧 {timestamp:.1f}s")

    def _try_extract_with_software(self, timestamp: float, output_path: str) -> bool:
        """
        使用纯软件方案提取帧（最后的备用方案）
        参考 clip_video.py 中的基本编码方案

        Args:
            timestamp: 时间戳
            output_path: 输出路径

        Returns:
            bool: 是否成功
        """
        # 最基本的兼容性方案，参考 clip_video.py 的 try_basic_fallback
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",  # 更详细的日志用于调试
            "-ss", str(timestamp),
            "-i", self.video_path,
            "-vframes", "1",
            "-q:v", "3",  # 稍微降低质量以提高兼容性
            "-pix_fmt", "yuv420p",
            "-avoid_negative_ts", "make_zero",  # 避免时间戳问题
            "-y",
            output_path
        ]

        return self._execute_ffmpeg_command(cmd, f"软件方案提取帧 {timestamp:.1f}s")

    def _try_extract_with_ultra_compatibility(self, timestamp: float, output_path: str) -> bool:
        """
        超级兼容性方案，专门解决 Windows 系统的 MJPEG 编码问题

        Args:
            timestamp: 时间戳
            output_path: 输出路径

        Returns:
            bool: 是否成功
        """
        # 方案1: 使用 PNG 格式避免 MJPEG 问题
        png_output = output_path.replace('.jpg', '.png')
        cmd1 = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(timestamp),
            "-i", self.video_path,
            "-vframes", "1",
            "-f", "image2",  # 明确指定图片格式
            "-y",
            png_output
        ]

        if self._execute_ffmpeg_command(cmd1, f"PNG格式提取帧 {timestamp:.1f}s"):
            # 如果 PNG 成功，转换为 JPG
            try:
                from PIL import Image
                with Image.open(png_output) as img:
                    # 转换为 RGB 模式（去除 alpha 通道）
                    if img.mode in ('RGBA', 'LA'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                        img = background
                    img.save(output_path, 'JPEG', quality=90)

                # 删除临时 PNG 文件
                os.remove(png_output)
                return True
            except Exception as e:
                logger.debug(f"PNG 转 JPG 失败: {e}")
                # 如果转换失败，直接重命名 PNG 为 JPG
                try:
                    os.rename(png_output, output_path)
                    return True
                except Exception:
                    pass

        # 方案2: 使用最简单的参数
        cmd2 = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-i", self.video_path,
            "-ss", str(timestamp),  # 把 -ss 放在 -i 后面
            "-vframes", "1",
            "-f", "mjpeg",  # 明确指定 MJPEG 格式
            "-q:v", "5",  # 降低质量要求
            "-y",
            output_path
        ]

        if self._execute_ffmpeg_command(cmd2, f"MJPEG格式提取帧 {timestamp:.1f}s"):
            return True

        # 方案3: 最后的尝试 - 使用 BMP 格式
        bmp_output = output_path.replace('.jpg', '.bmp')
        cmd3 = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-i", self.video_path,
            "-ss", str(timestamp),
            "-vframes", "1",
            "-f", "bmp",
            "-y",
            bmp_output
        ]

        if self._execute_ffmpeg_command(cmd3, f"BMP格式提取帧 {timestamp:.1f}s"):
            # 尝试转换 BMP 为 JPG
            try:
                from PIL import Image
                with Image.open(bmp_output) as img:
                    img.save(output_path, 'JPEG', quality=90)
                os.remove(bmp_output)
                return True
            except Exception:
                # 如果转换失败，直接重命名
                try:
                    os.rename(bmp_output, output_path)
                    return True
                except Exception:
                    pass

        return False

    def _execute_ffmpeg_command(self, cmd: List[str], description: str) -> bool:
        """
        执行 FFmpeg 命令并处理结果
        参考 clip_video.py 中的错误处理机制

        Args:
            cmd: FFmpeg 命令列表
            description: 操作描述

        Returns:
            bool: 是否成功
        """
        try:
            # 参考 clip_video.py 中的 Windows 处理方式
            is_windows = os.name == 'nt'
            process_kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "check": True,
                "timeout": 30  # 30秒超时
            }

            if is_windows:
                process_kwargs["encoding"] = 'utf-8'

            result = subprocess.run(cmd, **process_kwargs)

            # 验证输出文件
            output_path = cmd[-1]
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
            else:
                return False

        except subprocess.CalledProcessError as e:
            # 简化错误日志，仅记录关键信息
            return False
        except subprocess.TimeoutExpired:
            return False
        except Exception as e:
            return False

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

    def extract_frames_by_interval_ultra_compatible(self, output_dir: str, interval_seconds: float = 5.0) -> List[int]:
        """
        使用超级兼容性方案按指定时间间隔提取视频帧
        
        直接使用PNG格式提取，避免MJPEG编码问题，确保最高兼容性
        
        Args:
            output_dir: 输出目录
            interval_seconds: 帧提取间隔（秒）
            
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

        # 提取帧 - 使用美化的进度条
        frame_numbers = []
        successful_extractions = 0
        failed_extractions = 0

        logger.info(f"开始提取 {len(extraction_times)} 个关键帧，使用超级兼容性方案")

        with tqdm(total=len(extraction_times), desc="🎬 提取关键帧", unit="帧", 
                 bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]") as pbar:
            for i, timestamp in enumerate(extraction_times):
                frame_number = int(timestamp * self.fps)
                frame_numbers.append(frame_number)

                # 格式化时间戳字符串 (HHMMSSmmm)
                hours = int(timestamp // 3600)
                minutes = int((timestamp % 3600) // 60)
                seconds = int(timestamp % 60)
                milliseconds = int((timestamp % 1) * 1000)
                time_str = f"{hours:02d}{minutes:02d}{seconds:02d}{milliseconds:03d}"

                output_path = os.path.join(output_dir, f"keyframe_{frame_number:06d}_{time_str}.jpg")

                # 直接使用超级兼容性方案
                success = self._extract_frame_ultra_compatible(timestamp, output_path)

                if success:
                    successful_extractions += 1
                    pbar.set_postfix({
                        "✅": successful_extractions,
                        "❌": failed_extractions,
                        "时间": f"{timestamp:.1f}s"
                    })
                else:
                    failed_extractions += 1
                    pbar.set_postfix({
                        "✅": successful_extractions,
                        "❌": failed_extractions,
                        "时间": f"{timestamp:.1f}s"
                    })

                pbar.update(1)

        # 统计结果
        total_attempts = len(extraction_times)
        success_rate = (successful_extractions / total_attempts) * 100 if total_attempts > 0 else 0

        logger.info(f"关键帧提取完成: 成功 {successful_extractions}/{total_attempts} 帧 ({success_rate:.1f}%)")

        if failed_extractions > 0:
            logger.warning(f"有 {failed_extractions} 帧提取失败")

        # 验证实际生成的文件
        actual_files = [f for f in os.listdir(output_dir) if f.endswith('.jpg')]
        logger.info(f"实际生成文件数量: {len(actual_files)} 个")

        if len(actual_files) == 0:
            logger.error("未生成任何关键帧文件")
            raise Exception("关键帧提取完全失败，请检查视频文件")

        return frame_numbers

    def _extract_frame_ultra_compatible(self, timestamp: float, output_path: str) -> bool:
        """
        超级兼容性方案提取单帧
        
        Args:
            timestamp: 时间戳（秒）
            output_path: 输出文件路径
            
        Returns:
            bool: 是否成功提取
        """
        # 使用 PNG 格式避免 MJPEG 问题
        png_output = output_path.replace('.jpg', '.png')
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(timestamp),
            "-i", self.video_path,
            "-vframes", "1",
            "-f", "image2",  # 明确指定图片格式
            "-y",
            png_output
        ]

        try:
            # 执行FFmpeg命令
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
            
            # 验证PNG文件是否成功生成
            if os.path.exists(png_output) and os.path.getsize(png_output) > 0:
                # 转换PNG为JPG
                try:
                    from PIL import Image
                    with Image.open(png_output) as img:
                        # 转换为 RGB 模式（去除 alpha 通道）
                        if img.mode in ('RGBA', 'LA'):
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                            img = background
                        img.save(output_path, 'JPEG', quality=90)

                    # 删除临时 PNG 文件
                    os.remove(png_output)
                    return True
                except Exception as e:
                    logger.warning(f"PNG 转 JPG 失败: {e}")
                    # 如果转换失败，直接重命名 PNG 为 JPG
                    try:
                        os.rename(png_output, output_path)
                        return True
                    except Exception:
                        return False
            else:
                return False
                
        except subprocess.CalledProcessError as e:
            logger.warning(f"超级兼容性方案提取帧 {timestamp:.1f}s 失败: {e}")
            return False
        except subprocess.TimeoutExpired:
            logger.warning(f"超级兼容性方案提取帧 {timestamp:.1f}s 超时")
            return False
        except Exception as e:
            logger.warning(f"超级兼容性方案提取帧 {timestamp:.1f}s 异常: {e}")
            return False


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
