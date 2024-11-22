import streamlit as st
import os
from loguru import logger


def render_review_panel(tr):
    """渲染视频审查面板"""
    with st.expander(tr("Video Check"), expanded=False):
        try:
            video_list = st.session_state.get('video_clip_json', [])
            subclip_videos = st.session_state.get('subclip_videos', {})
        except KeyError:
            video_list = []
            subclip_videos = {}

        # 计算列数和行数
        num_videos = len(video_list)
        cols_per_row = 3
        rows = (num_videos + cols_per_row - 1) // cols_per_row  # 向上取整计算行数

        # 使用容器展示视频
        for row in range(rows):
            cols = st.columns(cols_per_row)
            for col in range(cols_per_row):
                index = row * cols_per_row + col
                if index < num_videos:
                    with cols[col]:
                        render_video_item(tr, video_list, subclip_videos, index)


def render_video_item(tr, video_list, subclip_videos, index):
    """渲染单个视频项"""
    video_script = video_list[index]

    # 显示时间戳
    timestamp = video_script.get('timestamp', '')
    st.text_area(
        tr("Timestamp"),
        value=timestamp,
        height=70,
        disabled=True,
        key=f"timestamp_{index}"
    )

    # 显示视频播放器
    video_path = subclip_videos.get(timestamp)
    if video_path and os.path.exists(video_path):
        try:
            st.video(video_path)
        except Exception as e:
            logger.error(f"加载视频失败 {video_path}: {e}")
            st.error(f"无法加载视频: {os.path.basename(video_path)}")
    else:
        st.warning(tr("视频文件未找到"))

    # 显示画面描述
    st.text_area(
        tr("Picture Description"),
        value=video_script.get('picture', ''),
        height=150,
        disabled=True,
        key=f"picture_{index}"
    )

    # 显示旁白文本
    narration = st.text_area(
        tr("Narration"),
        value=video_script.get('narration', ''),
        height=150,
        key=f"narration_{index}"
    )
    # 保存修改后的旁白文本
    if narration != video_script.get('narration', ''):
        video_script['narration'] = narration
        st.session_state['video_clip_json'] = video_list

    # 显示剪辑模式
    ost = st.selectbox(
        tr("Clip Mode"),
        options=range(0, 3),
        index=video_script.get('OST', 0),
        key=f"ost_{index}",
        help=tr("0: Keep the audio only, 1: Keep the original sound only, 2: Keep the original sound and audio")
    )
    # 保存修改后的剪辑模式
    if ost != video_script.get('OST', 0):
        video_script['OST'] = ost
        st.session_state['video_clip_json'] = video_list
