import cv2
import numpy as np
from sklearn.cluster import KMeans
import os
import re
from typing import List, Tuple, Generator


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
            threshold: 差异阈值
            
        Returns:
            List[int]: 镜头边界帧的索引列表
        """
        shot_boundaries = []
        for i in range(1, len(frames)):
            prev_frame = cv2.cvtColor(frames[i - 1], cv2.COLOR_BGR2GRAY)
            curr_frame = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
            diff = np.mean(np.abs(curr_frame.astype(int) - prev_frame.astype(int)))
            if diff > threshold:
                shot_boundaries.append(i)
        return shot_boundaries

    def extract_keyframes(self, frames: List[np.ndarray], shot_boundaries: List[int]) -> Tuple[List[np.ndarray], List[int]]:
        """
        从每个镜头中提取关键帧
        
        Args:
            frames: 视频帧列表
            shot_boundaries: 镜头边界列表
            
        Returns:
            Tuple[List[np.ndarray], List[int]]: 关���帧列表和对应的帧索引
        """
        keyframes = []
        keyframe_indices = []
        
        for i in range(len(shot_boundaries)):
            start = shot_boundaries[i - 1] if i > 0 else 0
            end = shot_boundaries[i]
            shot_frames = frames[start:end]

            frame_features = np.array([cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).flatten() 
                                     for frame in shot_frames])
            kmeans = KMeans(n_clusters=1, random_state=0).fit(frame_features)
            center_idx = np.argmin(np.sum((frame_features - kmeans.cluster_centers_[0]) ** 2, axis=1))

            keyframes.append(shot_frames[center_idx])
            keyframe_indices.append(start + center_idx)

        return keyframes, keyframe_indices

    def save_keyframes(self, keyframes: List[np.ndarray], keyframe_indices: List[int], 
                      output_dir: str) -> None:
        """
        保存关键帧到指定目录，文件名格式为：keyframe_帧序号_时间戳.jpg
        
        Args:
            keyframes: 关键帧列表
            keyframe_indices: 关键帧索引列表
            output_dir: 输出目录
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        for keyframe, frame_idx in zip(keyframes, keyframe_indices):
            # 计算时间戳（秒）
            timestamp = frame_idx / self.fps
            # 将时间戳转换为 HH:MM:SS 格式
            hours = int(timestamp // 3600)
            minutes = int((timestamp % 3600) // 60)
            seconds = int(timestamp % 60)
            time_str = f"{hours:02d}{minutes:02d}{seconds:02d}"
            
            # 构建新的文件名格式：keyframe_帧序号_时间戳.jpg
            output_path = os.path.join(output_dir, 
                                     f'keyframe_{frame_idx:06d}_{time_str}.jpg')
            cv2.imwrite(output_path, keyframe)

        print(f"已保存 {len(keyframes)} 个关键帧到 {output_dir}")

    def extract_frames_by_numbers(self, frame_numbers: List[int], output_folder: str) -> None:
        """
        根据指定的帧号提取帧
        
        Args:
            frame_numbers: 要提取的帧号列表
            output_folder: 输出文件夹路径
        """
        if not frame_numbers:
            raise ValueError("未提供帧号列表")
        
        if any(fn >= self.total_frames or fn < 0 for fn in frame_numbers):
            raise ValueError("存在无效的帧号")

        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        for frame_number in frame_numbers:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = self.cap.read()

            if ret:
                # 计算时间戳
                timestamp = frame_number / self.fps
                hours = int(timestamp // 3600)
                minutes = int((timestamp % 3600) // 60)
                seconds = int(timestamp % 60)
                time_str = f"{hours:02d}{minutes:02d}{seconds:02d}"
                
                # 使用与关键帧相同的命名格式
                output_path = os.path.join(output_folder, 
                                         f"extracted_frame_{frame_number:06d}_{time_str}.jpg")
                cv2.imwrite(output_path, frame)
                print(f"已提取并保存帧 {frame_number}")
            else:
                print(f"无法读取帧 {frame_number}")

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
        # 更新正则表达式以匹配新的文件名格式：keyframe_000123_010534.jpg
        pattern = re.compile(r'keyframe_(\d+)_\d+\.jpg$')
        numbers = []
        for f in files:
            match = pattern.search(f)
            if match:
                numbers.append(int(match.group(1)))
        return sorted(numbers)

    def process_video(self, output_dir: str, skip_seconds: float = 0) -> None:
        """
        处理视频并提取关键帧
        
        Args:
            output_dir: 输出目录
            skip_seconds: 跳过视频开头的秒数
        """
        # 计算要跳过的帧数
        skip_frames = int(skip_seconds * self.fps)
        
        # 获取所有帧
        frames = list(self.preprocess_video())
        
        # 跳过指定秒数的帧
        frames = frames[skip_frames:]
        
        if not frames:
            raise ValueError(f"跳过 {skip_seconds} 秒后没有剩余帧可以处理")
        
        shot_boundaries = self.detect_shot_boundaries(frames)
        keyframes, keyframe_indices = self.extract_keyframes(frames, shot_boundaries)
        
        # 调整关键帧索引，加上跳过的帧数
        adjusted_indices = [idx + skip_frames for idx in keyframe_indices]
        self.save_keyframes(keyframes, adjusted_indices, output_dir)