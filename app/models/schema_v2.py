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