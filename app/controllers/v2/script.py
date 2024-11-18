from fastapi import APIRouter, BackgroundTasks
from loguru import logger
import os

from app.models.schema_v2 import (
    GenerateScriptRequest, 
    GenerateScriptResponse,
    CropVideoRequest,
    CropVideoResponse,
    DownloadVideoRequest,
    DownloadVideoResponse,
    StartSubclipRequest,
    StartSubclipResponse
)
from app.models.schema import VideoClipParams
from app.services.script_service import ScriptGenerator
from app.services.video_service import VideoService
from app.utils import utils
from app.controllers.v2.base import v2_router
from app.models.schema import VideoClipParams
from app.services.youtube_service import YoutubeService
from app.services import task as task_service

router = v2_router()


@router.post(
    "/scripts/generate",
    response_model=GenerateScriptResponse,
    summary="同步请求；生成视频脚本 (V2)"
)
async def generate_script(
    request: GenerateScriptRequest,
    background_tasks: BackgroundTasks
):
    """
    生成视频脚本的V2版本API
    """
    task_id = utils.get_uuid()
    
    try:
        generator = ScriptGenerator()
        script = await generator.generate_script(
            video_path=request.video_path,
            video_theme=request.video_theme,
            custom_prompt=request.custom_prompt,
            skip_seconds=request.skip_seconds,
            threshold=request.threshold,
            vision_batch_size=request.vision_batch_size,
            vision_llm_provider=request.vision_llm_provider
        )
        
        return {
            "task_id": task_id,
            "script": script
        }
        
    except Exception as e:
        logger.exception(f"Generate script failed: {str(e)}")
        raise


@router.post(
    "/scripts/crop",
    response_model=CropVideoResponse,
    summary="同步请求；裁剪视频 (V2)"
)
async def crop_video(
    request: CropVideoRequest,
    background_tasks: BackgroundTasks
):
    """
    根据脚本裁剪视频的V2版本API
    """
    try:
        # 调用视频裁剪服务
        video_service = VideoService()
        task_id, subclip_videos = await video_service.crop_video(
            video_path=request.video_origin_path,
            video_script=request.video_script
        )
        logger.debug(f"裁剪视频成功，视频片段路径: {subclip_videos}")
        logger.debug(type(subclip_videos))
        return {
            "task_id": task_id,
            "subclip_videos": subclip_videos
        }
        
    except Exception as e:
        logger.exception(f"Crop video failed: {str(e)}")
        raise


@router.post(
    "/youtube/download",
    response_model=DownloadVideoResponse,
    summary="同步请求；下载YouTube视频 (V2)"
)
async def download_youtube_video(
    request: DownloadVideoRequest,
    background_tasks: BackgroundTasks
):
    """
    下载指定分辨率的YouTube视频
    """
    try:
        youtube_service = YoutubeService()
        task_id, output_path, filename = await youtube_service.download_video(
            url=request.url,
            resolution=request.resolution,
            output_format=request.output_format,
            rename=request.rename
        )
        
        return {
            "task_id": task_id,
            "output_path": output_path,
            "resolution": request.resolution,
            "format": request.output_format,
            "filename": filename
        }
        
    except Exception as e:
        logger.exception(f"Download YouTube video failed: {str(e)}")
        raise


@router.post(
    "/scripts/start-subclip",
    response_model=StartSubclipResponse,
    summary="异步请求；开始视频剪辑任务 (V2)"
)
async def start_subclip(
    request: VideoClipParams,
    background_tasks: BackgroundTasks
):
    """
    开始视频剪辑任务的V2版本API
    """
    try:
        # 构建参数对象
        params = VideoClipParams(
            video_origin_path=request.video_origin_path,
            video_clip_json_path=request.video_clip_json_path,
            voice_name=request.voice_name,
            voice_rate=request.voice_rate,
            voice_pitch=request.voice_pitch,
            subtitle_enabled=request.subtitle_enabled,
            video_aspect=request.video_aspect,
            n_threads=request.n_threads
        )
        
        # 在后台任务中执行视频剪辑
        background_tasks.add_task(
            task_service.start_subclip,
            task_id=request.task_id,
            params=params,
            subclip_path_videos=request.subclip_videos
        )
        
        return {
            "task_id": request.task_id,
            "state": "PROCESSING"  # 初始状态
        }
        
    except Exception as e:
        logger.exception(f"Start subclip task failed: {str(e)}")
        raise
