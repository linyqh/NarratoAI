import math
import json
import os.path
import re
import traceback
from os import path
from loguru import logger

from app.config import config
from app.models import const
from app.models.schema import VideoConcatMode, VideoParams, VideoClipParams
from app.services import llm, material, subtitle, video, voice, audio_merger, subtitle_merger, clip_video
from app.services import state as sm
from app.utils import utils


def generate_script(task_id, params):
    logger.info("\n\n## generating video script")
    video_script = params.video_script.strip()
    if not video_script:
        video_script = llm.generate_script(
            video_subject=params.video_subject,
            language=params.video_language,
            paragraph_number=params.paragraph_number,
        )
    else:
        logger.debug(f"video script: \n{video_script}")

    if not video_script:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error("failed to generate video script.")
        return None

    return video_script


def generate_terms(task_id, params, video_script):
    logger.info("\n\n## generating video terms")
    video_terms = params.video_terms
    if not video_terms:
        video_terms = llm.generate_terms(
            video_subject=params.video_subject, video_script=video_script, amount=5
        )
    else:
        if isinstance(video_terms, str):
            video_terms = [term.strip() for term in re.split(r"[,，]", video_terms)]
        elif isinstance(video_terms, list):
            video_terms = [term.strip() for term in video_terms]
        else:
            raise ValueError("video_terms must be a string or a list of strings.")

        logger.debug(f"video terms: {utils.to_json(video_terms)}")

    if not video_terms:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error("failed to generate video terms.")
        return None

    return video_terms


def save_script_data(task_id, video_script, video_terms, params):
    script_file = path.join(utils.task_dir(task_id), "script.json")
    script_data = {
        "script": video_script,
        "search_terms": video_terms,
        "params": params,
    }

    with open(script_file, "w", encoding="utf-8") as f:
        f.write(utils.to_json(script_data))


def generate_audio(task_id, params, video_script):
    logger.info("\n\n## generating audio")
    audio_file = path.join(utils.task_dir(task_id), "audio.mp3")
    sub_maker = voice.tts(
        text=video_script,
        voice_name=voice.parse_voice_name(params.voice_name),
        voice_rate=params.voice_rate,
        voice_file=audio_file,
    )
    if sub_maker is None:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error(
            """failed to generate audio:
1. check if the language of the voice matches the language of the video script.
2. check if the network is available. If you are in China, it is recommended to use a VPN and enable the global traffic mode.
        """.strip()
        )
        return None, None, None

    audio_duration = math.ceil(voice.get_audio_duration(sub_maker))
    return audio_file, audio_duration, sub_maker


def generate_subtitle(task_id, params, video_script, sub_maker, audio_file):
    if not params.subtitle_enabled:
        return ""

    subtitle_path = path.join(utils.task_dir(task_id), "subtitle111.srt")
    subtitle_provider = config.app.get("subtitle_provider", "").strip().lower()
    logger.info(f"\n\n## generating subtitle, provider: {subtitle_provider}")

    subtitle_fallback = False
    if subtitle_provider == "edge":
        voice.create_subtitle(
            text=video_script, sub_maker=sub_maker, subtitle_file=subtitle_path
        )
        if not os.path.exists(subtitle_path):
            subtitle_fallback = True
            logger.warning("subtitle file not found, fallback to whisper")

    if subtitle_provider == "whisper" or subtitle_fallback:
        subtitle.create(audio_file=audio_file, subtitle_file=subtitle_path)
        logger.info("\n\n## correcting subtitle")
        subtitle.correct(subtitle_file=subtitle_path, video_script=video_script)

    subtitle_lines = subtitle.file_to_subtitles(subtitle_path)
    if not subtitle_lines:
        logger.warning(f"subtitle file is invalid: {subtitle_path}")
        return ""

    return subtitle_path


def get_video_materials(task_id, params, video_terms, audio_duration):
    if params.video_source == "local":
        logger.info("\n\n## preprocess local materials")
        materials = video.preprocess_video(
            materials=params.video_materials, clip_duration=params.video_clip_duration
        )
        if not materials:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            logger.error(
                "no valid materials found, please check the materials and try again."
            )
            return None
        return [material_info.url for material_info in materials]
    else:
        logger.info(f"\n\n## downloading videos from {params.video_source}")
        downloaded_videos = material.download_videos(
            task_id=task_id,
            search_terms=video_terms,
            source=params.video_source,
            video_aspect=params.video_aspect,
            video_contact_mode=params.video_concat_mode,
            audio_duration=audio_duration * params.video_count,
            max_clip_duration=params.video_clip_duration,
        )
        if not downloaded_videos:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            logger.error(
                "failed to download videos, maybe the network is not available. if you are in China, please use a VPN."
            )
            return None
        return downloaded_videos


def start_subclip(task_id: str, params: VideoClipParams, subclip_path_videos: dict):
    """
    后台任务（自动剪辑视频进行剪辑）
    Args:
        task_id: 任务ID
        params: 视频参数
        subclip_path_videos: 视频片段路径
    """
    logger.info(f"\n\n## 开始任务: {task_id}")
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=0)

    # # 初始化 ImageMagick
    # if not utils.init_imagemagick():
    #     logger.warning("ImageMagick 初始化失败，字幕可能无法正常显示")

    # # tts 角色名称
    # voice_name = voice.parse_voice_name(params.voice_name)
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
                
                # 获取视频总时长(单位 s)
                last_timestamp = list_script[-1]['timestamp'].split("-")[1]
                total_duration = utils.time_to_seconds(last_timestamp)

        except Exception as e:
            logger.error(f"无法读取视频json脚本，请检查脚本格式是否正确")
            raise ValueError("无法读取视频json脚本，请检查脚本格式是否正确")
    else:
        logger.error(f"video_script_path: {video_script_path} \n\n", traceback.format_exc())
        raise ValueError("解说脚本不存在！请检查配置是否正确。")

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
        voice_name=params.voice_name,
        voice_rate=params.voice_rate,
        voice_pitch=params.voice_pitch,
        force_regenerate=True
    )
    audio_files = [
        tts_result["audio_file"] for tts_result in tts_results
    ]
    subtitle_files = [
        tts_result["subtitle_file"] for tts_result in tts_results
    ]
    if tts_results:
        logger.info(f"合并音频/字幕文件")
        try:
            # 合并音频文件
            merged_audio_path = audio_merger.merge_audio_files(
                task_id=task_id,
                audio_files=audio_files,
                total_duration=total_duration,
                list_script=list_script  # 传入完整脚本以便处理OST
            )
            logger.info(f"音频文件合并成功->{merged_audio_path}")
            # 合并字幕文件
            merged_subtitle_path = subtitle_merger.merge_subtitle_files(
                subtitle_files=subtitle_files,
            )
            logger.info(f"字幕文件合并成功->{merged_subtitle_path}")
        except Exception as e:
            logger.error(f"合并音频文件失败: {str(e)}")
            merged_audio_path = ""
            merged_subtitle_path = ""
    else:
        logger.error("TTS转换音频失败, 可能是网络不可用! 如果您在中国, 请使用VPN.")
        return
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=20)

    """
    3. (可选) 使用 whisper 生成字幕
    """
    if merged_subtitle_path is None:
        if audio_files:
            merged_subtitle_path = path.join(utils.task_dir(task_id), f"subtitle.srt")
            subtitle_provider = config.app.get("subtitle_provider", "").strip().lower()
            logger.info(f"\n\n使用 {subtitle_provider} 生成字幕")
            
            subtitle.create(
                audio_file=merged_audio_path,
                subtitle_file=merged_subtitle_path,
            )
            subtitle_lines = subtitle.file_to_subtitles(merged_subtitle_path)
            if not subtitle_lines:
                logger.warning(f"字幕文件无效: {merged_subtitle_path}")

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=40)

    """
    4. 裁剪视频 - 将超出音频长度的视频进行裁剪
    """
    logger.info("\n\n## 4. 裁剪视频")
    result = clip_video.clip_video(params.video_origin_path, tts_results)
    subclip_path_videos.update(result)
    subclip_videos = [x for x in subclip_path_videos.values()]

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=60)

    """
    5. 合并视频
    """
    final_video_paths = []
    combined_video_paths = []

    combined_video_path = path.join(utils.task_dir(task_id), f"merger.mp4")
    logger.info(f"\n\n## 5. 合并视频: => {combined_video_path}")

    video.combine_clip_videos(
        combined_video_path=combined_video_path,
        video_paths=subclip_videos,
        video_ost_list=video_ost,
        list_script=list_script,
        video_aspect=params.video_aspect,
        threads=params.n_threads  # 多线程
    )
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=80)


    """
    6. 合并字幕/BGM/配音/视频
    """
    final_video_path = path.join(utils.task_dir(task_id), f"combined.mp4")
    logger.info(f"\n\n## 6. 最后一步: 合并字幕/BGM/配音/视频 -> {final_video_path}")

    # 获取背景音乐
    bgm_path = None
    if params.bgm_type or params.bgm_file:
        try:
            bgm_path = utils.get_bgm_file(bgm_type=params.bgm_type, bgm_file=params.bgm_file)
            if bgm_path:
                logger.info(f"使用背景音乐: {bgm_path}")
        except Exception as e:
            logger.error(f"获取背景音乐失败: {str(e)}")

    # 示例：自定义字幕样式
    subtitle_style = {
        'fontsize': params.font_size,  # 字体大小
        'color': params.text_fore_color,  # 字体颜色
        'stroke_color': params.stroke_color,  # 描边颜色
        'stroke_width': params.stroke_width,  # 描边宽度, 范围0-10
        'bg_color': params.text_back_color,   # 半透明黑色背景
        'position': (params.subtitle_position, 0.2),  # 距离顶部60%的位置
        'method': 'caption'  # 渲染方法
    }

    # 示例：自定义音量配置
    volume_config = {
        'original': params.original_volume,  # 原声音量80%
        'bgm': params.bgm_volume,  # BGM音量20%
        'narration': params.tts_volume or params.voice_volume,  # 解说音量100%
    }
    font_path = utils.font_dir(params.font_name)
    video.generate_video_v3(
        video_path=combined_video_path,
        subtitle_path=merged_subtitle_path,
        bgm_path=bgm_path,
        narration_path=merged_audio_path,
        output_path=final_video_path,
        volume_config=volume_config,  # 添加音量配置
        subtitle_style=subtitle_style,
        font_path=font_path
    )

    final_video_paths.append(final_video_path)
    combined_video_paths.append(combined_video_path)

    logger.success(f"任务 {task_id} 已完成, 生成 {len(final_video_paths)} 个视频.")

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
    task_id = "qyn2-2-demo"

    # 提前裁剪是为了方便检查视频
    subclip_path_videos = {
        '00:00:00-00:01:15': '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-00-00-00-01-15.mp4',
        '00:01:15-00:04:40': '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-01-15-00-04-40.mp4',
        '00:04:41-00:04:58': '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-04-41-00-04-58.mp4',
        '00:04:58-00:05:45': '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-04-58-00-05-45.mp4',
        '00:05:45-00:06:00': '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-05-45-00-06-00.mp4',
        '00:06:00-00:06:03': '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-06-00-00-06-03.mp4',
    }

    params = VideoClipParams(
        video_clip_json_path="/Users/apple/Desktop/home/NarratoAI/resource/scripts/demo.json",
        video_origin_path="/Users/apple/Desktop/home/NarratoAI/resource/videos/qyn2-2无片头片尾.mp4",
    )
    start_subclip(task_id, params, subclip_path_videos)
