import os
import time
import math
import sys
import tempfile
import traceback
import shutil

import streamlit as st
from loguru import logger
from typing import List, Dict, Tuple
from dataclasses import dataclass
from streamlit.runtime.uploaded_file_manager import UploadedFile

from webui.utils.merge_video import merge_videos_and_subtitles
from app.utils.utils import video_dir, srt_dir
from app.services.subtitle import extract_audio_and_create_subtitle

# 定义临时目录路径
TEMP_MERGE_DIR = os.path.join("storage", "temp", "merge")

# 确保临时目录存在
os.makedirs(TEMP_MERGE_DIR, exist_ok=True)


@dataclass
class VideoSubtitlePair:
    video_file: UploadedFile | None
    subtitle_file: str | None
    base_name: str
    order: int = 0


def save_uploaded_file(uploaded_file: UploadedFile, target_dir: str) -> str:
    """Save uploaded file to target directory and return the file path"""
    file_path = os.path.join(target_dir, uploaded_file.name)
    # 如果文件已存在，先删除它
    if os.path.exists(file_path):
        os.remove(file_path)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getvalue())
    return file_path


def clean_temp_dir():
    """清空临时目录"""
    if os.path.exists(TEMP_MERGE_DIR):
        for file in os.listdir(TEMP_MERGE_DIR):
            file_path = os.path.join(TEMP_MERGE_DIR, file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                logger.error(f"清理临时文件失败: {str(e)}")


def group_files(files: List[UploadedFile]) -> Dict[str, VideoSubtitlePair]:
    """Group uploaded files by their base names"""
    pairs = {}
    order_counter = 0
    
    # 首先处理所有视频文件
    for file in files:
        base_name = os.path.splitext(file.name)[0]
        ext = os.path.splitext(file.name)[1].lower()
        
        if ext == ".mp4":
            if base_name not in pairs:
                pairs[base_name] = VideoSubtitlePair(None, None, base_name, order_counter)
                order_counter += 1
            pairs[base_name].video_file = file
            # 保存视频文件到临时目录
            video_path = save_uploaded_file(file, TEMP_MERGE_DIR)
    
    # 然后处理所有字幕文件
    for file in files:
        base_name = os.path.splitext(file.name)[0]
        ext = os.path.splitext(file.name)[1].lower()
        
        if ext == ".srt":
            # 即使没有对应视频也保存字幕文件
            subtitle_path = os.path.join(TEMP_MERGE_DIR, f"{base_name}.srt")
            save_uploaded_file(file, TEMP_MERGE_DIR)
            
            if base_name in pairs:  # 如果有对应的视频
                pairs[base_name].subtitle_file = subtitle_path
            
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
                num_rows = (num_pairs + 4) // 5  # 向上取整,每行5个
                
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
                                
                                # 显示视频预览（如果存在）
                                video_path = os.path.join(TEMP_MERGE_DIR, f"{base_name}.mp4")
                                if os.path.exists(video_path):
                                    st.video(video_path)
                                else:
                                    st.warning(tr("Missing Video"))
                                
                                # 显示字幕预览（如果存在）
                                subtitle_path = os.path.join(TEMP_MERGE_DIR, f"{base_name}.srt")
                                if os.path.exists(subtitle_path):
                                    with open(subtitle_path, 'r', encoding='utf-8') as f:
                                        subtitle_content = f.read()
                                        st.markdown(tr("Subtitle Preview"))
                                        st.text_area(
                                            "Subtitle Content",
                                            value=subtitle_content,
                                            height=100,  # 减高度以适应5列布局
                                            label_visibility="collapsed",
                                            key=f"subtitle_preview_{base_name}"
                                        )
                                else:
                                    st.warning(tr("Missing Subtitle"))
                                    # 如果有视频但没有字幕，显示一键转录按钮
                                    if os.path.exists(video_path):
                                        if st.button(tr("One-Click Transcribe"), key=f"transcribe_{base_name}"):
                                            with st.spinner(tr("Transcribing...")):
                                                try:
                                                    # 生成字幕文件
                                                    result = extract_audio_and_create_subtitle(video_path, subtitle_path)
                                                    if result:
                                                        # 读取生成的字幕文件内容并显示预览
                                                        with open(subtitle_path, 'r', encoding='utf-8') as f:
                                                            subtitle_content = f.read()
                                                            st.markdown(tr("Subtitle Preview"))
                                                            st.text_area(
                                                                "Subtitle Content",
                                                                value=subtitle_content,
                                                                height=150,
                                                                label_visibility="collapsed",
                                                                key=f"subtitle_preview_transcribed_{base_name}"
                                                            )
                                                            st.success(tr("Transcription Complete!"))
                                                            # 更新pair的字幕文件路径
                                                            pair.subtitle_file = subtitle_path
                                                    else:
                                                        st.error(tr("Transcription Failed. Please try again."))
                                                except Exception as e:
                                                    error_message = str(e)
                                                    logger.error(traceback.format_exc())
                                                    if "rate limit exceeded" in error_message.lower():
                                                        st.error(tr("API rate limit exceeded. Please wait about an hour and try again."))
                                                    elif "resource_exhausted" in error_message.lower():
                                                        st.error(tr("Resources exhausted. Please try again later."))
                                                    else:
                                                        st.error(f"{tr('Transcription Failed')}: {str(e)}")
                                
                                # 排序输入框
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
                
                # 如果需要重新排序，重新加载页面
                if st.session_state.needs_reorder:
                    st.session_state.needs_reorder = False
                    st.rerun()
                
                # 找出有完整视频和字幕的文件对
                complete_pairs = {
                    k: v for k, v in all_pairs.items()
                    if os.path.exists(os.path.join(TEMP_MERGE_DIR, f"{k}.mp4")) and 
                    os.path.exists(os.path.join(TEMP_MERGE_DIR, f"{k}.srt"))
                }
                
                # 合并按钮和结果显示
                cols = st.columns([1, 2, 1])
                with cols[0]:
                    st.write(f"{tr('Mergeable Files')}: {len(complete_pairs)}")
                
                merge_videos_result = None
                
                with cols[1]:
                    if st.button(tr("Merge All Files"), type="primary", use_container_width=True):
                        try:
                            # 获取排序后的完整文件对
                            sorted_complete_pairs = sorted(
                                [(k, v) for k, v in complete_pairs.items()],
                                key=lambda x: st.session_state.file_orders[x[0]]
                            )
                            
                            video_paths = []
                            subtitle_paths = []
                            for base_name, _ in sorted_complete_pairs:
                                video_paths.append(os.path.join(TEMP_MERGE_DIR, f"{base_name}.mp4"))
                                subtitle_paths.append(os.path.join(TEMP_MERGE_DIR, f"{base_name}.srt"))
                            
                            # 获取输出文件路径
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
                                    # 清理临时目录
                                    clean_temp_dir()
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
                
                # 合并结果预览放在合并按钮下方
                if merge_videos_result:
                    st.markdown(f"<h3 style='text-align: center'>{tr('Merge Result Preview')}</h3>", unsafe_allow_html=True)
                    # 使用列布局使视频居中
                    col1, col2, col3 = st.columns([1,2,1])
                    with col2:
                        st.video(merge_videos_result[0])
                        st.code(f"{tr('Video Path')}: {merge_videos_result[0]}")
                        st.code(f"{tr('Subtitle Path')}: {merge_videos_result[1]}")
            else:
                st.warning(tr("No Files Found"))
