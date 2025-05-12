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
            2. 分析字幕总结剧情
            """
            text_provider = config.app.get('text_llm_provider', 'gemini').lower()
            text_api_key = config.app.get(f'text_{text_provider}_api_key')
            text_model = config.app.get(f'text_{text_provider}_model_name')
            text_base_url = config.app.get(f'text_{text_provider}_base_url')
            analysis_result = analyze_subtitle(
                subtitle_file_path=subtitle_path,
                api_key=text_api_key,
                model=text_model,
                base_url=text_base_url,
                save_result=True,
                temperature=temperature
            )
            """
            3. 根据剧情生成解说文案
            """
            if analysis_result["status"] == "success":
                logger.info("字幕分析成功！")
                update_progress(60, "正在生成文案...")

                # 根据剧情生成解说文案
                narration_result = generate_narration_script(
                    short_name=video_theme,
                    plot_analysis=analysis_result["analysis"],
                    api_key=text_api_key,
                    model=text_model,
                    base_url=text_base_url,
                    save_result=True,
                    temperature=temperature
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
            narration_dict = json.loads(narration_script)
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
