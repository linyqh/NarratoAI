import streamlit as st
import os
import glob
import json
import time
from app.config import config
from app.models.schema import VideoClipParams
from app.services import llm
from app.utils import utils, check_script
from loguru import logger
from webui.utils import file_utils

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
    prompt = st.text_area(
        tr("Generation Prompt"),
        value=st.session_state.get('video_plot', ''),
        help=tr("Custom prompt for LLM, leave empty to use default prompt"),
        height=180
    )
    st.session_state['video_name'] = video_theme
    st.session_state['video_plot'] = prompt
    return video_theme, prompt

def render_script_buttons(tr, params):
    """渲染脚本操作按钮"""
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
            if not st.session_state.get('video_plot'):
                st.warning("视频剧情为空; 会极大影响生成效果！")
                
            if params.video_clip_json_path == "" and params.video_origin_path != "":
                update_progress(10, "压缩视频中...")
                script = llm.generate_script(
                    video_path=params.video_origin_path,
                    video_plot=st.session_state.get('video_plot', ''),
                    video_name=st.session_state.get('video_name', ''),
                    language=params.video_language,
                    progress_callback=update_progress
                )
                if script is None:
                    st.error("生成脚本失败，请检查日志")
                    st.stop()
                else:
                    update_progress(90)

                script = utils.clean_model_output(script)
                st.session_state['video_clip_json'] = json.loads(script)
            else:
                # 从本地加载
                with open(params.video_clip_json_path, 'r', encoding='utf-8') as f:
                    update_progress(50)
                    status_text.text("从本地加载中...")
                    script = f.read()
                    script = utils.clean_model_output(script)
                    st.session_state['video_clip_json'] = json.loads(script)
                    update_progress(100)
                    status_text.text("从本地加载成功")

        time.sleep(0.5)
        progress_bar.progress(100)
        status_text.text("脚本生成完成！")
        st.success("视频脚本生成成功！")
    except Exception as err:
        st.error(f"生成过程中发生错误: {str(err)}")
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
                
                # 强制重新加载页面以更新选择框
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