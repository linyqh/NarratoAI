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
from app.services import (
    voice,
    audio_merger,
    subtitle_merger,
    clip_video,
    merger_video,
    update_script,
    generate_video,
    script_subtitle,
    sonilo,
)
from app.services import state as sm
from app.utils import utils


VIDEO_GENERATION_TOTAL_STEPS = 6


def _update_video_generation_task(
    task_id: str,
    progress: int,
    message: str,
    step_current: int = 0,
    ffmpeg_progress: float | None = None,
    state: int = const.TASK_STATE_PROCESSING,
    **kwargs,
) -> None:
    task_fields = {
        "message": message,
        "step_current": step_current,
        "step_total": VIDEO_GENERATION_TOTAL_STEPS,
        **kwargs,
    }
    if ffmpeg_progress is not None:
        task_fields["ffmpeg_progress"] = round(
            max(0.0, min(100.0, float(ffmpeg_progress))),
            1,
        )

    sm.state.update_task(
        task_id,
        state=state,
        progress=progress,
        **task_fields,
    )


def _is_auto_transcription_enabled(params: VideoClipParams) -> bool:
    return bool(
        getattr(params, "subtitle_enabled", True)
        and getattr(params, "subtitle_auto_transcribe_enabled", False)
    )


def _get_auto_transcription_backend(params: VideoClipParams) -> str:
    backend = str(getattr(params, "subtitle_auto_transcribe_backend", "") or "").strip().lower()
    if backend not in {"local", "firered", "bailian"}:
        backend = "local"
    return backend


def _get_original_subtitle_paths(params: VideoClipParams) -> list[str]:
    subtitle_paths = getattr(params, "original_subtitle_paths", []) or []
    if isinstance(subtitle_paths, str):
        subtitle_paths = [subtitle_paths]

    normalized_paths = []
    seen = set()
    for subtitle_path in subtitle_paths:
        if not isinstance(subtitle_path, str):
            continue
        subtitle_path = subtitle_path.strip()
        if subtitle_path and subtitle_path not in seen:
            normalized_paths.append(subtitle_path)
            seen.add(subtitle_path)

    single_subtitle_path = str(getattr(params, "original_subtitle_path", "") or "").strip()
    if single_subtitle_path and single_subtitle_path not in seen:
        normalized_paths.insert(0, single_subtitle_path)

    if not normalized_paths:
        normalized_paths = _find_original_subtitle_paths_for_videos(_get_video_origin_paths(params))

    return normalized_paths


def _get_video_origin_paths(params: VideoClipParams) -> list[str]:
    video_paths = getattr(params, "video_origin_paths", []) or []
    if isinstance(video_paths, str):
        video_paths = [video_paths]

    normalized_paths = []
    seen = set()
    for video_path in video_paths:
        if not isinstance(video_path, str):
            continue
        video_path = video_path.strip()
        if video_path and video_path not in seen:
            normalized_paths.append(video_path)
            seen.add(video_path)

    single_video_path = str(getattr(params, "video_origin_path", "") or "").strip()
    if single_video_path and single_video_path not in seen:
        normalized_paths.insert(0, single_video_path)

    return normalized_paths


def _video_stem_candidates(video_path: str) -> list[str]:
    stem = path.splitext(path.basename(str(video_path or "").strip()))[0]
    if not stem:
        return []

    candidates = [stem]
    timestamp_stripped = re.sub(r"_[0-9]{14}$", "", stem)
    if timestamp_stripped and timestamp_stripped not in candidates:
        candidates.append(timestamp_stripped)
    return candidates


def _find_original_subtitle_paths_for_videos(video_paths: list[str]) -> list[str]:
    subtitle_dir = utils.subtitle_dir()
    if not path.isdir(subtitle_dir):
        return []

    subtitle_files = [
        path.join(subtitle_dir, filename)
        for filename in os.listdir(subtitle_dir)
        if filename.lower().endswith(".srt")
    ]
    if not subtitle_files:
        return []

    resolved_paths = []
    seen = set()
    for video_path in video_paths:
        candidates = _video_stem_candidates(video_path)
        if not candidates:
            continue

        matches = []
        for subtitle_path in subtitle_files:
            subtitle_stem = path.splitext(path.basename(subtitle_path))[0]
            for candidate in candidates:
                if subtitle_stem == candidate or subtitle_stem.startswith(f"{candidate}_"):
                    matches.append(subtitle_path)
                    break

        if not matches:
            continue

        matches.sort(key=lambda item: path.getmtime(item), reverse=True)
        selected_path = matches[0]
        if selected_path not in seen:
            resolved_paths.append(selected_path)
            seen.add(selected_path)

    if resolved_paths:
        logger.info(f"未从参数获取原片字幕，已按视频文件名自动匹配: {resolved_paths}")
    return resolved_paths


def _create_programmatic_subtitle_file(
    task_id: str,
    list_script: list[dict],
    params: VideoClipParams,
) -> str:
    if not getattr(params, "subtitle_enabled", True):
        return ""

    original_subtitle_paths = _get_original_subtitle_paths(params)
    logger.info(f"程序化字幕使用原片字幕路径: {original_subtitle_paths or '未提供'}")
    return script_subtitle.create_script_subtitle_file(
        task_id=task_id,
        list_script=list_script,
        original_subtitle_paths=original_subtitle_paths,
        video_origin_paths=_get_video_origin_paths(params),
    )


def _build_subtitle_mask_options(params: VideoClipParams, enabled=None) -> dict:
    mask_configured = bool(
        getattr(params, "subtitle_enabled", True)
        and getattr(params, "subtitle_mask_enabled", False)
    )
    mask_enabled = mask_configured if enabled is None else mask_configured and enabled
    return {
        'subtitle_mask_enabled': mask_enabled,
        'subtitle_mask_landscape_x_percent': getattr(params, "subtitle_mask_landscape_x_percent", 10.0),
        'subtitle_mask_landscape_y_percent': getattr(params, "subtitle_mask_landscape_y_percent", 78.0),
        'subtitle_mask_landscape_width_percent': getattr(params, "subtitle_mask_landscape_width_percent", 80.0),
        'subtitle_mask_landscape_height_percent': getattr(params, "subtitle_mask_landscape_height_percent", 14.0),
        'subtitle_mask_landscape_blur_radius': getattr(params, "subtitle_mask_landscape_blur_radius", 18),
        'subtitle_mask_landscape_opacity_percent': getattr(params, "subtitle_mask_landscape_opacity_percent", 82),
        'subtitle_mask_portrait_x_percent': getattr(params, "subtitle_mask_portrait_x_percent", 8.0),
        'subtitle_mask_portrait_y_percent': getattr(params, "subtitle_mask_portrait_y_percent", 79.0),
        'subtitle_mask_portrait_width_percent': getattr(params, "subtitle_mask_portrait_width_percent", 84.0),
        'subtitle_mask_portrait_height_percent': getattr(params, "subtitle_mask_portrait_height_percent", 16.0),
        'subtitle_mask_portrait_blur_radius': getattr(params, "subtitle_mask_portrait_blur_radius", 26),
        'subtitle_mask_portrait_opacity_percent': getattr(params, "subtitle_mask_portrait_opacity_percent", 84),
        'subtitle_position_landscape_y_percent': getattr(params, "subtitle_position_landscape_y_percent", 85.0),
        'subtitle_position_portrait_y_percent': getattr(params, "subtitle_position_portrait_y_percent", 82.0),
    }


def _resolve_bgm_path(task_id: str, params: VideoClipParams, combined_video_path: str) -> str:
    """解析最终合成使用的背景音乐文件路径。

    bgm_type 为 "sonilo" 时（可选功能，默认关闭），将合并后的成片上传到
    Sonilo API 生成配乐；任何失败都只记录日志并回退到现有的随机背景音乐
    逻辑，绝不中断成片任务。其余 bgm_type 走原有逻辑，保持不变。
    """
    if getattr(params, "bgm_type", "") == "sonilo":
        save_path = path.join(utils.task_dir(task_id), "sonilo_bgm.m4a")
        bgm_path = sonilo.generate_bgm(combined_video_path, save_path)
        if bgm_path:
            return bgm_path
        logger.warning("Sonilo 配乐不可用，回退到随机背景音乐")
        return utils.get_bgm_file(bgm_type="random", bgm_file="")

    return utils.get_bgm_file(
        bgm_type=getattr(params, "bgm_type", "random"),
        bgm_file=getattr(params, "bgm_file", ""),
    )


def _apply_sonilo_sfx(task_id: str, params: VideoClipParams, combined_video_path: str) -> str:
    """为合并后的成片混入 Sonilo AI 音效（可选功能，默认关闭）。

    仅当 params.sonilo_sfx_enabled 为 True 时启用：把合并后的成片上传到
    Sonilo API 生成音效，再用 ffmpeg 混在现有音轨之下，返回新视频路径。
    解说配音在后续 merge_materials 中单独混入，音量策略不受影响。任何
    失败都只记录日志并沿用原视频，绝不中断成片任务。
    """
    if not getattr(params, "sonilo_sfx_enabled", False):
        return combined_video_path
    output_path = path.join(utils.task_dir(task_id), "merger_sfx.mp4")
    sfx_video_path = sonilo.apply_sfx(combined_video_path, output_path)
    if sfx_video_path:
        return sfx_video_path
    logger.warning("Sonilo 音效不可用，继续使用未加音效的成片")
    return combined_video_path


def _transcribe_final_video(task_id: str, video_path: str, params: VideoClipParams) -> str:
    """Transcribe the fully merged video into an SRT file."""
    from app.services import fun_asr_subtitle

    if not video_path or not path.exists(video_path):
        raise FileNotFoundError(f"自动转录视频不存在: {video_path}")

    backend = _get_auto_transcription_backend(params)
    subtitle_file = path.join(utils.task_dir(task_id), "auto_transcribed_final.srt")
    logger.info(f"开始自动转录最终视频: {video_path}, backend={backend}")

    if backend == "local":
        api_url = str(
            getattr(params, "subtitle_auto_transcribe_api_url", "")
            or config.fun_asr.get("api_url", fun_asr_subtitle.LOCAL_FUN_ASR_API_URL)
        ).strip()
        if not api_url:
            raise ValueError("请先输入本地 FunASR-Pack API 地址")

        generated_path = fun_asr_subtitle.create_with_local_fun_asr(
            local_file=video_path,
            subtitle_file=subtitle_file,
            api_url=api_url,
            hotword=str(getattr(params, "subtitle_auto_transcribe_hotword", "") or "").strip(),
            enable_spk=bool(getattr(params, "subtitle_auto_transcribe_enable_spk", False)),
        )
    elif backend == "firered":
        api_url = str(
            getattr(params, "subtitle_auto_transcribe_firered_api_url", "")
            or config.fun_asr.get("firered_api_url", fun_asr_subtitle.LOCAL_FIRERED_ASR_API_URL)
        ).strip()
        if not api_url:
            raise ValueError("请先输入本地ASR API 地址")

        generated_path = fun_asr_subtitle.create_with_local_firered_asr(
            local_file=video_path,
            subtitle_file=subtitle_file,
            api_url=api_url,
        )
    else:
        api_key = str(
            getattr(params, "subtitle_auto_transcribe_api_key", "")
            or config.fun_asr.get("api_key", "")
        ).strip()
        if not api_key:
            raise ValueError("请先输入阿里百炼 API Key")

        generated_path = fun_asr_subtitle.create_with_fun_asr(
            local_file=video_path,
            subtitle_file=subtitle_file,
            api_key=api_key,
        )

    if not generated_path or not path.exists(generated_path):
        raise RuntimeError("自动转录失败：未生成字幕文件")

    logger.info(f"自动转录字幕生成成功: {generated_path}")
    return generated_path


def _merge_auto_transcribed_subtitles(
    source_video_path: str,
    output_video_path: str,
    subtitle_path: str,
    params: VideoClipParams,
) -> str:
    subtitle_options = {
        'voice_volume': 1.0,
        'bgm_volume': 0.0,
        'original_audio_volume': 1.0,
        'keep_original_audio': True,
        'subtitle_enabled': True,
        'subtitle_font': params.font_name,
        'subtitle_font_size': params.font_size,
        'subtitle_color': params.text_fore_color,
        'subtitle_bg_color': None,
        'subtitle_position': params.subtitle_position,
        'custom_position': params.custom_position,
        'threads': params.n_threads,
        **_build_subtitle_mask_options(params, enabled=True),
    }
    return generate_video.merge_materials(
        video_path=source_video_path,
        audio_path="",
        subtitle_path=subtitle_path,
        bgm_path="",
        output_path=output_video_path,
        options=subtitle_options
    )


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
        video_origin_paths=getattr(params, "video_origin_paths", []),
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
            merged_subtitle_path = ""
            if getattr(params, "subtitle_enabled", True):
                try:
                    merged_subtitle_path = _create_programmatic_subtitle_file(
                        task_id,
                        new_script_list,
                        params,
                    )
                except Exception as e:
                    logger.warning(f"程序化字幕生成失败，将尝试合并TTS字幕: {e}")

            if not merged_subtitle_path and getattr(params, "subtitle_enabled", True):
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
        if getattr(params, "subtitle_enabled", True):
            try:
                merged_subtitle_path = _create_programmatic_subtitle_file(
                    task_id,
                    new_script_list,
                    params,
                )
            except Exception as e:
                logger.warning(f"程序化字幕生成失败: {e}")

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
    auto_transcription_enabled = _is_auto_transcription_enabled(params)
    merge_output_video_path = (
        path.join(utils.task_dir(task_id), "combined_without_auto_subtitles.mp4")
        if auto_transcription_enabled
        else output_video_path
    )
    logger.info(f"\n\n## 6. 最后一步: 合并字幕/BGM/配音/视频 -> {merge_output_video_path}")

    # 可选功能，默认关闭：混入 Sonilo AI 音效（失败时沿用原视频）
    combined_video_path = _apply_sonilo_sfx(task_id, params, combined_video_path)

    # bgm_path = '/Users/apple/Desktop/home/NarratoAI/resource/songs/bgm.mp3'
    bgm_path = _resolve_bgm_path(task_id, params, combined_video_path)

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
        'subtitle_enabled': params.subtitle_enabled and not auto_transcription_enabled,
        'subtitle_font': params.font_name,  # 这里使用相对字体路径，会自动在 font_dir() 目录下查找
        'subtitle_font_size': params.font_size,
        'subtitle_color': params.text_fore_color,
        'subtitle_bg_color': None,  # 直接使用None表示透明背景
        'subtitle_position': params.subtitle_position,
        'custom_position': params.custom_position,
        'threads': params.n_threads,
        **_build_subtitle_mask_options(params, enabled=not auto_transcription_enabled),
    }
    generate_video.merge_materials(
        video_path=combined_video_path,
        audio_path=merged_audio_path,
        subtitle_path=merged_subtitle_path,
        bgm_path=bgm_path,
        output_path=merge_output_video_path,
        options=options
    )

    auto_subtitle_path = ""
    if auto_transcription_enabled:
        sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=90)
        logger.info("\n\n## 7. 自动转录最终视频字幕")
        auto_subtitle_path = _transcribe_final_video(task_id, merge_output_video_path, params)
        sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=95)
        logger.info(f"\n\n## 8. 压入自动转录字幕 -> {output_video_path}")
        _merge_auto_transcribed_subtitles(
            source_video_path=merge_output_video_path,
            output_video_path=output_video_path,
            subtitle_path=auto_subtitle_path,
            params=params,
        )

    final_video_paths.append(output_video_path)
    combined_video_paths.append(combined_video_path)

    logger.success(f"任务 {task_id} 已完成, 生成 {len(final_video_paths)} 个视频.")

    kwargs = {
        "videos": final_video_paths,
        "combined_videos": combined_video_paths
    }
    if auto_subtitle_path:
        kwargs["subtitles"] = [auto_subtitle_path]
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
    _update_video_generation_task(
        task_id,
        progress=0,
        message="正在初始化视频生成任务",
        step_current=0,
    )

    """
    1. 加载剪辑脚本
    """
    logger.info("\n\n## 1. 加载视频脚本")
    _update_video_generation_task(
        task_id,
        progress=5,
        message="正在加载剪辑脚本",
        step_current=1,
    )
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
    _update_video_generation_task(
        task_id,
        progress=10,
        message="正在生成 TTS 配音",
        step_current=2,
    )
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

    _update_video_generation_task(
        task_id,
        progress=20,
        message="TTS 配音生成完成",
        step_current=2,
    )

    """
    3. 统一视频裁剪 - 基于OST类型的差异化裁剪策略
    """
    logger.info("\n\n## 3. 统一视频裁剪（基于OST类型）")
    _update_video_generation_task(
        task_id,
        progress=30,
        message="正在按脚本裁剪视频片段",
        step_current=3,
    )

    # 使用新的统一裁剪策略
    video_clip_result = clip_video.clip_video_unified(
        video_origin_path=params.video_origin_path,
        video_origin_paths=getattr(params, "video_origin_paths", []),
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

    _update_video_generation_task(
        task_id,
        progress=60,
        message="视频片段裁剪完成",
        step_current=3,
    )

    """
    4. 合并音频和字幕
    """
    logger.info("\n\n## 4. 合并音频和字幕")
    _update_video_generation_task(
        task_id,
        progress=65,
        message="正在合并配音和字幕",
        step_current=4,
    )
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

            # 优先基于脚本文案和成片时间线生成字幕，失败时回退到TTS字幕合并
            merged_subtitle_path = ""
            if getattr(params, "subtitle_enabled", True):
                try:
                    merged_subtitle_path = _create_programmatic_subtitle_file(
                        task_id,
                        new_script_list,
                        params,
                    )
                except Exception as e:
                    logger.warning(f"程序化字幕生成失败，将尝试合并TTS字幕: {e}")

            if not merged_subtitle_path and getattr(params, "subtitle_enabled", True):
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
        if getattr(params, "subtitle_enabled", True):
            try:
                merged_subtitle_path = _create_programmatic_subtitle_file(
                    task_id,
                    new_script_list,
                    params,
                )
            except Exception as e:
                logger.warning(f"程序化字幕生成失败: {e}")
    _update_video_generation_task(
        task_id,
        progress=70,
        message="配音和字幕合并完成",
        step_current=4,
    )

    """
    5. 合并视频
    """
    final_video_paths = []
    combined_video_paths = []

    combined_video_path = path.join(utils.task_dir(task_id), f"merger.mp4")
    logger.info(f"\n\n## 5. 合并视频: => {combined_video_path}")
    _update_video_generation_task(
        task_id,
        progress=75,
        message="正在合并视频片段",
        step_current=5,
    )

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
    _update_video_generation_task(
        task_id,
        progress=80,
        message="视频片段合并完成",
        step_current=5,
    )

    """
    6. 合并字幕/BGM/配音/视频
    """
    output_video_path = path.join(utils.task_dir(task_id), f"combined.mp4")
    auto_transcription_enabled = _is_auto_transcription_enabled(params) and not bool(merged_subtitle_path)
    if _is_auto_transcription_enabled(params) and merged_subtitle_path:
        logger.info("已生成字幕文件，跳过最终视频自动转录")
    merge_output_video_path = (
        path.join(utils.task_dir(task_id), "combined_without_auto_subtitles.mp4")
        if auto_transcription_enabled
        else output_video_path
    )
    logger.info(f"\n\n## 6. 最后一步: 合并字幕/BGM/配音/视频 -> {merge_output_video_path}")
    _update_video_generation_task(
        task_id,
        progress=85,
        message="正在合成最终视频",
        step_current=6,
        ffmpeg_progress=0,
    )

    # 可选功能，默认关闭：混入 Sonilo AI 音效（失败时沿用原视频）
    combined_video_path = _apply_sonilo_sfx(task_id, params, combined_video_path)

    bgm_path = _resolve_bgm_path(task_id, params, combined_video_path)

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
        'subtitle_enabled': params.subtitle_enabled and not auto_transcription_enabled,
        'subtitle_font': params.font_name,
        'subtitle_font_size': params.font_size,
        'subtitle_color': params.text_fore_color,
        'subtitle_bg_color': None,
        'subtitle_position': params.subtitle_position,
        'custom_position': params.custom_position,
        'threads': params.n_threads,
        **_build_subtitle_mask_options(params, enabled=not auto_transcription_enabled),
    }
    final_merge_progress_start = 85
    final_merge_progress_end = 89 if auto_transcription_enabled else 99

    def update_final_merge_progress(ffmpeg_progress: float):
        progress_span = final_merge_progress_end - final_merge_progress_start
        overall_progress = final_merge_progress_start + int(
            round((max(0.0, min(100.0, float(ffmpeg_progress))) / 100) * progress_span)
        )
        _update_video_generation_task(
            task_id,
            progress=overall_progress,
            message="正在合成最终视频",
            step_current=6,
            ffmpeg_progress=ffmpeg_progress,
        )

    generate_video.merge_materials(
        video_path=combined_video_path,
        audio_path=merged_audio_path,
        subtitle_path=merged_subtitle_path,
        bgm_path=bgm_path,
        output_path=merge_output_video_path,
        options=options,
        progress_callback=update_final_merge_progress,
    )

    auto_subtitle_path = ""
    if auto_transcription_enabled:
        _update_video_generation_task(
            task_id,
            progress=90,
            message="正在自动转录最终视频",
            step_current=6,
        )
        logger.info("\n\n## 7. 自动转录最终视频字幕")
        auto_subtitle_path = _transcribe_final_video(task_id, merge_output_video_path, params)
        _update_video_generation_task(
            task_id,
            progress=95,
            message="正在压入自动转录字幕",
            step_current=6,
        )
        logger.info(f"\n\n## 8. 压入自动转录字幕 -> {output_video_path}")
        _merge_auto_transcribed_subtitles(
            source_video_path=merge_output_video_path,
            output_video_path=output_video_path,
            subtitle_path=auto_subtitle_path,
            params=params,
        )

    final_video_paths.append(output_video_path)
    combined_video_paths.append(combined_video_path)

    logger.success(f"统一处理任务 {task_id} 已完成, 生成 {len(final_video_paths)} 个视频.")

    kwargs = {
        "videos": final_video_paths,
        "combined_videos": combined_video_paths
    }
    if auto_subtitle_path:
        kwargs["subtitles"] = [auto_subtitle_path]
    _update_video_generation_task(
        task_id,
        progress=100,
        message="视频生成完成",
        step_current=VIDEO_GENERATION_TOTAL_STEPS,
        state=const.TASK_STATE_COMPLETE,
        **kwargs
    )
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
