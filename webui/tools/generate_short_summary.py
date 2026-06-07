#!/usr/bin/env python
# -*- coding: UTF-8 -*-

'''
@Project: NarratoAI
@File   : 短剧解说脚本生成
@Author : 小林同学
@Date   : 2025/5/10 下午10:26 
'''
import os
import json
import time
import traceback
import html
import streamlit as st
from loguru import logger

from app.config import config
from app.services.SDE.short_drama_explanation import (
    analyze_subtitle,
    generate_narration_copy as generate_narration_copy_legacy,
    match_narration_copy_to_script as match_narration_copy_to_script_legacy,
)
from app.services.subtitle_text import read_subtitle_text
from app.services.short_drama_narration_validation import (
    normalize_script_video_sources,
)
from app.services.tavily_search import TavilySearchError, format_search_context, search_short_drama
# 导入新的LLM服务模块 - 确保提供商被注册
import app.services.llm  # 这会触发提供商注册
from app.services.llm.migration_adapter import SubtitleAnalyzerAdapter
import re


PUBLIC_SCRIPT_FIELDS = ["_id", "video_id", "video_name", "timestamp", "picture", "narration", "OST"]


def _normalize_paths(paths):
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


def _build_combined_subtitle_content(subtitle_paths, video_paths=None):
    sections = []
    video_paths = _normalize_paths(video_paths)
    for index, subtitle_path in enumerate(_normalize_paths(subtitle_paths), start=1):
        if not os.path.exists(subtitle_path):
            continue

        video_path = video_paths[index - 1] if index <= len(video_paths) else ""
        if video_path:
            header = (
                f"# 视频 {index}: {os.path.basename(video_path)}\n"
                f"字幕文件: {os.path.basename(subtitle_path)}"
            )
        else:
            header = f"# 视频 {index}\n字幕文件: {os.path.basename(subtitle_path)}"
        sections.append(f"{header}\n{read_subtitle_text(subtitle_path).text}".strip())

    return "\n\n".join(sections)


def _normalize_narration_items_video_sources(items, video_paths):
    return normalize_script_video_sources(items, _normalize_paths(video_paths))


def _strip_planner_only_fields(items):
    return [
        {field: item[field] for field in PUBLIC_SCRIPT_FIELDS if field in item}
        for item in items
        if isinstance(item, dict)
    ]


def _format_progress_status(progress, message: str = "", tr=lambda key: key):
    message = str(message or "").strip()
    if message:
        return message
    return f"{tr('Progress')}: {progress}%"


def parse_and_fix_json(json_string):
    """
    解析并修复JSON字符串

    Args:
        json_string: 待解析的JSON字符串

    Returns:
        dict: 解析后的字典，如果解析失败返回None
    """
    if not json_string or not json_string.strip():
        logger.error("JSON字符串为空")
        return None

    # 清理字符串
    json_string = json_string.strip()

    # 尝试直接解析
    try:
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        logger.warning(f"直接JSON解析失败: {e}")

    # 尝试修复双大括号问题（LLM生成的常见问题）
    try:
        # 将双大括号替换为单大括号
        fixed_braces = json_string.replace('{{', '{').replace('}}', '}')
        logger.info("修复双大括号格式")
        return json.loads(fixed_braces)
    except json.JSONDecodeError:
        pass

    # 尝试提取JSON部分
    try:
        # 查找JSON代码块
        json_match = re.search(r'```json\s*(.*?)\s*```', json_string, re.DOTALL)
        if json_match:
            json_content = json_match.group(1).strip()
            logger.info("从代码块中提取JSON内容")
            return json.loads(json_content)
    except json.JSONDecodeError:
        pass

    # 尝试查找大括号包围的内容
    try:
        # 查找第一个 { 到最后一个 } 的内容
        start_idx = json_string.find('{')
        end_idx = json_string.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_content = json_string[start_idx:end_idx+1]
            logger.info("提取大括号包围的JSON内容")
            return json.loads(json_content)
    except json.JSONDecodeError:
        pass

    # 尝试综合修复JSON格式问题
    try:
        fixed_json = json_string

        # 1. 修复双大括号问题
        fixed_json = fixed_json.replace('{{', '{').replace('}}', '}')

        # 2. 提取JSON内容（如果有其他文本包围）
        start_idx = fixed_json.find('{')
        end_idx = fixed_json.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            fixed_json = fixed_json[start_idx:end_idx+1]

        # 3. 移除注释
        fixed_json = re.sub(r'#.*', '', fixed_json)
        fixed_json = re.sub(r'//.*', '', fixed_json)

        # 4. 移除多余的逗号
        fixed_json = re.sub(r',\s*}', '}', fixed_json)
        fixed_json = re.sub(r',\s*]', ']', fixed_json)

        # 5. 修复单引号
        fixed_json = re.sub(r"'([^']*)':", r'"\1":', fixed_json)

        # 6. 修复没有引号的属性名
        fixed_json = re.sub(r'(\w+)(\s*):', r'"\1"\2:', fixed_json)

        # 7. 修复重复的引号
        fixed_json = re.sub(r'""([^"]*?)""', r'"\1"', fixed_json)

        logger.info("尝试综合修复JSON格式问题后解析")
        return json.loads(fixed_json)
    except json.JSONDecodeError as e:
        logger.debug(f"综合修复失败: {e}")
        pass

    # 如果所有方法都失败，直接返回 None，避免生成不可剪辑的默认假脚本
    logger.error(f"所有JSON解析方法都失败，原始内容: {json_string[:200]}...")
    return None


def _get_tavily_api_key() -> str:
    return (
        st.session_state.get("tavily_api_key")
        or config.app.get("tavily_api_key")
        or ""
    ).strip()


def _build_tavily_context(short_name: str, tr=lambda key: key) -> str | None:
    short_name = str(short_name or "").strip()
    if not short_name:
        st.error(tr("Please enter short drama name before web search"))
        return None

    api_key = _get_tavily_api_key()
    if not api_key:
        st.error(tr("Please configure Tavily API Key in Basic Settings"))
        return None

    try:
        search_data = search_short_drama(
            short_name,
            api_key,
            search_depth=config.app.get("tavily_search_depth", "basic"),
            max_results=config.app.get("tavily_max_results", 5),
        )
        return format_search_context(search_data)
    except TavilySearchError as e:
        logger.error(f"Tavily 短剧检索失败: {str(e)}")
        st.error(f"{tr('Tavily search failed')}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Tavily 短剧检索异常: {traceback.format_exc()}")
        st.error(f"{tr('Tavily search failed')}: {str(e)}")
        return None


def _build_plot_analysis_input(
    subtitle_content: str,
    short_name: str = "",
    enable_web_search: bool = False,
    tr=lambda key: key,
) -> str | None:
    subtitle_content = str(subtitle_content or "").strip()
    if not enable_web_search:
        return subtitle_content

    tavily_context = _build_tavily_context(short_name, tr)
    if tavily_context is None:
        return None

    return f"""# 分析补充说明
请先参考 Tavily 联网检索结果理解短剧名称、人物关系、剧情背景和公开剧情梗概，再结合原始字幕完成剧情理解。
如果联网检索结果与字幕内容冲突，请以字幕内容为准；时间戳必须只从字幕内容中提取。

{tavily_context}

# 原始字幕
{subtitle_content}"""


def analyze_short_drama_plot(
    subtitle_path,
    temperature,
    tr=lambda key: key,
    subtitle_content=None,
    short_name: str = "",
    enable_web_search: bool = False,
    video_paths=None,
):
    """仅执行短剧字幕剧情理解，返回可编辑的剧情分析文本。"""
    subtitle_paths = _normalize_paths(subtitle_path)
    if not subtitle_paths:
        st.error(tr("Please generate or upload subtitles first"))
        return None
    missing_subtitle_paths = [path for path in subtitle_paths if not os.path.exists(path)]
    if missing_subtitle_paths:
        st.error(tr("Subtitle file does not exist"))
        return None

    text_provider = config.app.get('text_llm_provider', 'gemini').lower()
    text_api_key = config.app.get(f'text_{text_provider}_api_key')
    text_model = config.app.get(f'text_{text_provider}_model_name')
    text_base_url = config.app.get(f'text_{text_provider}_base_url')

    subtitle_content = str(subtitle_content or "").strip() or _build_combined_subtitle_content(
        subtitle_paths,
        video_paths,
    )
    if not subtitle_content:
        st.error(tr("Subtitle file is empty or unreadable"))
        return None

    plot_analysis_input = _build_plot_analysis_input(
        subtitle_content,
        short_name=short_name,
        enable_web_search=enable_web_search,
        tr=tr,
    )
    if plot_analysis_input is None:
        return None

    try:
        logger.info("使用新的LLM服务架构进行字幕分析")
        analyzer = SubtitleAnalyzerAdapter(text_api_key, text_model, text_base_url, text_provider)
        analysis_result = analyzer.analyze_subtitle(plot_analysis_input)
    except Exception as e:
        logger.warning(f"使用新LLM服务失败，回退到旧实现: {str(e)}")
        analysis_result = analyze_subtitle(
            subtitle_content=plot_analysis_input,
            api_key=text_api_key,
            model=text_model,
            base_url=text_base_url,
            save_result=True,
            temperature=temperature,
            provider=text_provider
        )

    if analysis_result["status"] != "success":
        logger.error(f"分析失败: {analysis_result['message']}")
        st.error(tr("Script generation failed check logs"))
        return None

    return analysis_result["analysis"]


def generate_short_drama_narration_copy(
    subtitle_path,
    video_theme,
    temperature,
    tr=lambda key: key,
    plot_analysis=None,
    subtitle_content=None,
    enable_web_search: bool = False,
    video_paths=None,
    narration_language: str = "简体中文（中国）",
    drama_genre: str = "逆袭/复仇",
):
    """生成可由用户审核修改的短剧解说正文，不绑定时间戳。"""
    subtitle_paths = _normalize_paths(subtitle_path)
    if not subtitle_paths:
        st.error(tr("Please generate or upload subtitles first"))
        return None
    missing_subtitle_paths = [path for path in subtitle_paths if not os.path.exists(path)]
    if missing_subtitle_paths:
        st.error(tr("Subtitle file does not exist"))
        return None

    selected_video_paths = _normalize_paths(video_paths)
    subtitle_content = str(subtitle_content or "").strip() or _build_combined_subtitle_content(
        subtitle_paths,
        selected_video_paths,
    )
    if not subtitle_content:
        st.error(tr("Subtitle file is empty or unreadable"))
        return None

    analysis_text = str(plot_analysis or "").strip()
    if not analysis_text:
        analysis_text = analyze_short_drama_plot(
            subtitle_paths,
            temperature,
            tr,
            subtitle_content=subtitle_content,
            short_name=video_theme,
            enable_web_search=enable_web_search,
            video_paths=selected_video_paths,
        )
        if not analysis_text:
            return None

    text_provider = config.app.get('text_llm_provider', 'gemini').lower()
    text_api_key = config.app.get(f'text_{text_provider}_api_key')
    text_model = config.app.get(f'text_{text_provider}_model_name')
    text_base_url = config.app.get(f'text_{text_provider}_base_url')

    try:
        logger.info("使用新的LLM服务架构生成可审核解说文案")
        analyzer = SubtitleAnalyzerAdapter(text_api_key, text_model, text_base_url, text_provider)
        narration_result = analyzer.generate_narration_copy(
            short_name=video_theme,
            plot_analysis=analysis_text,
            subtitle_content=subtitle_content,
            temperature=temperature,
            narration_language=narration_language,
            drama_genre=drama_genre,
        )
    except Exception as e:
        logger.warning(f"使用新LLM服务生成文案失败，回退到旧实现: {str(e)}")
        narration_result = generate_narration_copy_legacy(
            short_name=video_theme,
            plot_analysis=analysis_text,
            subtitle_content=subtitle_content,
            api_key=text_api_key,
            model=text_model,
            base_url=text_base_url,
            temperature=temperature,
            provider=text_provider,
            narration_language=narration_language,
            drama_genre=drama_genre,
        )

    if narration_result.get("status") != "success":
        logger.error(f"解说文案正文生成失败: {narration_result.get('message')}")
        st.error(tr("Script generation failed check logs"))
        return None

    narration_copy = str(narration_result.get("narration_copy", "")).strip()
    if not narration_copy:
        logger.error("模型返回空解说文案正文")
        st.error(tr("Generated narration copy is empty"))
        return None

    return {
        "narration_copy": narration_copy,
        "plot_analysis": analysis_text,
        "subtitle_content": subtitle_content,
    }


def generate_script_short_sunmmary(
    params,
    subtitle_path,
    video_theme,
    temperature,
    tr=lambda key: key,
    plot_analysis=None,
    subtitle_content=None,
    enable_web_search: bool = False,
    video_paths=None,
    narration_language: str = "简体中文（中国）",
    narration_copy: str = "",
    drama_genre: str = "逆袭/复仇",
    original_sound_ratio: int = 30,
):
    """
    生成 短剧解说 视频脚本
    要求: 提供高质量短剧字幕
    适合场景: 短剧
    """
    progress_bar = st.empty()
    status_text = st.empty()
    stream_text = st.empty()
    stream_state = {
        "reasoning": "",
        "content": "",
        "last_update": 0.0,
    }

    def update_progress(progress: float, message: str = ""):
        progress_bar.progress(progress)
        status_text.text(_format_progress_status(progress, message, tr))

    def update_waiting(message: str = ""):
        progress_bar.empty()
        if message:
            status_text.text(message)
        else:
            status_text.empty()

    def update_stream_window(event):
        event = event or {}
        chunk_type = str(event.get("type") or "content")
        chunk_text = str(event.get("text") or "")
        if chunk_type == "done" or not chunk_text:
            return

        bucket = "reasoning" if chunk_type == "reasoning" else "content"
        stream_state[bucket] += chunk_text

        now = time.time()
        if now - stream_state["last_update"] < 0.12:
            return
        stream_state["last_update"] = now

        blocks = []
        if stream_state["reasoning"].strip():
            blocks.append(
                f"{tr('Model reasoning stream')}\n"
                f"{stream_state['reasoning'][-900:]}"
            )
        if stream_state["content"].strip():
            blocks.append(
                f"{tr('Model output preview')}\n"
                f"{stream_state['content'][-900:]}"
            )

        preview = "\n\n".join(blocks)[-1800:]
        escaped_preview = html.escape(preview)
        stream_text.markdown(
            f"""
            <div style="height:150px; overflow:hidden; border:1px solid #e5e7eb;
                        border-radius:8px; padding:10px 12px; background:#f8fafc;
                        color:#334155;">
              <div style="font-size:12px; font-weight:600; color:#64748b; margin-bottom:6px;">
                {html.escape(tr('LLM stream window title'))}
              </div>
              <pre style="white-space:pre-wrap; margin:0; font-size:12px; line-height:1.45;
                          font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;">{escaped_preview}</pre>
            </div>
            """,
            unsafe_allow_html=True,
        )

    try:
        with st.spinner(tr("Generating script...")):
            selected_video_paths = _normalize_paths(
                video_paths
                or getattr(params, "video_origin_paths", [])
                or getattr(params, "video_origin_path", "")
            )
            if not selected_video_paths:
                st.error(tr("Please select video file first"))
                return
            """
            1. 获取字幕
            """
            update_progress(30, tr("Parsing subtitles..."))
            # 判断字幕文件是否存在
            subtitle_paths = _normalize_paths(subtitle_path)
            missing_subtitle_paths = [path for path in subtitle_paths if not os.path.exists(path)]
            if not subtitle_paths or missing_subtitle_paths:
                st.error(tr("Subtitle file does not exist"))
                return

            """
            2. 分析字幕总结剧情 - 使用新的LLM服务架构
            """
            text_provider = config.app.get('text_llm_provider', 'gemini').lower()
            text_api_key = config.app.get(f'text_{text_provider}_api_key')
            text_model = config.app.get(f'text_{text_provider}_model_name')
            text_base_url = config.app.get(f'text_{text_provider}_base_url')

            # 读取字幕文件内容（无论使用哪种实现都需要）
            subtitle_content = str(subtitle_content or "").strip() or _build_combined_subtitle_content(
                subtitle_paths,
                selected_video_paths,
            )
            if not subtitle_content:
                st.error(tr("Subtitle file is empty or unreadable"))
                return

            narration_copy = str(narration_copy or "").strip()
            if not narration_copy:
                st.error(tr("Please generate and review narration copy first"))
                return

            analyzer = SubtitleAnalyzerAdapter(text_api_key, text_model, text_base_url, text_provider)
            if plot_analysis and str(plot_analysis).strip():
                logger.info("使用用户编辑后的剧情理解结果匹配剪辑脚本")
                analysis_result = {
                    "status": "success",
                    "analysis": str(plot_analysis).strip(),
                }
            else:
                plot_analysis_input = subtitle_content
                if enable_web_search:
                    update_waiting(tr("Searching short drama with Tavily..."))
                    plot_analysis_input = _build_plot_analysis_input(
                        subtitle_content,
                        short_name=video_theme,
                        enable_web_search=True,
                        tr=tr,
                    )
                    if plot_analysis_input is None:
                        return
                try:
                    # 优先使用新的LLM服务架构
                    logger.info("使用新的LLM服务架构进行字幕分析")
                    update_waiting(tr("Analyzing subtitles with model..."))
                    analysis_result = analyzer.analyze_subtitle(plot_analysis_input)

                except Exception as e:
                    logger.warning(f"使用新LLM服务失败，回退到旧实现: {str(e)}")
                    # 回退到旧的实现
                    update_waiting(tr("Analyzing subtitles with model..."))
                    analysis_result = analyze_subtitle(
                        subtitle_content=plot_analysis_input,
                        api_key=text_api_key,
                        model=text_model,
                        base_url=text_base_url,
                        save_result=True,
                        temperature=temperature,
                        provider=text_provider
                    )
            """
            3. 根据用户审核后的文案匹配画面与时间戳
            """
            if analysis_result["status"] == "success":
                logger.info("字幕分析成功！")
                update_waiting()

                try:
                    logger.info("使用新的LLM服务架构将审核文案匹配到字幕画面")
                    update_waiting(tr("Matching narration copy to footage..."))
                    stream_text.info(tr("Waiting for model stream..."))
                    narration_result = analyzer.match_narration_copy_to_script(
                        short_name=video_theme,
                        plot_analysis=analysis_result["analysis"],
                        subtitle_content=subtitle_content,
                        narration_copy=narration_copy,
                        temperature=temperature,
                        narration_language=narration_language,
                        drama_genre=drama_genre,
                        original_sound_ratio=original_sound_ratio,
                        stream_callback=update_stream_window,
                    )
                except Exception as e:
                    logger.warning(f"使用新LLM服务匹配画面失败，回退到旧实现: {str(e)}")
                    stream_text.info(tr("Streaming unavailable fallback waiting..."))
                    narration_result = match_narration_copy_to_script_legacy(
                        short_name=video_theme,
                        plot_analysis=analysis_result["analysis"],
                        subtitle_content=subtitle_content,
                        narration_copy=narration_copy,
                        api_key=text_api_key,
                        model=text_model,
                        base_url=text_base_url,
                        temperature=temperature,
                        provider=text_provider,
                        narration_language=narration_language,
                        drama_genre=drama_genre,
                        original_sound_ratio=original_sound_ratio,
                    )

                if narration_result["status"] == "success":
                    logger.info("\n剪辑脚本匹配成功！")
                    logger.info(narration_result["narration_script"])
                else:
                    logger.info(f"\n剪辑脚本匹配失败: {narration_result['message']}")
                    st.error(tr("Script generation failed check logs"))
                    st.stop()
            else:
                logger.error(f"分析失败: {analysis_result['message']}")
                st.error(tr("Script generation failed check logs"))
                st.stop()

            """
            4. 生成文案
            """
            logger.info("开始准备生成解说文案")

            # 结果转换为JSON字符串
            narration_script = narration_result["narration_script"]

            # 增强JSON解析，包含错误处理和修复
            narration_dict = parse_and_fix_json(narration_script)
            if narration_dict is None:
                st.error(tr("Generated narration JSON parse failed"))
                logger.error(f"JSON解析失败，原始内容: {narration_script}")
                st.stop()

            # 验证JSON结构
            if 'items' not in narration_dict:
                st.error(tr("Generated narration missing items field"))
                logger.error(f"JSON结构错误，缺少items字段: {narration_dict}")
                st.stop()

            narration_items = _normalize_narration_items_video_sources(
                narration_dict['items'],
                selected_video_paths,
            )
            narration_items = _strip_planner_only_fields(narration_items)
            script = json.dumps(narration_items, ensure_ascii=False, indent=2)

            if script is None:
                st.error(tr("Script generation failed check logs"))
                st.stop()
            logger.success(f"剪辑脚本生成完成")
            if isinstance(script, list):
                st.session_state['video_clip_json'] = script
            elif isinstance(script, str):
                st.session_state['video_clip_json'] = json.loads(script)
            update_progress(90, tr("Preparing output..."))

        time.sleep(0.1)
        progress_bar.progress(100)
        status_text.text(tr("Script generation completed!"))
        st.success(tr("Video script generated successfully"))

    except Exception as err:
        st.error(f"{tr('Generation error')}: {str(err)}")
        logger.exception(f"生成脚本时发生错误\n{traceback.format_exc()}")
    finally:
        time.sleep(2)
        progress_bar.empty()
        status_text.empty()
        stream_text.empty()
