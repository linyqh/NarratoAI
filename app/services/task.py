import math
import json
import os.path
import re
import traceback
from os import path
from loguru import logger

from app.config import config
from app.config.audio_config import AudioConfig, get_recommended_volumes_for_content
from app.models import const
from app.models.schema import VideoClipParams
from app.services import (voice, audio_merger, subtitle_merger, clip_video, merger_video, update_script, generate_video)
from app.services import state as sm
from app.utils import utils


def start_subclip(task_id: str, params: VideoClipParams, subclip_path_videos: dict = None):
    """
    后台任务（统一视频裁剪处理）- 优化版本

    实施基于OST类型的统一视频裁剪策略，消除双重裁剪问题：
    - OST=0: 根据TTS音频时长动态裁剪，移除原声
    - OST=1: 严格按照脚本timestamp精确裁剪，保持原声
    - OST=2: 根据TTS音频时长动态裁剪，保持原声

    Args:
        task_id: 任务ID
        params: 视频参数
        subclip_path_videos: 视频片段路径（可选，仅作为备用方案）
    """
    global merged_audio_path, merged_subtitle_path

    logger.info(f"\n\n## 开始任务: {task_id}")
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=0)

    """
    1. 加载剪辑脚本
    """
    logger.info("\n\n## 1. 加载视频脚本")
    video_script_path = path.join(params.video_clip_json_path)
    
    if path.exists(video_script_path):
        try:
            with open(video_script_path, "r", encoding="utf-8") as f:
                list_script = json.load(f)
                video_list = [i['narration'] for i in list_script]
                video_ost = [i['OST'] for i in list_script]
                time_list = [i['timestamp'] for i in list_script]

                video_script = " ".join(video_list)
                logger.debug(f"解说完整脚本: \n{video_script}")
                logger.debug(f"解说 OST 列表: \n{video_ost}")
                logger.debug(f"解说时间戳列表: \n{time_list}")
        except Exception as e:
            logger.error(f"无法读取视频json脚本，请检查脚本格式是否正确")
            raise ValueError("无法读取视频json脚本，请检查脚本格式是否正确")
    else:
        logger.error(f"解说脚本文件不存在: {video_script_path}，请先点击【保存脚本】按钮保存脚本后再生成视频")
        raise ValueError("解说脚本文件不存在！请先点击【保存脚本】按钮保存脚本后再生成视频。")

    """
    2. 使用 TTS 生成音频素材
    """
    logger.info("\n\n## 2. 根据OST设置生成音频列表")
    # 只为OST=0 or 2的判断生成音频， OST=0 仅保留解说 OST=2 保留解说和原声
    tts_segments = [
        segment for segment in list_script 
        if segment['OST'] in [0, 2]
    ]
    logger.debug(f"需要生成TTS的片段数: {len(tts_segments)}")

    tts_results = voice.tts_multiple(
        task_id=task_id,
        list_script=tts_segments,  # 只传入需要TTS的片段
        tts_engine=params.tts_engine,
        voice_name=params.voice_name,
        voice_rate=params.voice_rate,
        voice_pitch=params.voice_pitch,
    )

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=20)

    # """
    # 3. (可选) 使用 whisper 生成字幕
    # """
    # if merged_subtitle_path is None:
    #     if audio_files:
    #         merged_subtitle_path = path.join(utils.task_dir(task_id), f"subtitle.srt")
    #         subtitle_provider = config.app.get("subtitle_provider", "").strip().lower()
    #         logger.info(f"\n\n使用 {subtitle_provider} 生成字幕")
    #
    #         subtitle.create(
    #             audio_file=merged_audio_path,
    #             subtitle_file=merged_subtitle_path,
    #         )
    #         subtitle_lines = subtitle.file_to_subtitles(merged_subtitle_path)
    #         if not subtitle_lines:
    #             logger.warning(f"字幕文件无效: {merged_subtitle_path}")
    #
    # sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=40)

    """
    3. 统一视频裁剪 - 基于OST类型的差异化裁剪策略
    """
    logger.info("\n\n## 3. 统一视频裁剪（基于OST类型）")

    # 使用新的统一裁剪策略
    video_clip_result = clip_video.clip_video_unified(
        video_origin_path=params.video_origin_path,
        script_list=list_script,
        tts_results=tts_results
    )

    # 更新 list_script 中的时间戳和路径信息
    tts_clip_result = {tts_result['_id']: tts_result['audio_file'] for tts_result in tts_results}
    subclip_clip_result = {
        tts_result['_id']: tts_result['subtitle_file'] for tts_result in tts_results
    }
    new_script_list = update_script.update_script_timestamps(list_script, video_clip_result, tts_clip_result, subclip_clip_result)

    logger.info(f"统一裁剪完成，处理了 {len(video_clip_result)} 个视频片段")

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=60)

    """
    4. 合并音频和字幕
    """
    logger.info("\n\n## 4. 合并音频和字幕")
    total_duration = sum([script["duration"] for script in new_script_list])
    if tts_segments:
        try:
            # 合并音频文件
            merged_audio_path = audio_merger.merge_audio_files(
                task_id=task_id,
                total_duration=total_duration,
                list_script=new_script_list
            )
            logger.info(f"音频文件合并成功->{merged_audio_path}")

            # 合并字幕文件
            merged_subtitle_path = subtitle_merger.merge_subtitle_files(new_script_list)
            if merged_subtitle_path:
                logger.info(f"字幕文件合并成功->{merged_subtitle_path}")
            else:
                logger.warning("没有有效的字幕内容，将生成无字幕视频")
                merged_subtitle_path = ""
        except Exception as e:
            logger.error(f"合并音频/字幕文件失败: {str(e)}")
            # 确保即使合并失败也有默认值
            if 'merged_audio_path' not in locals():
                merged_audio_path = ""
            if 'merged_subtitle_path' not in locals():
                merged_subtitle_path = ""
    else:
        logger.warning("没有需要合并的音频/字幕")
        merged_audio_path = ""
        merged_subtitle_path = ""

    """
    5. 合并视频
    """
    final_video_paths = []
    combined_video_paths = []

    combined_video_path = path.join(utils.task_dir(task_id), f"merger.mp4")
    logger.info(f"\n\n## 5. 合并视频: => {combined_video_path}")

    # 使用统一裁剪后的视频片段
    video_clips = []
    for new_script in new_script_list:
        video_path = new_script.get('video')
        if video_path and os.path.exists(video_path):
            video_clips.append(video_path)
        else:
            logger.warning(f"片段 {new_script.get('_id')} 的视频文件不存在或未生成: {video_path}")
            # 如果统一裁剪失败，尝试使用备用方案（如果提供了subclip_path_videos）
            if subclip_path_videos and new_script.get('_id') in subclip_path_videos:
                backup_video = subclip_path_videos[new_script.get('_id')]
                if os.path.exists(backup_video):
                    video_clips.append(backup_video)
                    logger.info(f"使用备用视频: {backup_video}")
                else:
                    logger.error(f"备用视频也不存在: {backup_video}")
            else:
                logger.error(f"无法找到片段 {new_script.get('_id')} 的视频文件")

    logger.info(f"准备合并 {len(video_clips)} 个视频片段")

    merger_video.combine_clip_videos(
        output_video_path=combined_video_path,
        video_paths=video_clips,
        video_ost_list=video_ost,
        video_aspect=params.video_aspect,
        threads=params.n_threads
    )
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=80)

    """
    6. 合并字幕/BGM/配音/视频
    """
    output_video_path = path.join(utils.task_dir(task_id), f"combined.mp4")
    logger.info(f"\n\n## 6. 最后一步: 合并字幕/BGM/配音/视频 -> {output_video_path}")

    # bgm_path = '/Users/apple/Desktop/home/NarratoAI/resource/songs/bgm.mp3'
    bgm_path = utils.get_bgm_file()

    # 获取优化的音量配置
    optimized_volumes = get_recommended_volumes_for_content('mixed')

    # 检查是否有OST=1的原声片段，如果有，则保持原声音量为1.0不变
    has_original_audio_segments = any(segment['OST'] == 1 for segment in list_script)

    # 应用用户设置和优化建议的组合
    # 如果用户设置了非默认值，优先使用用户设置
    final_tts_volume = params.tts_volume if hasattr(params, 'tts_volume') and params.tts_volume != 1.0 else optimized_volumes['tts_volume']

    # 关键修复：如果有原声片段，保持原声音量为1.0，确保与原视频音量一致
    if has_original_audio_segments:
        final_original_volume = 1.0  # 保持原声音量不变
        logger.info("检测到原声片段，原声音量设置为1.0以保持与原视频一致")
    else:
        final_original_volume = params.original_volume if hasattr(params, 'original_volume') and params.original_volume != 0.7 else optimized_volumes['original_volume']

    final_bgm_volume = params.bgm_volume if hasattr(params, 'bgm_volume') and params.bgm_volume != 0.3 else optimized_volumes['bgm_volume']

    logger.info(f"音量配置 - TTS: {final_tts_volume}, 原声: {final_original_volume}, BGM: {final_bgm_volume}")

    # 调用示例
    options = {
        'voice_volume': final_tts_volume,  # 配音音量（优化后）
        'bgm_volume': final_bgm_volume,  # 背景音乐音量（优化后）
        'original_audio_volume': final_original_volume,  # 视频原声音量（优化后）
        'keep_original_audio': True,  # 是否保留原声
        'subtitle_enabled': params.subtitle_enabled,  # 是否启用字幕 - 修复字幕开关bug
        'subtitle_font': params.font_name,  # 这里使用相对字体路径，会自动在 font_dir() 目录下查找
        'subtitle_font_size': params.font_size,
        'subtitle_color': params.text_fore_color,
        'subtitle_bg_color': None,  # 直接使用None表示透明背景
        'subtitle_position': params.subtitle_position,
        'custom_position': params.custom_position,
        'threads': params.n_threads
    }
    generate_video.merge_materials(
        video_path=combined_video_path,
        audio_path=merged_audio_path,
        subtitle_path=merged_subtitle_path,
        bgm_path=bgm_path,
        output_path=output_video_path,
        options=options
    )

    final_video_paths.append(output_video_path)
    combined_video_paths.append(combined_video_path)

    logger.success(f"任务 {task_id} 已完成, 生成 {len(final_video_paths)} 个视频.")

    kwargs = {
        "videos": final_video_paths,
        "combined_videos": combined_video_paths
    }
    sm.state.update_task(task_id, state=const.TASK_STATE_COMPLETE, progress=100, **kwargs)
    return kwargs


def start_subclip_unified(task_id: str, params: VideoClipParams):
    """
    统一视频裁剪处理函数 - 完全基于OST类型的新实现

    这是优化后的版本，完全移除了对预裁剪视频的依赖，
    实现真正的统一裁剪策略。

    Args:
        task_id: 任务ID
        params: 视频参数
    """
    global merged_audio_path, merged_subtitle_path

    logger.info(f"\n\n## 开始统一视频处理任务: {task_id}")
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=0)

    """
    1. 加载剪辑脚本
    """
    logger.info("\n\n## 1. 加载视频脚本")
    video_script_path = path.join(params.video_clip_json_path)

    if path.exists(video_script_path):
        try:
            with open(video_script_path, "r", encoding="utf-8") as f:
                list_script = json.load(f)
                video_list = [i['narration'] for i in list_script]
                video_ost = [i['OST'] for i in list_script]
                time_list = [i['timestamp'] for i in list_script]

                video_script = " ".join(video_list)
                logger.debug(f"解说完整脚本: \n{video_script}")
                logger.debug(f"解说 OST 列表: \n{video_ost}")
                logger.debug(f"解说时间戳列表: \n{time_list}")
        except Exception as e:
            logger.error(f"无法读取视频json脚本，请检查脚本格式是否正确")
            raise ValueError("无法读取视频json脚本，请检查脚本格式是否正确")
    else:
        logger.error(f"解说脚本文件不存在: {video_script_path}，请先点击【保存脚本】按钮保存脚本后再生成视频")
        raise ValueError("解说脚本文件不存在！请先点击【保存脚本】按钮保存脚本后再生成视频。")

    """
    2. 使用 TTS 生成音频素材
    """
    logger.info("\n\n## 2. 根据OST设置生成音频列表")
    # 只为OST=0 or 2的判断生成音频， OST=0 仅保留解说 OST=2 保留解说和原声
    tts_segments = [
        segment for segment in list_script
        if segment['OST'] in [0, 2]
    ]
    logger.debug(f"需要生成TTS的片段数: {len(tts_segments)}")

    tts_results = voice.tts_multiple(
        task_id=task_id,
        list_script=tts_segments,  # 只传入需要TTS的片段
        tts_engine=params.tts_engine,
        voice_name=params.voice_name,
        voice_rate=params.voice_rate,
        voice_pitch=params.voice_pitch,
    )

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=20)

    """
    3. 统一视频裁剪 - 基于OST类型的差异化裁剪策略
    """
    logger.info("\n\n## 3. 统一视频裁剪（基于OST类型）")

    # 使用新的统一裁剪策略
    video_clip_result = clip_video.clip_video_unified(
        video_origin_path=params.video_origin_path,
        script_list=list_script,
        tts_results=tts_results
    )

    # 更新 list_script 中的时间戳和路径信息
    tts_clip_result = {tts_result['_id']: tts_result['audio_file'] for tts_result in tts_results}
    subclip_clip_result = {
        tts_result['_id']: tts_result['subtitle_file'] for tts_result in tts_results
    }
    new_script_list = update_script.update_script_timestamps(list_script, video_clip_result, tts_clip_result, subclip_clip_result)

    logger.info(f"统一裁剪完成，处理了 {len(video_clip_result)} 个视频片段")

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=60)

    """
    4. 合并音频和字幕
    """
    logger.info("\n\n## 4. 合并音频和字幕")
    total_duration = sum([script["duration"] for script in new_script_list])
    if tts_segments:
        try:
            # 合并音频文件
            merged_audio_path = audio_merger.merge_audio_files(
                task_id=task_id,
                total_duration=total_duration,
                list_script=new_script_list
            )
            logger.info(f"音频文件合并成功->{merged_audio_path}")

            # 合并字幕文件
            merged_subtitle_path = subtitle_merger.merge_subtitle_files(new_script_list)
            if merged_subtitle_path:
                logger.info(f"字幕文件合并成功->{merged_subtitle_path}")
            else:
                logger.warning("没有有效的字幕内容，将生成无字幕视频")
                merged_subtitle_path = ""
        except Exception as e:
            logger.error(f"合并音频/字幕文件失败: {str(e)}")
            # 确保即使合并失败也有默认值
            if 'merged_audio_path' not in locals():
                merged_audio_path = ""
            if 'merged_subtitle_path' not in locals():
                merged_subtitle_path = ""
    else:
        logger.warning("没有需要合并的音频/字幕")
        merged_audio_path = ""
        merged_subtitle_path = ""

    """
    5. 合并视频
    """
    final_video_paths = []
    combined_video_paths = []

    combined_video_path = path.join(utils.task_dir(task_id), f"merger.mp4")
    logger.info(f"\n\n## 5. 合并视频: => {combined_video_path}")

    # 使用统一裁剪后的视频片段
    video_clips = []
    for new_script in new_script_list:
        video_path = new_script.get('video')
        if video_path and os.path.exists(video_path):
            video_clips.append(video_path)
        else:
            logger.error(f"片段 {new_script.get('_id')} 的视频文件不存在: {video_path}")

    logger.info(f"准备合并 {len(video_clips)} 个视频片段")

    merger_video.combine_clip_videos(
        output_video_path=combined_video_path,
        video_paths=video_clips,
        video_ost_list=video_ost,
        video_aspect=params.video_aspect,
        threads=params.n_threads
    )
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=80)

    """
    6. 合并字幕/BGM/配音/视频
    """
    output_video_path = path.join(utils.task_dir(task_id), f"combined.mp4")
    logger.info(f"\n\n## 6. 最后一步: 合并字幕/BGM/配音/视频 -> {output_video_path}")

    bgm_path = utils.get_bgm_file()

    # 获取优化的音量配置
    optimized_volumes = get_recommended_volumes_for_content('mixed')

    # 检查是否有OST=1的原声片段，如果有，则保持原声音量为1.0不变
    has_original_audio_segments = any(segment['OST'] == 1 for segment in list_script)

    # 应用用户设置和优化建议的组合
    final_tts_volume = params.tts_volume if hasattr(params, 'tts_volume') and params.tts_volume != 1.0 else optimized_volumes['tts_volume']

    # 关键修复：如果有原声片段，保持原声音量为1.0，确保与原视频音量一致
    if has_original_audio_segments:
        final_original_volume = 1.0  # 保持原声音量不变
        logger.info("检测到原声片段，原声音量设置为1.0以保持与原视频一致")
    else:
        final_original_volume = params.original_volume if hasattr(params, 'original_volume') and params.original_volume != 0.7 else optimized_volumes['original_volume']

    final_bgm_volume = params.bgm_volume if hasattr(params, 'bgm_volume') and params.bgm_volume != 0.3 else optimized_volumes['bgm_volume']

    logger.info(f"音量配置 - TTS: {final_tts_volume}, 原声: {final_original_volume}, BGM: {final_bgm_volume}")

    # 调用示例
    options = {
        'voice_volume': final_tts_volume,
        'bgm_volume': final_bgm_volume,
        'original_audio_volume': final_original_volume,
        'keep_original_audio': True,
        'subtitle_enabled': params.subtitle_enabled,
        'subtitle_font': params.font_name,
        'subtitle_font_size': params.font_size,
        'subtitle_color': params.text_fore_color,
        'subtitle_bg_color': None,
        'subtitle_position': params.subtitle_position,
        'custom_position': params.custom_position,
        'threads': params.n_threads
    }
    generate_video.merge_materials(
        video_path=combined_video_path,
        audio_path=merged_audio_path,
        subtitle_path=merged_subtitle_path,
        bgm_path=bgm_path,
        output_path=output_video_path,
        options=options
    )

    final_video_paths.append(output_video_path)
    combined_video_paths.append(combined_video_path)

    logger.success(f"统一处理任务 {task_id} 已完成, 生成 {len(final_video_paths)} 个视频.")

    kwargs = {
        "videos": final_video_paths,
        "combined_videos": combined_video_paths
    }
    sm.state.update_task(task_id, state=const.TASK_STATE_COMPLETE, progress=100, **kwargs)
    return kwargs


def validate_params(video_path, audio_path, output_file, params):
    """
    验证输入参数
    Args:
        video_path: 视频文件路径
        audio_path: 音频文件路径（可以为空字符串）
        output_file: 输出文件路径
        params: 视频参数

    Raises:
        FileNotFoundError: 文件不存在时抛出
        ValueError: 参数无效时抛出
    """
    if not video_path:
        raise ValueError("视频路径不能为空")
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
    # 如果提供了音频路径，则验证文件是否存在
    if audio_path and not os.path.exists(audio_path):
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
    if not output_file:
        raise ValueError("输出文件路径不能为空")
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    if not params:
        raise ValueError("视频参数不能为空")


if __name__ == "__main__":
    task_id = "demo"

    # 提前裁剪是为了方便检查视频
    subclip_path_videos = {
        1: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/113343d127b5a09d0bf84b68bd1b3b97/vid_00-00-05-390@00-00-57-980.mp4',
        2: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/113343d127b5a09d0bf84b68bd1b3b97/vid_00-00-28-900@00-00-43-700.mp4',
        3: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/113343d127b5a09d0bf84b68bd1b3b97/vid_00-01-17-840@00-01-27-600.mp4',
        4: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/113343d127b5a09d0bf84b68bd1b3b97/vid_00-02-35-460@00-02-52-380.mp4',
        5: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/113343d127b5a09d0bf84b68bd1b3b97/vid_00-06-59-520@00-07-29-500.mp4',
    }

    params = VideoClipParams(
        video_clip_json_path="/Users/apple/Desktop/home/NarratoAI/resource/scripts/2025-0507-223311.json",
        video_origin_path="/Users/apple/Desktop/home/NarratoAI/resource/videos/merged_video_4938.mp4",
    )
    start_subclip(task_id, params, subclip_path_videos)
