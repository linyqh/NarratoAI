# 纪录片脚本生成
import os
import json
import time
import asyncio
import traceback
import streamlit as st
from loguru import logger
from datetime import datetime

from app.config import config
from app.utils import utils, video_processor
from webui.tools.base import create_vision_analyzer, get_batch_files, get_batch_timestamps


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
            llm_params = dict()
            logger.debug(f"VLM 视觉大模型提供商: {vision_llm_provider}")

            try:
                # ===================初始化视觉分析器===================
                update_progress(30, "正在初始化视觉分析器...")

                # 从配置中获取相关配置
                if vision_llm_provider == 'gemini':
                    vision_api_key = st.session_state.get('vision_gemini_api_key')
                    vision_model = st.session_state.get('vision_gemini_model_name')
                    vision_base_url = st.session_state.get('vision_gemini_base_url')
                else:
                    vision_api_key = st.session_state.get(f'vision_{vision_llm_provider}_api_key')
                    vision_model = st.session_state.get(f'vision_{vision_llm_provider}_model_name')
                    vision_base_url = st.session_state.get(f'vision_{vision_llm_provider}_base_url')

                # 创建视觉分析器实例
                llm_params = {
                  "vision_provider": vision_llm_provider,
                  "vision_api_key": vision_api_key,
                  "vision_model_name": vision_model,
                  "vision_base_url": vision_base_url,
                }
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

                """
                3. 处理分析结果（格式化为 json 数据）
                """
                # ===================处理分析结果===================
                update_progress(60, "正在整理分析结果...")

                # 合并所有批次的分析结果
                frame_analysis = ""
                merged_frame_observations = []  # 合并所有批次的帧观察
                overall_activity_summaries = []  # 合并所有批次的整体总结
                prev_batch_files = None
                frame_counter = 1  # 初始化帧计数器，用于给所有帧分配连续的序号
                # logger.debug(json.dumps(results, indent=4, ensure_ascii=False))
                # 确保分析目录存在
                analysis_dir = os.path.join(utils.storage_dir(), "temp", "analysis")
                os.makedirs(analysis_dir, exist_ok=True)
                origin_res = os.path.join(analysis_dir, "frame_analysis.json")
                with open(origin_res, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                
                # 开始处理
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
                                            # 修正时间戳解析逻辑
                                            # 格式为000100000，表示00:01:00,000，即1分钟
                                            # 需要按照对应位数进行解析:
                                            # 前两位是小时，中间两位是分钟，后面是秒和毫秒
                                            if len(timestamp_str) >= 9:  # 确保格式正确
                                                hours = int(timestamp_str[0:2])
                                                minutes = int(timestamp_str[2:4])
                                                seconds = int(timestamp_str[4:6])
                                                milliseconds = int(timestamp_str[6:9])
                                                
                                                # 计算总秒数
                                                timestamp_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000
                                                formatted_time = utils.format_time(timestamp_seconds)  # 格式化时间戳
                                            else:
                                                # 兼容旧的解析方式
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
                                    obs["batch_index"] = result['batch_index']
                                    
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
                                    # 修正解析逻辑，与上面相同的方式解析时间戳
                                    if len(first_time_str) >= 9 and len(last_time_str) >= 9:
                                        # 解析第一个时间戳
                                        first_hours = int(first_time_str[0:2])
                                        first_minutes = int(first_time_str[2:4])
                                        first_seconds = int(first_time_str[4:6])
                                        first_ms = int(first_time_str[6:9])
                                        first_time_seconds = first_hours * 3600 + first_minutes * 60 + first_seconds + first_ms / 1000
                                        
                                        # 解析第二个时间戳
                                        last_hours = int(last_time_str[0:2])
                                        last_minutes = int(last_time_str[2:4])
                                        last_seconds = int(last_time_str[4:6])
                                        last_ms = int(last_time_str[6:9])
                                        last_time_seconds = last_hours * 3600 + last_minutes * 60 + last_seconds + last_ms / 1000
                                        
                                        batch_duration = last_time_seconds - first_time_seconds
                                    else:
                                        # 兼容旧的解析方式
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
                
                # 使用当前时间创建文件名
                now = datetime.now()
                timestamp_str = now.strftime("%Y%m%d_%H%M")
                
                # 保存完整的分析结果为JSON
                analysis_filename = f"frame_analysis_{timestamp_str}.json"
                analysis_json_path = os.path.join(analysis_dir, analysis_filename)
                with open(analysis_json_path, 'w', encoding='utf-8') as f:
                    json.dump(merged_results, f, ensure_ascii=False, indent=2)
                logger.info(f"分析结果已保存到: {analysis_json_path}")

                """
                4. 生成文案
                """
                logger.info("开始准备生成解说文案")
                update_progress(80, "正在生成文案...")
                from app.services.generate_narration_script import parse_frame_analysis_to_markdown, generate_narration
                # 从配置中获取文本生成相关配置
                text_provider = config.app.get('text_llm_provider', 'gemini').lower()
                text_api_key = config.app.get(f'text_{text_provider}_api_key')
                text_model = config.app.get(f'text_{text_provider}_model_name')
                text_base_url = config.app.get(f'text_{text_provider}_base_url')
                llm_params.update({
                    "text_provider": text_provider,
                    "text_api_key": text_api_key,
                    "text_model_name": text_model,
                    "text_base_url": text_base_url
                })
                # 整理帧分析数据
                markdown_output = parse_frame_analysis_to_markdown(analysis_json_path)

                # 生成解说文案
                narration = generate_narration(
                    markdown_output,
                    text_api_key,
                    base_url=text_base_url,
                    model=text_model
                )

                # 使用增强的JSON解析器
                from webui.tools.generate_short_summary import parse_and_fix_json
                narration_data = parse_and_fix_json(narration)

                if not narration_data or 'items' not in narration_data:
                    logger.error(f"解说文案JSON解析失败，原始内容: {narration[:200]}...")
                    raise Exception("解说文案格式错误，无法解析JSON或缺少items字段")

                narration_dict = narration_data['items']
                # 为 narration_dict 中每个 item 新增一个 OST: 2 的字段, 代表保留原声和配音
                narration_dict = [{**item, "OST": 2} for item in narration_dict]
                logger.debug(f"解说文案创作完成:\n{"\n".join([item['narration'] for item in narration_dict])}")
                # 结果转换为JSON字符串
                script = json.dumps(narration_dict, ensure_ascii=False, indent=2)

            except Exception as e:
                logger.exception(f"大模型处理过程中发生错误\n{traceback.format_exc()}")
                raise Exception(f"分析失败: {str(e)}")

            if script is None:
                st.error("生成脚本失败，请检查日志")
                st.stop()
            logger.success(f"剪辑脚本生成完成")
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
