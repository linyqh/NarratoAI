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
import streamlit as st
from loguru import logger

from app.config import config
from app.services.SDE.short_drama_explanation import analyze_subtitle, generate_narration_script
from app.services.subtitle_text import read_subtitle_text
from app.services.tavily_search import TavilySearchError, format_search_context, search_short_drama
# 导入新的LLM服务模块 - 确保提供商被注册
import app.services.llm  # 这会触发提供商注册
from app.services.llm.migration_adapter import SubtitleAnalyzerAdapter
import re


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


def _coerce_video_id(value):
    try:
        video_id = int(value)
    except (TypeError, ValueError):
        return None
    return video_id if video_id > 0 else None


def _match_video_id_by_name(video_name, video_paths):
    video_name = str(video_name or "").strip()
    if not video_name:
        return None

    for index, video_path in enumerate(video_paths, start=1):
        if os.path.basename(video_path) == os.path.basename(video_name):
            return index
    return None


def _normalize_narration_items_video_sources(items, video_paths):
    video_paths = _normalize_paths(video_paths)
    if not video_paths:
        return items

    normalized_items = []
    for item in items:
        if not isinstance(item, dict):
            normalized_items.append(item)
            continue

        item_copy = item.copy()
        video_id = _coerce_video_id(item_copy.get("video_id") or item_copy.get("video_index"))
        matched_video_id = _match_video_id_by_name(
            item_copy.get("video_name") or item_copy.get("source_video"),
            video_paths,
        )
        if matched_video_id:
            video_id = matched_video_id
        if video_id is None or video_id > len(video_paths):
            logger.warning(f"片段 {item_copy.get('_id')} 未提供有效 video_id，默认使用视频 1")
            video_id = 1

        item_copy["video_id"] = video_id
        item_copy["video_name"] = os.path.basename(video_paths[video_id - 1])
        normalized_items.append(item_copy)

    return normalized_items


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

    # 如果所有方法都失败，尝试创建一个基本的结构
    logger.error(f"所有JSON解析方法都失败，原始内容: {json_string[:200]}...")

    # 尝试从文本中提取关键信息创建基本结构
    try:
        # 这是一个简单的回退方案
        return {
            "items": [
                {
                    "_id": 1,
                    "timestamp": "00:00:00,000-00:00:10,000",
                    "picture": "解析失败，使用默认内容",
                    "narration": json_string[:100] + "..." if len(json_string) > 100 else json_string,
                    "OST": 0
                }
            ]
        }
    except Exception:
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
):
    """
    生成 短剧解说 视频脚本
    要求: 提供高质量短剧字幕
    适合场景: 短剧
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

            analyzer = SubtitleAnalyzerAdapter(text_api_key, text_model, text_base_url, text_provider)
            if plot_analysis and str(plot_analysis).strip():
                logger.info("使用用户编辑后的剧情理解结果生成解说文案")
                analysis_result = {
                    "status": "success",
                    "analysis": str(plot_analysis).strip(),
                }
            else:
                plot_analysis_input = subtitle_content
                if enable_web_search:
                    update_progress(40, tr("Searching short drama with Tavily..."))
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
                    analysis_result = analyzer.analyze_subtitle(plot_analysis_input)

                except Exception as e:
                    logger.warning(f"使用新LLM服务失败，回退到旧实现: {str(e)}")
                    # 回退到旧的实现
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
            3. 根据剧情生成解说文案
            """
            if analysis_result["status"] == "success":
                logger.info("字幕分析成功！")
                update_progress(60, tr("Generating narration copy..."))

                # 根据剧情生成解说文案 - 使用新的LLM服务架构
                try:
                    # 优先使用新的LLM服务架构
                    logger.info("使用新的LLM服务架构生成解说文案")
                    narration_result = analyzer.generate_narration_script(
                        short_name=video_theme,
                        plot_analysis=analysis_result["analysis"],
                        subtitle_content=subtitle_content,  # 传递原始字幕内容
                        temperature=temperature
                    )
                except Exception as e:
                    logger.warning(f"使用新LLM服务失败，回退到旧实现: {str(e)}")
                    # 回退到旧的实现
                    narration_result = generate_narration_script(
                        short_name=video_theme,
                        plot_analysis=analysis_result["analysis"],
                        subtitle_content=subtitle_content,  # 传递原始字幕内容
                        api_key=text_api_key,
                        model=text_model,
                        base_url=text_base_url,
                        save_result=True,
                        temperature=temperature,
                        provider=text_provider
                    )

                if narration_result["status"] == "success":
                    logger.info("\n解说文案生成成功！")
                    logger.info(narration_result["narration_script"])
                else:
                    logger.info(f"\n解说文案生成失败: {narration_result['message']}")
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
