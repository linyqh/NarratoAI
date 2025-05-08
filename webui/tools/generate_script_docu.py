# 纪录片脚本生成
import os
import json
import time
import asyncio
import traceback
import requests
from app.utils import video_processor
import streamlit as st
from loguru import logger
from requests.adapters import HTTPAdapter

from app.config import config
from app.utils.script_generator import ScriptProcessor
from app.utils import utils, video_processor, qwenvl_analyzer
from webui.tools.base import create_vision_analyzer, get_batch_files, get_batch_timestamps, chekc_video_config


def generate_script_docu(params):
    """
    生成 纪录片 视频脚本
    要求: 原视频无字幕无配音
    适合场景: 纪录片、动物搞笑解说、荒野建造等
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
            1. 提取键帧
            """
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
                    processor = video_processor.VideoProcessor(params.video_origin_path)
                    # 处理视频并提取关键帧
                    processor.process_video_pipeline(
                        output_dir=video_keyframes_dir,
                        interval_seconds=st.session_state.get('frame_interval_input'),
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

            """
            2. 视觉分析(批量分析每一帧)
            """
            vision_llm_provider = st.session_state.get('vision_llm_providers').lower()
            logger.debug(f"VLM 视觉大模型提供商: {vision_llm_provider}")

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
                vision_analysis_prompt = """
我提供了 %s 张视频帧，它们按时间顺序排列，代表一个连续的视频片段。请仔细分析每一帧的内容，并关注帧与帧之间的变化，以理解整个片段的活动。

首先，请详细描述每一帧的关键视觉信息（包含：主要内容、人物、动作和场景）。
然后，基于所有帧的分析，请用**简洁的语言**总结整个视频片段中发生的主要活动或事件流程。

请务必使用 JSON 格式输出你的结果。JSON 结构应如下：
{
  "frame_observations": [
    {
      "frame_number": 1, // 或其他标识帧的方式
      "observation": "描述每张视频帧中的主要内容、人物、动作和场景。"
    },
    // ... 更多帧的观察 ...
  ],
  "overall_activity_summary": "在这里填写你总结的整个片段的主要活动，保持简洁。"
}

请务必不要遗漏视频帧，我提供了 %s 张视频帧，frame_observations 必须包含 %s 个元素

请只返回 JSON 字符串，不要包含任何其他解释性文字。
                """
                results = loop.run_until_complete(
                    analyzer.analyze_images(
                        images=keyframe_files,
                        prompt=vision_analysis_prompt,
                        batch_size=vision_batch_size
                    )
                )
                loop.close()

                # ===================处理分析结果===================
                update_progress(60, "正在整理分析结果...")

                # 合并所有批次的分析结果
                frame_analysis = ""
                merged_frame_observations = []  # 合并所有批次的帧观察
                overall_activity_summaries = []  # 合并所有批次的整体总结
                prev_batch_files = None
                frame_counter = 1  # 初始化帧计数器，用于给所有帧分配连续的序号
                logger.debug(json.dumps(results, indent=4, ensure_ascii=False))
                
                for result in results:
                    if 'error' in result:
                        logger.warning(f"批次 {result['batch_index']} 处理出现警告: {result['error']}")
                        continue
                        
                    # 获取当前批次的文件列表
                    batch_files = get_batch_files(keyframe_files, result, vision_batch_size)
                    logger.debug(f"批次 {result['batch_index']} 处理完成，共 {len(batch_files)} 张图片")
                    
                    # 获取批次的时间戳范围
                    first_timestamp, last_timestamp, timestamp_range = get_batch_timestamps(batch_files, prev_batch_files)
                    logger.debug(f"处理时间戳: {first_timestamp}-{last_timestamp}")
                    
                    # 解析响应中的JSON数据
                    response_text = result['response']
                    try:
                        # 处理可能包含```json```格式的响应
                        if "```json" in response_text:
                            json_content = response_text.split("```json")[1].split("```")[0].strip()
                        elif "```" in response_text:
                            json_content = response_text.split("```")[1].split("```")[0].strip()
                        else:
                            json_content = response_text.strip()
                            
                        response_data = json.loads(json_content)
                        
                        # 提取frame_observations和overall_activity_summary
                        if "frame_observations" in response_data:
                            frame_obs = response_data["frame_observations"]
                            overall_summary = response_data.get("overall_activity_summary", "")
                            
                            # 添加时间戳信息到每个帧观察
                            for i, obs in enumerate(frame_obs):
                                if i < len(batch_files):
                                    # 从文件名中提取时间戳
                                    file_path = batch_files[i]
                                    file_name = os.path.basename(file_path)
                                    # 提取时间戳字符串 (格式如: keyframe_000675_000027000.jpg)
                                    # 格式解析: keyframe_帧序号_毫秒时间戳.jpg
                                    timestamp_parts = file_name.split('_')
                                    if len(timestamp_parts) >= 3:
                                        timestamp_str = timestamp_parts[-1].split('.')[0]
                                        try:
                                            timestamp_seconds = int(timestamp_str) / 1000  # 转换为秒
                                            formatted_time = utils.format_time(timestamp_seconds)  # 格式化时间戳
                                        except ValueError:
                                            logger.warning(f"无法解析时间戳: {timestamp_str}")
                                            timestamp_seconds = 0
                                            formatted_time = "00:00:00,000"
                                    else:
                                        logger.warning(f"文件名格式不符合预期: {file_name}")
                                        timestamp_seconds = 0
                                        formatted_time = "00:00:00,000"
                                    
                                    # 添加额外信息到帧观察
                                    obs["frame_path"] = file_path
                                    obs["timestamp"] = formatted_time
                                    obs["timestamp_seconds"] = timestamp_seconds
                                    
                                    # 使用全局递增的帧计数器替换原始的frame_number
                                    if "frame_number" in obs:
                                        obs["original_frame_number"] = obs["frame_number"]  # 保留原始编号作为参考
                                    obs["frame_number"] = frame_counter  # 赋值连续的帧编号
                                    frame_counter += 1  # 增加帧计数器
                                    
                                    # 添加到合并列表
                                    merged_frame_observations.append(obs)
                            
                            # 添加批次整体总结信息
                            if overall_summary:
                                # 从文件名中提取时间戳数值
                                first_time_str = first_timestamp.split('_')[-1].split('.')[0]
                                last_time_str = last_timestamp.split('_')[-1].split('.')[0]
                                
                                # 转换为毫秒并计算持续时间（秒）
                                try:
                                    first_time_ms = int(first_time_str)
                                    last_time_ms = int(last_time_str)
                                    batch_duration = (last_time_ms - first_time_ms) / 1000
                                except ValueError:
                                    # 使用 utils.time_to_seconds 函数处理格式化的时间戳
                                    first_time_seconds = utils.time_to_seconds(first_time_str.replace('_', ':').replace('-', ','))
                                    last_time_seconds = utils.time_to_seconds(last_time_str.replace('_', ':').replace('-', ','))
                                    batch_duration = last_time_seconds - first_time_seconds
                                
                                overall_activity_summaries.append({
                                    "batch_index": result['batch_index'],
                                    "time_range": f"{first_timestamp}-{last_timestamp}",
                                    "duration_seconds": batch_duration,
                                    "summary": overall_summary
                                })
                    except Exception as e:
                        logger.error(f"解析批次 {result['batch_index']} 的响应数据失败: {str(e)}")
                        # 添加原始响应作为回退
                        frame_analysis += f"\n=== {first_timestamp}-{last_timestamp} ===\n"
                        frame_analysis += response_text
                        frame_analysis += "\n"
                    
                    # 更新上一个批次的文件
                    prev_batch_files = batch_files
                
                # 将合并后的结果转为JSON字符串
                merged_results = {
                    "frame_observations": merged_frame_observations,
                    "overall_activity_summaries": overall_activity_summaries
                }
                
                # 保存完整的分析结果为JSON
                analysis_json_path = os.path.join(utils.task_dir(), "frame_analysis.json")
                with open(analysis_json_path, 'w', encoding='utf-8') as f:
                    json.dump(merged_results, f, ensure_ascii=False, indent=2)
                
                # 同时保存原始文本格式的分析结果（兼容性）
                if not frame_analysis.strip() and merged_frame_observations:
                    # 如果没有原始文本但有合并结果，则从合并结果生成文本
                    frame_analysis = json.dumps(merged_results, ensure_ascii=False, indent=2)
                
                if not frame_analysis.strip():
                    raise Exception("未能生成有效的帧分析结果")
                
                # # 保存文本格式分析结果
                # analysis_path = os.path.join(utils.temp_dir(), "frame_analysis.txt")
                # with open(analysis_path, 'w', encoding='utf-8') as f:
                #     f.write(frame_analysis)

                update_progress(70, "正在生成脚本...")

                # 从配置中获取文本生成相关配置
                text_provider = config.app.get('text_llm_provider', 'gemini').lower()
                text_api_key = config.app.get(f'text_{text_provider}_api_key')
                text_model = config.app.get(f'text_{text_provider}_model_name')
                text_base_url = config.app.get(f'text_{text_provider}_base_url')

                # 构建帧内容列表
                frame_content_list = []
                prev_batch_files = None

                # 使用合并后的观察结果构建帧内容列表
                if merged_frame_observations:
                    for obs in merged_frame_observations:
                        frame_content = {
                            "_id": obs.get("frame_number", 0),  # 使用全局连续的帧编号作为ID
                            "timestamp": obs.get("timestamp", ""),
                            "picture": obs.get("observation", ""),
                            "narration": "",
                            "OST": 2,
                            "timestamp_seconds": obs.get("timestamp_seconds", 0)
                        }
                        frame_content_list.append(frame_content)
                        logger.debug(f"添加帧内容: ID={obs.get('frame_number', 0)}, 时间={obs.get('timestamp', '')}, 描述长度={len(obs.get('observation', ''))}")
                else:
                    # 兼容旧的处理方式，如果没有合并后的观察结果
                    for i, result in enumerate(results):
                        if 'error' in result:
                            continue

                        batch_files = get_batch_files(keyframe_files, result, vision_batch_size)
                        _, _, timestamp_range = get_batch_timestamps(batch_files, prev_batch_files)

                        frame_content = {
                            "_id": i + 1,
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
