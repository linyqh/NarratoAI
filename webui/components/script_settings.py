import os
import glob
import json
import time
import traceback
import streamlit as st
from loguru import logger

from app.config import config
from app.models.schema import VideoClipParams
from app.utils import utils, check_script
from app.utils.utils import sanitize_filename, secure_path
from webui.tools.generate_script_docu import generate_script_docu
from webui.tools.generate_script_short import generate_script_short
from webui.tools.generate_short_summary import generate_script_short_sunmmary


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
        elif script_path == "summary":
            # 短剧解说
            short_drama_summary(tr)
        else:
            # 默认为空
            pass

        # 渲染脚本操作按钮
        render_script_buttons(tr, params)


def render_script_file(tr, params):
    """渲染脚本文件选择"""
    script_list = [
        (tr("None"), ""),
        (tr("Auto Generate"), "auto"),
        (tr("Short Generate"), "short"),
        (tr("Short Drama Summary"), "summary"),
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
    saved_script_path = st.session_state.get('video_clip_json_path', '')
    selected_index = 0
    for i, (_, path) in enumerate(script_list):
        if path == saved_script_path:
            selected_index = i
            break

    selected_script_index = st.selectbox(
        tr("Script Files"),
        index=selected_index,
        options=range(len(script_list)),
        format_func=lambda x: script_list[x][0]
    )

    script_path = script_list[selected_script_index][1]
    st.session_state['video_clip_json_path'] = script_path
    params.video_clip_json_path = script_path

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
                safe_name = sanitize_filename(uploaded_file.name)
                script_file_path = secure_path(os.path.join(script_dir, safe_name), script_dir)
                file_name, file_extension = os.path.splitext(safe_name)

                # 如果文件已存在,添加时间戳
                if os.path.exists(script_file_path):
                    timestamp = time.strftime("%Y%m%d%H%M%S")
                    file_name_with_timestamp = f"{file_name}_{timestamp}"
                    script_file_path = secure_path(os.path.join(script_dir, file_name_with_timestamp + file_extension), script_dir)

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


def render_video_file(tr, params):
    """渲染视频文件选择"""
    video_list = [(tr("None"), ""), (tr("Upload Local Files"), "upload_local")]

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

    if video_path == "upload_local":
        uploaded_file = st.file_uploader(
            tr("Upload Local Files"),
            type=["mp4", "mov", "avi", "flv", "mkv"],
            accept_multiple_files=False,
        )

        if uploaded_file is not None:
            safe_name = sanitize_filename(uploaded_file.name)
            video_file_path = secure_path(os.path.join(utils.video_dir(), safe_name), utils.video_dir())
            file_name, file_extension = os.path.splitext(safe_name)

            if os.path.exists(video_file_path):
                timestamp = time.strftime("%Y%m%d%H%M%S")
                file_name_with_timestamp = f"{file_name}_{timestamp}"
                video_file_path = secure_path(os.path.join(utils.video_dir(), file_name_with_timestamp + file_extension), utils.video_dir())

            with open(video_file_path, "wb") as f:
                f.write(uploaded_file.read())
                st.success(tr("File Uploaded Successfully"))
                st.session_state['video_origin_path'] = video_file_path
                params.video_origin_path = video_file_path
                time.sleep(1)
                st.rerun()


def render_short_generate_options(tr):
    """
    渲染Short Generate模式下的特殊选项
    在Short Generate模式下，替换原有的输入框为自定义片段选项
    """
    short_drama_summary(tr)
    # 显示自定义片段数量选择器
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


def short_drama_summary(tr):
    """短剧解说 渲染视频主题和提示词"""
    # 检查是否已经处理过字幕文件
    if 'subtitle_file_processed' not in st.session_state:
        st.session_state['subtitle_file_processed'] = False
    
    subtitle_file = st.file_uploader(
        tr("上传字幕文件"),
        type=["srt"],
        accept_multiple_files=False,
        key="subtitle_file_uploader"  # 添加唯一key
    )
    
    # 显示当前已上传的字幕文件路径
    if 'subtitle_path' in st.session_state and st.session_state['subtitle_path']:
        st.info(f"已上传字幕: {os.path.basename(st.session_state['subtitle_path'])}")
        if st.button(tr("清除已上传字幕")):
            st.session_state['subtitle_path'] = None
            st.session_state['subtitle_file_processed'] = False
            st.rerun()
    
    # 只有当有文件上传且尚未处理时才执行处理逻辑
    if subtitle_file is not None and not st.session_state['subtitle_file_processed']:
        try:
            # 读取上传的SRT内容
            script_content = subtitle_file.read().decode('utf-8')

            # 保存到字幕目录
            safe_name = sanitize_filename(subtitle_file.name)
            script_file_path = secure_path(os.path.join(utils.subtitle_dir(), safe_name), utils.subtitle_dir())
            file_name, file_extension = os.path.splitext(safe_name)

            # 如果文件已存在,添加时间戳
            if os.path.exists(script_file_path):
                timestamp = time.strftime("%Y%m%d%H%M%S")
                file_name_with_timestamp = f"{file_name}_{timestamp}"
                script_file_path = secure_path(os.path.join(utils.subtitle_dir(), file_name_with_timestamp + file_extension), utils.subtitle_dir())

            # 直接写入SRT内容，不进行JSON转换
            with open(script_file_path, "w", encoding='utf-8') as f:
                f.write(script_content)

            # 更新状态
            st.success(tr("字幕上传成功"))
            st.session_state['subtitle_path'] = script_file_path
            st.session_state['subtitle_file_processed'] = True  # 标记已处理
            
            # 避免使用rerun，使用更新状态的方式
            # st.rerun()
            
        except Exception as e:
            st.error(f"{tr('Upload failed')}: {str(e)}")

    # 名称输入框
    video_theme = st.text_input(tr("短剧名称"))
    st.session_state['video_theme'] = video_theme
    # 数字输入框
    temperature = st.slider("temperature", 0.0, 2.0, 0.7)
    st.session_state['temperature'] = temperature
    return video_theme


def render_script_buttons(tr, params):
    """渲染脚本操作按钮"""
    # 获取当前选择的脚本类型
    script_path = st.session_state.get('video_clip_json_path', '')

    # 生成/加载按钮
    if script_path == "auto":
        button_name = tr("Generate Video Script")
    elif script_path == "short":
        button_name = tr("Generate Short Video Script")
    elif script_path == "summary":
        button_name = tr("生成短剧解说脚本")
    elif script_path.endswith("json"):
        button_name = tr("Load Video Script")
    else:
        button_name = tr("Please Select Script File")

    if st.button(button_name, key="script_action", disabled=not script_path):
        if script_path == "auto":
            # 执行纪录片视频脚本生成（视频无字幕无配音）
            generate_script_docu(params)
        elif script_path == "short":
            # 执行 短剧混剪 脚本生成
            custom_clips = st.session_state.get('custom_clips')
            generate_script_short(tr, params, custom_clips)
        elif script_path == "summary":
            # 执行 短剧解说 脚本生成
            subtitle_path = st.session_state.get('subtitle_path')
            video_theme = st.session_state.get('video_theme')
            temperature = st.session_state.get('temperature')
            generate_script_short_sunmmary(params, subtitle_path, video_theme, temperature)
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
        script_path = secure_path(script_path, utils.script_dir())
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()
            script = utils.clean_model_output(script)
            st.session_state['video_clip_json'] = json.loads(script)
            st.success(tr("Script loaded successfully"))
            st.rerun()
    except Exception as e:
        logger.error(f"加载脚本文件时发生错误\n{traceback.format_exc()}")
        st.error(f"{tr('Failed to load script')}: {str(e)}")


def save_script(tr, video_clip_json_details):
    """保存视频脚本"""
    if not video_clip_json_details:
        st.error(tr("请输入视频脚本"))
        st.stop()

    with st.spinner(tr("Save Script")):
        script_dir = utils.script_dir()
        timestamp = time.strftime("%Y-%m%d-%H%M%S")
        save_path = secure_path(os.path.join(script_dir, f"{timestamp}.json"), script_dir)

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
        st.success("视频剪辑成功完成！")
    except Exception as e:
        st.error(f"剪辑过程中发生错误: {str(e)}")
    finally:
        time.sleep(1)
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
