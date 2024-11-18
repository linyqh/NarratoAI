from fastapi import APIRouter, BackgroundTasks
from loguru import logger

from app.models.schema_v2 import GenerateScriptRequest, GenerateScriptResponse
from app.services.script_service import ScriptGenerator
from app.utils import utils
from app.controllers.v2.base import v2_router

# router = APIRouter(prefix="/api/v2", tags=["Script Generation V2"])
router = v2_router()

@router.post(
    "/scripts/generate",
    response_model=GenerateScriptResponse,
    summary="生成视频脚本 (V2)"
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