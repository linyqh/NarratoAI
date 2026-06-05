import json
import os
import subprocess
import time
from os import path
from loguru import logger

from app.config import config
from app.models import const
from app.models.schema import VideoClipParams
from app.services import voice, clip_video, update_script
from app.services import state as sm
from app.utils import utils


def get_audio_duration_ffprobe(audio_file: str) -> float:
    """
    使用ffprobe获取音频文件的精确时长（秒）
    
    Args:
        audio_file: 音频文件路径
        
    Returns:
        float: 音频时长（秒），精确到微秒
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'csv=p=0',
            audio_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
        logger.debug(f"使用ffprobe获取音频时长: {duration:.6f}秒")
        return duration
    except subprocess.CalledProcessError as e:
        logger.error(f"ffprobe执行失败: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"获取音频时长失败: {str(e)}")
        raise


def _strip_indextts2_prefix(voice_name: str) -> str:
    prefix = "indextts2:"
    if voice_name.startswith(prefix):
        return voice_name[len(prefix):]
    return voice_name


def _floor_duration_to_milliseconds(duration: float) -> float:
    return int(duration * 1000) / 1000.0


def _normalize_indextts2_reference_audio(params: VideoClipParams) -> None:
    """Ensure IndexTTS2 uses the configured reference audio instead of a stale UI voice."""
    if params.tts_engine != "indextts2":
        return

    candidate = _strip_indextts2_prefix(getattr(params, "voice_name", "") or "")
    if candidate and os.path.isfile(candidate):
        params.voice_name = f"indextts2:{candidate}"
        logger.info(f"IndexTTS2 使用参考音频: {candidate}")
        return

    configured_ref = _strip_indextts2_prefix(config.indextts2.get("reference_audio", "") or "")
    if configured_ref and os.path.isfile(configured_ref):
        params.voice_name = f"indextts2:{configured_ref}"
        logger.info(f"IndexTTS2 使用配置中的参考音频: {configured_ref}")
        return

    raise ValueError("IndexTTS2 参考音频不存在，请在音频设置中上传或选择有效的参考音频")


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
    _normalize_indextts2_reference_audio(params)
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
        import pyJianYingDraft
        from pyJianYingDraft import DraftFolder, VideoSegment, AudioSegment, trange, TrackType
        jianying_draft_path = config.ui.get("jianying_draft_path", "")
        if not jianying_draft_path:
            raise ValueError("剪映草稿路径未配置")
        
        # 创建DraftFolder实例
        draft_folder = DraftFolder(jianying_draft_path)
        
        # 使用从参数中获取的草稿名称，如果为空则使用默认名称
        draft_name = getattr(params, 'draft_name', "")
        logger.debug(f"从params获取的草稿名称: '{draft_name}' (类型: {type(draft_name)})")
        if not draft_name:
            draft_name = f"NarratoAI_{int(time.time())}"
            logger.debug(f"使用默认草稿名称: '{draft_name}'")
        
        # 创建新草稿
        script = draft_folder.create_draft(draft_name, 1920, 1080)
        
        # 添加视频轨道和音频轨道
        script.add_track(TrackType.video, '视频轨道')
        script.add_track(TrackType.audio, '音频轨道')
        
        # 处理脚本数据
        current_time = 0
        output_dir = utils.task_dir(task_id)
        
        for item in new_script_list:
            # 获取时间信息
            start_time = float(item.get('start_time', 0.0))
            duration = float(item.get('duration', 0.0))
            timestamp = item.get('timestamp', '')
            
            logger.info(f"处理片段: OST={item['OST']}, start_time={start_time}, duration={duration}, timestamp={timestamp}")
            
            # 生成音频文件路径
            audio_file = ""
            if timestamp:
                timestamp_formatted = timestamp.replace(':', '_')
                audio_file = os.path.join(
                    output_dir,
                    f"audio_{timestamp_formatted}.mp3"
                )
            
            # 检查是否有裁剪后的视频文件
            video_file = item.get('video', '')
            if video_file and not os.path.exists(video_file):
                video_file = ""
            
            # 添加视频片段
            if video_file:
                # 使用裁剪后的视频文件
                # 对于裁剪后的视频，target_timerange的第二个参数是持续时间
                video_segment = VideoSegment(
                    video_file,
                    trange(f"{current_time}s", f"{duration}s")
                )
            else:
                # 使用原始视频文件
                # source_timerange是从原始视频中截取的部分
                # target_timerange是片段在时间轴上的位置
                video_segment = VideoSegment(
                    params.video_origin_path,
                    trange(f"{current_time}s", f"{duration}s"),
                    source_timerange=trange(f"{start_time}s", f"{duration}s")
                )
            script.add_segment(video_segment, '视频轨道')
            
            # 处理音频
            if item['OST'] in [0, 2]:  # 需要TTS的片段
                if os.path.exists(audio_file):
                    # 使用ffprobe获取精确的音频时长，避免因TTS引擎差异导致时长不匹配
                    actual_audio_duration = get_audio_duration_ffprobe(audio_file)
                    actual_audio_duration = _floor_duration_to_milliseconds(actual_audio_duration)
                    logger.info(f"音频文件实际时长: {actual_audio_duration:.6f}秒, 脚本时长(视频): {duration:.3f}秒")
                    
                    # 使用音频实际时长和视频时长中的较小值，确保不超过素材时长
                    # 当TTS语速调整时，音频可能比视频长或短，取较小值可以避免超出素材
                    safe_duration = min(actual_audio_duration, duration)
                    logger.info(f"使用时长: {safe_duration:.6f}秒 (取音频和视频时长的较小值)")
                    
                    audio_segment = AudioSegment(
                        audio_file,
                        trange(f"{current_time}s", f"{safe_duration}s")
                    )
                    script.add_segment(audio_segment, '音频轨道')
                else:
                    logger.warning(f"音频文件不存在: {audio_file}")
            # OST=1的片段保留原声，不需要添加额外音频
            
            # 更新当前时间
            current_time += duration
        
        # 保存草稿
        script.save()
        
        draft_path = os.path.join(jianying_draft_path, draft_name)
        
        logger.success(f"成功导出到剪映草稿: {draft_name}")
        logger.info(f"草稿已保存到: {draft_path}")
        
        # 更新任务状态
        sm.state.update_task(task_id, state=const.TASK_STATE_COMPLETE, progress=100, draft_path=draft_path, draft_name=draft_name)
        
        return {"draft_path": draft_path, "draft_name": draft_name}
        
    except ImportError as e:
        logger.error(f"导入pyJianYingDraft失败: {e}")
        raise ImportError(f"pyJianYingDraft库导入失败: {e}\n请确保已正确安装该库")
    except Exception as e:
        logger.error(f"导出到剪映草稿失败: {e}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        raise Exception(f"导出到剪映草稿失败: {e}")
