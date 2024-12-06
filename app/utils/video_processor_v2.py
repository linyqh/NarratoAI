import cv2
import numpy as np
from sklearn.cluster import KMeans
import os
import re
from typing import List, Tuple, Generator
from loguru import logger
import subprocess
from tqdm import tqdm


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
        self.cap = cv2.VideoCapture(video_path)

        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开视频文件: {video_path}")

        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = int(self.cap.get(cv2.CAP_PROP_FPS))

    def __del__(self):
        """析构函数，确保视频资源被释放"""
        if hasattr(self, 'cap'):
            self.cap.release()

    def preprocess_video(self) -> Generator[np.ndarray, None, None]:
        """
        使用生成器方式读取视频帧

        Yields:
            np.ndarray: 视频帧
        """
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # 重置到视频开始
        while self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                break
            yield frame

    def detect_shot_boundaries(self, frames: List[np.ndarray], threshold: int = 30) -> List[int]:
        """
        使用帧差法检测镜头边界
        
        Args:
            frames: 视频帧列表
            threshold: 差异阈值，默认值调低为30
        
        Returns:
            List[int]: 镜头边界帧的索引列表
        """
        shot_boundaries = []
        if len(frames) < 2:  # 添加帧数检查
            logger.warning("视频帧数过少，无法检测场景边界")
            return [len(frames) - 1]  # 返回最后一帧作为边界
        
        for i in range(1, len(frames)):
            prev_frame = cv2.cvtColor(frames[i - 1], cv2.COLOR_BGR2GRAY)
            curr_frame = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
            
            # 计算帧差
            diff = np.mean(np.abs(curr_frame.astype(float) - prev_frame.astype(float)))
            
            if diff > threshold:
                shot_boundaries.append(i)

        # 如果没有检测到任何边界，至少返回最后一帧
        if not shot_boundaries:
            logger.warning("未检测到场景边界，将视频作为单个场景处理")
            shot_boundaries.append(len(frames) - 1)
        
        return shot_boundaries

    def extract_keyframes(self, frames: List[np.ndarray], shot_boundaries: List[int]) -> Tuple[
        List[np.ndarray], List[int]]:
        """
        从每个镜头中提取关键帧

        Args:
            frames: 视频帧列表
            shot_boundaries: 镜头边界列表

        Returns:
            Tuple[List[np.ndarray], List[int]]: 关键帧列表和对应的帧索引
        """
        keyframes = []
        keyframe_indices = []

        for i in tqdm(range(len(shot_boundaries)), desc="提取关键帧"):
            start = shot_boundaries[i - 1] if i > 0 else 0
            end = shot_boundaries[i]
            shot_frames = frames[start:end]

            if not shot_frames:
                continue

            # 将每一帧转换为灰度图并展平为一维数组
            frame_features = np.array([cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).flatten()
                                       for frame in shot_frames])
            
            try:
                # 尝试使用 KMeans
                kmeans = KMeans(n_clusters=1, random_state=0).fit(frame_features)
                center_idx = np.argmin(np.sum((frame_features - kmeans.cluster_centers_[0]) ** 2, axis=1))
            except Exception as e:
                logger.warning(f"KMeans 聚类失败，使用备选方案: {str(e)}")
                # 备选方案：选择镜头中间的帧作为关键帧
                center_idx = len(shot_frames) // 2

            keyframes.append(shot_frames[center_idx])
            keyframe_indices.append(start + center_idx)

        return keyframes, keyframe_indices

    def save_keyframes(self, keyframes: List[np.ndarray], keyframe_indices: List[int],
                       output_dir: str, desc: str = "保存关键帧") -> None:
        """
        保存关键帧到指定目录，文件名格式为：keyframe_帧序号_时间戳.jpg
        时间戳精确到毫秒，格式为：HHMMSSmmm
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        for keyframe, frame_idx in tqdm(zip(keyframes, keyframe_indices),
                                        total=len(keyframes),
                                        desc=desc):
            # 计算精确到毫秒的时间戳
            timestamp = frame_idx / self.fps
            hours = int(timestamp // 3600)
            minutes = int((timestamp % 3600) // 60)
            seconds = int(timestamp % 60)
            milliseconds = int((timestamp % 1) * 1000)  # 计算毫秒部分
            time_str = f"{hours:02d}{minutes:02d}{seconds:02d}{milliseconds:03d}"

            output_path = os.path.join(output_dir,
                                       f'keyframe_{frame_idx:06d}_{time_str}.jpg')
            cv2.imwrite(output_path, keyframe)

    def extract_frames_by_numbers(self, frame_numbers: List[int], output_folder: str) -> None:
        """
        根据指定的帧号提取帧，如果多个帧在同一毫秒内，只保留一个
        """
        if not frame_numbers:
            raise ValueError("未提供帧号列表")

        if any(fn >= self.total_frames or fn < 0 for fn in frame_numbers):
            raise ValueError("存在无效的帧号")

        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        # 用于记录已处理的时间戳（毫秒）
        processed_timestamps = set()

        for frame_number in tqdm(frame_numbers, desc="提取高清帧"):
            # 计算精确到毫秒的时间戳
            timestamp = frame_number / self.fps
            timestamp_ms = int(timestamp * 1000)  # 转换为毫秒

            # 如果这一毫秒已经处理过，跳过
            if timestamp_ms in processed_timestamps:
                continue

            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = self.cap.read()

            if ret:
                # 记录这一毫秒已经处理
                processed_timestamps.add(timestamp_ms)

                # 计算时间戳字符串
                hours = int(timestamp // 3600)
                minutes = int((timestamp % 3600) // 60)
                seconds = int(timestamp % 60)
                milliseconds = int((timestamp % 1) * 1000)  # 计算毫秒部分
                time_str = f"{hours:02d}{minutes:02d}{seconds:02d}{milliseconds:03d}"

                output_path = os.path.join(output_folder,
                                           f"keyframe_{frame_number:06d}_{time_str}.jpg")
                cv2.imwrite(output_path, frame)
            else:
                logger.info(f"无法读取帧 {frame_number}")

        logger.info(f"共提取了 {len(processed_timestamps)} 个不同时间戳的帧")

    @staticmethod
    def extract_numbers_from_folder(folder_path: str) -> List[int]:
        """
        从文件夹中提取帧号
        
        Args:
            folder_path: 关键帧文件夹路径
        
        Returns:
            List[int]: 排序后的帧号列表
        """
        files = [f for f in os.listdir(folder_path) if f.endswith('.jpg')]
        # 更新正则表达式以匹配新的文件名格式：keyframe_000123_010534123.jpg
        pattern = re.compile(r'keyframe_(\d+)_\d{9}\.jpg$')
        numbers = []
        
        for f in files:
            match = pattern.search(f)
            if match:
                numbers.append(int(match.group(1)))
            else:
                logger.warning(f"文件名格式不匹配: {f}")
        
        if not numbers:
            logger.error(f"在目录 {folder_path} 中未找到有效的关键帧文件")
        
        return sorted(numbers)

    def process_video(self, output_dir: str, skip_seconds: float = 0, threshold: int = 30) -> None:
        """
        处理视频并提取关键帧

        Args:
            output_dir: 输出目录
            skip_seconds: 跳过视频开头的秒数
        """
        skip_frames = int(skip_seconds * self.fps)

        logger.info("读取视频帧...")
        frames = []
        for frame in tqdm(self.preprocess_video(),
                          total=self.total_frames,
                          desc="读取视频"):
            frames.append(frame)

        frames = frames[skip_frames:]

        if not frames:
            raise ValueError(f"跳过 {skip_seconds} 秒后没有剩余帧可以处理")

        logger.info("检测场景边界...")
        shot_boundaries = self.detect_shot_boundaries(frames, threshold)
        logger.info(f"检测到 {len(shot_boundaries)} 个场景边界")

        keyframes, keyframe_indices = self.extract_keyframes(frames, shot_boundaries)

        adjusted_indices = [idx + skip_frames for idx in keyframe_indices]
        self.save_keyframes(keyframes, adjusted_indices, output_dir, desc="保存压缩关键帧")

    def process_video_pipeline(self,
                               output_dir: str,
                               skip_seconds: float = 0,
                               threshold: int = 20,  # 降低默认阈值
                               compressed_width: int = 320,
                               keep_temp: bool = False) -> None:
        """
        执行完整的视频处理流程
        
        Args:
            threshold: 降低默认阈值为20，使场景检测更敏感
        """
        os.makedirs(output_dir, exist_ok=True)
        temp_dir = os.path.join(output_dir, 'temp')
        compressed_dir = os.path.join(temp_dir, 'compressed')
        mini_frames_dir = os.path.join(temp_dir, 'mini_frames')
        hd_frames_dir = output_dir

        os.makedirs(temp_dir, exist_ok=True)
        os.makedirs(compressed_dir, exist_ok=True)
        os.makedirs(mini_frames_dir, exist_ok=True)
        os.makedirs(hd_frames_dir, exist_ok=True)

        mini_processor = None
        compressed_video = None

        try:
            # 1. 压缩视频
            video_name = os.path.splitext(os.path.basename(self.video_path))[0]
            compressed_video = os.path.join(compressed_dir, f"{video_name}_compressed.mp4")

            # 获取原始视频的宽度和高度
            original_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            original_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            logger.info("步骤1: 压缩视频...")
            if original_width > original_height:
                # 横版视频
                scale_filter = f'scale={compressed_width}:-1'
            else:
                # 竖版视频
                scale_filter = f'scale=-1:{compressed_width}'
            
            ffmpeg_cmd = [
                'ffmpeg', '-i', self.video_path,
                '-vf', scale_filter,
                '-y',
                compressed_video
            ]
            
            try:
                subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg 错误输出: {e.stderr}")
                raise

            # 2. 从压缩视频中提取关键帧
            logger.info("\n步骤2: 从压缩视频提取关键帧...")
            mini_processor = VideoProcessor(compressed_video)
            mini_processor.process_video(mini_frames_dir, skip_seconds, threshold)

            # 3. 从原始视频提取高清关键帧
            logger.info("\n步骤3: 提取高清关键帧...")
            frame_numbers = self.extract_numbers_from_folder(mini_frames_dir)

            if not frame_numbers:
                raise ValueError("未能从压缩视频中提取到有效的关键帧")

            self.extract_frames_by_numbers(frame_numbers, hd_frames_dir)

            logger.info(f"处理完成！高清关键帧保存在: {hd_frames_dir}")

        except Exception as e:
            import traceback
            logger.error(f"视频处理失败: \n{traceback.format_exc()}")
            raise

        finally:
            # 释放资源
            if mini_processor:
                mini_processor.cap.release()
                del mini_processor

            # 确保视频文件句柄被释放
            if hasattr(self, 'cap'):
                self.cap.release()

            # 等待资源释放
            import time
            time.sleep(0.5)

            if not keep_temp:
                try:
                    # 先删除压缩视频文件
                    if compressed_video and os.path.exists(compressed_video):
                        try:
                            os.remove(compressed_video)
                        except Exception as e:
                            logger.warning(f"删除压缩视频失败: {e}")

                    # 再删除临时目录
                    import shutil
                    if os.path.exists(temp_dir):
                        max_retries = 3
                        for i in range(max_retries):
                            try:
                                shutil.rmtree(temp_dir)
                                break
                            except Exception as e:
                                if i == max_retries - 1:
                                    logger.warning(f"清理临时文件失败: {e}")
                                else:
                                    time.sleep(1)  # 等待1秒后重试
                                    continue

                    logger.info("临时文件已清理")
                except Exception as e:
                    logger.warning(f"清理临时文件时出错: {e}")


if __name__ == "__main__":
    import time

    start_time = time.time()
    processor = VideoProcessor("E:\\projects\\NarratoAI\\resource\\videos\\test.mp4")
    processor.process_video_pipeline(output_dir="output")
    end_time = time.time()
    print(f"处理完成！总耗时: {end_time - start_time:.2f} 秒")
