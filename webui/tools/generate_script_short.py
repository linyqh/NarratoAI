import os
import json
import time
import asyncio
import traceback
import requests
import streamlit as st
from loguru import logger

from app.config import config
from webui.tools.base import chekc_video_config


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
            text_provider = config.app.get('text_llm_provider', 'gemini').lower()
            text_api_key = config.app.get(f'text_{text_provider}_api_key')
            text_model = config.app.get(f'text_{text_provider}_model_name')
            text_base_url = config.app.get(f'text_{text_provider}_base_url')
            vision_api_key = st.session_state.get(f'vision_{text_provider}_api_key', "")
            vision_model = st.session_state.get(f'vision_{text_provider}_model_name', "")
            vision_base_url = st.session_state.get(f'vision_{text_provider}_base_url', "")
            narrato_api_key = config.app.get('narrato_api_key')

            update_progress(20, "开始准备生成脚本")

            srt_path = params.video_origin_path.replace(".mp4", ".srt").replace("videos", "srt").replace("video", "subtitle")
            if not os.path.exists(srt_path):
                logger.error(f"{srt_path} 文件不存在请检查或重新转录")
                st.error(f"{srt_path} 文件不存在请检查或重新转录")
                st.stop()

            api_params = {
                "vision_api_key": vision_api_key,
                "vision_model_name": vision_model,
                "vision_base_url": vision_base_url or "",
                "text_api_key": text_api_key,
                "text_model_name": text_model,
                "text_base_url": text_base_url or ""
            }
            chekc_video_config(api_params)
            from app.services.SDP.generate_script_short import generate_script
            script = generate_script(
                srt_path=srt_path,
                output_path="resource/scripts/merged_subtitle.json",
                api_key=text_api_key,
                model_name=text_model,
                base_url=text_base_url,
                narrato_api_key=narrato_api_key,
                bert_path="app/models/bert/",
                custom_clips=custom_clips,
            )

            if script is None:
                st.error("生成脚本失败，请检查日志")
                st.stop()
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
