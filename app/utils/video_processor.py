import cv2
import numpy as np
from sklearn.cluster import MiniBatchKMeans
import os
import re
from typing import List, Tuple, Generator
from loguru import logger
import gc
from tqdm import tqdm


class VideoProcessor:
    def __init__(self, video_path: str, batch_size: int = 100):
        """
        初始化视频处理器
        
        Args:
            video_path: 视频文件路径
            batch_size: 批处理大小，控制内存使用
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
        self.video_path = video_path
        self.batch_size = batch_size
        self.cap = cv2.VideoCapture(video_path)
        
        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开视频文件: {video_path}")
        
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = int(self.cap.get(cv2.CAP_PROP_FPS))

    def __del__(self):
        """析构函数，确保视频资源被释放"""
        if hasattr(self, 'cap'):
            self.cap.release()
        gc.collect()

    def preprocess_video(self) -> Generator[Tuple[int, np.ndarray], None, None]:
        """
        使用生成器方式分批读取视频帧
        
        Yields:
            Tuple[int, np.ndarray]: (帧索引, 视频帧)
        """
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        frame_idx = 0
        
        while self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                break
                
            # 降低分辨率以减少内存使用
            frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            yield frame_idx, frame
            
            frame_idx += 1
            
            # 定期进行垃圾回收
            if frame_idx % 1000 == 0:
                gc.collect()

    def detect_shot_boundaries(self, threshold: int = 70) -> List[int]:
        """
        使用批处理方式检测镜头边界
        
        Args:
            threshold: 差异阈值
            
        Returns:
            List[int]: 镜头边界帧的索引列表
        """
        shot_boundaries = []
        prev_frame = None
        prev_idx = -1
        
        pbar = tqdm(self.preprocess_video(), 
                   total=self.total_frames,
                   desc="检测镜头边界",
                   unit="帧")
        
        for frame_idx, curr_frame in pbar:
            if prev_frame is not None:
                prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
                curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
                
                diff = np.mean(np.abs(curr_gray.astype(float) - prev_gray.astype(float)))
                if diff > threshold:
                    shot_boundaries.append(frame_idx)
                    pbar.set_postfix({"检测到边界": len(shot_boundaries)})
            
            prev_frame = curr_frame.copy()
            prev_idx = frame_idx
            
            del curr_frame
            if frame_idx % 100 == 0:
                gc.collect()
        
        return shot_boundaries

    def process_shot(self, shot_frames: List[Tuple[int, np.ndarray]]) -> Tuple[np.ndarray, int]:
        """
        处理单个镜头的帧
        
        Args:
            shot_frames: 镜头中的帧列表
            
        Returns:
            Tuple[np.ndarray, int]: (关键帧, 帧索引)
        """
        if not shot_frames:
            return None, -1
            
        frame_features = []
        frame_indices = []
        
        for idx, frame in tqdm(shot_frames, 
                             desc="处理镜头帧",
                             unit="帧",
                             leave=False):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            resized_gray = cv2.resize(gray, (32, 32))
            frame_features.append(resized_gray.flatten())
            frame_indices.append(idx)
            
        frame_features = np.array(frame_features)
        
        kmeans = MiniBatchKMeans(n_clusters=1, batch_size=min(len(frame_features), 100),
                                random_state=0).fit(frame_features)
        
        center_idx = np.argmin(np.sum((frame_features - kmeans.cluster_centers_[0]) ** 2, axis=1))
        
        return shot_frames[center_idx][1], frame_indices[center_idx]

    def extract_keyframes(self, shot_boundaries: List[int]) -> Generator[Tuple[np.ndarray, int], None, None]:
        """
        使用生成器方式提取关键帧
        
        Args:
            shot_boundaries: 镜头边界列表
            
        Yields:
            Tuple[np.ndarray, int]: (关键帧, 帧索引)
        """
        shot_frames = []
        current_shot_start = 0
        
        for frame_idx, frame in self.preprocess_video():
            if frame_idx in shot_boundaries:
                if shot_frames:
                    keyframe, keyframe_idx = self.process_shot(shot_frames)
                    if keyframe is not None:
                        yield keyframe, keyframe_idx
                    
                    # 清理内存
                    shot_frames.clear()
                    gc.collect()
                
                current_shot_start = frame_idx
            
            shot_frames.append((frame_idx, frame))
            
            # 控制单个镜头的最大帧数
            if len(shot_frames) > self.batch_size:
                keyframe, keyframe_idx = self.process_shot(shot_frames)
                if keyframe is not None:
                    yield keyframe, keyframe_idx
                shot_frames.clear()
                gc.collect()
        
        # 处理最后一个镜头
        if shot_frames:
            keyframe, keyframe_idx = self.process_shot(shot_frames)
            if keyframe is not None:
                yield keyframe, keyframe_idx

    def process_video(self, output_dir: str, skip_seconds: float = 0) -> None:
        """
        处理视频并提取关键帧，使用分批处理方式
        
        Args:
            output_dir: 输出目录
            skip_seconds: 跳过视频开头的秒数
        """
        try:
            # 创建输出目录
            os.makedirs(output_dir, exist_ok=True)
            
            # 计算要跳过的帧数
            skip_frames = int(skip_seconds * self.fps)
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, skip_frames)
            
            # 检测镜头边界
            logger.info("开始检测镜头边界...")
            shot_boundaries = self.detect_shot_boundaries()
            
            # 提取关键帧
            logger.info("开始提取关键帧...")
            frame_count = 0
            
            pbar = tqdm(self.extract_keyframes(shot_boundaries),
                       desc="提取关键帧",
                       unit="帧")
            
            for keyframe, frame_idx in pbar:
                if frame_idx < skip_frames:
                    continue
                    
                # 计算时间戳
                timestamp = frame_idx / self.fps
                hours = int(timestamp // 3600)
                minutes = int((timestamp % 3600) // 60)
                seconds = int(timestamp % 60)
                time_str = f"{hours:02d}{minutes:02d}{seconds:02d}"
                
                # 保存关键帧
                output_path = os.path.join(output_dir, 
                                         f'keyframe_{frame_idx:06d}_{time_str}.jpg')
                cv2.imwrite(output_path, keyframe)
                frame_count += 1
                
                pbar.set_postfix({"已保存": frame_count})
                
                if frame_count % 10 == 0:
                    gc.collect()
            
            logger.info(f"关键帧提取完成，共保存 {frame_count} 帧到 {output_dir}")
            
        except Exception as e:
            logger.error(f"视频处理失败: {str(e)}")
            raise
        finally:
            # 确保资源被释放
            self.cap.release()
            gc.collect()
