import os
import time
import math
import sys
import tempfile
import streamlit as st
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass
from streamlit.runtime.uploaded_file_manager import UploadedFile

from webui.utils.merge_video import merge_videos_and_subtitles
from app.utils.utils import video_dir, srt_dir


@dataclass
class VideoSubtitlePair:
    video_file: UploadedFile | None
    subtitle_file: UploadedFile | None
    base_name: str
    order: int = 0


def save_uploaded_file(uploaded_file: UploadedFile, temp_dir: str) -> str:
    """Save uploaded file to temporary directory and return the file path"""
    file_path = os.path.join(temp_dir, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getvalue())
    return file_path


def group_files(files: List[UploadedFile]) -> Dict[str, VideoSubtitlePair]:
    """Group uploaded files by their base names"""
    pairs = {}
    order_counter = 0
    for file in files:
        base_name = os.path.splitext(file.name)[0]
        ext = os.path.splitext(file.name)[1].lower()
        
        if base_name not in pairs:
            pairs[base_name] = VideoSubtitlePair(None, None, base_name, order_counter)
            order_counter += 1
            
        if ext == ".mp4":
            pairs[base_name].video_file = file
        elif ext == ".srt":
            pairs[base_name].subtitle_file = file
            
    return pairs


def render_merge_settings(tr):
    """Render the merge settings section"""
    with st.expander(tr("Video Subtitle Merge"), expanded=False):
        # 上传文件区域
        uploaded_files = st.file_uploader(
            tr("Upload Video and Subtitle Files"),
            type=["mp4", "srt"],
            accept_multiple_files=True,
            key="merge_files"
        )
        
        if uploaded_files:
            all_pairs = group_files(uploaded_files)
            
            if all_pairs:
                st.write(tr("All Uploaded Files"))
                
                # 初始化或更新session state中的排序信息
                if 'file_orders' not in st.session_state:
                    st.session_state.file_orders = {
                        name: pair.order for name, pair in all_pairs.items()
                    }
                    st.session_state.needs_reorder = False
                
                # 确保所有新文件都有排序值
                for name, pair in all_pairs.items():
                    if name not in st.session_state.file_orders:
                        st.session_state.file_orders[name] = pair.order
                
                # 移除不存在的文件的排序值
                st.session_state.file_orders = {
                    k: v for k, v in st.session_state.file_orders.items() 
                    if k in all_pairs
                }
                
                # 按照排序值对文件对进行排序
                sorted_pairs = sorted(
                    all_pairs.items(),
                    key=lambda x: st.session_state.file_orders[x[0]]
                )
                
                # 计算需要多少行来显示所有视频（每行5个）
                num_pairs = len(sorted_pairs)
                num_rows = (num_pairs + 4) // 5  # 向上取整
                
                # 遍历每一行
                for row in range(num_rows):
                    # 创建5列
                    cols = st.columns(5)
                    
                    # 在这一行中填充视频（最多5个）
                    for col_idx in range(5):
                        pair_idx = row * 5 + col_idx
                        if pair_idx < num_pairs:
                            base_name, pair = sorted_pairs[pair_idx]
                            with cols[col_idx]:
                                st.caption(base_name)
                                
                                # 显示视频（如果存在）
                                if pair.video_file:
                                    st.video(pair.video_file)
                                else:
                                    st.warning(tr("Missing Video"))
                                
                                # 添加排序输入框
                                order = st.number_input(
                                    tr("Order"),
                                    min_value=0,
                                    value=st.session_state.file_orders[base_name],
                                    key=f"order_{base_name}",
                                    on_change=lambda: setattr(st.session_state, 'needs_reorder', True)
                                )
                                if order != st.session_state.file_orders[base_name]:
                                    st.session_state.file_orders[base_name] = order
                                    st.session_state.needs_reorder = True
                                
                                # 显示字幕（如果存在）
                                if pair.subtitle_file:
                                    subtitle_content = pair.subtitle_file.getvalue().decode('utf-8')
                                    st.text_area(
                                        "字幕预览",
                                        value=subtitle_content,
                                        height=150,
                                        label_visibility="collapsed"
                                    )
                                else:
                                    st.warning(tr("Missing Subtitle"))
                # 合并后的视频预览
                merge_videos_result = None
                # 只有当存在完整的配对时才显示按钮
                complete_pairs = {k: v for k, v in all_pairs.items() if v.video_file and v.subtitle_file}
                if complete_pairs:
                    # 创建按钮
                    cols = st.columns([1, 1, 3, 3, 3])
                    with cols[0]:
                        if st.button(tr("Reorder"), disabled=not st.session_state.needs_reorder, use_container_width=True):
                            st.session_state.needs_reorder = False
                            st.rerun()
                    
                    with cols[1]:
                        if st.button(tr("Merge All Files"), type="primary", use_container_width=True):
                            try:
                                # 获取排序后的完整文件对
                                sorted_complete_pairs = sorted(
                                    [(k, v) for k, v in complete_pairs.items()],
                                    key=lambda x: st.session_state.file_orders[x[0]]
                                )
                                
                                # 创建临时目录保存文件
                                with tempfile.TemporaryDirectory() as temp_dir:
                                    # 保存上传的文件到临时目录
                                    video_paths = []
                                    subtitle_paths = []
                                    for _, pair in sorted_complete_pairs:
                                        video_path = save_uploaded_file(pair.video_file, temp_dir)
                                        subtitle_path = save_uploaded_file(pair.subtitle_file, temp_dir)
                                        video_paths.append(video_path)
                                        subtitle_paths.append(subtitle_path)
                                    
                                    # 获取输出目录, 文件名添加 MMSS 时间戳
                                    output_video = os.path.join(video_dir(), f"merged_video_{time.strftime('%M%S')}.mp4")
                                    output_subtitle = os.path.join(srt_dir(), f"merged_subtitle_{time.strftime('%M%S')}.srt")
                                    
                                    with st.spinner(tr("Merging files...")):
                                        # 合并文件
                                        merge_videos_and_subtitles(
                                            video_paths,
                                            subtitle_paths,
                                            output_video,
                                            output_subtitle
                                        )
                                        
                                        success = True
                                        error_msg = ""
                                        
                                        # 检查输出文件是否成功生成
                                        if not os.path.exists(output_video):
                                            success = False
                                            error_msg += tr("Failed to generate merged video. ")
                                        if not os.path.exists(output_subtitle):
                                            success = False
                                            error_msg += tr("Failed to generate merged subtitle. ")
                                        
                                        if success:
                                            # 显示成功消息
                                            st.success(tr("Merge completed!"))
                                            merge_videos_result = (output_video, output_subtitle)
                                        else:
                                            st.error(error_msg)
                                            
                            except Exception as e:
                                error_message = str(e)
                                if "moviepy" in error_message.lower():
                                    st.error(tr("Error processing video files. Please check if the videos are valid MP4 files."))
                                elif "pysrt" in error_message.lower():
                                    st.error(tr("Error processing subtitle files. Please check if the subtitles are valid SRT files."))
                                else:
                                    st.error(f"{tr('Error during merge')}: {error_message}")
                    with cols[2]:    
                        # 提供视频和字幕的预览
                        if merge_videos_result:
                            with st.popover(tr("Preview Merged Video")):
                                st.video(merge_videos_result[0], subtitles=merge_videos_result[1])
                                st.code(f"{tr('Video Path')}: {merge_videos_result[0]}")
                                st.code(f"{tr('Subtitle Path')}: {merge_videos_result[1]}")
            else:
                st.warning(tr("No Matched Pairs Found"))
