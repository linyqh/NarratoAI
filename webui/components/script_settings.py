import os
import ssl
import glob
import json
import time
import asyncio
import traceback
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests
import streamlit as st
from loguru import logger

from app.config import config
from app.models.schema import VideoClipParams
from app.utils.script_generator import ScriptProcessor
from app.utils import utils, check_script, vision_analyzer, video_processor, video_processor_v2
from webui.utils import file_utils


def get_batch_timestamps(batch_files, prev_batch_files=None):
    """
    获取一批文件的时间戳范围
    返回: (first_timestamp, last_timestamp, timestamp_range)
    
    文件名格式: keyframe_001253_000050.jpg
    其中 000050 表示 00:00:50 (50秒)
         000101 表示 00:01:01 (1分1秒)
         
    Args:
        batch_files: 当前批次的文件列表
        prev_batch_files: 上一个批次的文件列表，用于处理单张图片的情况
    """
    if not batch_files:
        logger.warning("Empty batch files")
        return "00:00", "00:00", "00:00-00:00"
        
    # 如果当前批次只有一张图片，且有上一个批次的文件，则使用上一批次的最后一张作为首帧
    if len(batch_files) == 1 and prev_batch_files and len(prev_batch_files) > 0:
        first_frame = os.path.basename(prev_batch_files[-1])
        last_frame = os.path.basename(batch_files[0])
        logger.debug(f"单张图片批次，使用上一批次最后一帧作为首帧: {first_frame}")
    else:
        # 提取首帧和尾帧的时间戳
        first_frame = os.path.basename(batch_files[0])
        last_frame = os.path.basename(batch_files[-1])
    
    # 从文件名中提取时间信息
    first_time = first_frame.split('_')[2].replace('.jpg', '')  # 000050
    last_time = last_frame.split('_')[2].replace('.jpg', '')    # 000101
    
    # 转换为分:秒格式
    def format_timestamp(time_str):
        # 时间格式为 MMSS，如 0050 表示 00:50, 0101 表示 01:01
        if len(time_str) < 4:
            logger.warning(f"Invalid timestamp format: {time_str}")
            return "00:00"
            
        minutes = int(time_str[-4:-2])  # 取后4位的前2位作为分钟
        seconds = int(time_str[-2:])    # 取后2位作为秒数
        
        # 处理进位
        if seconds >= 60:
            minutes += seconds // 60
            seconds = seconds % 60
            
        return f"{minutes:02d}:{seconds:02d}"
    
    first_timestamp = format_timestamp(first_time)
    last_timestamp = format_timestamp(last_time)
    timestamp_range = f"{first_timestamp}-{last_timestamp}"
    
    logger.debug(f"解析时间戳: {first_frame} -> {first_timestamp}, {last_frame} -> {last_timestamp}")
    return first_timestamp, last_timestamp, timestamp_range

def get_batch_files(keyframe_files, result, batch_size=5):
    """
    获取当前批次的图片文件
    """
    batch_start = result['batch_index'] * batch_size
    batch_end = min(batch_start + batch_size, len(keyframe_files))
    return keyframe_files[batch_start:batch_end]

def render_script_panel(tr):
    """渲染脚本配置面板"""
    with st.container(border=True):
        st.write(tr("Video Script Configuration"))
        params = VideoClipParams()

        # 渲染脚本文件选择
        render_script_file(tr, params)

        # 渲染视频文件选择
        render_video_file(tr, params)

        # 渲染视频主题和提示词
        render_video_details(tr)

        # 渲染脚本操作按钮
        render_script_buttons(tr, params)


def render_script_file(tr, params):
    """渲染脚本文件选择"""
    script_list = [(tr("None"), ""), (tr("Auto Generate"), "auto")]

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
    saved_script_path = st.session_state.get('video_clip_json_path', '')
    selected_index = 0
    for i, (_, path) in enumerate(script_list):
        if path == saved_script_path:
            selected_index = i
            break

    selected_script_index = st.selectbox(
        tr("Script Files"),
        index=selected_index,  # 使用找到的索引
        options=range(len(script_list)),
        format_func=lambda x: script_list[x][0]
    )

    script_path = script_list[selected_script_index][1]
    st.session_state['video_clip_json_path'] = script_path
    params.video_clip_json_path = script_path


def render_video_file(tr, params):
    """渲染视频文件选择"""
    video_list = [(tr("None"), ""), (tr("Upload Local Files"), "local")]

    # 获取已有视频文件
    for suffix in ["*.mp4", "*.mov", "*.avi", "*.mkv"]:
        video_files = glob.glob(os.path.join(utils.video_dir(), suffix))
        for file in video_files:
            display_name = file.replace(config.root_dir, "")
            video_list.append((display_name, file))

    selected_video_index = st.selectbox(
        tr("Video File"),
        index=0,
        options=range(len(video_list)),
        format_func=lambda x: video_list[x][0]
    )

    video_path = video_list[selected_video_index][1]
    st.session_state['video_origin_path'] = video_path
    params.video_origin_path = video_path

    if video_path == "local":
        uploaded_file = st.file_uploader(
            tr("Upload Local Files"),
            type=["mp4", "mov", "avi", "flv", "mkv"],
            accept_multiple_files=False,
        )

        if uploaded_file is not None:
            video_file_path = os.path.join(utils.video_dir(), uploaded_file.name)
            file_name, file_extension = os.path.splitext(uploaded_file.name)

            if os.path.exists(video_file_path):
                timestamp = time.strftime("%Y%m%d%H%M%S")
                file_name_with_timestamp = f"{file_name}_{timestamp}"
                video_file_path = os.path.join(utils.video_dir(), file_name_with_timestamp + file_extension)

            with open(video_file_path, "wb") as f:
                f.write(uploaded_file.read())
                st.success(tr("File Uploaded Successfully"))
                st.session_state['video_origin_path'] = video_file_path
                params.video_origin_path = video_file_path
                time.sleep(1)
                st.rerun()


def render_video_details(tr):
    """渲染视频主题和提示词"""
    video_theme = st.text_input(tr("Video Theme"))
    custom_prompt = st.text_area(
        tr("Generation Prompt"),
        value=st.session_state.get('video_plot', ''),
        help=tr("Custom prompt for LLM, leave empty to use default prompt"),
        height=180
    )
    st.session_state['video_theme'] = video_theme
    st.session_state['custom_prompt'] = custom_prompt
    return video_theme, custom_prompt


def render_script_buttons(tr, params):
    """渲染脚本操作按钮"""
    # 新增三个输入框，放在同一行
    input_cols = st.columns(3)
    
    with input_cols[0]:
        skip_seconds = st.number_input(
            "skip_seconds",
            min_value=0,
            value=st.session_state.get('skip_seconds', config.frames.get('skip_seconds', 0)),
            help=tr("Skip the first few seconds"),
            key="skip_seconds_input"
        )
        st.session_state['skip_seconds'] = skip_seconds
        
    with input_cols[1]:
        threshold = st.number_input(
            "threshold",
            min_value=0,
            value=st.session_state.get('threshold', config.frames.get('threshold', 30)),
            help=tr("Difference threshold"),
            key="threshold_input"
        )
        st.session_state['threshold'] = threshold
        
    with input_cols[2]:
        vision_batch_size = st.number_input(
            "vision_batch_size",
            min_value=1,
            max_value=20,
            value=st.session_state.get('vision_batch_size', config.frames.get('vision_batch_size', 5)),
            help=tr("Vision processing batch size"),
            key="vision_batch_size_input"
        )
        st.session_state['vision_batch_size'] = vision_batch_size

    # 生成/加载按钮
    script_path = st.session_state.get('video_clip_json_path', '')
    if script_path == "auto":
        button_name = tr("Generate Video Script")
    elif script_path:
        button_name = tr("Load Video Script")
    else:
        button_name = tr("Please Select Script File")

    if st.button(button_name, key="script_action", disabled=not script_path):
        if script_path == "auto":
            generate_script(tr, params)
        else:
            load_script(tr, script_path)

    # 视频脚本编辑区
    video_clip_json_details = st.text_area(
        tr("Video Script"),
        value=json.dumps(st.session_state.get('video_clip_json', []), indent=2, ensure_ascii=False),
        height=180
    )

    # 操作按钮行
    button_cols = st.columns(3)
    with button_cols[0]:
        if st.button(tr("Check Format"), key="check_format", use_container_width=True):
            check_script_format(tr, video_clip_json_details)

    with button_cols[1]:
        if st.button(tr("Save Script"), key="save_script", use_container_width=True):
            save_script(tr, video_clip_json_details)

    with button_cols[2]:
        script_valid = st.session_state.get('script_format_valid', False)
        if st.button(tr("Crop Video"), key="crop_video", disabled=not script_valid, use_container_width=True):
            crop_video(tr, params)


def check_script_format(tr, script_content):
    """检查脚本格式"""
    try:
        result = check_script.check_format(script_content)
        if result.get('success'):
            st.success(tr("Script format check passed"))
            st.session_state['script_format_valid'] = True
        else:
            st.error(f"{tr('Script format check failed')}: {result.get('message')}")
            st.session_state['script_format_valid'] = False
    except Exception as e:
        st.error(f"{tr('Script format check error')}: {str(e)}")
        st.session_state['script_format_valid'] = False


def load_script(tr, script_path):
    """加载脚本文件"""
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()
            script = utils.clean_model_output(script)
            st.session_state['video_clip_json'] = json.loads(script)
            st.success(tr("Script loaded successfully"))
            st.rerun()
    except Exception as e:
        st.error(f"{tr('Failed to load script')}: {str(e)}")


def generate_script(tr, params):
    """生成视频脚本"""
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
                    
                    # 获取所有关键帧文件路径
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
            
            if vision_llm_provider == 'gemini':
                try:
                    # ===================初始化视觉分析器===================
                    update_progress(30, "正在初始化视觉分析器...")
                    
                    # 从配置中获取 Gemini 相关配置
                    vision_api_key = st.session_state.get('vision_gemini_api_key')
                    vision_model = st.session_state.get('vision_gemini_model_name')
                    vision_base_url = st.session_state.get('vision_gemini_base_url')
                    
                    if not vision_api_key or not vision_model:
                        raise ValueError("未配置 Gemini API Key 或者 模型，请在基础设置中配置")

                    analyzer = vision_analyzer.VisionAnalyzer(
                        model_name=vision_model,
                        api_key=vision_api_key,
                    )

                    update_progress(40, "正在分析关键帧...")

                    # ===================创建异步事件循环===================
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # 执行异步分析
                    results = loop.run_until_complete(
                        analyzer.analyze_images(
                            images=keyframe_files,
                            prompt=config.app.get('vision_analysis_prompt'),
                            batch_size=config.frames.get("vision_batch_size", st.session_state.get('vision_batch_size', 5))
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
                            continue
                            
                        batch_files = get_batch_files(keyframe_files, result, config.frames.get("vision_batch_size", 5))
                        logger.debug(f"批次 {result['batch_index']} 处理完成，共 {len(batch_files)} 张图片")
                        logger.debug(batch_files)
                        
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
                        
                        batch_files = get_batch_files(keyframe_files, result, config.frames.get("vision_batch_size", 5))
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
                    headers = {
                        'accept': 'application/json',
                        'Content-Type': 'application/json'
                    }
                    session = requests.Session()
                    retry_strategy = Retry(
                        total=3,
                        backoff_factor=1,
                        status_forcelist=[500, 502, 503, 504]
                    )
                    adapter = HTTPAdapter(max_retries=retry_strategy)
                    session.mount("https://", adapter)
                    try:
                        response = session.post(
                            f"{config.app.get('narrato_api_url')}/video/config",
                            headers=headers,
                            json=api_params,
                            timeout=30,
                            verify=True
                        )
                    except Exception as e:
                        pass
                    custom_prompt = st.session_state.get('custom_prompt', '')
                    processor = ScriptProcessor(
                        model_name=text_model,
                        api_key=text_api_key,
                        prompt=custom_prompt,
                        video_theme=st.session_state.get('video_theme', '')
                    )

                    # 处理帧内容生成脚本
                    script_result = processor.process_frames(frame_content_list)

                    # ��结果转换为JSON字符串
                    script = json.dumps(script_result, ensure_ascii=False, indent=2)
                    
                except Exception as e:
                    logger.exception(f"大模型处理过程中发生错误\n{traceback.format_exc()}")
                    raise Exception(f"分析失败: {str(e)}")

            elif vision_llm_provider == 'narratoapi':  # NarratoAPI
                try:
                    # 创建临时目录
                    temp_dir = utils.temp_dir("narrato")
                    
                    # 打包关键帧
                    update_progress(30, "正在打包关键帧...")
                    zip_path = os.path.join(temp_dir, f"keyframes_{int(time.time())}.zip")
                    if not file_utils.create_zip(keyframe_files, zip_path):
                        raise Exception("打包关键帧失败")
                    
                    # 获取API配置
                    api_url = st.session_state.get('narrato_api_url')
                    api_key = st.session_state.get('narrato_api_key')
                    
                    if not api_key:
                        raise ValueError("未配置 Narrato API Key，请在基础设置中配置")
                    
                    # 准���API请求
                    headers = {
                        'X-API-Key': api_key,
                        'accept': 'application/json'
                    }
                    
                    api_params = {
                        'batch_size': st.session_state.get('narrato_batch_size', 10),
                        'use_ai': False,
                        'start_offset': 0,
                        'vision_model': st.session_state.get('narrato_vision_model', 'gemini-1.5-flash'),
                        'vision_api_key': st.session_state.get('narrato_vision_key'),
                        'llm_model': st.session_state.get('narrato_llm_model', 'qwen-plus'),
                        'llm_api_key': st.session_state.get('narrato_llm_key'),
                        'custom_prompt': st.session_state.get('custom_prompt', '')
                    }
                    
                    # 发送API请求
                    logger.info(f"请求NarratoAPI: {api_url}")
                    update_progress(40, "正在上传文件...")
                    with open(zip_path, 'rb') as f:
                        files = {'file': (os.path.basename(zip_path), f, 'application/x-zip-compressed')}
                        try:
                            response = requests.post(
                                f"{api_url}/video/analyze",
                                headers=headers, 
                                params=api_params, 
                                files=files,
                                timeout=30  # 设置超时时间
                            )
                            response.raise_for_status()
                        except requests.RequestException as e:
                            logger.error(f"Narrato API 请求失败:\n{traceback.format_exc()}")
                            raise Exception(f"API请求失败: {str(e)}")
                    
                    task_data = response.json()
                    task_id = task_data["data"].get('task_id')
                    if not task_id:
                        raise Exception(f"无效的API响应: {response.text}")
                    
                    # 轮询任务状态
                    update_progress(50, "正在等待分析结果...")
                    retry_count = 0
                    max_retries = 60  # 最多等待2分钟
                    
                    while retry_count < max_retries:
                        try:
                            status_response = requests.get(
                                f"{api_url}/video/tasks/{task_id}",
                                headers=headers,
                                timeout=10
                            )
                            status_response.raise_for_status()
                            task_status = status_response.json()['data']
                            
                            if task_status['status'] == 'SUCCESS':
                                script = task_status['result']['data']
                                break
                            elif task_status['status'] in ['FAILURE', 'RETRY']:
                                raise Exception(f"任务失败: {task_status.get('error')}")
                            
                            retry_count += 1
                            time.sleep(2)
                            
                        except requests.RequestException as e:
                            logger.warning(f"获取任务状态失败，重试中: {str(e)}")
                            retry_count += 1
                            time.sleep(2)
                            continue
                    
                    if retry_count >= max_retries:
                        raise Exception("任务执行超时")
                    
                except Exception as e:
                    logger.exception(f"NarratoAPI 处理过程中发生错误\n{traceback.format_exc()}")
                    raise Exception(f"NarratoAPI 处理失败: {str(e)}")
                finally:
                    # 清理临时文件
                    try:
                        if os.path.exists(zip_path):
                            os.remove(zip_path)
                    except Exception as e:
                        logger.warning(f"清理临时文件失败: {str(e)}")

            else:
                logger.exception("Vision Model 未启用，请检查配置")

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


def save_script(tr, video_clip_json_details):
    """保存视频脚本"""
    if not video_clip_json_details:
        st.error(tr("请输入视频脚本"))
        st.stop()

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

                # 更新配置
                config.app["video_clip_json_path"] = save_path

                # 显示成功消息
                st.success(tr("Script saved successfully"))

                # 强制重新加载页面更新选择框
                time.sleep(0.5)  # 给一点时间让用户看到成功消息
                st.rerun()

        except Exception as err:
            st.error(f"{tr('Failed to save script')}: {str(err)}")
            st.stop()


def crop_video(tr, params):
    """裁剪视频"""
    progress_bar = st.progress(0)
    status_text = st.empty()

    def update_progress(progress):
        progress_bar.progress(progress)
        status_text.text(f"剪辑进度: {progress}%")

    try:
        utils.cut_video(params, update_progress)
        time.sleep(0.5)
        progress_bar.progress(100)
        status_text.text("剪辑完成！")
        st.success("视频剪辑成功完成！")
    except Exception as e:
        st.error(f"剪辑过程中发生错误: {str(e)}")
    finally:
        time.sleep(2)
        progress_bar.empty()
        status_text.empty()


def get_script_params():
    """获取脚本参数"""
    return {
        'video_language': st.session_state.get('video_language', ''),
        'video_clip_json_path': st.session_state.get('video_clip_json_path', ''),
        'video_origin_path': st.session_state.get('video_origin_path', ''),
        'video_name': st.session_state.get('video_name', ''),
        'video_plot': st.session_state.get('video_plot', '')
    }
