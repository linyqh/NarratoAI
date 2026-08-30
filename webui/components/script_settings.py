import os
import glob
import json
import math
import time
import traceback
import pandas as pd
import streamlit as st
from loguru import logger

from app.config import config
from app.models.schema import VideoClipParams
from app.services.subtitle_text import decode_subtitle_bytes, read_subtitle_text
from app.utils import utils, check_script
from webui.tools.generate_script_docu import generate_script_docu
from app.services.film_vision_fusion import load_visual_evidence_artifact
from app.services.fusion_script_pipeline import FusionScriptPipeline
from app.services.documentary.frame_analysis_models import TimeRange
from app.services.fusion_workspace import locate_fusion_review_item, project_fusion_workspace
from app.services.visual_evidence_artifact import build_source_video_identity
from app.services.visual_evidence_artifact import read_highlight_candidate_intake
from webui.tools.generate_film_vision_fusion import (
    cancel_local_visual_analysis,
    collect_visual_evidence,
    estimate_local_visual_analysis,
    find_local_visual_analysis,
    list_local_visual_evidence_artifacts,
    local_visual_analysis_status,
    resume_local_visual_analysis,
    start_local_visual_analysis,
)
from webui.tools.generate_script_short import generate_script_short
from webui.tools.generate_short_summary import (
    FILM_TV_PROMPT_CATEGORY,
    FILM_TV_SEARCH_KEYWORDS,
    SHORT_DRAMA_PROMPT_CATEGORY,
    SHORT_DRAMA_SEARCH_KEYWORDS,
    analyze_short_drama_plot,
    generate_script_short_sunmmary,
    generate_short_drama_narration_copy,
    approve_fusion_segment_plan,
    acknowledge_fusion_audit,
    start_fusion_matching_task,
    find_fusion_matching_task,
    fusion_matching_task_status,
    list_fusion_matching_tasks,
    override_fusion_matching_render_warning,
    review_fusion_narrative_map,
    approve_fusion_quality_repair,
    compare_fusion_matching_versions,
    cancel_fusion_matching_task,
    ignore_fusion_quality_finding,
    restore_fusion_matching_version,
    resume_fusion_matching_task,
    undo_fusion_quality_ignore,
)


SCRIPT_TABLE_BASE_COLUMNS = ["_id", "video_id", "video_name", "timestamp", "picture", "narration", "OST"]
SCRIPT_TABLE_TEXT_COLUMNS = {"video_name", "timestamp", "picture", "narration", "value"}
MODE_FILE = "file_selection"
MODE_AUTO = "auto"
MODE_SHORT = "short"
MODE_SHORT_SUMMARY = "summary"
MODE_FILM_SUMMARY = "film_summary"
MODE_FILM_VISION_FUSION = "film_vision_fusion"
SUMMARY_SCRIPT_MODES = {MODE_SHORT_SUMMARY, MODE_FILM_SUMMARY, MODE_FILM_VISION_FUSION}
VIDEO_UPLOAD_TYPES = ["mp4", "mov", "avi", "flv", "mkv", "mpeg4"]
VIDEO_GLOB_PATTERNS = [f"*.{suffix}" for suffix in VIDEO_UPLOAD_TYPES]
SHORT_DRAMA_NARRATION_LANGUAGE_OPTIONS = [
    ("zh-CN", "简体中文（中国）"),
    ("en-US", "英语（美国）"),
    ("ja-JP", "日语（日本）"),
    ("ko-KR", "韩语（韩国）"),
    ("fr-FR", "法语（法国）"),
    ("de-DE", "德语（德国）"),
    ("es-ES", "西班牙语（西班牙）"),
    ("pt-BR", "葡萄牙语（巴西）"),
    ("ru-RU", "俄语（俄罗斯）"),
    ("custom", "自定义"),
]
SHORT_DRAMA_NARRATION_LANGUAGE_VALUES = {
    "zh-CN": "简体中文（中国）",
    "en-US": "英语（美国）",
    "ja-JP": "日语（日本）",
    "ko-KR": "韩语（韩国）",
    "fr-FR": "法语（法国）",
    "de-DE": "德语（德国）",
    "es-ES": "西班牙语（西班牙）",
    "pt-BR": "葡萄牙语（巴西）",
    "ru-RU": "俄语（俄罗斯）",
}
SHORT_DRAMA_TYPE_OPTIONS = [
    ("counterattack", "逆袭/复仇"),
    ("ceo_romance", "霸总/甜宠"),
    ("family", "家庭伦理"),
    ("costume", "古装/权谋"),
    ("suspense", "悬疑/犯罪"),
    ("urban_emotion", "都市情感"),
    ("period_rural", "年代/乡村"),
    ("custom", "自定义"),
]
SHORT_DRAMA_TYPE_VALUES = {
    "counterattack": "逆袭/复仇",
    "ceo_romance": "霸总/甜宠",
    "family": "家庭伦理",
    "costume": "古装/权谋",
    "suspense": "悬疑/犯罪",
    "urban_emotion": "都市情感",
    "period_rural": "年代/乡村",
}
FILM_TV_TYPE_OPTIONS = [
    ("drama_emotion", "剧情/情感"),
    ("suspense_crime", "悬疑/犯罪"),
    ("action_adventure", "动作/冒险"),
    ("comedy_light", "喜剧/轻松"),
    ("sci_fi_fantasy", "科幻/奇幻"),
    ("history_war", "历史/战争"),
    ("horror_thriller", "恐怖/惊悚"),
    ("custom", "自定义"),
]
FILM_TV_TYPE_VALUES = {
    "drama_emotion": "剧情/情感",
    "suspense_crime": "悬疑/犯罪",
    "action_adventure": "动作/冒险",
    "comedy_light": "喜剧/轻松",
    "sci_fi_fantasy": "科幻/奇幻",
    "history_war": "历史/战争",
    "horror_thriller": "恐怖/惊悚",
}
SHORT_DRAMA_ORIGINAL_SOUND_RATIO_OPTIONS = list(range(0, 100, 10))
DEFAULT_NARRATION_WORD_COUNT = 500
MIN_NARRATION_WORD_COUNT = 100
MAX_NARRATION_WORD_COUNT = 5000
SUMMARY_MODE_CONFIGS = {
    MODE_FILM_SUMMARY: {
        "mode_label_key": "Film TV Narration",
        "session_prefix": "film_tv",
        "prompt_category": FILM_TV_PROMPT_CATEGORY,
        "search_keywords": FILM_TV_SEARCH_KEYWORDS,
        "web_search_context_description": "影视作品名称、人物关系、剧情背景和公开剧情梗概",
        "empty_title_message_key": "Please enter film/tv title before web search",
        "title_label_key": "影视名称",
        "type_label_key": "影视类型",
        "custom_type_label_key": "自定义影视类型",
        "custom_type_placeholder_key": "例如：悬疑犯罪",
        "custom_type_empty_key": "请输入自定义影视类型",
        "narration_copy_label_key": "影视解说文案",
        "type_options": FILM_TV_TYPE_OPTIONS,
        "type_values": FILM_TV_TYPE_VALUES,
        "default_type": "drama_emotion",
        "default_type_value": "剧情/情感",
    },
    MODE_FILM_VISION_FUSION: {
        "mode_label_key": "Film Vision Fusion Narration",
        "session_prefix": "film_vision_fusion",
        "prompt_category": FILM_TV_PROMPT_CATEGORY,
        "search_keywords": FILM_TV_SEARCH_KEYWORDS,
        "web_search_context_description": "影视作品名称、人物关系、剧情背景和公开剧情梗概",
        "empty_title_message_key": "Please enter film/tv title before web search",
        "title_label_key": "影视名称",
        "type_label_key": "影视类型",
        "custom_type_label_key": "自定义影视类型",
        "custom_type_placeholder_key": "例如：悬疑犯罪",
        "custom_type_empty_key": "请输入自定义影视类型",
        "narration_copy_label_key": "影视解说文案",
        "type_options": FILM_TV_TYPE_OPTIONS,
        "type_values": FILM_TV_TYPE_VALUES,
        "default_type": "drama_emotion",
        "default_type_value": "剧情/情感",
    },
    MODE_SHORT_SUMMARY: {
        "mode_label_key": "Short Drama Summary",
        "session_prefix": "short_drama",
        "prompt_category": SHORT_DRAMA_PROMPT_CATEGORY,
        "search_keywords": SHORT_DRAMA_SEARCH_KEYWORDS,
        "web_search_context_description": "短剧名称、人物关系、剧情背景和公开剧情梗概",
        "empty_title_message_key": "Please enter short drama name before web search",
        "title_label_key": "短剧名称",
        "type_label_key": "短剧类型",
        "custom_type_label_key": "自定义短剧类型",
        "custom_type_placeholder_key": "例如：豪门虐恋",
        "custom_type_empty_key": "请输入自定义短剧类型",
        "narration_copy_label_key": "短剧解说文案",
        "type_options": SHORT_DRAMA_TYPE_OPTIONS,
        "type_values": SHORT_DRAMA_TYPE_VALUES,
        "default_type": "counterattack",
        "default_type_value": "逆袭/复仇",
    },
}


def _normalize_video_paths(paths):
    if isinstance(paths, str):
        paths = [paths]
    if not paths:
        return []

    normalized_paths = []
    seen = set()
    for path in paths:
        if not isinstance(path, str):
            continue
        path = path.strip()
        if not path or path in seen:
            continue
        normalized_paths.append(path)
        seen.add(path)
    return normalized_paths


def _set_video_origin_state(paths, params=None):
    video_paths = _normalize_video_paths(paths)
    first_video_path = video_paths[0] if video_paths else ""
    st.session_state['video_origin_paths'] = video_paths
    st.session_state['video_origin_path'] = first_video_path
    if params is not None:
        params.video_origin_path = first_video_path
        params.video_origin_paths = video_paths


def _selected_video_paths():
    video_paths = _normalize_video_paths(st.session_state.get('video_origin_paths', []))
    if not video_paths:
        video_paths = _normalize_video_paths(st.session_state.get('video_origin_path', ''))
    return video_paths


def _store_fusion_visual_evidence(evidence, *, reuse_active, visual_signature=None):
    """Keep all session projections of one visual-evidence artifact in sync."""
    st.session_state["fusion_visual_evidence"] = evidence.context
    st.session_state["fusion_highlight_candidates"] = evidence.highlight_candidates
    st.session_state["fusion_visual_artifact_path"] = evidence.artifact_path
    st.session_state["fusion_visual_reuse_active"] = bool(reuse_active)
    st.session_state["fusion_visual_source_verified"] = bool(evidence.source_verified)
    st.session_state["fusion_visual_regression_only"] = not bool(evidence.source_verified)
    st.session_state["fusion_visual_highlight_state"] = evidence.highlight_state
    st.session_state["fusion_visual_source_identity"] = evidence.artifact.get(
        "source_video_identity"
    )
    candidate_intake = read_highlight_candidate_intake(evidence.artifact)
    st.session_state["fusion_highlight_candidate_intake"] = candidate_intake
    st.session_state["fusion_highlight_candidate_items"] = list(candidate_intake.candidates)
    st.session_state["fusion_highlight_candidate_rejections"] = [
        item.to_dict() for item in candidate_intake.rejections
    ]
    if visual_signature is not None:
        st.session_state["fusion_visual_signature"] = visual_signature


def is_unverified_fusion_regression() -> bool:
    """Return whether the current draft is backed by an unverified legacy artifact."""
    return bool(st.session_state.get("fusion_visual_regression_only"))


def _uploaded_files_signature(uploaded_files):
    return "|".join(f"{uploaded_file.name}:{uploaded_file.size}" for uploaded_file in uploaded_files)


def _unique_file_path(directory, filename):
    safe_filename = os.path.basename(filename).strip()
    if not safe_filename:
        safe_filename = f"video_{int(time.time())}.mp4"

    os.makedirs(directory, exist_ok=True)
    file_name, file_extension = os.path.splitext(safe_filename)
    candidate_path = os.path.join(directory, safe_filename)
    if not os.path.exists(candidate_path):
        return candidate_path

    timestamp = time.strftime("%Y%m%d%H%M%S")
    counter = 1
    while True:
        suffix = f"_{timestamp}" if counter == 1 else f"_{timestamp}_{counter}"
        candidate_path = os.path.join(directory, f"{file_name}{suffix}{file_extension}")
        if not os.path.exists(candidate_path):
            return candidate_path
        counter += 1


def _format_file_list_for_display(paths, max_items=3):
    file_names = [os.path.basename(path) for path in _normalize_video_paths(paths)]
    if len(file_names) <= max_items:
        return ", ".join(file_names)
    visible_names = ", ".join(file_names[:max_items])
    return f"{visible_names} +{len(file_names) - max_items}"


def _safe_filename_fragment(value, fallback="translated"):
    fragment = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in str(value or "").strip()
    ).strip("_")
    return fragment or fallback


def _read_subtitle_file(path):
    try:
        return read_subtitle_text(path).text
    except Exception:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()


def _build_combined_subtitle_content(subtitle_paths, video_paths=None):
    sections = []
    subtitle_contents = {}
    video_paths = _normalize_video_paths(video_paths)
    for index, subtitle_path in enumerate(subtitle_paths, start=1):
        if not subtitle_path or not os.path.exists(subtitle_path):
            continue
        content = _read_subtitle_file(subtitle_path)
        subtitle_contents[subtitle_path] = content
        video_path = video_paths[index - 1] if index <= len(video_paths) else ""
        if video_path:
            header = (
                f"# 视频 {index}: {os.path.basename(video_path)}\n"
                f"字幕文件: {os.path.basename(subtitle_path)}"
            )
        else:
            header = f"# 视频 {index}\n字幕文件: {os.path.basename(subtitle_path)}"
        sections.append(f"{header}\n{content}".strip())
    return "\n\n".join(sections), subtitle_contents


def _selected_subtitle_paths():
    subtitle_paths = _normalize_video_paths(st.session_state.get('subtitle_paths', []))
    if not subtitle_paths:
        subtitle_paths = _normalize_video_paths(st.session_state.get('subtitle_path', ''))
    return subtitle_paths


def _set_subtitle_state(subtitle_paths):
    subtitle_paths = _normalize_video_paths(subtitle_paths)
    subtitle_content, subtitle_contents = _build_combined_subtitle_content(
        subtitle_paths,
        _selected_video_paths(),
    )
    st.session_state['subtitle_path'] = subtitle_paths[0] if subtitle_paths else None
    st.session_state['subtitle_paths'] = subtitle_paths
    st.session_state['subtitle_content'] = subtitle_content if subtitle_content else None
    st.session_state['subtitle_contents'] = subtitle_contents
    st.session_state['subtitle_file_processed'] = bool(subtitle_paths)


def _short_drama_plot_analysis_signature(subtitle_paths, video_theme, web_search_enabled, video_paths=None):
    theme = str(video_theme or "").strip() if web_search_enabled else ""
    return json.dumps(
        {
            "subtitle_paths": _normalize_video_paths(subtitle_paths),
            "video_paths": _normalize_video_paths(video_paths),
            "video_theme": theme,
            "web_search_enabled": bool(web_search_enabled),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _summary_mode_config(script_path=None):
    script_path = script_path or st.session_state.get('video_clip_json_path', MODE_FILM_SUMMARY)
    return SUMMARY_MODE_CONFIGS.get(script_path, SUMMARY_MODE_CONFIGS[MODE_SHORT_SUMMARY])


def _summary_state_key(summary_config, suffix):
    return f"{summary_config['session_prefix']}_{suffix}"


def _resolve_summary_narration_language(summary_config):
    selected_language = st.session_state.get(
        _summary_state_key(summary_config, "narration_language_option"),
        "zh-CN",
    )
    custom_language = str(
        st.session_state.get(_summary_state_key(summary_config, "custom_narration_language"), "") or ""
    ).strip()
    if selected_language == "custom" and custom_language:
        return custom_language
    return SHORT_DRAMA_NARRATION_LANGUAGE_VALUES.get(selected_language, "简体中文（中国）")


def _resolve_summary_type(summary_config):
    selected_type = st.session_state.get(
        _summary_state_key(summary_config, "type_option"),
        summary_config["default_type"],
    )
    custom_type = str(
        st.session_state.get(_summary_state_key(summary_config, "custom_type"), "") or ""
    ).strip()
    if selected_type == "custom" and custom_type:
        return custom_type
    return summary_config["type_values"].get(selected_type, summary_config["default_type_value"])


def _resolve_short_drama_narration_language():
    return _resolve_summary_narration_language(SUMMARY_MODE_CONFIGS[MODE_SHORT_SUMMARY])


def _resolve_short_drama_type():
    return _resolve_summary_type(SUMMARY_MODE_CONFIGS[MODE_SHORT_SUMMARY])


def render_script_panel(tr):
    """渲染脚本配置面板"""
    with st.container(border=True):
        st.write(tr("Video Script Configuration"))
        params = VideoClipParams()

        # 渲染脚本文件选择
        render_script_file(tr, params)

        # 渲染视频文件选择
        render_video_file(tr, params)

        # 获取当前选择的脚本类型
        script_path = st.session_state.get('video_clip_json_path', '')

        # 根据脚本类型显示不同的布局
        if script_path == "auto":
            # 画面解说
            render_video_details(tr)
        elif script_path == "short":
            # 短剧混剪
            render_short_generate_options(tr)
        elif script_path in SUMMARY_SCRIPT_MODES:
            # 影视解说 / 短剧解说
            summary_narration_panel(tr, _summary_mode_config(script_path))
            if script_path == MODE_FILM_VISION_FUSION:
                render_fusion_visual_settings(tr)
        else:
            # 默认为空
            pass

        # 渲染脚本操作按钮
        render_script_buttons(tr, params)


def render_script_file(tr, params):
    """渲染脚本文件选择"""
    # 模式选项映射，按工作流优先级展示
    mode_options = {
        tr("Film TV Narration"): MODE_FILM_SUMMARY,
        tr("Film Vision Fusion Narration"): MODE_FILM_VISION_FUSION,
        tr("Short Drama Summary"): MODE_SHORT_SUMMARY,
        tr("Auto Generate"): MODE_AUTO,
        tr("Short Generate"): MODE_SHORT,
        tr("Select/Upload Script"): MODE_FILE,
    }
    
    # 获取当前状态
    current_path = st.session_state.get('video_clip_json_path', '')
    
    # 确定当前选中的模式索引
    default_index = 0
    mode_keys = list(mode_options.keys())
    
    if current_path == "auto":
        default_index = mode_keys.index(tr("Auto Generate"))
    elif current_path == "short":
        default_index = mode_keys.index(tr("Short Generate"))
    elif current_path == "summary":
        default_index = mode_keys.index(tr("Short Drama Summary"))
    elif current_path == "film_summary":
        default_index = mode_keys.index(tr("Film TV Narration"))
    elif current_path == MODE_FILM_VISION_FUSION:
        default_index = mode_keys.index(tr("Film Vision Fusion Narration"))
    elif current_path:
        default_index = mode_keys.index(tr("Select/Upload Script"))
    else:
        default_index = 0

    # 1. 渲染功能选择组件
    default_mode_label = mode_keys[default_index]
    default_mode = mode_options[default_mode_label]

    if st.session_state.get('_switch_to_file_mode'):
        st.session_state['script_mode_selection'] = tr("Select/Upload Script")
        del st.session_state['_switch_to_file_mode']
    elif (
        'script_mode_selection' not in st.session_state
        or st.session_state['script_mode_selection'] not in mode_options
    ):
        st.session_state['script_mode_selection'] = default_mode_label
    elif mode_options[st.session_state['script_mode_selection']] != default_mode:
        st.session_state['script_mode_selection'] = default_mode_label
    
    # 定义回调函数来处理状态更新
    def update_script_mode():
        # 获取当前选中的标签
        selected_label = st.session_state.script_mode_selection
        if selected_label:
            # 更新实际的 path 状态
            new_mode = mode_options[selected_label]
            st.session_state.video_clip_json_path = new_mode
            params.video_clip_json_path = new_mode
        else:
            st.session_state.video_clip_json_path = default_mode
            params.video_clip_json_path = default_mode

    # 渲染组件
    selected_mode_label = st.selectbox(
        tr("Video Type"),
        options=mode_keys,
        index=None,
        key="script_mode_selection",
        on_change=update_script_mode,
    )
    
    # 处理旧状态为空的兜底情况
    if not selected_mode_label:
        selected_mode_label = default_mode_label
        
    selected_mode = mode_options[selected_mode_label]

    # 2. 根据选择的模式处理逻辑
    if selected_mode == MODE_FILE:
        # --- 文件选择模式 ---
        script_list = [
            (tr("None"), ""),
            (tr("Upload Script"), "upload_script")
        ]

        # 获取已有脚本文件
        suffix = "*.json"
        script_dir = utils.script_dir()
        files = glob.glob(os.path.join(script_dir, suffix))
        file_list = []

        for file in files:
            file_list.append({
                "name": os.path.basename(file),
                "file": file,
                "ctime": os.path.getctime(file)
            })

        file_list.sort(key=lambda x: x["ctime"], reverse=True)
        for file in file_list:
            display_name = file['file'].replace(config.root_dir, "")
            script_list.append((display_name, file['file']))

        # 找到保存的脚本文件在列表中的索引
        # 如果当前path是特殊值(auto/short/summary/film_summary)，则重置为空
        saved_script_path = (
            current_path
            if current_path not in [MODE_FILE, MODE_AUTO, MODE_SHORT, MODE_SHORT_SUMMARY, MODE_FILM_SUMMARY, MODE_FILM_VISION_FUSION]
            else ""
        )
        
        selected_index = 0
        for i, (_, path) in enumerate(script_list):
            if path == saved_script_path:
                selected_index = i
                break

        # 用 session_state 作为 selectbox 的唯一来源，避免同时传默认 index 和设置 key 状态。
        if (
            "script_file_selection" not in st.session_state
            or st.session_state["script_file_selection"] >= len(script_list)
        ):
            st.session_state["script_file_selection"] = selected_index
        elif saved_script_path and selected_index > 0:
            st.session_state['script_file_selection'] = selected_index

        selected_script_index = st.selectbox(
            tr("Script Files"),
            index=None,
            options=range(len(script_list)),
            format_func=lambda x: script_list[x][0],
            key="script_file_selection"
        )

        script_path = script_list[selected_script_index][1]
        # 只有当用户实际选择了脚本时才更新路径，避免覆盖已保存的路径
        if script_path:
            st.session_state['video_clip_json_path'] = script_path
            params.video_clip_json_path = script_path
        elif saved_script_path:
            # 如果用户选择了 "None" 但之前有保存的脚本，保持原有路径
            st.session_state['video_clip_json_path'] = saved_script_path
            params.video_clip_json_path = saved_script_path

        # 处理脚本上传
        if script_path == "upload_script":
            uploaded_file = st.file_uploader(
                tr("Upload Script File"),
                type=["json"],
                accept_multiple_files=False,
            )

            if uploaded_file is not None:
                try:
                    # 读取上传的JSON内容并验证格式
                    script_content = uploaded_file.read().decode('utf-8')
                    json_data = json.loads(script_content)

                    # 保存到脚本目录
                    safe_filename = os.path.basename(uploaded_file.name)
                    script_file_path = os.path.join(script_dir, safe_filename)
                    file_name, file_extension = os.path.splitext(safe_filename)

                    # 如果文件已存在,添加时间戳
                    if os.path.exists(script_file_path):
                        timestamp = time.strftime("%Y%m%d%H%M%S")
                        file_name_with_timestamp = f"{file_name}_{timestamp}"
                        script_file_path = os.path.join(script_dir, file_name_with_timestamp + file_extension)

                    # 写入文件
                    with open(script_file_path, "w", encoding='utf-8') as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=2)

                    # 更新状态
                    st.success(tr("Script Uploaded Successfully"))
                    st.session_state['video_clip_json_path'] = script_file_path
                    params.video_clip_json_path = script_file_path
                    time.sleep(1)
                    st.rerun()

                except json.JSONDecodeError:
                    st.error(tr("Invalid JSON format"))
                except Exception as e:
                    st.error(f"{tr('Upload failed')}: {str(e)}")
    else:
        # --- 功能生成模式 ---
        st.session_state['video_clip_json_path'] = selected_mode
        params.video_clip_json_path = selected_mode


def render_video_file(tr, params):
    """渲染视频文件选择"""
    source_options = {
        tr("Select from resource directory"): "resource",
        tr("Upload Local Files"): "upload",
    }
    source_labels = list(source_options.keys())
    default_source_label = source_labels[0]
    source_default_version = "resource_first_v3"

    if st.session_state.get('_video_source_default_version') != source_default_version:
        if (
            st.session_state.get('video_source_selection') not in source_options
            or not _selected_video_paths()
        ):
            st.session_state['video_source_selection'] = default_source_label
        st.session_state['_video_source_default_version'] = source_default_version
    elif st.session_state.get('video_source_selection') not in source_options:
        st.session_state['video_source_selection'] = default_source_label

    current_source = st.session_state['video_source_selection']
    source_caption = (
        tr("Select a video from resource videos directory")
        if source_options[current_source] == "resource"
        else tr("Upload new video files up to 2GB each")
    )
    st.markdown(f"**{tr('Video Source')}**  :gray[{source_caption}]")

    source = st.pills(
        tr("Video Source"),
        options=source_labels,
        selection_mode="single",
        key="video_source_selection",
        label_visibility="collapsed",
        width="stretch",
    )
    if not source:
        source = default_source_label

    if source_options[source] == "resource":
        video_files = []
        for suffix in VIDEO_GLOB_PATTERNS:
            video_files.extend(glob.glob(os.path.join(utils.video_dir(), suffix)))

        video_files = sorted(video_files, key=os.path.getctime, reverse=True)
        saved_video_path = st.session_state.get('video_origin_path', '')
        selected_video_path = st.session_state.get('resource_video_selection')
        if selected_video_path not in video_files:
            st.session_state['resource_video_selection'] = (
                saved_video_path if saved_video_path in video_files else None
            )

        def format_video_name(path):
            return path.replace(config.root_dir, "")

        video_path = st.selectbox(
            tr("Select Video"),
            options=video_files,
            index=None,
            placeholder=tr("Choose a video file"),
            format_func=format_video_name,
            key="resource_video_selection",
        )

        if video_path:
            _set_video_origin_state([video_path], params)
        else:
            _set_video_origin_state([], params)
            if not video_files:
                st.info(tr("No video files found in resource videos directory"))
        return

    if source_options[source] == "upload":
        uploaded_files = st.file_uploader(
            tr("Upload Video"),
            type=VIDEO_UPLOAD_TYPES,
            accept_multiple_files=True,
            key="video_file_uploader",
        )

        if not uploaded_files:
            _set_video_origin_state([], params)
            st.session_state['video_file_processed'] = False
            st.session_state['uploaded_video_path'] = ""
            st.session_state['uploaded_video_paths'] = []
            st.session_state['uploaded_video_signature'] = ""
        else:
            uploaded_signature = _uploaded_files_signature(uploaded_files)
            uploaded_video_paths = _normalize_video_paths(st.session_state.get('uploaded_video_paths', []))
            is_processed = (
                st.session_state.get('video_file_processed', False)
                and st.session_state.get('uploaded_video_signature') == uploaded_signature
                and uploaded_video_paths
                and all(os.path.exists(path) for path in uploaded_video_paths)
            )

            if is_processed:
                _set_video_origin_state(uploaded_video_paths, params)
            else:
                video_paths = []
                for uploaded_file in uploaded_files:
                    video_file_path = _unique_file_path(utils.video_dir(), uploaded_file.name)
                    with open(video_file_path, "wb") as f:
                        f.write(uploaded_file.read())
                    video_paths.append(video_file_path)

                _set_video_origin_state(video_paths, params)
                st.session_state['uploaded_video_path'] = video_paths[0] if video_paths else ""
                st.session_state['uploaded_video_paths'] = video_paths
                st.session_state['uploaded_video_signature'] = uploaded_signature
                st.session_state['video_file_processed'] = True

            current_video_paths = _selected_video_paths()
            if current_video_paths:
                st.info(
                    tr("Selected videos for processing").format(
                        count=len(current_video_paths),
                        files=_format_file_list_for_display(current_video_paths),
                    )
                )


def render_short_generate_options(tr):
    """
    渲染Short Generate模式下的特殊选项
    在Short Generate模式下，替换原有的输入框为自定义片段选项
    """
    summary_config = SUMMARY_MODE_CONFIGS[MODE_SHORT_SUMMARY]
    summary_narration_panel(tr, summary_config)

    type_option_key = _summary_state_key(summary_config, "type_option")
    custom_type_key = _summary_state_key(summary_config, "custom_type")
    type_options = [code for code, _ in summary_config["type_options"]]
    if st.session_state.get(type_option_key) not in type_options:
        st.session_state[type_option_key] = summary_config["default_type"]

    show_custom_type = st.session_state.get(type_option_key, summary_config["default_type"]) == "custom"
    option_cols = st.columns([1.1, 1.1, 1], vertical_alignment="bottom") if show_custom_type else st.columns([1.1, 1], vertical_alignment="bottom")
    with option_cols[0]:
        st.selectbox(
            tr(summary_config["type_label_key"]),
            options=type_options,
            format_func=lambda code: tr(dict(summary_config["type_options"]).get(code, code)),
            key=type_option_key,
        )
    option_index = 1
    if show_custom_type:
        with option_cols[option_index]:
            st.text_input(
                tr(summary_config["custom_type_label_key"]),
                key=custom_type_key,
                placeholder=tr(summary_config["custom_type_placeholder_key"]),
            )
        option_index += 1
    with option_cols[option_index]:
        custom_clips = st.number_input(
            tr("自定义片段"),
            min_value=1,
            max_value=20,
            value=st.session_state.get('custom_clips', 5),
            help=tr("设置需要生成的短视频片段数量"),
            key="custom_clips_input"
        )
    st.session_state['custom_clips'] = custom_clips


def render_video_details(tr):
    """画面解说 渲染视频主题和提示词"""
    video_theme = st.text_input(tr("Video Theme"))
    custom_prompt = st.text_area(
        tr("Generation Prompt"),
        value=st.session_state.get('video_plot', ''),
        help=tr("Custom prompt for LLM, leave empty to use default prompt"),
        height=180
    )
    # 非短视频模式下显示原有的三个输入框
    input_cols = st.columns(2)

    with input_cols[0]:
        st.number_input(
            tr("Frame Interval (seconds)"),
            min_value=0,
            value=st.session_state.get('frame_interval_input', config.frames.get('frame_interval_input', 3)),
            help=tr("Frame Interval (seconds) (More keyframes consume more tokens)"),
            key="frame_interval_input"
        )

    with input_cols[1]:
        st.number_input(
            tr("Batch Size"),
            min_value=0,
            value=st.session_state.get('vision_batch_size', config.frames.get('vision_batch_size', 10)),
            help=tr("Batch Size (More keyframes consume more tokens)"),
            key="vision_batch_size"
        )
    st.session_state['video_theme'] = video_theme
    st.session_state['custom_prompt'] = custom_prompt
    return video_theme, custom_prompt


def render_fusion_visual_settings(tr):
    """Render settings that belong only to the film-vision fusion mode."""
    with st.expander(tr("视觉融合设置"), expanded=True):
        st.caption(tr("字幕用于剧情和对白，视觉模型只确认实际画面；视觉失败不会静默退回纯字幕模式。"))
        st.text_area(
            tr("视觉分析提示词"),
            key="fusion_visual_prompt",
            value=st.session_state.get(
                "fusion_visual_prompt",
                "按时间顺序记录画面中可确认的人物、动物或其他主体、动作与互动、环境与地点、关键物体、空间关系，以及镜头或场景变化。只描述画面可见的事实；不推断对白、声音、音乐、气味、动机、身份、剧情因果或画外事件。画面不清或无法确认时明确标注“无法确认”。可标记具有明显视觉冲击、动作、表演或场景变化价值的高光片段，但理由必须来自可见画面。",
            ),
            height=100,
        )
        columns = st.columns(2)
        with columns[0]:
            st.number_input(
                tr("视觉关键帧间隔（秒）"),
                min_value=2,
                max_value=30,
                value=int(st.session_state.get("fusion_frame_interval", 6)),
                key="fusion_frame_interval",
                help=tr("两小时电影建议 6 秒；动作密集时可调为 3 秒。"),
            )
        with columns[1]:
            st.number_input(
                tr("视觉批次大小"),
                min_value=1,
                max_value=20,
                value=int(st.session_state.get("fusion_vision_batch_size", 8)),
                key="fusion_vision_batch_size",
            )

        st.divider()
        st.caption(tr("可导入历史视觉证据产物，跳过视觉模型调用以测试后续解说和剪辑流程。"))
        allow_unverified_source = st.checkbox(
            tr("允许导入未验证来源的历史产物（仅用于回归测试）"),
            key="fusion_allow_unverified_artifact",
            help=tr("旧版产物没有视频内容哈希；可测试后续流程，但不能保存为正式脚本或用于渲染。"),
        )

        def load_artifact(artifact, artifact_path: str):
            selected_video_paths = _selected_video_paths()
            if len(selected_video_paths) != 1:
                st.error(tr("导入视觉证据前，请选择一部完整电影。"))
            else:
                try:
                    with st.spinner(tr("正在校验并加载视觉证据…")):
                        evidence = load_visual_evidence_artifact(
                            artifact,
                            source_video_path=selected_video_paths[0],
                            artifact_path=artifact_path,
                            allow_unverified_source=allow_unverified_source,
                        )
                    _store_fusion_visual_evidence(evidence, reuse_active=True)
                    st.session_state["fusion_reused_visual_artifact"] = artifact
                    st.session_state["fusion_reuse_source_identity"] = build_source_video_identity(
                        selected_video_paths[0]
                    )
                    st.session_state["fusion_visual_allow_unverified_source"] = allow_unverified_source
                    st.success(tr("历史视觉证据已加载；后续生成将复用它，不会重新调用视觉模型。"))
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as exc:
                    st.error(f"{tr('视觉证据导入失败')}: {exc}")

        local_artifacts = list_local_visual_evidence_artifacts()
        if local_artifacts:
            selected_local_artifact = st.selectbox(
                tr("本地视觉产物"),
                local_artifacts,
                format_func=lambda path: path.name,
                key="fusion_local_visual_artifact",
                help=tr("默认显示最新产物；无需在文件选择器中逐层查找。"),
            )
            if st.button(tr("加载所选本地视觉产物"), key="fusion_load_local_visual_artifact"):
                try:
                    with selected_local_artifact.open(encoding="utf-8") as artifact_file:
                        load_artifact(json.load(artifact_file), str(selected_local_artifact))
                except (OSError, json.JSONDecodeError) as exc:
                    st.error(f"{tr('视觉证据导入失败')}: {exc}")
        else:
            st.info(tr("尚未发现本地视觉产物；完成一次视觉分析后会自动显示在这里。"))

        uploaded_artifact = st.file_uploader(
            tr("或手动导入视觉证据 JSON"),
            type=["json"],
            accept_multiple_files=False,
            key="fusion_visual_artifact_uploader",
        )
        if st.button(tr("加载手动选择的视觉证据产物"), key="fusion_load_visual_artifact"):
            if uploaded_artifact is None:
                st.error(tr("请先选择视觉证据 JSON 文件。"))
            else:
                try:
                    load_artifact(
                        json.loads(uploaded_artifact.getvalue().decode("utf-8")),
                        f"导入：{uploaded_artifact.name}",
                    )
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as exc:
                    st.error(f"{tr('视觉证据导入失败')}: {exc}")

        if st.session_state.get("fusion_visual_reuse_active"):
            source_verified = bool(st.session_state.get("fusion_visual_source_verified"))
            highlight_state = st.session_state.get("fusion_visual_highlight_state", "unavailable_legacy")
            if source_verified:
                st.info(tr("当前使用已校验来源的历史视觉证据。"))
            else:
                st.warning(tr("当前使用未验证来源的历史视觉证据；请只用于已确认内容一致的视频。"))
            if highlight_state == "unavailable_legacy":
                st.warning(tr("该历史产物不含高光候选：剪辑脚本可生成，但不会使用高光候选推理。"))
            elif highlight_state == "analyzed_empty":
                st.info(tr("该历史产物已执行高光候选推理，但没有产出可用候选。"))
            else:
                st.success(tr("该历史产物包含高光候选，剪辑脚本将使用高光候选推理。"))
            if st.button(tr("重新运行视觉分析"), key="fusion_clear_reused_visual_artifact"):
                for state_key in (
                    "fusion_visual_evidence",
                    "fusion_highlight_candidates",
                    "fusion_visual_artifact_path",
                    "fusion_visual_signature",
                    "fusion_visual_reuse_active",
                    "fusion_visual_source_verified",
                    "fusion_visual_highlight_state",
                    "fusion_reused_visual_artifact",
                    "fusion_reuse_source_identity",
                    "fusion_visual_allow_unverified_source",
                    "fusion_highlight_candidate_items",
                    "fusion_finalization_report",
                    "fusion_evidence_conflicts",
                    "fusion_original_matched_script",
                    "fusion_visual_regression_only",
                    "fusion_visual_source_identity",
                ):
                    st.session_state.pop(state_key, None)
                selected_video_paths = _selected_video_paths()
                if len(selected_video_paths) != 1:
                    st.error(tr("重新分析前，请选择一部完整电影。"))
                else:
                    try:
                        with st.spinner(tr("正在重新逐帧分析画面…")):
                            evidence = collect_visual_evidence(
                                video_path=selected_video_paths[0],
                                video_theme=str(st.session_state.get("video_theme", "")),
                                custom_prompt=str(st.session_state.get("fusion_visual_prompt", "")),
                                frame_interval_seconds=float(st.session_state.get("fusion_frame_interval", 6)),
                                vision_batch_size=int(st.session_state.get("fusion_vision_batch_size", 8)),
                            )
                        try:
                            video_mtime = os.path.getmtime(selected_video_paths[0])
                        except OSError:
                            video_mtime = 0
                        visual_signature = "|".join(
                            [
                                selected_video_paths[0],
                                str(video_mtime),
                                str(st.session_state.get("fusion_frame_interval", 6)),
                                str(st.session_state.get("fusion_vision_batch_size", 8)),
                                str(st.session_state.get("fusion_visual_prompt", "")),
                                str(st.session_state.get("video_theme", "")),
                                "visual-context-summary-v2-highlights",
                            ]
                        )
                        _store_fusion_visual_evidence(
                            evidence,
                            reuse_active=False,
                            visual_signature=visual_signature,
                        )
                        st.success(tr("视觉分析已重新完成。"))
                    except Exception as exc:
                        st.error(f"{tr('视觉分析失败')}: {exc}")


def summary_narration_panel(tr, summary_config):
    """影视/短剧解说 渲染视频主题和提示词"""
    # 检查是否已经处理过字幕文件
    if 'subtitle_file_processed' not in st.session_state:
        st.session_state['subtitle_file_processed'] = False

    render_fun_asr_transcription(tr)
    render_subtitle_preview(tr)

    current_subtitle_paths = _selected_subtitle_paths()
    current_subtitle_path = current_subtitle_paths[0] if current_subtitle_paths else ''
    web_search_key = _summary_state_key(summary_config, "web_search_enabled")
    plot_button_key = _summary_state_key(summary_config, "plot_analysis_button")
    plot_analysis_key = _summary_state_key(summary_config, "plot_analysis")
    plot_source_key = _summary_state_key(summary_config, "plot_analysis_subtitle_path")
    plot_signature_key = _summary_state_key(summary_config, "plot_analysis_signature")
    pending_plot_key = _summary_state_key(summary_config, "pending_plot_analysis")

    st.markdown(
        f"""
        <style>
        .st-key-{web_search_key} [data-testid="stMarkdownContainer"] {{
            display: none;
        }}
        .st-key-{web_search_key} [data-testid="stWidgetLabel"] {{
            min-width: 0;
            transform: translateX(-1.2rem);
        }}
        .st-key-{web_search_key} label {{
            align-items: center;
            gap: 0.45rem;
        }}
        .st-key-{web_search_key} label > div:first-child {{
            width: 3rem !important;
            min-width: 3rem !important;
            height: 1.55rem !important;
            border-radius: 999px !important;
            border: 1px solid #d1d5db !important;
            background: #e5e7eb !important;
            box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.08) !important;
            transition: background 160ms ease, border-color 160ms ease, box-shadow 160ms ease !important;
        }}
        .st-key-{web_search_key} label:hover > div:first-child {{
            background: #dbe3ef !important;
            border-color: #b8c2d3 !important;
        }}
        .st-key-{web_search_key} label:has(input[aria-checked="true"]) > div:first-child {{
            border-color: transparent !important;
            background: linear-gradient(135deg, #2563eb, #14b8a6) !important;
            box-shadow: 0 6px 14px rgba(37, 99, 235, 0.22) !important;
        }}
        .st-key-{web_search_key} label > div:first-child > div {{
            width: 1.05rem !important;
            height: 1.05rem !important;
            border-radius: 999px !important;
            background: #ffffff !important;
            box-shadow: 0 2px 6px rgba(15, 23, 42, 0.24) !important;
        }}
        .st-key-{web_search_key} button[aria-label^="Help for"] {{
            color: #6b7280 !important;
        }}
        .st-key-{web_search_key} button[aria-label^="Help for"]:hover {{
            color: #2563eb !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    name_cols = st.columns([3.4, 1.1, 2], vertical_alignment="bottom")
    with name_cols[0]:
        video_theme = st.text_input(tr(summary_config["title_label_key"]))
    with name_cols[1]:
        web_search_enabled = st.toggle(
            tr("联网搜索"),
            key=web_search_key,
            help=tr("Enable Web Search Help"),
            disabled=not current_subtitle_path,
        )
    with name_cols[2]:
        analyze_plot_clicked = st.button(
            tr("剧情理解"),
            key=plot_button_key,
            disabled=not current_subtitle_path,
            use_container_width=True,
        )
    st.session_state['video_theme'] = video_theme

    current_signature = _short_drama_plot_analysis_signature(
        current_subtitle_paths,
        video_theme,
        web_search_enabled,
        _selected_video_paths(),
    )
    saved_signature = st.session_state.get(plot_signature_key)
    legacy_source = st.session_state.get(plot_source_key)
    if (
        (saved_signature and saved_signature != current_signature)
        or (legacy_source and legacy_source != current_subtitle_path)
    ):
        st.session_state[plot_analysis_key] = ""
        st.session_state[plot_source_key] = ""
        st.session_state[plot_signature_key] = ""
        st.session_state.pop(pending_plot_key, None)
    else:
        pending_plot = st.session_state.pop(pending_plot_key, None)
        if isinstance(pending_plot, dict) and pending_plot.get("signature") == current_signature:
            pending_analysis = str(pending_plot.get("plot_analysis") or "")
            if pending_analysis:
                st.session_state[plot_analysis_key] = pending_analysis
                st.session_state[plot_source_key] = pending_plot.get("subtitle_path") or current_subtitle_path
                st.session_state[plot_signature_key] = current_signature

    if analyze_plot_clicked:
        with st.spinner(tr("Analyzing plot...")):
            plot_analysis = analyze_short_drama_plot(
                current_subtitle_paths,
                st.session_state.get('temperature', 0.7),
                tr,
                subtitle_content=st.session_state.get('subtitle_content', ''),
                short_name=video_theme,
                enable_web_search=web_search_enabled,
                video_paths=_selected_video_paths(),
                prompt_category=summary_config["prompt_category"],
                search_keywords=summary_config["search_keywords"],
                empty_title_message_key=summary_config["empty_title_message_key"],
                web_search_context_description=summary_config["web_search_context_description"],
            )
        if plot_analysis:
            st.session_state[plot_analysis_key] = plot_analysis
            st.session_state[plot_source_key] = current_subtitle_path
            st.session_state[plot_signature_key] = current_signature
            st.success(tr("Plot analysis completed"))

    if st.session_state.get(plot_analysis_key):
        st.text_area(
            tr("剧情理解结果"),
            key=plot_analysis_key,
            height=240,
        )

    return video_theme


def short_drama_summary(tr):
    """短剧解说 渲染视频主题和提示词"""
    return summary_narration_panel(tr, SUMMARY_MODE_CONFIGS[MODE_SHORT_SUMMARY])


def render_subtitle_preview(tr):
    """渲染可折叠的当前字幕预览；没有字幕时提示用户先转写或上传。"""
    subtitle_paths = _selected_subtitle_paths()
    subtitle_content = st.session_state.get('subtitle_content', '')
    subtitle_contents = st.session_state.get('subtitle_contents', {})
    if not isinstance(subtitle_contents, dict):
        subtitle_contents = {}

    if subtitle_paths and (not subtitle_content or not subtitle_contents):
        subtitle_content, subtitle_contents = _build_combined_subtitle_content(
            subtitle_paths,
            _selected_video_paths(),
        )
        st.session_state['subtitle_content'] = subtitle_content
        st.session_state['subtitle_contents'] = subtitle_contents

    with st.expander(tr("Subtitle Preview"), expanded=False):
        if not subtitle_paths or not subtitle_content:
            st.info(tr("Please transcribe or upload subtitles first"))
            return

        if len(subtitle_paths) > 1:
            for index, path in enumerate(subtitle_paths, start=1):
                content = subtitle_contents.get(path, "")
                if not content and os.path.exists(path):
                    content = _read_subtitle_file(path)
                st.markdown(f"**{index}. {os.path.basename(path)}**")
                st.text_area(
                    tr("Subtitle Preview"),
                    value=content,
                    height=180,
                    label_visibility="collapsed",
                    disabled=True,
                    key=f"subtitle_content_preview_{index}",
                )
            return

        st.text_area(
            tr("Subtitle Preview"),
            key="subtitle_content",
            height=180,
            label_visibility="collapsed",
        )


def render_subtitle_upload(tr):
    """上传并保存用户提供的 SRT 字幕文件。"""
    subtitle_dir_label = utils.subtitle_dir().replace(config.root_dir, ".")
    st.markdown(
        f"**{tr('上传字幕文件')}**  "
        f":gray[{tr('Transcribed subtitles storage hint').format(path=subtitle_dir_label)}]"
    )
    subtitle_file = st.file_uploader(
        tr("上传字幕文件"),
        type=["srt"],
        accept_multiple_files=False,
        key="subtitle_file_uploader",  # 添加唯一key
        label_visibility="collapsed",
    )
    
    # 显示当前已上传的字幕文件路径
    if 'subtitle_path' in st.session_state and st.session_state['subtitle_path']:
        st.info(tr("Uploaded subtitle").format(file=os.path.basename(st.session_state['subtitle_path'])))
        if st.button(tr("清除已上传字幕")):
            _set_subtitle_state([])
            st.rerun()
    
    # 只有当有文件上传且尚未处理时才执行处理逻辑
    if subtitle_file is not None and not st.session_state['subtitle_file_processed']:
        try:
            # 清理文件名，防止路径污染和路径遍历攻击
            safe_filename = os.path.basename(subtitle_file.name)

            decoded = decode_subtitle_bytes(subtitle_file.getvalue())
            script_content = decoded.text
            detected_encoding = decoded.encoding

            if not script_content:
                st.error(tr("无法读取字幕文件，请检查文件编码（支持 UTF-8、UTF-16、GBK、GB2312）"))
                st.stop()

            # 验证字幕内容（简单检查）
            if len(script_content.strip()) < 10:
                st.warning(tr("字幕文件内容似乎为空，请检查文件"))

            # 保存到字幕目录
            script_file_path = os.path.join(utils.subtitle_dir(), safe_filename)
            file_name, file_extension = os.path.splitext(safe_filename)

            # 如果文件已存在,添加时间戳
            if os.path.exists(script_file_path):
                timestamp = time.strftime("%Y%m%d%H%M%S")
                file_name_with_timestamp = f"{file_name}_{timestamp}"
                script_file_path = os.path.join(utils.subtitle_dir(), file_name_with_timestamp + file_extension)

            # 直接写入SRT内容（统一使用 UTF-8）
            with open(script_file_path, "w", encoding='utf-8') as f:
                f.write(script_content)

            # 更新状态
            st.success(
                f"{tr('字幕上传成功')} "
                f"({tr('Encoding')}: {detected_encoding.upper()}, "
                f"{tr('Size')}: {len(script_content)} {tr('Characters')})"
            )
            _set_subtitle_state([script_file_path])

            # 避免使用rerun，使用更新状态的方式
            # st.rerun()

        except Exception as e:
            st.error(f"{tr('Upload failed')}: {str(e)}")


def _is_blank_table_value(value):
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _ordered_script_columns(script_rows):
    columns = []
    for column in SCRIPT_TABLE_BASE_COLUMNS:
        columns.append(column)

    for row in script_rows:
        if not isinstance(row, dict):
            continue
        for column in row.keys():
            if column not in columns:
                columns.append(column)

    return columns


def _script_json_to_table(script_data):
    if not isinstance(script_data, list):
        script_data = []

    if not script_data:
        return pd.DataFrame(columns=SCRIPT_TABLE_BASE_COLUMNS)

    if not all(isinstance(item, dict) for item in script_data):
        rows = [
            {"value": json.dumps(item, ensure_ascii=False)}
            for item in script_data
        ]
        return _normalize_script_table_types(pd.DataFrame(rows, columns=["value"]))

    columns = _ordered_script_columns(script_data)
    return _normalize_script_table_types(pd.DataFrame(script_data, columns=columns))


def _normalize_script_table_types(table_data):
    for column in SCRIPT_TABLE_TEXT_COLUMNS:
        if column in table_data.columns:
            table_data[column] = table_data[column].where(table_data[column].notna(), "").astype(str).astype("object")
    return table_data


def _normalize_script_table_value(column, value):
    if _is_blank_table_value(value):
        return ""

    if column in {"_id", "video_id", "OST"}:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    return value


def _script_table_to_json(edited_data):
    if isinstance(edited_data, pd.DataFrame):
        records = edited_data.to_dict("records")
    elif isinstance(edited_data, list):
        records = edited_data
    else:
        records = pd.DataFrame(edited_data).to_dict("records")

    script_data = []
    for row in records:
        if not isinstance(row, dict):
            continue
        if all(_is_blank_table_value(value) for value in row.values()):
            continue

        cleaned_row = {}
        for column, value in row.items():
            if not column:
                continue
            normalized_value = _normalize_script_table_value(column, value)
            if _is_blank_table_value(normalized_value) and column not in SCRIPT_TABLE_BASE_COLUMNS:
                continue
            cleaned_row[column] = normalized_value

        if cleaned_row:
            script_data.append(cleaned_row)

    return json.dumps(script_data, indent=2, ensure_ascii=False)


def render_video_script_editor(tr):
    """使用弹窗和表格编辑视频脚本 JSON。"""
    @st.dialog(tr("Video Script"), width="large")
    def video_script_dialog():
        script_data = st.session_state.get('video_clip_json', [])
        table_data = _script_json_to_table(script_data)
        column_order = list(table_data.columns)

        st.caption(tr("Video script table help"))
        edited_table = st.data_editor(
            table_data,
            key="video_script_table_editor",
            hide_index=True,
            num_rows="dynamic",
            use_container_width=True,
            height=520,
            row_height=72,
            column_order=column_order,
            column_config={
                "_id": st.column_config.NumberColumn(tr("Script Column ID"), step=1, format="%d", width=52),
                "video_id": st.column_config.NumberColumn(
                    tr("Script Column Video ID"),
                    min_value=1,
                    step=1,
                    format="%d",
                    width=80,
                ),
                "video_name": st.column_config.TextColumn(tr("Script Column Video Name"), width=180),
                "timestamp": st.column_config.TextColumn(tr("Script Column Timestamp"), width=200),
                "picture": st.column_config.TextColumn(tr("Script Column Picture"), width=320),
                "narration": st.column_config.TextColumn(tr("Script Column Narration"), width=480),
                "OST": st.column_config.NumberColumn(
                    tr("Script Column OST"),
                    min_value=0,
                    max_value=2,
                    step=1,
                    format="%d",
                    width=52,
                ),
            },
        )

        video_clip_json_details = _script_table_to_json(edited_table)
        with st.expander(tr("Raw JSON Preview"), expanded=False):
            st.code(video_clip_json_details, language="json")

        if st.button(tr("Save Script"), key="save_script_from_dialog", use_container_width=True):
            save_script_with_validation(tr, video_clip_json_details)

    script_data = st.session_state.get('video_clip_json', [])
    script_count = len(script_data) if isinstance(script_data, list) else 0
    st.markdown(f"**{tr('Video Script')}**  :gray[{tr('Video script row count').format(count=script_count)}]")

    if st.button(tr("Edit Video Script"), key="open_video_script_editor", use_container_width=True):
        video_script_dialog()


def render_fun_asr_transcription(tr):
    """使用 Fun-ASR 从本地音视频转写生成字幕。"""
    def clear_fun_asr_subtitle_state():
        _set_subtitle_state([])

    from app.services import fun_asr_subtitle

    backend_options = {
        tr("Local FunASR-Pack API"): "local",
        tr("Local FireRedASR API"): "firered",
        tr("Ali Bailian Online Fun-ASR"): "bailian",
        tr("上传字幕文件"): "upload",
    }
    saved_backend = str(config.fun_asr.get("backend", "")).strip().lower()
    if saved_backend not in {"local", "firered", "bailian", "upload"}:
        saved_backend = (
            "bailian"
            if config.fun_asr.get("api_key") and not config.fun_asr.get("api_url")
            else "local"
        )

    backend_values = list(backend_options.values())
    backend_labels = list(backend_options.keys())
    backend = saved_backend
    api_key = ""
    api_url = config.fun_asr.get("api_url", fun_asr_subtitle.LOCAL_FUN_ASR_API_URL)
    firered_api_url = config.fun_asr.get("firered_api_url", fun_asr_subtitle.LOCAL_FIRERED_ASR_API_URL)
    hotword = config.fun_asr.get("hotword", "")
    enable_spk = bool(config.fun_asr.get("enable_spk", False))
    media_paths = _selected_video_paths()

    subtitle_cols = st.columns([3, 2], vertical_alignment="top")

    with subtitle_cols[0]:
        with st.expander(tr("Ali Bailian Fun-ASR Subtitle Transcription"), expanded=False):
            backend_label = st.selectbox(
                tr("Subtitle Processing Method"),
                options=backend_labels,
                index=backend_values.index(saved_backend),
                key="fun_asr_backend",
            )
            backend = backend_options[backend_label]

            st.markdown(tr("Subtitle transcription package downloads"))

            if backend == "upload":
                render_subtitle_upload(tr)
            elif backend == "local":
                st.caption(tr("Local Fun-ASR upload caption"))
                api_url = st.text_input(
                    tr("Local FunASR-Pack API URL"),
                    value=api_url,
                    help=tr("Local FunASR-Pack API URL Help"),
                    key="fun_asr_api_url",
                )
                hotword = st.text_input(
                    tr("Fun-ASR Hotword"),
                    value=hotword,
                    help=tr("Fun-ASR Hotword Help"),
                    key="fun_asr_hotword",
                )
                enable_spk = st.checkbox(
                    tr("Enable speaker diarization"),
                    value=enable_spk,
                    help=tr("Enable speaker diarization Help"),
                    key="fun_asr_enable_spk",
                )
            elif backend == "firered":
                st.caption(tr("Local FireRed-ASR upload caption"))
                firered_api_url = st.text_input(
                    tr("Local FireRedASR API URL"),
                    value=firered_api_url,
                    help=tr("Local FireRedASR API URL Help"),
                    key="fun_asr_firered_api_url",
                )
            else:
                st.caption(tr("Fun-ASR upload caption"))
                st.markdown(
                    f"{tr('API Key URL')}: "
                    "[https://bailian.console.aliyun.com/?tab=model#/api-key]"
                    "(https://bailian.console.aliyun.com/?tab=model#/api-key)"
                )

                api_key = st.text_input(
                    tr("Ali Bailian API Key"),
                    value=config.fun_asr.get("api_key", ""),
                    type="password",
                    help=tr("Ali Bailian API Key Help"),
                    key="fun_asr_api_key",
                )

            if backend != "upload":
                if media_paths:
                    if len(media_paths) == 1:
                        st.info(
                            tr("Using selected video for subtitle transcription").format(
                                file=os.path.basename(media_paths[0])
                            )
                        )
                    else:
                        st.info(
                            tr("Using selected videos for subtitle transcription").format(
                                count=len(media_paths),
                                files=_format_file_list_for_display(media_paths),
                            )
                        )
                else:
                    st.warning(tr("Please select or upload a video first"))

    # 上传字幕面板会在本轮渲染中更新 session_state，这里重新读取一次，保证按钮状态同步。
    subtitle_paths = _selected_subtitle_paths()
    can_transcribe = backend != "upload" and bool(media_paths)
    can_manage_subtitles = bool(subtitle_paths)
    saved_target_language = str(config.ui.get("subtitle_translate_target_language", "中文") or "中文")

    with subtitle_cols[1]:
        transcribe_clicked = st.button(
            tr("Transcribe subtitles"),
            key="fun_asr_transcribe",
            disabled=not can_transcribe,
            use_container_width=True,
        )

    subtitle_action_cols = st.columns(3, vertical_alignment="bottom")
    with subtitle_action_cols[0]:
        target_language = st.text_input(
            tr("Subtitle target language"),
            value=saved_target_language,
            key="subtitle_translate_target_language",
            placeholder=tr("Subtitle target language placeholder"),
        )
    with subtitle_action_cols[1]:
        translate_clicked = st.button(
            tr("Translate subtitles"),
            key="subtitle_translate",
            disabled=not can_manage_subtitles,
            use_container_width=True,
        )
    with subtitle_action_cols[2]:
        correct_clicked = st.button(
            tr("Calibrate subtitles"),
            key="subtitle_correct",
            disabled=not can_manage_subtitles,
            use_container_width=True,
        )

    target_language = str(target_language or "").strip() or "中文"

    if correct_clicked:
        from app.services import subtitle_corrector

        text_provider = config.app.get('text_llm_provider', 'openai').lower()
        text_api_key = config.app.get(f'text_{text_provider}_api_key')
        text_base_url = config.app.get(f'text_{text_provider}_base_url')

        corrected_paths = []
        try:
            spinner_text = tr("Calibrating subtitles...")
            with st.spinner(spinner_text):
                progress_bar = st.progress(0) if len(subtitle_paths) > 1 else None
                for index, subtitle_path in enumerate(subtitle_paths, start=1):
                    subtitle_name = f"{os.path.splitext(os.path.basename(subtitle_path))[0]}_corrected.srt"
                    output_path = _unique_file_path(utils.subtitle_dir(), subtitle_name)
                    corrected_path = subtitle_corrector.correct_subtitle_file(
                        subtitle_file=subtitle_path,
                        output_file=output_path,
                        provider=text_provider,
                        api_key=text_api_key,
                        base_url=text_base_url,
                    )
                    corrected_paths.append(corrected_path)
                    if progress_bar:
                        progress_bar.progress(index / len(subtitle_paths))

                if progress_bar:
                    progress_bar.empty()

            _set_subtitle_state(corrected_paths)
            success_placeholder = st.empty()
            if len(corrected_paths) == 1:
                success_placeholder.success(
                    tr("Subtitle calibration succeeded").format(file=os.path.basename(corrected_paths[0]))
                )
            else:
                success_placeholder.success(
                    tr("Subtitle calibration succeeded for multiple files").format(
                        count=len(corrected_paths),
                        files=_format_file_list_for_display(corrected_paths),
                    )
                )
            time.sleep(3)
            success_placeholder.empty()
        except Exception as e:
            logger.error(f"字幕校准失败: {traceback.format_exc()}")
            st.error(f"{tr('Subtitle calibration failed')}: {str(e)}")
        return

    if translate_clicked:
        from app.services import subtitle_translator

        text_provider = config.app.get('text_llm_provider', 'openai').lower()
        text_api_key = config.app.get(f'text_{text_provider}_api_key')
        text_base_url = config.app.get(f'text_{text_provider}_base_url')

        translated_paths = []
        try:
            config.ui["subtitle_translate_target_language"] = target_language
            config.save_config()

            spinner_text = tr("Translating subtitles...").format(language=target_language)
            with st.spinner(spinner_text):
                progress_bar = st.progress(0)
                progress_caption = st.empty()
                target_suffix = _safe_filename_fragment(target_language)
                for index, subtitle_path in enumerate(subtitle_paths, start=1):
                    subtitle_name = (
                        f"{os.path.splitext(os.path.basename(subtitle_path))[0]}"
                        f"_translated_{target_suffix}.srt"
                    )
                    output_path = _unique_file_path(utils.subtitle_dir(), subtitle_name)
                    subtitle_file_label = os.path.basename(subtitle_path)

                    def update_translation_progress(
                        completed,
                        total,
                        message,
                        file_index=index,
                        file_label=subtitle_file_label,
                    ):
                        total = max(int(total or 0), 1)
                        completed = max(0, min(int(completed or 0), total))
                        file_progress = completed / total
                        overall_progress = ((file_index - 1) + file_progress) / max(len(subtitle_paths), 1)
                        progress_bar.progress(min(overall_progress, 1.0))
                        progress_caption.caption(
                            tr("Subtitle translation progress").format(
                                file=file_label,
                                completed=completed,
                                total=total,
                                message=message,
                            )
                        )

                    translated_path = subtitle_translator.translate_subtitle_file(
                        subtitle_file=subtitle_path,
                        output_file=output_path,
                        target_language=target_language,
                        provider=text_provider,
                        api_key=text_api_key,
                        base_url=text_base_url,
                        progress_callback=update_translation_progress,
                    )
                    translated_paths.append(translated_path)
                    progress_bar.progress(index / len(subtitle_paths))

                progress_caption.empty()
                progress_bar.empty()

            _set_subtitle_state(translated_paths)
            success_placeholder = st.empty()
            if len(translated_paths) == 1:
                success_placeholder.success(
                    tr("Subtitle translation succeeded").format(file=os.path.basename(translated_paths[0]))
                )
            else:
                success_placeholder.success(
                    tr("Subtitle translation succeeded for multiple files").format(
                        count=len(translated_paths),
                        files=_format_file_list_for_display(translated_paths),
                    )
                )
            time.sleep(3)
            success_placeholder.empty()
        except Exception as e:
            logger.error(f"字幕翻译失败: {traceback.format_exc()}")
            st.error(f"{tr('Subtitle translation failed')}: {str(e)}")
        return

    if not transcribe_clicked:
        return

    if backend == "bailian" and not api_key.strip():
        clear_fun_asr_subtitle_state()
        st.error(tr("Please enter Ali Bailian API Key"))
        return
    if backend == "local" and not str(api_url).strip():
        clear_fun_asr_subtitle_state()
        st.error(tr("Please enter local FunASR-Pack API URL"))
        return
    if backend == "firered" and not str(firered_api_url).strip():
        clear_fun_asr_subtitle_state()
        st.error(tr("Please enter local FireRedASR API URL"))
        return
    missing_paths = [path for path in media_paths if not os.path.exists(path)]
    if not media_paths or missing_paths:
        clear_fun_asr_subtitle_state()
        if missing_paths:
            st.error(
                tr("Selected video files do not exist").format(
                    files=_format_file_list_for_display(missing_paths)
                )
            )
        else:
            st.error(tr("Selected video file does not exist"))
        return

    try:
        clear_fun_asr_subtitle_state()

        config.fun_asr["backend"] = backend
        config.fun_asr["api_url"] = str(api_url).strip()
        config.fun_asr["firered_api_url"] = str(firered_api_url).strip()
        config.fun_asr["api_key"] = api_key.strip()
        config.fun_asr["hotword"] = str(hotword).strip()
        config.fun_asr["enable_spk"] = bool(enable_spk)
        config.fun_asr["model"] = "fun-asr"
        config.save_config()

        if backend == "local":
            spinner_text = tr("Transcribing with local FunASR-Pack...")
        elif backend == "firered":
            spinner_text = tr("Transcribing with local FireRedASR...")
        else:
            spinner_text = tr("Transcribing with Fun-ASR...")
        with st.spinner(spinner_text):
            progress_bar = st.progress(0) if len(media_paths) > 1 else None
            generated_paths = []
            for index, media_path in enumerate(media_paths, start=1):
                subtitle_suffix = "firered_asr" if backend == "firered" else "fun_asr"
                subtitle_name = f"{os.path.splitext(os.path.basename(media_path))[0]}_{subtitle_suffix}.srt"
                subtitle_path = _unique_file_path(utils.subtitle_dir(), subtitle_name)

                if backend == "local":
                    generated_path = fun_asr_subtitle.create_with_local_fun_asr(
                        local_file=media_path,
                        subtitle_file=subtitle_path,
                        api_url=str(api_url).strip(),
                        hotword=str(hotword).strip(),
                        enable_spk=bool(enable_spk),
                    )
                elif backend == "firered":
                    generated_path = fun_asr_subtitle.create_with_local_firered_asr(
                        local_file=media_path,
                        subtitle_file=subtitle_path,
                        api_url=str(firered_api_url).strip(),
                    )
                else:
                    generated_path = fun_asr_subtitle.create_with_fun_asr(
                        local_file=media_path,
                        subtitle_file=subtitle_path,
                        api_key=api_key.strip(),
                    )

                if not generated_path or not os.path.exists(generated_path):
                    raise RuntimeError(tr("Fun-ASR failed without subtitle file"))

                generated_paths.append(generated_path)
                if progress_bar:
                    progress_bar.progress(index / len(media_paths))

            if progress_bar:
                progress_bar.empty()

        if not generated_paths:
            clear_fun_asr_subtitle_state()
            st.error(tr("Fun-ASR failed without subtitle file"))
            return

        subtitle_content, subtitle_contents = _build_combined_subtitle_content(
            generated_paths,
            media_paths,
        )
        if not subtitle_content.strip():
            clear_fun_asr_subtitle_state()
            st.error(tr("Fun-ASR failed without subtitle file"))
            return

        _set_subtitle_state(generated_paths)
        success_placeholder = st.empty()
        if len(generated_paths) == 1:
            success_placeholder.success(
                tr("Subtitle transcription succeeded").format(file=os.path.basename(generated_paths[0]))
            )
        else:
            success_placeholder.success(
                tr("Subtitle transcription succeeded for multiple files").format(
                    count=len(generated_paths),
                    files=_format_file_list_for_display(generated_paths),
                )
            )
        time.sleep(3)
        success_placeholder.empty()
        st.rerun()
    except Exception as e:
        clear_fun_asr_subtitle_state()
        logger.error(f"Fun-ASR 字幕转写失败: {traceback.format_exc()}")
        st.error(f"{tr('Fun-ASR transcription failed')}: {str(e)}")


def render_script_buttons(tr, params):
    """渲染脚本操作按钮"""
    # 获取当前选择的脚本类型
    script_path = st.session_state.get('video_clip_json_path', '')

    # 生成/加载按钮
    if script_path == "auto":
        button_name = tr("Generate Video Script")
    elif script_path == "short":
        button_name = tr("Generate Short Video Script")
    elif script_path in SUMMARY_SCRIPT_MODES:
        button_name = tr("生成剪辑脚本")
    elif script_path.endswith("json"):
        button_name = tr("Load Video Script")
    else:
        button_name = tr("Please Select Script File")

    if script_path in SUMMARY_SCRIPT_MODES:
        summary_config = _summary_mode_config(script_path)
        type_option_key = _summary_state_key(summary_config, "type_option")
        custom_type_key = _summary_state_key(summary_config, "custom_type")
        original_sound_ratio_key = _summary_state_key(summary_config, "original_sound_ratio")
        narration_word_count_key = _summary_state_key(summary_config, "narration_word_count")
        language_option_key = _summary_state_key(summary_config, "narration_language_option")
        custom_language_key = _summary_state_key(summary_config, "custom_narration_language")
        narration_copy_key = _summary_state_key(summary_config, "narration_copy")

        type_options = [code for code, _ in summary_config["type_options"]]
        if st.session_state.get(type_option_key) not in type_options:
            st.session_state[type_option_key] = summary_config["default_type"]
        language_options = [code for code, _ in SHORT_DRAMA_NARRATION_LANGUAGE_OPTIONS]
        if st.session_state.get(language_option_key) not in language_options:
            st.session_state[language_option_key] = "zh-CN"

        show_custom_type = st.session_state.get(type_option_key, summary_config["default_type"]) == "custom"
        show_custom_language = (
            st.session_state.get(language_option_key, 'zh-CN') == "custom"
        )
        config_col_widths = [1.15]
        if show_custom_type:
            config_col_widths.append(1.15)
        config_col_widths.extend([0.9, 0.9, 1.15])
        if show_custom_language:
            config_col_widths.append(1.15)

        config_cols = st.columns(config_col_widths, vertical_alignment="bottom")
        config_col_index = 0
        with config_cols[config_col_index]:
            st.selectbox(
                tr(summary_config["type_label_key"]),
                options=type_options,
                format_func=lambda code: tr(dict(summary_config["type_options"]).get(code, code)),
                key=type_option_key,
            )
        config_col_index += 1
        if show_custom_type:
            with config_cols[config_col_index]:
                st.text_input(
                    tr(summary_config["custom_type_label_key"]),
                    key=custom_type_key,
                    placeholder=tr(summary_config["custom_type_placeholder_key"]),
                )
            config_col_index += 1
        with config_cols[config_col_index]:
            st.selectbox(
                tr("原片占比"),
                options=SHORT_DRAMA_ORIGINAL_SOUND_RATIO_OPTIONS,
                format_func=lambda ratio: f"{ratio}%",
                index=SHORT_DRAMA_ORIGINAL_SOUND_RATIO_OPTIONS.index(30),
                key=original_sound_ratio_key,
            )
        config_col_index += 1
        with config_cols[config_col_index]:
            st.number_input(
                tr("文案字数"),
                min_value=MIN_NARRATION_WORD_COUNT,
                max_value=MAX_NARRATION_WORD_COUNT,
                value=DEFAULT_NARRATION_WORD_COUNT,
                step=50,
                key=narration_word_count_key,
            )
        config_col_index += 1
        with config_cols[config_col_index]:
            st.selectbox(
                tr("解说语言"),
                options=[code for code, _ in SHORT_DRAMA_NARRATION_LANGUAGE_OPTIONS],
                format_func=lambda code: tr(dict(SHORT_DRAMA_NARRATION_LANGUAGE_OPTIONS).get(code, code)),
                key=language_option_key,
            )
        config_col_index += 1
        if show_custom_language:
            with config_cols[config_col_index]:
                st.text_input(
                    tr("自定义解说语言"),
                    key=custom_language_key,
                    placeholder=tr("例如：意大利语（意大利）"),
                )

        action_cols = st.columns([1, 1], vertical_alignment="bottom")
        with action_cols[0]:
            narration_copy_clicked = st.button(
                tr("生成解说文案"),
                key=_summary_state_key(summary_config, "narration_copy_action"),
                disabled=not script_path,
                use_container_width=True,
            )
        with action_cols[1]:
            action_clicked = st.button(
                button_name,
                key="script_action",
                disabled=not script_path,
                use_container_width=True,
            )

        if script_path == MODE_FILM_VISION_FUSION:
            pending_plan = st.session_state.get("fusion_segment_plan_pending")
            approved_plan = st.session_state.get("fusion_segment_plan")
            current_narration_copy = str(st.session_state.get(narration_copy_key, "")).strip()
            if approved_plan and st.session_state.get("fusion_segment_plan_narration") != current_narration_copy:
                active_task_id = str(st.session_state.get("fusion_matching_task_id") or "")
                if active_task_id:
                    cancel_fusion_matching_task(active_task_id)
                st.session_state.pop("fusion_segment_plan", None)
                st.session_state.pop("fusion_segment_plan_approval", None)
                st.session_state.pop("fusion_matching_task_id", None)
                st.session_state.pop("fusion_matching_resume_snapshot", None)
                approved_plan = None
                st.warning(tr("解说文案已修改，请重新生成并确认分段计划。"))
            if pending_plan:
                with st.expander(tr("Fusion Segment Plan（待确认）"), expanded=True):
                    st.caption(tr("可直接编辑计划 JSON；确认后才会开始分段匹配。"))
                    st.text_area(
                        tr("Fusion Segment Plan"),
                        key="fusion_segment_plan_editor",
                        height=300,
                    )
                    if st.button(tr("确认分段计划"), key="approve_fusion_segment_plan"):
                        try:
                            edited_plan = json.loads(st.session_state["fusion_segment_plan_editor"])
                            FusionScriptPipeline().validate_plan(current_narration_copy, edited_plan)
                            continuity_report = FusionScriptPipeline().validate_continuity(
                                current_narration_copy, edited_plan
                            )
                            if not continuity_report.is_renderable:
                                finding_messages = "; ".join(
                                    finding.message for finding in continuity_report.findings
                                )
                                raise ValueError(f"叙事连续性未通过：{finding_messages}")
                            st.session_state["fusion_segment_plan"] = edited_plan
                            st.session_state["fusion_segment_plan_narration"] = current_narration_copy
                            st.session_state["fusion_segment_plan_source_identity"] = st.session_state.get(
                                "fusion_visual_source_identity"
                            )
                            st.session_state["fusion_segment_plan_approval"] = approve_fusion_segment_plan(
                                plan_payload=edited_plan,
                                narration_copy=current_narration_copy,
                                source_identity=st.session_state.get("fusion_visual_source_identity"),
                            )
                            st.session_state.pop("fusion_segment_plan_pending", None)
                            st.success(tr("分段计划已确认；点击生成剪辑脚本即可开始分段匹配。"))
                            st.rerun()
                        except (ValueError, json.JSONDecodeError) as exc:
                            st.error(f"{tr('分段计划无效')}: {exc}")
            elif approved_plan:
                with st.expander(tr("Fusion Segment Plan（已确认）"), expanded=False):
                    st.json(approved_plan)
                    if st.button(tr("编辑分段计划"), key="edit_fusion_segment_plan"):
                        active_task_id = str(st.session_state.get("fusion_matching_task_id") or "")
                        task = None
                        if active_task_id:
                            task = fusion_matching_task_status(active_task_id)
                        else:
                            task = find_fusion_matching_task(
                                source_identity=st.session_state.get("fusion_visual_source_identity"),
                                plan_payload=approved_plan,
                                narration_copy=current_narration_copy,
                            )
                        if task:
                            snapshot = task.get("matching_snapshot") or (
                                task.get("matched_plan") or {}
                            ).get("matching_snapshot")
                            if not isinstance(snapshot, dict):
                                completed = {
                                    str(record.get("segment_id")): record["response"]
                                    for record in task.get("completed_batches") or []
                                    if isinstance(record, dict)
                                    and record.get("status") == "succeeded"
                                    and isinstance(record.get("response"), dict)
                                }
                                snapshot = {
                                    "plan_payload": approved_plan,
                                    "completed_segment_results": completed,
                                    "attempts_by_segment": {},
                                    "repair_attempts_by_segment": {},
                            }
                            st.session_state["fusion_matching_resume_snapshot"] = snapshot
                        if active_task_id:
                            cancel_fusion_matching_task(active_task_id)
                        st.session_state["fusion_segment_plan_pending"] = approved_plan
                        st.session_state["fusion_segment_plan_editor"] = json.dumps(
                            approved_plan, ensure_ascii=False, indent=2
                        )
                        st.session_state.pop("fusion_segment_plan", None)
                        st.session_state.pop("fusion_segment_plan_approval", None)
                        st.session_state.pop("fusion_matching_task_id", None)
                        st.rerun()
    else:
        narration_copy_clicked = False
        action_clicked = st.button(button_name, key="script_action", disabled=not script_path)

    matching_task_needs_polling = bool(
        script_path == MODE_FILM_VISION_FUSION
        and st.session_state.get("fusion_matching_task_id")
    )
    if script_path in SUMMARY_SCRIPT_MODES and (
        narration_copy_clicked or action_clicked or matching_task_needs_polling
    ):
        summary_config = _summary_mode_config(script_path)
        type_option_key = _summary_state_key(summary_config, "type_option")
        custom_type_key = _summary_state_key(summary_config, "custom_type")
        original_sound_ratio_key = _summary_state_key(summary_config, "original_sound_ratio")
        narration_word_count_key = _summary_state_key(summary_config, "narration_word_count")
        language_option_key = _summary_state_key(summary_config, "narration_language_option")
        custom_language_key = _summary_state_key(summary_config, "custom_narration_language")
        narration_copy_key = _summary_state_key(summary_config, "narration_copy")
        plot_analysis_key = _summary_state_key(summary_config, "plot_analysis")
        plot_source_key = _summary_state_key(summary_config, "plot_analysis_subtitle_path")
        plot_signature_key = _summary_state_key(summary_config, "plot_analysis_signature")
        web_search_key = _summary_state_key(summary_config, "web_search_enabled")

        narration_language = _resolve_summary_narration_language(summary_config)
        drama_genre = _resolve_summary_type(summary_config)
        original_sound_ratio = int(st.session_state.get(original_sound_ratio_key, 30))
        narration_word_count = int(
            st.session_state.get(narration_word_count_key, DEFAULT_NARRATION_WORD_COUNT)
        )
        if (
            st.session_state.get(type_option_key) == "custom"
            and not str(st.session_state.get(custom_type_key, '') or '').strip()
        ):
            st.error(tr(summary_config["custom_type_empty_key"]))
            st.stop()
        if (
            st.session_state.get(language_option_key) == "custom"
            and not str(st.session_state.get(custom_language_key, '') or '').strip()
        ):
            st.error(tr("请输入自定义解说语言"))
            st.stop()

        subtitle_paths = _selected_subtitle_paths()
        subtitle_path = subtitle_paths[0] if subtitle_paths else None
        video_theme = st.session_state.get('video_theme')
        temperature = st.session_state.get('temperature')
        web_search_enabled = bool(st.session_state.get(web_search_key, False))
        current_signature = _short_drama_plot_analysis_signature(
            subtitle_paths,
            video_theme,
            web_search_enabled,
            _selected_video_paths(),
        )
        plot_analysis = ""
        if st.session_state.get(plot_signature_key) == current_signature:
            plot_analysis = st.session_state.get(plot_analysis_key, '')
        elif (
            not web_search_enabled
            and st.session_state.get(plot_source_key) == subtitle_path
        ):
            plot_analysis = st.session_state.get(plot_analysis_key, '')

        visual_evidence = ""
        highlight_candidates = ""
        if script_path == MODE_FILM_VISION_FUSION:
            selected_video_paths = _selected_video_paths()
            if len(selected_video_paths) != 1:
                st.error(tr("影视视觉融合解说首版仅支持选择一部完整电影。"))
                st.stop()

            source_video = selected_video_paths[0]
            if st.session_state.get("fusion_visual_reuse_active"):
                try:
                    artifact = st.session_state.get("fusion_reused_visual_artifact")
                    imported_identity = st.session_state.get("fusion_reuse_source_identity")
                    current_identity = build_source_video_identity(source_video)
                    if not isinstance(artifact, dict) or current_identity != imported_identity:
                        raise ValueError("当前视频已变化，不能继续复用之前导入的视觉证据。")
                    evidence = load_visual_evidence_artifact(
                        artifact,
                        source_video_path=source_video,
                        artifact_path=str(st.session_state.get("fusion_visual_artifact_path", "导入产物")),
                        allow_unverified_source=bool(
                            st.session_state.get("fusion_visual_allow_unverified_source")
                        ),
                    )
                    _store_fusion_visual_evidence(evidence, reuse_active=True)
                except (ValueError, OSError) as exc:
                    st.error(f"{tr('视觉证据复用失败')}: {exc}")
                    st.stop()
            try:
                video_mtime = os.path.getmtime(source_video)
            except OSError:
                video_mtime = 0
            visual_signature = "|".join(
                [
                    source_video,
                    str(video_mtime),
                    str(st.session_state.get("fusion_frame_interval", 6)),
                    str(st.session_state.get("fusion_vision_batch_size", 8)),
                    str(st.session_state.get("fusion_visual_prompt", "")),
                    str(video_theme or ""),
                    "visual-context-summary-v2-highlights",
                ]
            )
            if (
                not st.session_state.get("fusion_visual_reuse_active")
                and st.session_state.get("fusion_visual_signature") != visual_signature
            ):
                task_id = str(st.session_state.get("fusion_visual_task_id", ""))
                if task_id and st.session_state.get("fusion_visual_task_signature") != visual_signature:
                    task_id = ""
                    st.session_state.pop("fusion_visual_task_id", None)
                if not task_id:
                    persisted_task = find_local_visual_analysis(source_video, visual_signature)
                    if persisted_task:
                        task_id = str(persisted_task["task_id"])
                        st.session_state["fusion_visual_task_id"] = task_id
                        st.session_state["fusion_visual_task_signature"] = visual_signature
                if st.session_state.get("fusion_visual_confirmation_signature") != visual_signature:
                    try:
                        estimate = estimate_local_visual_analysis(
                            source_video,
                            float(st.session_state.get("fusion_frame_interval", 6)),
                            int(st.session_state.get("fusion_vision_batch_size", 8)),
                        )
                        st.warning(
                            tr("将分析完整影片：预计提取 {frames} 帧、发送 {requests} 次视觉请求，预计至少 {minutes} 分钟。")
                            .format(frames=estimate.keyframe_count, requests=estimate.request_count, minutes=estimate.estimated_minutes)
                        )
                    except Exception as exc:
                        st.error(f"{tr('无法预估视觉分析工作量')}: {exc}")
                        st.stop()
                    if st.button(tr("确认并开始全片视觉分析"), key="confirm_fusion_visual_analysis"):
                        st.session_state["fusion_visual_confirmation_signature"] = visual_signature
                    else:
                        st.stop()
                if not task_id:
                    task_id = start_local_visual_analysis(
                        video_path=source_video, video_theme=str(video_theme or ""),
                        custom_prompt=str(st.session_state.get("fusion_visual_prompt", "")),
                        frame_interval_seconds=float(st.session_state.get("fusion_frame_interval", 6)),
                        vision_batch_size=int(st.session_state.get("fusion_vision_batch_size", 8)),
                        analysis_signature=visual_signature,
                    )
                    st.session_state["fusion_visual_task_id"] = task_id
                    st.session_state["fusion_visual_task_signature"] = visual_signature
                task = local_visual_analysis_status(task_id)
                status = task.get("status")
                if status == "completed":
                    with open(str(task["artifact_path"]), encoding="utf-8") as artifact_file:
                        artifact = json.load(artifact_file)
                    evidence = load_visual_evidence_artifact(
                        artifact, source_video_path=source_video, artifact_path=str(task["artifact_path"])
                    )
                    _store_fusion_visual_evidence(evidence, reuse_active=False, visual_signature=visual_signature)
                    st.session_state.pop("fusion_visual_task_id", None)
                else:
                    progress = max(0, min(100, int(round(float(task.get("progress", 0))))))
                    st.progress(progress, text=f"🎬 {task.get('message') or '正在逐帧分析画面…'}")
                    if status in {"queued", "running"} and st.button(tr("取消视觉分析"), key="cancel_fusion_visual_task"):
                        cancel_local_visual_analysis(task_id)
                    if status in {"failed", "cancelled", "interrupted"}:
                        st.error(f"{tr('视觉融合失败')}: {task.get('error_message') or status}")
                        if st.button(tr("恢复视觉分析"), key="resume_fusion_visual_task"):
                            resume_local_visual_analysis(task_id)
                    st.info(tr("视觉分析正在后台运行。完成后再次点击生成即可继续。"))
                    st.stop()
            visual_evidence = str(st.session_state.get("fusion_visual_evidence", "")).strip()
            highlight_candidates = str(st.session_state.get("fusion_highlight_candidates", "")).strip()
            if not visual_evidence:
                st.error(tr("视觉融合失败：没有可用的画面证据。"))
                st.stop()

        if narration_copy_clicked:
            with st.spinner(tr("Generating narration copy...")):
                copy_result = generate_short_drama_narration_copy(
                    subtitle_paths,
                    video_theme,
                    temperature,
                    tr,
                    plot_analysis=plot_analysis,
                    subtitle_content=st.session_state.get('subtitle_content', ''),
                    enable_web_search=web_search_enabled,
                    video_paths=_selected_video_paths(),
                    narration_language=narration_language,
                    drama_genre=drama_genre,
                    narration_word_count=narration_word_count,
                    prompt_category=summary_config["prompt_category"],
                    search_keywords=summary_config["search_keywords"],
                    empty_title_message_key=summary_config["empty_title_message_key"],
                    web_search_context_description=summary_config["web_search_context_description"],
                    visual_evidence=visual_evidence,
            )
            if copy_result:
                active_task_id = str(st.session_state.get("fusion_matching_task_id") or "")
                if active_task_id:
                    cancel_fusion_matching_task(active_task_id)
                for state_key in (
                    "fusion_segment_plan",
                    "fusion_segment_plan_pending",
                    "fusion_segment_plan_narration",
                    "fusion_segment_plan_editor",
                    "fusion_segment_plan_source_identity",
                    "fusion_segment_plan_approval",
                    "fusion_matching_task_id",
                    "fusion_matching_resume_snapshot",
                ):
                    st.session_state.pop(state_key, None)
                st.session_state[narration_copy_key] = copy_result["narration_copy"]
                if not plot_analysis:
                    st.session_state[plot_analysis_key] = copy_result["plot_analysis"]
                st.session_state[plot_source_key] = subtitle_path
                st.session_state[plot_signature_key] = current_signature
                st.success(tr("Narration copy generated successfully"))

        pre_matched_fusion_result = None
        automatic_finalization = False
        if (action_clicked or matching_task_needs_polling) and script_path == MODE_FILM_VISION_FUSION:
            approved_plan = st.session_state.get("fusion_segment_plan")
            if approved_plan and (
                st.session_state.get("fusion_segment_plan_source_identity")
                != st.session_state.get("fusion_visual_source_identity")
            ):
                active_task_id = str(st.session_state.get("fusion_matching_task_id") or "")
                if active_task_id:
                    cancel_fusion_matching_task(active_task_id)
                st.session_state.pop("fusion_segment_plan", None)
                st.session_state.pop("fusion_segment_plan_approval", None)
                st.session_state.pop("fusion_matching_task_id", None)
                st.session_state.pop("fusion_matching_resume_snapshot", None)
                approved_plan = None
                st.warning(tr("视觉证据来源已变化，请重新生成并确认分段计划。"))
            if approved_plan:
                task_id = str(st.session_state.get("fusion_matching_task_id") or "")
                if not task_id:
                    persisted_task = find_fusion_matching_task(
                        source_identity=st.session_state.get("fusion_visual_source_identity"),
                        plan_payload=approved_plan,
                        narration_copy=str(st.session_state.get(narration_copy_key, "")),
                    )
                    if persisted_task:
                        task_id = str(persisted_task["task_id"])
                        st.session_state["fusion_matching_task_id"] = task_id
                if not task_id:
                    candidate_payloads = [
                        candidate.to_dict() if hasattr(candidate, "to_dict") else candidate
                        for candidate in st.session_state.get("fusion_highlight_candidate_items", [])
                    ]
                    finalization_context = {
                        "candidate_payloads": candidate_payloads,
                        "candidate_rejections": st.session_state.get(
                            "fusion_highlight_candidate_rejections", []
                        ),
                        "original_sound_ratio": original_sound_ratio,
                        "source_identity": st.session_state.get("fusion_visual_source_identity"),
                        "source_durations": {
                            os.path.basename(source_video): VideoProcessor(source_video).duration
                        },
                    }
                    task_id = start_fusion_matching_task(
                        short_name=video_theme,
                        narration_copy=str(st.session_state.get(narration_copy_key, "")),
                        narration_language=narration_language,
                        drama_genre=drama_genre,
                        original_sound_ratio=original_sound_ratio,
                        subtitle_content=str(st.session_state.get("subtitle_content", "")),
                        visual_evidence=visual_evidence,
                        highlight_candidates=highlight_candidates,
                        plan_payload=approved_plan,
                        plan_approval=st.session_state.get("fusion_segment_plan_approval") or {},
                        temperature=temperature,
                        source_identity=st.session_state.get("fusion_visual_source_identity"),
                        finalization_context=finalization_context,
                        resume_snapshot=st.session_state.get("fusion_matching_resume_snapshot"),
                    )
                    st.session_state["fusion_matching_task_id"] = task_id
                    st.session_state.pop("fusion_matching_resume_snapshot", None)
                task = fusion_matching_task_status(task_id)
                status = str(task.get("status") or "")
                if status == "completed":
                    finalization = task.get("finalization")
                    if not isinstance(finalization, dict):
                        st.error(tr("分段匹配完成，但最终校验结果缺失。"))
                        st.stop()
                    st.session_state["fusion_original_matched_script"] = finalization.get(
                        "original_script", []
                    )
                    st.session_state["fusion_evidence_conflicts"] = finalization.get(
                        "evidence_conflicts", []
                    )
                    st.session_state["fusion_finalization_report"] = finalization.get(
                        "finalization_report", {}
                    )
                    st.session_state["fusion_continuity_report"] = finalization.get(
                        "continuity_report", {}
                    )
                    st.session_state["fusion_render_preflight"] = finalization.get(
                        "preflight", {}
                    )
                    st.session_state["fusion_narrative_map"] = finalization.get(
                        "narrative_map", {}
                    )
                    st.session_state["fusion_narrative_quality_findings"] = finalization.get(
                        "narrative_quality_findings", []
                    )
                    st.session_state["fusion_workspace"] = project_fusion_workspace(
                        task=task,
                        finalization=finalization,
                    )
                    if not finalization.get("renderable"):
                        preflight = finalization.get("preflight") or {}
                        continuity = finalization.get("continuity_report") or {}
                        narrative_map = finalization.get("narrative_map") or {}
                        if narrative_map.get("approval_status") == "pending":
                            st.caption(tr("请审阅 Narrative Map；可批准、明确跳过，或应用受限草稿。"))
                            draft_text = st.text_area(
                                tr("Narrative Map 草稿"),
                                value=json.dumps(narrative_map.get("beats") or [], ensure_ascii=False, indent=2),
                                key=f"fusion_narrative_map_draft_{task_id}",
                            )
                            review_columns = st.columns(3)
                            for action, label, column in (
                                ("approved", tr("批准 Narrative Map"), review_columns[0]),
                                ("skipped", tr("跳过 Narrative Map 审阅"), review_columns[1]),
                                ("applied_draft", tr("应用草稿并显示影响"), review_columns[2]),
                            ):
                                if column.button(label, key=f"fusion_narrative_map_{action}_{task_id}"):
                                    try:
                                        beats = json.loads(draft_text) if action == "applied_draft" else None
                                        review_fusion_narrative_map(task_id, action=action, edited_beats=beats)
                                        st.rerun()
                                    except (ValueError, json.JSONDecodeError) as exc:
                                        st.error(str(exc))
                        elif preflight.get("warnings") and not preflight.get("blockers"):
                            override_reason = st.text_area(
                                tr("Render Preflight 警告覆盖理由"),
                                key=f"fusion_warning_override_{task_id}",
                                help=tr("该理由会写入本地审计记录；它不会覆盖任何阻断项。"),
                            )
                            if st.button(tr("记录理由并继续渲染"), key=f"fusion_warning_override_apply_{task_id}"):
                                try:
                                    override_fusion_matching_render_warning(task_id, override_reason)
                                    st.rerun()
                                except ValueError as exc:
                                    st.error(str(exc))
                        if not continuity.get("is_renderable", True):
                            st.error(tr("分段匹配发现待审阅叙事连续性问题，脚本未进入最终校验或可渲染状态。"))
                            st.json(continuity)
                        else:
                            st.error(tr("Render Preflight 仍有待处理项，脚本未进入可渲染状态。"))
                            st.json(preflight)
                        st.stop()
                    st.session_state["video_clip_json"] = finalization.get("finalized_script", [])
                    st.session_state.pop("fusion_matching_task_id", None)
                    action_clicked = False
                    st.success(tr("分段匹配与最终校验已完成。"))
                else:
                    progress = max(0, min(100, int(round(float(task.get("progress", 0))))))
                    st.progress(progress, text=f"✂️ {task.get('message') or '正在分段匹配剪辑脚本…'}")
                    stream_snapshot = task.get("stream_snapshot") or {}
                    if isinstance(stream_snapshot, dict) and stream_snapshot.get("phase") == "matching":
                        stream_state = str(stream_snapshot.get("state") or "waiting_first_chunk")
                        segment_id = str(stream_snapshot.get("segment_id") or "")
                        attempt = int(stream_snapshot.get("attempt") or 1)
                        state_label = {
                            "waiting_first_chunk": "正在等待模型首个分片",
                            "streaming": "模型正在流式生成",
                            "completed": "当前段落流式生成完成",
                            "waiting_first_chunk_timeout": "等待首个模型分片超时",
                            "timed_out_after_progress": "模型已有输出后停止推进",
                            "total_budget_expired": "本次请求已达到总时限",
                            "failed": "模型请求失败",
                        }.get(stream_state, "正在同步模型进度")
                        st.caption(f"{state_label} · {segment_id} · 第 {attempt} 次尝试")
                        reasoning_text = str(stream_snapshot.get("reasoning_text") or "")
                        content_text = str(stream_snapshot.get("content_text") or "")
                        if content_text:
                            st.text_area(
                                tr("模型输出预览"),
                                value=content_text[-1800:],
                                height=120,
                                disabled=True,
                                key=f"fusion_content_preview_{task_id}_{stream_snapshot.get('revision', 0)}",
                            )
                        if reasoning_text or stream_snapshot.get("failure_diagnostics"):
                            with st.expander(tr("高级流式诊断"), expanded=False):
                                if reasoning_text:
                                    st.text_area(
                                        tr("模型推理过程"),
                                        value=reasoning_text[-1800:],
                                        height=120,
                                        disabled=True,
                                        key=f"fusion_reasoning_preview_{task_id}_{stream_snapshot.get('revision', 0)}",
                                    )
                                if stream_snapshot.get("failure_diagnostics"):
                                    st.json(stream_snapshot["failure_diagnostics"])
                    if status in {"queued", "running"} and st.button(
                        tr("取消分段匹配"), key="cancel_fusion_matching_task"
                    ):
                        cancel_fusion_matching_task(task_id)
                    if status in {"failed", "cancelled", "interrupted"}:
                        st.error(f"{tr('分段匹配失败')}: {task.get('error_message') or status}")
                        if task.get("segment_matches"):
                            st.json(task["segment_matches"])
                        if st.button(tr("恢复分段匹配"), key="resume_fusion_matching_task"):
                            resume_fusion_matching_task(task_id)
                    st.info(tr("分段匹配正在后台运行；完成后会自动进入最终校验。"))
                    if status in {"queued", "running"}:
                        time.sleep(1)
                        st.rerun()
                    st.stop()

        if action_clicked or automatic_finalization:
            generate_script_short_sunmmary(
                params,
                subtitle_paths,
                video_theme,
                temperature,
                tr,
                plot_analysis=plot_analysis,
                subtitle_content=st.session_state.get('subtitle_content', ''),
                enable_web_search=web_search_enabled,
                video_paths=_selected_video_paths(),
                narration_language=narration_language,
                narration_copy=st.session_state.get(narration_copy_key, ''),
                drama_genre=drama_genre,
                original_sound_ratio=original_sound_ratio,
                prompt_category=summary_config["prompt_category"],
                search_keywords=summary_config["search_keywords"],
                empty_title_message_key=summary_config["empty_title_message_key"],
                web_search_context_description=summary_config["web_search_context_description"],
                visual_evidence=visual_evidence,
                highlight_candidates=highlight_candidates,
                highlight_candidate_items=st.session_state.get("fusion_highlight_candidate_items", []),
                highlight_candidate_rejections=st.session_state.get("fusion_highlight_candidate_rejections", []),
                highlight_candidate_intake=st.session_state.get("fusion_highlight_candidate_intake"),
                visual_source_identity=st.session_state.get("fusion_visual_source_identity"),
                fusion_segment_plan=st.session_state.get("fusion_segment_plan"),
                fusion_plan_approval=st.session_state.get("fusion_segment_plan_approval"),
                pre_matched_fusion_result=pre_matched_fusion_result,
            )

    if script_path in SUMMARY_SCRIPT_MODES:
        summary_config = _summary_mode_config(script_path)
        st.text_area(
            tr(summary_config["narration_copy_label_key"]),
            key=_summary_state_key(summary_config, "narration_copy"),
            height=220,
            help=tr("Narration Copy Help"),
        )
        if script_path == MODE_FILM_VISION_FUSION and st.session_state.get("fusion_visual_evidence"):
            with st.expander(tr("视觉证据摘要"), expanded=False):
                st.caption(str(st.session_state.get("fusion_visual_artifact_path", "")))
                st.text_area(
                    tr("视觉证据摘要"),
                    value=st.session_state["fusion_visual_evidence"],
                    height=240,
                    disabled=True,
                    key="fusion_visual_evidence_preview",
                )
            if st.session_state.get("fusion_highlight_candidates"):
                with st.expander(tr("原片高光候选"), expanded=False):
                    st.text_area(
                        tr("原片高光候选"),
                        value=st.session_state["fusion_highlight_candidates"],
                        height=180,
                        disabled=True,
                        key="fusion_highlight_candidates_preview",
                    )
            if st.session_state.get("fusion_finalization_report"):
                with st.expander(tr("原片占比校验报告"), expanded=True):
                    st.json(st.session_state["fusion_finalization_report"])
                    if st.session_state.get("fusion_generation_audit_path"):
                        st.caption(
                            f"{tr('本地审计文件')}: {st.session_state['fusion_generation_audit_path']}"
                        )
            if st.session_state.get("fusion_render_preflight"):
                with st.expander(tr("Render Preflight"), expanded=True):
                    st.json(st.session_state["fusion_render_preflight"])
            if st.session_state.get("fusion_workspace"):
                with st.expander(tr("Fusion Project Workspace"), expanded=True):
                    workspace = st.session_state["fusion_workspace"]
                    st.caption(f"{tr('当前阶段')}: {workspace.get('phase')}")
                    queue = workspace.get("review_queue") or []
                    if queue:
                        st.caption(tr("审阅队列（按优先级）"))
                        st.json(queue)
                        locatable = [item for item in queue if item.get("segment_id")]
                        if locatable:
                            selected = st.selectbox(
                                tr("定位审阅项"),
                                options=locatable,
                                format_func=lambda item: f"{item.get('kind')} · {item.get('code')} · {item.get('segment_id')}",
                                key="fusion_workspace_selected_review_item",
                            )
                            location = locate_fusion_review_item(
                                narrative_map=workspace.get("inspector", {}).get("narrative_map", {}),
                                segment_id=selected.get("segment_id", ""),
                            )
                            if location.get("time_range"):
                                st.caption(f"{tr('源视频定位')}: {location['time_range']} · {location['active_subject']}")
                                selected_beat = next(
                                    (
                                        beat for beat in workspace.get("inspector", {}).get("narrative_map", {}).get("beats", [])
                                        if isinstance(beat, dict)
                                        and str(beat.get("segment_id") or "") == str(selected.get("segment_id") or "")
                                    ),
                                    {},
                                )
                                preview_columns = st.columns((3, 2))
                                source_videos = _selected_video_paths()
                                with preview_columns[0]:
                                    if source_videos and os.path.isfile(source_videos[0]):
                                        try:
                                            start_seconds = TimeRange.parse(location["time_range"]).start_seconds
                                            st.video(source_videos[0], start_time=start_seconds)
                                        except ValueError:
                                            st.caption(tr("该审阅项的时间范围无法用于视频预览。"))
                                    else:
                                        st.caption(tr("未找到可用于审阅的源视频。"))
                                with preview_columns[1]:
                                    st.caption(tr("对应 Story Beat"))
                                    st.json(selected_beat)
                            if selected.get("kind") == "quality":
                                quality_actions = st.columns(2)
                                if quality_actions[0].button(tr("批准并定向修复此分段"), key="fusion_approve_quality_repair"):
                                    try:
                                        workspace_task_id = str(
                                            workspace.get("task_center", {}).get("task_id")
                                            or st.session_state.get("fusion_matching_task_id")
                                            or ""
                                        )
                                        if not workspace_task_id:
                                            raise ValueError("Fusion Matching Task is unavailable for targeted repair")
                                        approve_fusion_quality_repair(
                                            workspace_task_id,
                                            segment_id=str(selected.get("segment_id") or ""),
                                            finding_code=str(selected.get("code") or ""),
                                        )
                                        resume_fusion_matching_task(workspace_task_id)
                                        st.rerun()
                                    except ValueError as exc:
                                        st.error(str(exc))
                                if quality_actions[1].button(tr("忽略此质量建议"), key="fusion_ignore_quality_finding"):
                                    try:
                                        workspace_task_id = str(
                                            workspace.get("task_center", {}).get("task_id")
                                            or st.session_state.get("fusion_matching_task_id")
                                            or ""
                                        )
                                        if not workspace_task_id:
                                            raise ValueError("Fusion Matching Task is unavailable for this review decision")
                                        updated_task = ignore_fusion_quality_finding(
                                            workspace_task_id,
                                            segment_id=str(selected.get("segment_id") or ""),
                                            finding_code=str(selected.get("code") or ""),
                                        )
                                        st.session_state["fusion_workspace"] = project_fusion_workspace(
                                            task=updated_task,
                                            finalization=updated_task.get("finalization") or {},
                                        )
                                        st.rerun()
                                    except ValueError as exc:
                                        st.error(str(exc))
                    else:
                        st.caption(tr("当前没有待处理的审阅项。"))
                    with st.expander(tr("Task Center"), expanded=False):
                        st.json(list_fusion_matching_tasks())
                    workspace_task_id = str(
                        workspace.get("task_center", {}).get("task_id")
                        or st.session_state.get("fusion_matching_task_id")
                        or ""
                    )
                    ignored_decisions = [
                        item for item in workspace.get("inspector", {}).get("review_decisions", [])
                        if isinstance(item, dict) and item.get("kind") == "quality" and item.get("action") == "ignored"
                    ]
                    if workspace_task_id and ignored_decisions:
                        latest_ignore = ignored_decisions[-1]
                        if st.button(tr("撤销最近一次忽略质量建议"), key="fusion_undo_quality_ignore"):
                            try:
                                updated_task = undo_fusion_quality_ignore(
                                    workspace_task_id,
                                    decision_id=str(latest_ignore.get("decision_id") or ""),
                                )
                                st.session_state["fusion_workspace"] = project_fusion_workspace(
                                    task=updated_task,
                                    finalization=updated_task.get("finalization") or {},
                                )
                                st.rerun()
                            except ValueError as exc:
                                st.error(str(exc))
                    restorable_versions = [
                        item for item in workspace.get("versions", [])
                        if isinstance(item, dict) and isinstance(item.get("snapshot"), dict)
                    ]
                    if workspace_task_id and restorable_versions:
                        with st.expander(tr("版本比较与恢复"), expanded=False):
                            version_ids = [str(item.get("version_id") or "") for item in restorable_versions]
                            if len(version_ids) > 1:
                                baseline_id = st.selectbox(
                                    tr("比较基准版本"), version_ids, key="fusion_version_baseline"
                                )
                                candidate_id = st.selectbox(
                                    tr("比较目标版本"), version_ids,
                                    index=len(version_ids) - 1,
                                    key="fusion_version_candidate",
                                )
                                if st.button(tr("比较版本"), key="fusion_compare_versions"):
                                    try:
                                        st.session_state["fusion_version_comparison"] = compare_fusion_matching_versions(
                                            workspace_task_id,
                                            baseline_version_id=baseline_id,
                                            candidate_version_id=candidate_id,
                                        )
                                    except ValueError as exc:
                                        st.error(str(exc))
                                if st.session_state.get("fusion_version_comparison"):
                                    st.json(st.session_state["fusion_version_comparison"])
                            restore_id = st.selectbox(
                                tr("恢复保存的审阅上下文"), version_ids,
                                key="fusion_restore_version",
                            )
                            if st.button(tr("恢复该版本"), key="fusion_restore_version_apply"):
                                try:
                                    updated_task = restore_fusion_matching_version(
                                        workspace_task_id, version_id=restore_id
                                    )
                                    restored_finalization = updated_task.get("finalization") or {}
                                    st.session_state["fusion_workspace"] = project_fusion_workspace(
                                        task=updated_task, finalization=restored_finalization
                                    )
                                    st.session_state["fusion_render_preflight"] = restored_finalization.get("preflight") or {}
                                    st.session_state["video_clip_json"] = restored_finalization.get("finalized_script") or []
                                    st.rerun()
                                except ValueError as exc:
                                    st.error(str(exc))
            if st.session_state.get("fusion_narrative_map"):
                with st.expander(tr("Narrative Map"), expanded=False):
                    st.json(st.session_state["fusion_narrative_map"])
                    if st.session_state.get("fusion_narrative_quality_findings"):
                        st.caption(tr("叙事质量建议（不会自动改写脚本）"))
                        st.json(st.session_state["fusion_narrative_quality_findings"])
            if st.session_state.get("fusion_evidence_conflicts"):
                with st.expander(tr("证据冲突（待审阅）"), expanded=True):
                    st.json(st.session_state["fusion_evidence_conflicts"])
                    if st.button(tr("确认已审阅全部证据冲突"), key="fusion_acknowledge_conflicts"):
                        st.session_state["fusion_evidence_conflicts"] = [
                            {**item, "status": "acknowledged"}
                            for item in st.session_state["fusion_evidence_conflicts"]
                            if isinstance(item, dict)
                        ]
                        report = st.session_state.get("fusion_finalization_report")
                        if isinstance(report, dict):
                            report["unresolved_conflict_count"] = 0
                            report["acknowledged_conflict_count"] = len(
                                st.session_state["fusion_evidence_conflicts"]
                            )
                        acknowledge_fusion_audit(
                            str(st.session_state.get("fusion_generation_audit_path", "")),
                            st.session_state["fusion_evidence_conflicts"],
                        )
                        pending_script = st.session_state.pop(
                            "fusion_finalized_script_pending_review", None
                        )
                        if isinstance(pending_script, list):
                            st.session_state["video_clip_json"] = pending_script
                        st.success(tr("证据冲突已标记为已审阅；这不代表任一证据来源已被验证。"))
                        st.rerun()

    if action_clicked and script_path not in SUMMARY_SCRIPT_MODES:
        if script_path == "auto":
            # 执行纪录片视频脚本生成（视频无字幕无配音）
            generate_script_docu(params, tr)
        elif script_path == "short":
            # 执行 短剧混剪 脚本生成
            summary_config = SUMMARY_MODE_CONFIGS[MODE_SHORT_SUMMARY]
            type_option_key = _summary_state_key(summary_config, "type_option")
            custom_type_key = _summary_state_key(summary_config, "custom_type")
            web_search_key = _summary_state_key(summary_config, "web_search_enabled")
            plot_analysis_key = _summary_state_key(summary_config, "plot_analysis")
            plot_source_key = _summary_state_key(summary_config, "plot_analysis_subtitle_path")
            plot_signature_key = _summary_state_key(summary_config, "plot_analysis_signature")
            pending_plot_key = _summary_state_key(summary_config, "pending_plot_analysis")
            if (
                st.session_state.get(type_option_key) == "custom"
                and not str(st.session_state.get(custom_type_key, '') or '').strip()
            ):
                st.error(tr(summary_config["custom_type_empty_key"]))
                st.stop()

            subtitle_paths = _selected_subtitle_paths()
            subtitle_path = subtitle_paths[0] if subtitle_paths else None
            video_theme = st.session_state.get('video_theme')
            web_search_enabled = bool(st.session_state.get(web_search_key, False))
            current_signature = _short_drama_plot_analysis_signature(
                subtitle_paths,
                video_theme,
                web_search_enabled,
                _selected_video_paths(),
            )
            plot_analysis = ""
            if st.session_state.get(plot_signature_key) == current_signature:
                plot_analysis = st.session_state.get(plot_analysis_key, '')
            elif (
                not web_search_enabled
                and st.session_state.get(plot_source_key) == subtitle_path
            ):
                plot_analysis = st.session_state.get(plot_analysis_key, '')

            custom_clips = st.session_state.get('custom_clips')
            short_result = generate_script_short(
                tr,
                params,
                custom_clips,
                subtitle_paths=subtitle_paths,
                video_theme=video_theme,
                temperature=st.session_state.get('temperature', 0.7),
                plot_analysis=plot_analysis,
                subtitle_content=st.session_state.get('subtitle_content', ''),
                enable_web_search=web_search_enabled,
                video_paths=_selected_video_paths(),
                drama_genre=_resolve_short_drama_type(),
                prompt_category=summary_config["prompt_category"],
                search_keywords=summary_config["search_keywords"],
                empty_title_message_key=summary_config["empty_title_message_key"],
                web_search_context_description=summary_config["web_search_context_description"],
            )
            if short_result and short_result.get("plot_analysis"):
                st.session_state[pending_plot_key] = {
                    "plot_analysis": short_result["plot_analysis"],
                    "subtitle_path": subtitle_path,
                    "signature": current_signature,
                }
                st.session_state[plot_source_key] = subtitle_path
                st.session_state[plot_signature_key] = current_signature
        else:
            load_script(tr, script_path)

    render_video_script_editor(tr)


def load_script(tr, script_path):
    """加载脚本文件"""
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()
            script = utils.clean_model_output(script)
            st.session_state['video_clip_json'] = json.loads(script)
            st.session_state["fusion_visual_regression_only"] = False
            st.success(tr("Script loaded successfully"))
            st.rerun()
    except Exception as e:
        logger.error(f"加载脚本文件时发生错误\n{traceback.format_exc()}")
        st.error(f"{tr('Failed to load script')}: {str(e)}")


def save_script_with_validation(tr, video_clip_json_details):
    """保存视频脚本（包含格式验证）"""
    if is_unverified_fusion_regression():
        st.error(tr("未验证来源的旧视觉证据仅可用于回归测试，不能保存为正式脚本或用于渲染。"))
        return
    if not video_clip_json_details:
        st.error(tr("请输入视频脚本"))
        st.stop()

    # 第一步：格式验证
    with st.spinner(tr("Validating script format...")):
        try:
            result = check_script.check_format(video_clip_json_details)
            if not result.get('success'):
                # 格式验证失败，显示详细错误信息
                error_message = result.get('message', '未知错误')
                error_details = result.get('details', '')

                st.error(f"**{tr('Script format validation failed')}**")
                st.error(f"**{tr('Error Message')}:** {error_message}")
                if error_details:
                    st.error(f"**{tr('Details')}:** {error_details}")

                # 显示正确格式示例
                st.info(f"**{tr('Correct script format example')}:**")
                example_script = [
                    {
                        "_id": 1,
                        "video_id": 1,
                        "video_name": "1.mp4",
                        "timestamp": "00:00:00,600-00:00:07,559",
                        "picture": "工地上，蔡晓艳奋力救人，场面混乱",
                        "narration": "灾后重建，工地上险象环生！泼辣女工蔡晓艳挺身而出，救人第一！",
                        "OST": 0
                    },
                    {
                        "_id": 2,
                        "video_id": 2,
                        "video_name": "2.mp4",
                        "timestamp": "00:00:08,240-00:00:12,359",
                        "picture": "领导视察，蔡晓艳不屑一顾",
                        "narration": "播放原片4",
                        "OST": 1
                    }
                ]
                st.code(json.dumps(example_script, ensure_ascii=False, indent=2), language='json')
                st.stop()

        except Exception as e:
            st.error(f"{tr('Script format validation error')}: {str(e)}")
            st.stop()

    # 第二步：保存脚本
    with st.spinner(tr("Save Script")):
        script_dir = utils.script_dir()
        timestamp = time.strftime("%Y-%m%d-%H%M%S")
        save_path = os.path.join(script_dir, f"{timestamp}.json")

        try:
            data = json.loads(video_clip_json_details)
            with open(save_path, 'w', encoding='utf-8') as file:
                json.dump(data, file, ensure_ascii=False, indent=4)
                st.session_state['video_clip_json'] = data
                st.session_state['video_clip_json_path'] = save_path
                
                # 标记需要切换到文件选择模式（在下次渲染前处理）
                st.session_state['_switch_to_file_mode'] = True

                # 更新配置
                config.app["video_clip_json_path"] = save_path

                # 显示成功消息
                st.success(tr("Script validated and saved successfully"))

                # 强制重新加载页面更新选择框
                time.sleep(0.5)  # 给一点时间让用户看到成功消息
                st.rerun()

        except Exception as err:
            st.error(f"{tr('Failed to save script')}: {str(err)}")
            st.stop()


# crop_video函数已移除 - 现在使用统一裁剪策略，不再需要预裁剪步骤


def get_script_params():
    """获取脚本参数"""
    subtitle_paths = _selected_subtitle_paths()
    return {
        'video_language': st.session_state.get('video_language', ''),
        'video_clip_json_path': st.session_state.get('video_clip_json_path', ''),
        'video_origin_path': st.session_state.get('video_origin_path', ''),
        'video_origin_paths': _selected_video_paths(),
        'original_subtitle_path': subtitle_paths[0] if subtitle_paths else '',
        'original_subtitle_paths': subtitle_paths,
        'video_name': st.session_state.get('video_name', ''),
        'video_plot': st.session_state.get('video_plot', '')
    }
