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
from app.services import llm, material, subtitle, video, voice, audio_merger
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


def generate_final_videos(
        task_id, params, downloaded_videos, audio_file, subtitle_path
):
    final_video_paths = []
    combined_video_paths = []
    video_concat_mode = (
        params.video_concat_mode if params.video_count == 1 else VideoConcatMode.random
    )

    _progress = 50
    for i in range(params.video_count):
        index = i + 1
        combined_video_path = path.join(
            utils.task_dir(task_id), f"combined-{index}.mp4"
        )
        logger.info(f"\n\n## combining video: {index} => {combined_video_path}")
        video.combine_videos(
            combined_video_path=combined_video_path,
            video_paths=downloaded_videos,
            audio_file=audio_file,
            video_aspect=params.video_aspect,
            video_concat_mode=video_concat_mode,
            max_clip_duration=params.video_clip_duration,
            threads=params.n_threads,
        )

        _progress += 50 / params.video_count / 2
        sm.state.update_task(task_id, progress=_progress)

        final_video_path = path.join(utils.task_dir(task_id), f"final-{index}.mp4")

        logger.info(f"\n\n## generating video: {index} => {final_video_path}")
        video.generate_video(
            video_path=combined_video_path,
            audio_path=audio_file,
            subtitle_path=subtitle_path,
            output_file=final_video_path,
            params=params,
        )

        _progress += 50 / params.video_count / 2
        sm.state.update_task(task_id, progress=_progress)

        final_video_paths.append(final_video_path)
        combined_video_paths.append(combined_video_path)

    return final_video_paths, combined_video_paths


def start_subclip(task_id: str, params: VideoClipParams, subclip_path_videos: dict):
    """后台任务（自动剪辑视频进行剪辑）"""
    logger.info(f"\n\n## 开始任务: {task_id}")
    
    # 初始化 ImageMagick
    if not utils.init_imagemagick():
        logger.warning("ImageMagick 初始化失败，字幕可能无法正常显示")
    
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=5)

    # tts 角色名称
    voice_name = voice.parse_voice_name(params.voice_name)

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
                last_timestamp = list_script[-1]['new_timestamp']
                end_time = last_timestamp.split("-")[1]
                total_duration = utils.time_to_seconds(end_time)
                
        except Exception as e:
            logger.error(f"无法读取视频json脚本，请检查配置是否正确。{e}")
            raise ValueError("无法读取视频json脚本，请检查配置是否正确")
    else:
        logger.error(f"video_script_path: {video_script_path} \n\n", traceback.format_exc())
        raise ValueError("解说脚本不存在！请检查配置是否正确。")

    logger.info("\n\n## 2. 根据OST设置生成音频列表")
    # 只为OST=0或2的片段生成TTS音频
    tts_segments = [
        segment for segment in list_script 
        if segment['OST'] in [0, 2]
    ]
    logger.debug(f"tts_segments: {tts_segments}")
    if tts_segments:
        audio_files, sub_maker_list = voice.tts_multiple(
            task_id=task_id,
            list_script=tts_segments,  # 只传入需要TTS的片段
            voice_name=voice_name,
            voice_rate=params.voice_rate,
            voice_pitch=params.voice_pitch,
            force_regenerate=True
        )
        if audio_files is None:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            logger.error("TTS转换音频失败, 可能是网络不可用! 如果您在中国, 请使用VPN.")
            return
    else:
        audio_files = []
        
    logger.info(f"合并音频文件:\n{audio_files}")
    # 传入OST信息以便正确处理音频
    final_audio = audio_merger.merge_audio_files(
        task_id=task_id, 
        audio_files=audio_files, 
        total_duration=total_duration, 
        list_script=list_script  # 传入完整脚本以便处理OST
    )

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=30)

    # 只为OST=0或2的片段生成字幕
    subtitle_path = ""
    if params.subtitle_enabled:
        subtitle_path = path.join(utils.task_dir(task_id), f"subtitle.srt")
        subtitle_provider = config.app.get("subtitle_provider", "").strip().lower()
        logger.info(f"\n\n## 3. 生成字幕、提供程序是: {subtitle_provider}")
         
        subtitle.create(
            audio_file=final_audio,
            subtitle_file=subtitle_path,
        )

        subtitle_lines = subtitle.file_to_subtitles(subtitle_path)
        if not subtitle_lines:
            logger.warning(f"字幕文件无效: {subtitle_path}")
            subtitle_path = ""

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=40)

    logger.info("\n\n## 4. 裁剪视频")
    subclip_videos = [x for x in subclip_path_videos.values()]
    logger.debug(f"\n\n## 裁剪后的视频文件列表: \n{subclip_videos}")

    if not subclip_videos:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error(
            "裁剪视频失败，可能是 ImageMagick 不可用")
        return

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=50)

    final_video_paths = []
    combined_video_paths = []

    _progress = 50
    index = 1
    combined_video_path = path.join(utils.task_dir(task_id), f"combined.mp4")
    logger.info(f"\n\n## 5. 合并视频: => {combined_video_path}")

    video.combine_clip_videos(
        combined_video_path=combined_video_path,
        video_paths=subclip_videos,
        video_ost_list=video_ost,
        list_script=list_script,
        video_aspect=params.video_aspect,
        threads=params.n_threads  # 多线程
    )

    _progress += 50 / 2
    sm.state.update_task(task_id, progress=_progress)

    final_video_path = path.join(utils.task_dir(task_id), f"final-{index}.mp4")

    logger.info(f"\n\n## 6. 最后合成: {index} => {final_video_path}")
    # 传入OST信息以便正确处理音频和视频
    video.generate_video_v2(
        video_path=combined_video_path,
        audio_path=final_audio,
        subtitle_path=subtitle_path,
        output_file=final_video_path,
        params=params,
        list_script=list_script  # 传入完整脚本以便处理OST
    )

    _progress += 50 / 2
    sm.state.update_task(task_id, progress=_progress)

    final_video_paths.append(final_video_path)
    combined_video_paths.append(combined_video_path)

    logger.success(f"任务 {task_id} 已完成, 生成 {len(final_video_paths)} 个视频.")

    kwargs = {
        "videos": final_video_paths,
        "combined_videos": combined_video_paths
    }
    sm.state.update_task(task_id, state=const.TASK_STATE_COMPLETE, progress=100, **kwargs)
    return kwargs


if __name__ == "__main__":
    # task_id = "test123"
    # subclip_path_videos = {'00:41-01:58': 'E:\\projects\\NarratoAI\\storage\\cache_videos/vid-00_41-01_58.mp4',
    #                        '00:06-00:15': 'E:\\projects\\NarratoAI\\storage\\cache_videos/vid-00_06-00_15.mp4',
    #                        '01:10-01:17': 'E:\\projects\\NarratoAI\\storage\\cache_videos/vid-01_10-01_17.mp4',
    #                        '00:47-01:03': 'E:\\projects\\NarratoAI\\storage\\cache_videos/vid-00_47-01_03.mp4',
    #                        '01:03-01:10': 'E:\\projects\\NarratoAI\\storage\\cache_videos/vid-01_03-01_10.mp4',
    #                        '02:40-03:08': 'E:\\projects\\NarratoAI\\storage\\cache_videos/vid-02_40-03_08.mp4',
    #                        '03:02-03:20': 'E:\\projects\\NarratoAI\\storage\\cache_videos/vid-03_02-03_20.mp4',
    #                        '03:18-03:20': 'E:\\projects\\NarratoAI\\storage\\cache_videos/vid-03_18-03_20.mp4'}
    #
    # params = VideoClipParams(
    #     video_clip_json_path="E:\\projects\\NarratoAI\\resource/scripts/test003.json",
    #     video_origin_path="E:\\projects\\NarratoAI\\resource/videos/1.mp4",
    # )
    # start_subclip(task_id, params, subclip_path_videos=subclip_path_videos)

    task_id = "test456"
    subclip_path_videos = {'01:10-01:17': './storage/cache_videos/vid-01_10-01_17.mp4',
                           '01:58-02:04': './storage/cache_videos/vid-01_58-02_04.mp4',
                           '02:25-02:31': './storage/cache_videos/vid-02_25-02_31.mp4',
                           '01:28-01:33': './storage/cache_videos/vid-01_28-01_33.mp4',
                           '03:14-03:18': './storage/cache_videos/vid-03_14-03_18.mp4',
                           '00:24-00:28': './storage/cache_videos/vid-00_24-00_28.mp4',
                           '03:02-03:08': './storage/cache_videos/vid-03_02-03_08.mp4',
                           '00:41-00:44': './storage/cache_videos/vid-00_41-00_44.mp4',
                           '02:12-02:25': './storage/cache_videos/vid-02_12-02_25.mp4'}

    params = VideoClipParams(
        video_clip_json_path="/Users/apple/Desktop/home/NarratoAI/resource/scripts/test004.json",
        video_origin_path="/Users/apple/Desktop/home/NarratoAI/resource/videos/1.mp4",
    )
    start_subclip(task_id, params, subclip_path_videos=subclip_path_videos)
