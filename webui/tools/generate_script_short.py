import os
import json
import time
import traceback
import streamlit as st
from loguru import logger

from app.config import config
from app.services.upload_validation import ensure_existing_file, InputValidationError
from app.utils import utils


def generate_script_short(tr, params, custom_clips=5):
    """
    生成短视频脚本
    
    Args:
        tr: 翻译函数
        params: 视频参数对象
        custom_clips: 自定义片段数量，默认为5
    """
    progress_bar = st.progress(0)
    status_text = st.empty()

    def update_progress(progress: float, message: str = ""):
        progress_bar.progress(progress)
        if message:
            status_text.text(f"{progress}% - {message}")
        else:
            status_text.text(f"进度: {progress}%")

    try:
        with st.spinner("正在生成脚本..."):
            # ========== 严格验证：必须上传视频和字幕（与短剧解说保持一致）==========
            # 1. 验证视频文件
            video_path = getattr(params, "video_origin_path", None)
            if not video_path or not str(video_path).strip():
                st.error("请先选择视频文件")
                st.stop()

            try:
                ensure_existing_file(
                    str(video_path),
                    label="视频",
                    allowed_exts=(".mp4", ".mov", ".avi", ".flv", ".mkv"),
                )
            except InputValidationError as e:
                st.error(str(e))
                st.stop()

            # 2. 验证字幕文件（移除推断逻辑，必须上传）
            subtitle_path = st.session_state.get("subtitle_path")
            if not subtitle_path or not str(subtitle_path).strip():
                st.error("请先上传字幕文件")
                st.stop()

            try:
                subtitle_path = ensure_existing_file(
                    str(subtitle_path),
                    label="字幕",
                    allowed_exts=(".srt",),
                )
            except InputValidationError as e:
                st.error(str(e))
                st.stop()

            logger.info(f"使用用户上传的字幕文件: {subtitle_path}")

            # ========== 获取 LLM 配置 ==========
            text_provider = config.app.get('text_llm_provider', 'gemini').lower()
            text_api_key = config.app.get(f'text_{text_provider}_api_key')
            text_model = config.app.get(f'text_{text_provider}_model_name')
            text_base_url = config.app.get(f'text_{text_provider}_base_url')

            vision_llm_provider = st.session_state.get('vision_llm_providers') or config.app.get('vision_llm_provider', 'gemini')
            vision_llm_provider = vision_llm_provider.lower()
            vision_api_key = st.session_state.get(f'vision_{vision_llm_provider}_api_key') or config.app.get(f'vision_{vision_llm_provider}_api_key', "")
            vision_model = st.session_state.get(f'vision_{vision_llm_provider}_model_name') or config.app.get(f'vision_{vision_llm_provider}_model_name', "")
            vision_base_url = st.session_state.get(f'vision_{vision_llm_provider}_base_url') or config.app.get(f'vision_{vision_llm_provider}_base_url', "")

            update_progress(20, "开始准备生成脚本")

            # ========== 调用后端生成脚本 ==========
            from app.services.SDP.generate_script_short import generate_script_result

            output_path = os.path.join(utils.script_dir(), "merged_subtitle.json")

            subtitle_content = st.session_state.get("subtitle_content")
            subtitle_kwargs = (
                {"subtitle_content": str(subtitle_content)}
                if subtitle_content is not None and str(subtitle_content).strip()
                else {"subtitle_file_path": subtitle_path}
            )

            result = generate_script_result(
                api_key=text_api_key,
                model_name=text_model,
                output_path=output_path,
                base_url=text_base_url,
                custom_clips=custom_clips,
                provider=text_provider,
                **subtitle_kwargs,
            )

            if result.get("status") != "success":
                st.error(result.get("message", "生成脚本失败，请检查日志"))
                st.stop()

            script = result.get("script")
            logger.info(f"脚本生成完成 {json.dumps(script, ensure_ascii=False, indent=4)}")

            if isinstance(script, list):
                st.session_state['video_clip_json'] = script
            elif isinstance(script, str):
                st.session_state['video_clip_json'] = json.loads(script)

            update_progress(80, "脚本生成完成")

        time.sleep(0.1)
        progress_bar.progress(100)
        status_text.text("脚本生成完成！")
        st.success("视频脚本生成成功！")

    except Exception as err:
        progress_bar.progress(100)
        st.error(f"生成过程中发生错误: {str(err)}")
        logger.exception(f"生成脚本时发生错误\n{traceback.format_exc()}")
