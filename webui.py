import streamlit as st
import os
import sys
from uuid import uuid4
from app.config import config
from webui.components import basic_settings, video_settings, audio_settings, subtitle_settings, script_settings, review_settings, merge_settings, system_settings
from webui.utils import cache, file_utils
from app.utils import utils
from app.models.schema import VideoClipParams, VideoAspect
from webui.utils.performance import PerformanceMonitor

# 初始化配置 - 必须是第一个 Streamlit 命令
st.set_page_config(
    page_title="NarratoAI",
    page_icon="📽️",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Report a bug": "https://github.com/linyqh/NarratoAI/issues",
        'About': f"# NarratoAI:sunglasses: 📽️ \n #### Version: v{config.project_version} \n "
                 f"自动化影视解说视频详情请移步：https://github.com/linyqh/NarratoAI"
    },
)

# 设置页面样式
hide_streamlit_style = """
<style>#root > div:nth-child(1) > div > div > div > div > section > div {padding-top: 6px; padding-bottom: 10px; padding-left: 20px; padding-right: 20px;}</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

def init_log():
    """初始化日志配置"""
    from loguru import logger
    logger.remove()
    _lvl = "DEBUG"

    def format_record(record):
        # 增加更多需要过滤的警告消息
        ignore_messages = [
            "Examining the path of torch.classes raised",
            "torch.cuda.is_available()",
            "CUDA initialization"
        ]
        
        for msg in ignore_messages:
            if msg in record["message"]:
                return ""
            
        file_path = record["file"].path
        relative_path = os.path.relpath(file_path, config.root_dir)
        record["file"].path = f"./{relative_path}"
        record['message'] = record['message'].replace(config.root_dir, ".")

        _format = '<green>{time:%Y-%m-%d %H:%M:%S}</> | ' + \
                  '<level>{level}</> | ' + \
                  '"{file.path}:{line}":<blue> {function}</> ' + \
                  '- <level>{message}</>' + "\n"
        return _format

    # 优化日志过滤器
    def log_filter(record):
        ignore_messages = [
            "Examining the path of torch.classes raised",
            "torch.cuda.is_available()",
            "CUDA initialization"
        ]
        return not any(msg in record["message"] for msg in ignore_messages)

    logger.add(
        sys.stdout,
        level=_lvl,
        format=format_record,
        colorize=True,
        filter=log_filter
    )

def init_global_state():
    """初始化全局状态"""
    if 'video_clip_json' not in st.session_state:
        st.session_state['video_clip_json'] = []
    if 'video_plot' not in st.session_state:
        st.session_state['video_plot'] = ''
    if 'ui_language' not in st.session_state:
        st.session_state['ui_language'] = config.ui.get("language", utils.get_system_locale())
    if 'subclip_videos' not in st.session_state:
        st.session_state['subclip_videos'] = {}

def tr(key):
    """翻译函数"""
    i18n_dir = os.path.join(os.path.dirname(__file__), "webui", "i18n")
    locales = utils.load_locales(i18n_dir)
    loc = locales.get(st.session_state['ui_language'], {})
    return loc.get("Translation", {}).get(key, key)

def render_generate_button():
    """渲染生成按钮和处理逻辑"""
    if st.button(tr("Generate Video"), use_container_width=True, type="primary"):
        try:
            from app.services import task as tm
            import torch
            
            # 重置日志容器和记录
            log_container = st.empty()
            log_records = []

            def log_received(msg):
                with log_container:
                    log_records.append(msg)
                    st.code("\n".join(log_records))

            from loguru import logger
            logger.add(log_received)

            config.save_config()
            task_id = st.session_state.get('task_id')

            if not task_id:
                st.error(tr("请先裁剪视频"))
                return
            if not st.session_state.get('video_clip_json_path'):
                st.error(tr("脚本文件不能为空"))
                return
            if not st.session_state.get('video_origin_path'):
                st.error(tr("视频文件不能为空"))
                return

            st.toast(tr("生成视频"))
            logger.info(tr("开始生成视频"))

            # 获取所有参数
            script_params = script_settings.get_script_params()
            video_params = video_settings.get_video_params()
            audio_params = audio_settings.get_audio_params()
            subtitle_params = subtitle_settings.get_subtitle_params()

            # 合并所有参数
            all_params = {
                **script_params,
                **video_params,
                **audio_params,
                **subtitle_params
            }

            # 创建参数对象
            params = VideoClipParams(**all_params)

            result = tm.start_subclip(
                task_id=task_id,
                params=params,
                subclip_path_videos=st.session_state['subclip_videos']
            )

            video_files = result.get("videos", [])
            st.success(tr("视生成完成"))
            
            try:
                if video_files:
                    player_cols = st.columns(len(video_files) * 2 + 1)
                    for i, url in enumerate(video_files):
                        player_cols[i * 2 + 1].video(url)
            except Exception as e:
                logger.error(f"播放视频失败: {e}")

            file_utils.open_task_folder(config.root_dir, task_id)
            logger.info(tr("视频生成完成"))

        finally:
            PerformanceMonitor.cleanup_resources()

def main():
    """主函数"""
    init_log()
    init_global_state()
    utils.init_resources()
    
    st.title(f"NarratoAI :sunglasses:📽️")
    st.write(tr("Get Help"))
    
    # 渲染基础设置面板
    basic_settings.render_basic_settings(tr)
    # 渲染合并设置
    merge_settings.render_merge_settings(tr)

    # 渲染主面板
    panel = st.columns(3)
    with panel[0]:
        script_settings.render_script_panel(tr)
    with panel[1]:
        video_settings.render_video_panel(tr)
        audio_settings.render_audio_panel(tr)
    with panel[2]:
        subtitle_settings.render_subtitle_panel(tr)
        # 渲染系统设置面板
        system_settings.render_system_panel(tr)
    
    # 渲染视频审查面板
    review_settings.render_review_panel(tr)
    
    # 渲染生成按钮和处理逻辑
    render_generate_button()

if __name__ == "__main__":
    main()
