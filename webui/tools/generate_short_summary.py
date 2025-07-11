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
# 导入新的LLM服务模块 - 确保提供商被注册
import app.services.llm  # 这会触发提供商注册
from app.services.llm.migration_adapter import SubtitleAnalyzerAdapter
import re


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


def generate_script_short_sunmmary(params, subtitle_path, video_theme, temperature):
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
            status_text.text(f"进度: {progress}%")

    try:
        with st.spinner("正在生成脚本..."):
            if not params.video_origin_path:
                st.error("请先选择视频文件")
                return
            """
            1. 获取字幕
            """
            update_progress(30, "正在解析字幕...")
            # 判断字幕文件是否存在
            if not os.path.exists(subtitle_path):
                st.error("字幕文件不存在")
                return

            """
            2. 分析字幕总结剧情 - 使用新的LLM服务架构
            """
            text_provider = config.app.get('text_llm_provider', 'gemini').lower()
            text_api_key = config.app.get(f'text_{text_provider}_api_key')
            text_model = config.app.get(f'text_{text_provider}_model_name')
            text_base_url = config.app.get(f'text_{text_provider}_base_url')

            # 读取字幕文件内容（无论使用哪种实现都需要）
            with open(subtitle_path, 'r', encoding='utf-8') as f:
                subtitle_content = f.read()

            try:
                # 优先使用新的LLM服务架构
                logger.info("使用新的LLM服务架构进行字幕分析")
                analyzer = SubtitleAnalyzerAdapter(text_api_key, text_model, text_base_url, text_provider)

                analysis_result = analyzer.analyze_subtitle(subtitle_content)

            except Exception as e:
                logger.warning(f"使用新LLM服务失败，回退到旧实现: {str(e)}")
                # 回退到旧的实现
                analysis_result = analyze_subtitle(
                    subtitle_file_path=subtitle_path,
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
                update_progress(60, "正在生成文案...")

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
                    st.error("生成脚本失败，请检查日志")
                    st.stop()
            else:
                logger.error(f"分析失败: {analysis_result['message']}")
                st.error("生成脚本失败，请检查日志")
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
                st.error("生成的解说文案格式错误，无法解析为JSON")
                logger.error(f"JSON解析失败，原始内容: {narration_script}")
                st.stop()

            # 验证JSON结构
            if 'items' not in narration_dict:
                st.error("生成的解说文案缺少必要的'items'字段")
                logger.error(f"JSON结构错误，缺少items字段: {narration_dict}")
                st.stop()

            script = json.dumps(narration_dict['items'], ensure_ascii=False, indent=2)

            if script is None:
                st.error("生成脚本失败，请检查日志")
                st.stop()
            logger.success(f"剪辑脚本生成完成")
            if isinstance(script, list):
                st.session_state['video_clip_json'] = script
            elif isinstance(script, str):
                st.session_state['video_clip_json'] = json.loads(script)
            update_progress(90, "整理输出...")

        time.sleep(0.1)
        progress_bar.progress(100)
        status_text.text("脚本生成完成！")
        st.success("视频脚本生成成功！")

    except Exception as err:
        st.error(f"生成过程中发生错误: {str(err)}")
        logger.exception(f"生成脚本时发生错误\n{traceback.format_exc()}")
    finally:
        time.sleep(2)
        progress_bar.empty()
        status_text.empty()
