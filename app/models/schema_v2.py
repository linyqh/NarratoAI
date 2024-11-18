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
