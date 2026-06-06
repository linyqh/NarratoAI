import json
import os
import subprocess
import time
from os import path
from typing import Dict
from loguru import logger

from app.config import config
from app.models import const
from app.models.schema import VideoClipParams
from app.services import voice, clip_video, update_script
from app.services.jianying_draft_builder import write_plaintext_jianying_draft
from app.services import state as sm
from app.utils import utils


def get_media_duration_ffprobe(media_file: str) -> float:
    """
    使用ffprobe获取媒体文件的精确时长（秒）
    
    Args:
        media_file: 媒体文件路径
        
    Returns:
        float: 媒体时长（秒），精确到微秒
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'csv=p=0',
            media_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
        logger.debug(f"使用ffprobe获取媒体时长: {duration:.6f}秒, 文件: {media_file}")
        return duration
    except subprocess.CalledProcessError as e:
        logger.error(f"ffprobe执行失败: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"获取媒体时长失败: {str(e)}")
        raise


def get_audio_duration_ffprobe(audio_file: str) -> float:
    return get_media_duration_ffprobe(audio_file)


def _strip_tts_voice_prefix(voice_name: str, prefix: str) -> str:
    voice_name = voice_name or ""
    if voice_name.startswith(prefix):
        return voice_name[len(prefix):]
    return voice_name


def _strip_indextts_prefix(voice_name: str) -> str:
    return _strip_tts_voice_prefix(
        config.normalize_indextts_voice_prefix(voice_name or ""),
        config.INDEXTTS_VOICE_PREFIX,
    )


def _floor_duration_to_milliseconds(duration: float) -> float:
    return int(duration * 1000) / 1000.0


def _format_seconds_for_trange(seconds: float) -> str:
    return f"{seconds:.3f}s"


def _get_cached_media_duration(media_file: str, duration_cache: Dict[str, float]) -> float:
    if media_file not in duration_cache:
        duration_cache[media_file] = _floor_duration_to_milliseconds(
            get_media_duration_ffprobe(media_file)
        )
    return duration_cache[media_file]


def _clamp_duration_to_media(
    requested_duration: float,
    media_file: str,
    duration_cache: Dict[str, float],
    media_label: str,
    source_start_time: float = 0.0,
) -> float:
    requested_duration = _floor_duration_to_milliseconds(max(requested_duration, 0.0))
    actual_duration = _get_cached_media_duration(media_file, duration_cache)
    available_duration = _floor_duration_to_milliseconds(
        max(actual_duration - max(source_start_time, 0.0), 0.0)
    )
    safe_duration = min(requested_duration, available_duration)

    logger.info(
        f"{media_label}实际时长: {actual_duration:.6f}秒, "
        f"可用时长: {available_duration:.6f}秒, 请求时长: {requested_duration:.3f}秒"
    )
    if safe_duration < requested_duration:
        logger.warning(
            f"{media_label}短于脚本时长，已将剪映片段时长从 "
            f"{requested_duration:.3f}秒 调整为 {safe_duration:.3f}秒"
        )

    return safe_duration


def _normalize_indextts_reference_audio(params: VideoClipParams) -> None:
    """Ensure IndexTTS engines use the configured reference audio instead of a stale UI voice."""
    params.tts_engine = config.normalize_tts_engine_name(params.tts_engine)
    if params.tts_engine == config.INDEXTTS_ENGINE:
        tts_config = config.indextts
        voice_prefix = config.INDEXTTS_VOICE_PREFIX
        display_name = "IndexTTS-1.5"
    elif params.tts_engine == config.INDEXTTS2_ENGINE:
        tts_config = config.indextts2
        voice_prefix = config.INDEXTTS2_VOICE_PREFIX
        display_name = "IndexTTS-2"
    else:
        return

    candidate = _strip_tts_voice_prefix(getattr(params, "voice_name", "") or "", voice_prefix)
    if candidate and os.path.isfile(candidate):
        params.voice_name = f"{voice_prefix}{candidate}"
        logger.info(f"{display_name} 使用参考音频: {candidate}")
        return

    configured_ref = _strip_tts_voice_prefix(tts_config.get("reference_audio", "") or "", voice_prefix)
    if configured_ref and os.path.isfile(configured_ref):
        params.voice_name = f"{voice_prefix}{configured_ref}"
        logger.info(f"{display_name} 使用配置中的参考音频: {configured_ref}")
        return

    raise ValueError(f"{display_name} 参考音频不存在，请在音频设置中上传或选择有效的参考音频")


def start_export_jianying_draft(task_id: str, params: VideoClipParams):
    """
    导出到剪映草稿的后台任务
    
    Args:
        task_id: 任务ID
        params: 视频参数
    """
    logger.info(f"\n\n## 开始导出到剪映草稿任务: {task_id}")
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
    _normalize_indextts_reference_audio(params)
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
    video_clip_result = clip_video.clip_video_unified(
        video_origin_path=params.video_origin_path,
        script_list=list_script,
        tts_results=tts_results
    )

    tts_clip_result = {tts_result['_id']: tts_result['audio_file'] for tts_result in tts_results}
    subclip_clip_result = {
        tts_result['_id']: tts_result['subtitle_file'] for tts_result in tts_results
    }
    new_script_list = update_script.update_script_timestamps(list_script, video_clip_result, tts_clip_result, subclip_clip_result)

    logger.info(f"统一裁剪完成，处理了 {len(video_clip_result)} 个视频片段")

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=60)

    """
    4. 导出到剪映草稿
    """
    logger.info("\n\n## 4. 导出到剪映草稿")
    
    try:
        jianying_draft_path = config.ui.get("jianying_draft_path", "")
        if not jianying_draft_path:
            raise ValueError("剪映草稿路径未配置")
        
        # 使用从参数中获取的草稿名称，如果为空则使用默认名称
        draft_name = getattr(params, 'draft_name', "")
        logger.debug(f"从params获取的草稿名称: '{draft_name}' (类型: {type(draft_name)})")
        if not draft_name:
            draft_name = f"NarratoAI_{int(time.time())}"
            logger.debug(f"使用默认草稿名称: '{draft_name}'")

        output_dir = utils.task_dir(task_id)

        draft_path, draft_name = write_plaintext_jianying_draft(
            jianying_draft_path=jianying_draft_path,
            draft_name=draft_name,
            new_script_list=new_script_list,
            params=params,
            output_dir=output_dir,
        )
        
        logger.success(f"成功导出到剪映草稿: {draft_name}")
        logger.info(f"草稿已保存到: {draft_path}")
        
        # 更新任务状态
        sm.state.update_task(task_id, state=const.TASK_STATE_COMPLETE, progress=100, draft_path=draft_path, draft_name=draft_name)
        
        return {"draft_path": draft_path, "draft_name": draft_name}
    except Exception as e:
        logger.error(f"导出到剪映草稿失败: {e}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        raise Exception(f"导出到剪映草稿失败: {e}")
