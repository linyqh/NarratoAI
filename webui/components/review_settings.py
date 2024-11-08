import streamlit as st
import os
from loguru import logger

def render_review_panel(tr):
    """渲染视频审查面板"""
    with st.expander(tr("Video Check"), expanded=False):
        try:
            video_list = st.session_state.get('video_clip_json', [])
        except KeyError:
            video_list = []

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
                        render_video_item(tr, video_list, index)

def render_video_item(tr, video_list, index):
    """渲染单个视频项"""
    video_info = video_list[index]
    video_path = video_info.get('path')
    if video_path is not None and os.path.exists(video_path):
        initial_narration = video_info.get('narration', '')
        initial_picture = video_info.get('picture', '')
        initial_timestamp = video_info.get('timestamp', '')

        # 显示视频
        with open(video_path, 'rb') as video_file:
            video_bytes = video_file.read()
            st.video(video_bytes)

        # 显示信息（只读）
        text_panels = st.columns(2)
        with text_panels[0]:
            st.text_area(
                tr("timestamp"), 
                value=initial_timestamp, 
                height=20,
                key=f"timestamp_{index}",
                disabled=True
            )
        with text_panels[1]:
            st.text_area(
                tr("Picture description"), 
                value=initial_picture, 
                height=20,
                key=f"picture_{index}",
                disabled=True
            )
        st.text_area(
            tr("Narration"), 
            value=initial_narration, 
            height=100,
            key=f"narration_{index}",
            disabled=True
        )