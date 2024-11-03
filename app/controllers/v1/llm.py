from fastapi import Request, File, UploadFile
import os
from app.controllers.v1.base import new_router
from app.models.schema import (
    VideoScriptResponse,
    VideoScriptRequest,
    VideoTermsResponse,
    VideoTermsRequest,
    VideoTranscriptionRequest,
    VideoTranscriptionResponse,
)
from app.services import llm
from app.utils import utils
from app.config import config

# 认证依赖项
# router = new_router(dependencies=[Depends(base.verify_token)])
router = new_router()

# 定义上传目录
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")

@router.post(
    "/scripts",
    response_model=VideoScriptResponse,
    summary="Create a script for the video",
)
def generate_video_script(request: Request, body: VideoScriptRequest):
    video_script = llm.generate_script(
        video_subject=body.video_subject,
        language=body.video_language,
        paragraph_number=body.paragraph_number,
    )
    response = {"video_script": video_script}
    return utils.get_response(200, response)


@router.post(
    "/terms",
    response_model=VideoTermsResponse,
    summary="Generate video terms based on the video script",
)
def generate_video_terms(request: Request, body: VideoTermsRequest):
    video_terms = llm.generate_terms(
        video_subject=body.video_subject,
        video_script=body.video_script,
        amount=body.amount,
    )
    response = {"video_terms": video_terms}
    return utils.get_response(200, response)


@router.post(
    "/transcription",
    response_model=VideoTranscriptionResponse, 
    summary="Transcribe video content using Gemini"
)
async def transcribe_video(
    request: Request,
    video_name: str,
    language: str = "zh-CN",
    video_file: UploadFile = File(...)
):
    """
    使用 Gemini 转录视频内容,包括时间戳、画面描述和语音内容
    
    Args:
        video_name: 视频名称
        language: 语言代码,默认zh-CN
        video_file: 上传的视频文件
    """
    # 创建临时目录用于存储上传的视频
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    # 保存上传的视频文件
    video_path = os.path.join(UPLOAD_DIR, video_file.filename)
    with open(video_path, "wb") as buffer:
        content = await video_file.read()
        buffer.write(content)
    
    try:
        transcription = llm.gemini_video_transcription(
            video_name=video_name,
            video_path=video_path,
            language=language,
            llm_provider_video=config.app.get("video_llm_provider", "gemini")
        )
        response = {"transcription": transcription}
        return utils.get_response(200, response)
    finally:
        # 处理完成后删除临时文件
        if os.path.exists(video_path):
            os.remove(video_path)
