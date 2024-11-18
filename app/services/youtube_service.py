import yt_dlp
import os
from typing import List, Dict, Optional, Tuple
from loguru import logger
from uuid import uuid4

from app.utils import utils


class YoutubeService:
    def __init__(self):
        self.supported_formats = ['mp4', 'mkv', 'webm', 'flv', 'avi']

    def _get_video_formats(self, url: str) -> List[Dict]:
        """获取视频可用的格式列表"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])

                format_list = []
                for f in formats:
                    format_info = {
                        'format_id': f.get('format_id', 'N/A'),
                        'ext': f.get('ext', 'N/A'),
                        'resolution': f.get('format_note', 'N/A'),
                        'filesize': f.get('filesize', 'N/A'),
                        'vcodec': f.get('vcodec', 'N/A'),
                        'acodec': f.get('acodec', 'N/A')
                    }
                    format_list.append(format_info)

                return format_list
        except Exception as e:
            logger.error(f"获取视频格式失败: {str(e)}")
            raise

    def _validate_format(self, output_format: str) -> None:
        """验证输出格式是否支持"""
        if output_format.lower() not in self.supported_formats:
            raise ValueError(
                f"不支持的视频格式: {output_format}。"
                f"支持的格式: {', '.join(self.supported_formats)}"
            )

    async def download_video(
            self,
            url: str,
            resolution: str,
            output_format: str = 'mp4',
            rename: Optional[str] = None
    ) -> Tuple[str, str, str]:
        """
        下载指定分辨率的视频
        
        Args:
            url: YouTube视频URL
            resolution: 目标分辨率 ('2160p', '1440p', '1080p', '720p' etc.)
            output_format: 输出视频格式
            rename: 可选的重命名
            
        Returns:
            Tuple[str, str, str]: (task_id, output_path, filename)
        """
        try:
            task_id = str(uuid4())
            self._validate_format(output_format)

            # 获取所有可用格式
            formats = self._get_video_formats(url)

            # 查找指定分辨率的最佳视频格式
            target_format = None
            for fmt in formats:
                if fmt['resolution'] == resolution and fmt['vcodec'] != 'none':
                    target_format = fmt
                    break

            if target_format is None:
                available_resolutions = set(
                    fmt['resolution'] for fmt in formats
                    if fmt['resolution'] != 'N/A' and fmt['vcodec'] != 'none'
                )
                raise ValueError(
                    f"未找到 {resolution} 分辨率的视频。"
                    f"可用分辨率: {', '.join(sorted(available_resolutions))}"
                )

            # 创建输出目录
            output_dir = utils.video_dir()
            os.makedirs(output_dir, exist_ok=True)

            # 设置下载选项
            if rename:
                # 如果指定了重命名，直接使用新名字
                filename = f"{rename}.{output_format}"
                output_template = os.path.join(output_dir, filename)
            else:
                # 否则使用任务ID和原标题
                output_template = os.path.join(output_dir, f'{task_id}_%(title)s.%(ext)s')

            ydl_opts = {
                'format': f"{target_format['format_id']}+bestaudio[ext=m4a]/best",
                'outtmpl': output_template,
                'merge_output_format': output_format.lower(),
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': output_format.lower(),
                }]
            }

            # 执行下载
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if rename:
                    # 如果指定了重命名，使用新文件名
                    output_path = output_template
                    filename = os.path.basename(output_path)
                else:
                    # 否则使用原始标题
                    video_title = info.get('title', task_id)
                    filename = f"{task_id}_{video_title}.{output_format}"
                    output_path = os.path.join(output_dir, filename)

            logger.info(f"视频下载成功: {output_path}")
            return task_id, output_path, filename

        except Exception as e:
            logger.exception("下载视频失败")
            raise
