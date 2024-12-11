# 纪录片脚本生成
import os
import json
import time
import asyncio
import traceback
import requests
import streamlit as st
from loguru import logger
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import config
from app.utils.script_generator import ScriptProcessor
from app.utils import utils, video_processor, video_processor_v2, qwenvl_analyzer
from webui.tools.base import create_vision_analyzer, get_batch_files, get_batch_timestamps, chekc_video_config


def generate_script_docu(tr, params):
    """
    生成 纪录片 视频脚本
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

            # ===================提取键帧===================
            update_progress(10, "正在提取关键帧...")

            # 创建临时目录用于存储关键帧
            keyframes_dir = os.path.join(utils.temp_dir(), "keyframes")
            video_hash = utils.md5(params.video_origin_path + str(os.path.getmtime(params.video_origin_path)))
            video_keyframes_dir = os.path.join(keyframes_dir, video_hash)

            # 检查是否已经提取过关键帧
            keyframe_files = []
            if os.path.exists(video_keyframes_dir):
                # 取已有的关键帧文件
                for filename in sorted(os.listdir(video_keyframes_dir)):
                    if filename.endswith('.jpg'):
                        keyframe_files.append(os.path.join(video_keyframes_dir, filename))

                if keyframe_files:
                    logger.info(f"使用已缓存的关键帧: {video_keyframes_dir}")
                    st.info(f"使用已缓存的关键帧，如需重新提取请删除目录: {video_keyframes_dir}")
                    update_progress(20, f"使用已缓存关键帧，共 {len(keyframe_files)} 帧")

            # 如果没有缓存的关键帧，则进行提取
            if not keyframe_files:
                try:
                    # 确保目录存在
                    os.makedirs(video_keyframes_dir, exist_ok=True)

                    # 初始化视频处理器
                    if config.frames.get("version") == "v2":
                        processor = video_processor_v2.VideoProcessor(params.video_origin_path)
                        # 处理视频并提取关键帧
                        processor.process_video_pipeline(
                            output_dir=video_keyframes_dir,
                            skip_seconds=st.session_state.get('skip_seconds'),
                            threshold=st.session_state.get('threshold')
                        )
                    else:
                        processor = video_processor.VideoProcessor(params.video_origin_path)
                        # 处理视频并提取关键帧
                        processor.process_video(
                            output_dir=video_keyframes_dir,
                            skip_seconds=0
                        )

                    # 获取所有关键文件路径
                    for filename in sorted(os.listdir(video_keyframes_dir)):
                        if filename.endswith('.jpg'):
                            keyframe_files.append(os.path.join(video_keyframes_dir, filename))

                    if not keyframe_files:
                        raise Exception("未提取到任何关键帧")

                    update_progress(20, f"关键帧提取完成，共 {len(keyframe_files)} 帧")

                except Exception as e:
                    # 如果提取失败，清理创建的目录
                    try:
                        if os.path.exists(video_keyframes_dir):
                            import shutil
                            shutil.rmtree(video_keyframes_dir)
                    except Exception as cleanup_err:
                        logger.error(f"清理失败的关键帧目录时出错: {cleanup_err}")

                    raise Exception(f"关键帧提取失败: {str(e)}")

            # 根据不同的 LLM 提供商处理
            vision_llm_provider = st.session_state.get('vision_llm_providers').lower()
            logger.debug(f"Vision LLM 提供商: {vision_llm_provider}")

            try:
                # ===================初始化视觉分析器===================
                update_progress(30, "正在初始化视觉分析器...")

                # 从配置中获取相关配置
                if vision_llm_provider == 'gemini':
                    vision_api_key = st.session_state.get('vision_gemini_api_key')
                    vision_model = st.session_state.get('vision_gemini_model_name')
                    vision_base_url = st.session_state.get('vision_gemini_base_url')
                elif vision_llm_provider == 'qwenvl':
                    vision_api_key = st.session_state.get('vision_qwenvl_api_key')
                    vision_model = st.session_state.get('vision_qwenvl_model_name', 'qwen-vl-max-latest')
                    vision_base_url = st.session_state.get('vision_qwenvl_base_url')
                else:
                    raise ValueError(f"不支持的视觉分析提供商: {vision_llm_provider}")

                # 创建视觉分析器实例
                analyzer = create_vision_analyzer(
                    provider=vision_llm_provider,
                    api_key=vision_api_key,
                    model=vision_model,
                    base_url=vision_base_url
                )

                update_progress(40, "正在分析关键帧...")

                # ===================创建异步事件循环===================
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # 执行异步分析
                vision_batch_size = st.session_state.get('vision_batch_size') or config.frames.get("vision_batch_size")
                results = loop.run_until_complete(
                    analyzer.analyze_images(
                        images=keyframe_files,
                        prompt=config.app.get('vision_analysis_prompt'),
                        batch_size=vision_batch_size
                    )
                )
                loop.close()

                # ===================处理分析结果===================
                update_progress(60, "正在整理分析结果...")

                # 合并所有批次的析结果
                frame_analysis = ""
                prev_batch_files = None

                for result in results:
                    if 'error' in result:
                        logger.warning(f"批次 {result['batch_index']} 处理出现警告: {result['error']}")

                    # 获取当前批次的文件列表 keyframe_001136_000045.jpg 将 000045 精度提升到 毫秒
                    batch_files = get_batch_files(keyframe_files, result, vision_batch_size)
                    logger.debug(f"批次 {result['batch_index']} 处理完成，共 {len(batch_files)} 张图片")
                    # logger.debug(batch_files)

                    first_timestamp, last_timestamp, _ = get_batch_timestamps(batch_files, prev_batch_files)
                    logger.debug(f"处理时间戳: {first_timestamp}-{last_timestamp}")

                    # 添加带时间戳的分析结果
                    frame_analysis += f"\n=== {first_timestamp}-{last_timestamp} ===\n"
                    frame_analysis += result['response']
                    frame_analysis += "\n"

                    # 更新上一个批次的文件
                    prev_batch_files = batch_files

                if not frame_analysis.strip():
                    raise Exception("未能生成有效的帧分析结果")

                # 保存分析结果
                analysis_path = os.path.join(utils.temp_dir(), "frame_analysis.txt")
                with open(analysis_path, 'w', encoding='utf-8') as f:
                    f.write(frame_analysis)

                update_progress(70, "正在生成脚本...")

                # 从配置中获取文本生成相关配置
                text_provider = config.app.get('text_llm_provider', 'gemini').lower()
                text_api_key = config.app.get(f'text_{text_provider}_api_key')
                text_model = config.app.get(f'text_{text_provider}_model_name')
                text_base_url = config.app.get(f'text_{text_provider}_base_url')

                # 构建帧内容列表
                frame_content_list = []
                prev_batch_files = None

                for i, result in enumerate(results):
                    if 'error' in result:
                        continue

                    batch_files = get_batch_files(keyframe_files, result, vision_batch_size)
                    _, _, timestamp_range = get_batch_timestamps(batch_files, prev_batch_files)

                    frame_content = {
                        "timestamp": timestamp_range,
                        "picture": result['response'],
                        "narration": "",
                        "OST": 2
                    }
                    frame_content_list.append(frame_content)

                    logger.debug(f"添加帧内容: 时间范围={timestamp_range}, 分析结果长度={len(result['response'])}")

                    # 更新上一个批次的文件
                    prev_batch_files = batch_files

                if not frame_content_list:
                    raise Exception("没有有效的帧内容可以处理")

                # ===================开始生成文案===================
                update_progress(80, "正在生成文案...")
                # 校验配置
                api_params = {
                    "vision_api_key": vision_api_key,
                    "vision_model_name": vision_model,
                    "vision_base_url": vision_base_url or "",
                    "text_api_key": text_api_key,
                    "text_model_name": text_model,
                    "text_base_url": text_base_url or ""
                }
                chekc_video_config(api_params)
                custom_prompt = st.session_state.get('custom_prompt', '')
                processor = ScriptProcessor(
                    model_name=text_model,
                    api_key=text_api_key,
                    prompt=custom_prompt,
                    base_url=text_base_url or "",
                    video_theme=st.session_state.get('video_theme', '')
                )

                # 处理帧内容生成脚本
                script_result = processor.process_frames(frame_content_list)

                # 结果转换为JSON字符串
                script = json.dumps(script_result, ensure_ascii=False, indent=2)

            except Exception as e:
                logger.exception(f"大模型处理过程中发生错误\n{traceback.format_exc()}")
                raise Exception(f"分析失败: {str(e)}")

            if script is None:
                st.error("生成脚本失败，请检查日志")
                st.stop()
            logger.info(f"脚本生成完成")
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
        st.error(f"生成过程中发生错误: {str(err)}")
        logger.exception(f"生成脚本时发生错误\n{traceback.format_exc()}")
    finally:
        time.sleep(2)
        progress_bar.empty()
        status_text.empty()
