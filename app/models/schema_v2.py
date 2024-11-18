from typing import Optional, List
from pydantic import BaseModel


class GenerateScriptRequest(BaseModel):
    video_path: str
    video_theme: Optional[str] = ""
    custom_prompt: Optional[str] = ""
    skip_seconds: Optional[int] = 0
    threshold: Optional[int] = 30
    vision_batch_size: Optional[int] = 5
    vision_llm_provider: Optional[str] = "gemini"


class GenerateScriptResponse(BaseModel):
    task_id: str
    script: List[dict]


class CropVideoRequest(BaseModel):
    video_origin_path: str
    video_script: List[dict]


class CropVideoResponse(BaseModel):
    task_id: str
    subclip_videos: dict


class DownloadVideoRequest(BaseModel):
    url: str
    resolution: str
    output_format: Optional[str] = "mp4"
    rename: Optional[str] = None


class DownloadVideoResponse(BaseModel):
    task_id: str
    output_path: str
    resolution: str
    format: str
    filename: str


class StartSubclipRequest(BaseModel):
    task_id: str
    video_origin_path: str
    video_clip_json_path: str
    voice_name: Optional[str] = None
    voice_rate: Optional[int] = 0
    voice_pitch: Optional[int] = 0
    subtitle_enabled: Optional[bool] = True
    video_aspect: Optional[str] = "16:9"
    n_threads: Optional[int] = 4
    subclip_videos: list  # 从裁剪视频接口获取的视频片段字典


class StartSubclipResponse(BaseModel):
    task_id: str
    state: str
    videos: Optional[List[str]] = None
    combined_videos: Optional[List[str]] = None
