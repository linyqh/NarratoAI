import os
import json
import time
import traceback
import streamlit as st
from loguru import logger

from app.config import config
from app.services.upload_validation import ensure_existing_file, InputValidationError
from app.utils import utils
from webui.tools.generate_short_summary import (
    SHORT_DRAMA_PROMPT_CATEGORY,
    SHORT_DRAMA_SEARCH_KEYWORDS,
    _build_combined_subtitle_content,
    _normalize_paths,
    analyze_short_drama_plot,
)


def generate_script_short(
    tr,
    params,
    custom_clips=5,
    subtitle_paths=None,
    video_theme=None,
    temperature=0.7,
    plot_analysis=None,
    subtitle_content=None,
    enable_web_search=False,
    video_paths=None,
    drama_genre="逆袭/复仇",
    prompt_category=SHORT_DRAMA_PROMPT_CATEGORY,
    search_keywords=SHORT_DRAMA_SEARCH_KEYWORDS,
    empty_title_message_key="Please enter short drama name before web search",
    web_search_context_description="短剧名称、人物关系、剧情背景和公开剧情梗概",
):
    """
    生成短视频脚本
    
    Args:
        tr: 翻译函数
        params: 视频参数对象
        custom_clips: 自定义片段数量，默认为5
        subtitle_paths: 已转写/上传/翻译/校准后的字幕路径列表
        video_theme: 短剧名称
        temperature: LLM温度
        plot_analysis: 已完成的剧情理解文本
        subtitle_content: 已合并的字幕文本
        enable_web_search: 是否在剧情理解前联网搜索
        video_paths: 原始视频路径列表
        drama_genre: 用户选择的短剧类型
    """
    progress_bar = st.progress(0)
    status_text = st.empty()

    def update_progress(progress: float, message: str = ""):
        progress_bar.progress(progress)
        if message:
            status_text.text(f"{progress}% - {message}")
        else:
            status_text.text(f"{tr('Progress')}: {progress}%")

    try:
        with st.spinner(tr("Generating script...")):
            # ========== 严格验证：必须上传视频和字幕（与短剧解说保持一致）==========
            # 1. 验证视频文件
            selected_video_paths = _normalize_paths(
                video_paths
                or getattr(params, "video_origin_paths", [])
                or getattr(params, "video_origin_path", "")
            )
            if not selected_video_paths:
                st.error(tr("Please select video file first"))
                st.stop()

            for video_path in selected_video_paths:
                try:
                    ensure_existing_file(
                        str(video_path),
                        label=tr("Video"),
                        allowed_exts=(".mp4", ".mov", ".avi", ".flv", ".mkv"),
                    )
                except InputValidationError as e:
                    st.error(str(e))
                    st.stop()

            # 2. 验证字幕文件（移除推断逻辑，必须上传）
            subtitle_paths = _normalize_paths(subtitle_paths or st.session_state.get("subtitle_paths") or st.session_state.get("subtitle_path"))
            if not subtitle_paths:
                st.error(tr("Please upload subtitle file first"))
                st.stop()

            validated_subtitle_paths = []
            try:
                for subtitle_path in subtitle_paths:
                    validated_subtitle_paths.append(
                        ensure_existing_file(
                            str(subtitle_path),
                            label=tr("Subtitle"),
                            allowed_exts=(".srt",),
                        )
                    )
            except InputValidationError as e:
                st.error(str(e))
                st.stop()

            logger.info(f"使用用户处理后的字幕文件: {validated_subtitle_paths}")

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

            update_progress(20, tr("Preparing script generation"))

            subtitle_content = str(subtitle_content or "").strip() or _build_combined_subtitle_content(
                validated_subtitle_paths,
                selected_video_paths,
            )
            if not subtitle_content:
                st.error(tr("Subtitle file is empty or unreadable"))
                st.stop()

            plot_analysis = str(plot_analysis or "").strip()
            if not plot_analysis:
                update_progress(35, tr("Analyzing subtitles with model..."))
                plot_analysis = analyze_short_drama_plot(
                    validated_subtitle_paths,
                    temperature,
                    tr,
                    subtitle_content=subtitle_content,
                    short_name=video_theme,
                    enable_web_search=enable_web_search,
                    video_paths=selected_video_paths,
                    prompt_category=prompt_category,
                    search_keywords=search_keywords,
                    empty_title_message_key=empty_title_message_key,
                    web_search_context_description=web_search_context_description,
                )
                if not plot_analysis:
                    st.error(tr("Script generation failed check logs"))
                    st.stop()

            # ========== 调用后端生成脚本 ==========
            from app.services.SDP.generate_script_short import generate_script_result

            output_path = os.path.join(utils.script_dir(), "merged_subtitle.json")

            update_progress(55, tr("Generating script..."))
            result = generate_script_result(
                api_key=text_api_key,
                model_name=text_model,
                output_path=output_path,
                base_url=text_base_url,
                custom_clips=custom_clips,
                provider=text_provider,
                subtitle_content=subtitle_content,
                video_paths=selected_video_paths,
                plot_analysis=plot_analysis,
                short_name=video_theme or "",
                drama_genre=drama_genre or "",
            )

            if result.get("status") != "success":
                st.error(result.get("message", tr("Script generation failed check logs")))
                st.stop()

            script = result.get("script")
            logger.info(f"脚本生成完成 {json.dumps(script, ensure_ascii=False, indent=4)}")

            if isinstance(script, list):
                st.session_state['video_clip_json'] = script
            elif isinstance(script, str):
                st.session_state['video_clip_json'] = json.loads(script)

            update_progress(80, tr("Script generation completed"))

        time.sleep(0.1)
        progress_bar.progress(100)
        status_text.text(tr("Script generation completed!"))
        st.success(tr("Video script generated successfully"))
        return {
            "script": st.session_state.get('video_clip_json', []),
            "plot_analysis": plot_analysis,
            "subtitle_content": subtitle_content,
        }

    except Exception as err:
        progress_bar.progress(100)
        st.error(f"{tr('Generation error')}: {str(err)}")
        logger.exception(f"生成脚本时发生错误\n{traceback.format_exc()}")
        return None
