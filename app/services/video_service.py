import os
from uuid import uuid4
from loguru import logger
from typing import Dict, List, Optional, Tuple

from app.services import material
from app.models.schema import VideoClipParams
from app.utils import utils


class VideoService:
    @staticmethod
    async def crop_video(
        video_path: str,
        video_script: List[dict]
    ) -> Tuple[str, Dict[str, str]]:
        """
        裁剪视频服务
        
        Args:
            video_path: 视频文件路径
            video_script: 视频脚本列表
            
        Returns:
            Tuple[str, Dict[str, str]]: (task_id, 裁剪后的视频片段字典)
            视频片段字典格式: {timestamp: video_path}
        """
        try:
            task_id = str(uuid4())
            
            # 从脚本中提取时间戳列表
            time_list = [scene['timestamp'] for scene in video_script]
            
            # 调用裁剪服务
            subclip_videos = material.clip_videos(
                task_id=task_id,
                timestamp_terms=time_list,
                origin_video=video_path
            )
            
            if subclip_videos is None:
                raise ValueError("裁剪视频失败")
                
            # 更新脚本中的视频路径
            for scene in video_script:
                try:
                    scene['path'] = subclip_videos[scene['timestamp']]
                except KeyError as err:
                    logger.error(f"更新视频路径失败: {err}")
                    
            logger.debug(f"裁剪视频成功，共生成 {len(time_list)} 个视频片段")
            logger.debug(f"视频片段路径: {subclip_videos}")
            
            return task_id, subclip_videos
            
        except Exception as e:
            logger.exception("裁剪视频失败")
            raise 