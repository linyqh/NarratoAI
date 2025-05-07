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
from app.services import (llm, material, subtitle, video, voice, audio_merger,
                          subtitle_merger, clip_video, merger_video, update_script, generate_video)
from app.services import state as sm
from app.utils import utils


# def generate_script(task_id, params):
#     logger.info("\n\n## generating video script")
#     video_script = params.video_script.strip()
#     if not video_script:
#         video_script = llm.generate_script(
#             video_subject=params.video_subject,
#             language=params.video_language,
#             paragraph_number=params.paragraph_number,
#         )
#     else:
#         logger.debug(f"video script: \n{video_script}")

#     if not video_script:
#         sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
#         logger.error("failed to generate video script.")
#         return None

#     return video_script


# def generate_terms(task_id, params, video_script):
#     logger.info("\n\n## generating video terms")
#     video_terms = params.video_terms
#     if not video_terms:
#         video_terms = llm.generate_terms(
#             video_subject=params.video_subject, video_script=video_script, amount=5
#         )
#     else:
#         if isinstance(video_terms, str):
#             video_terms = [term.strip() for term in re.split(r"[,，]", video_terms)]
#         elif isinstance(video_terms, list):
#             video_terms = [term.strip() for term in video_terms]
#         else:
#             raise ValueError("video_terms must be a string or a list of strings.")

#         logger.debug(f"video terms: {utils.to_json(video_terms)}")

#     if not video_terms:
#         sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
#         logger.error("failed to generate video terms.")
#         return None

#     return video_terms


# def save_script_data(task_id, video_script, video_terms, params):
#     script_file = path.join(utils.task_dir(task_id), "script.json")
#     script_data = {
#         "script": video_script,
#         "search_terms": video_terms,
#         "params": params,
#     }

#     with open(script_file, "w", encoding="utf-8") as f:
#         f.write(utils.to_json(script_data))


# def generate_audio(task_id, params, video_script):
#     logger.info("\n\n## generating audio")
#     audio_file = path.join(utils.task_dir(task_id), "audio.mp3")
#     sub_maker = voice.tts(
#         text=video_script,
#         voice_name=voice.parse_voice_name(params.voice_name),
#         voice_rate=params.voice_rate,
#         voice_file=audio_file,
#     )
#     if sub_maker is None:
#         sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
#         logger.error(
#             """failed to generate audio:
# 1. check if the language of the voice matches the language of the video script.
# 2. check if the network is available. If you are in China, it is recommended to use a VPN and enable the global traffic mode.
#         """.strip()
#         )
#         return None, None, None

#     audio_duration = math.ceil(voice.get_audio_duration(sub_maker))
#     return audio_file, audio_duration, sub_maker


# def generate_subtitle(task_id, params, video_script, sub_maker, audio_file):
#     if not params.subtitle_enabled:
#         return ""

#     subtitle_path = path.join(utils.task_dir(task_id), "subtitle111.srt")
#     subtitle_provider = config.app.get("subtitle_provider", "").strip().lower()
#     logger.info(f"\n\n## generating subtitle, provider: {subtitle_provider}")

#     subtitle_fallback = False
#     if subtitle_provider == "edge":
#         voice.create_subtitle(
#             text=video_script, sub_maker=sub_maker, subtitle_file=subtitle_path
#         )
#         if not os.path.exists(subtitle_path):
#             subtitle_fallback = True
#             logger.warning("subtitle file not found, fallback to whisper")

#     if subtitle_provider == "whisper" or subtitle_fallback:
#         subtitle.create(audio_file=audio_file, subtitle_file=subtitle_path)
#         logger.info("\n\n## correcting subtitle")
#         subtitle.correct(subtitle_file=subtitle_path, video_script=video_script)

#     subtitle_lines = subtitle.file_to_subtitles(subtitle_path)
#     if not subtitle_lines:
#         logger.warning(f"subtitle file is invalid: {subtitle_path}")
#         return ""

#     return subtitle_path


# def get_video_materials(task_id, params, video_terms, audio_duration):
#     if params.video_source == "local":
#         logger.info("\n\n## preprocess local materials")
#         materials = video.preprocess_video(
#             materials=params.video_materials, clip_duration=params.video_clip_duration
#         )
#         if not materials:
#             sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
#             logger.error(
#                 "no valid materials found, please check the materials and try again."
#             )
#             return None
#         return [material_info.url for material_info in materials]
#     else:
#         logger.info(f"\n\n## downloading videos from {params.video_source}")
#         downloaded_videos = material.download_videos(
#             task_id=task_id,
#             search_terms=video_terms,
#             source=params.video_source,
#             video_aspect=params.video_aspect,
#             video_contact_mode=params.video_concat_mode,
#             audio_duration=audio_duration * params.video_count,
#             max_clip_duration=params.video_clip_duration,
#         )
#         if not downloaded_videos:
#             sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
#             logger.error(
#                 "failed to download videos, maybe the network is not available. if you are in China, please use a VPN."
#             )
#             return None
#         return downloaded_videos


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
    3. 裁剪视频 - 将超出音频长度的视频进行裁剪
    """
    logger.info("\n\n## 3. 裁剪视频")
    video_clip_result = clip_video.clip_video(params.video_origin_path, tts_results)
    # 更新 list_script 中的时间戳
    tts_clip_result = {tts_result['_id']: tts_result['audio_file'] for tts_result in tts_results}
    subclip_clip_result = {
        tts_result['_id']: tts_result['subtitle_file'] for tts_result in tts_results
    }
    new_script_list = update_script.update_script_timestamps(list_script, video_clip_result, tts_clip_result, subclip_clip_result)

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=60)

    """
    4. 合并音频和字幕
    """
    logger.info("\n\n## 4. 合并音频和字幕")
    total_duration = sum([script["duration"] for script in new_script_list])
    if tts_results:
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
            logger.info(f"字幕文件合并成功->{merged_subtitle_path}")
        except Exception as e:
            logger.error(f"合并音频文件失败: {str(e)}")
            merged_audio_path = ""
            merged_subtitle_path = ""
    else:
        logger.error("TTS转换音频失败, 可能是网络不可用! 如果您在中国, 请使用VPN.")
        return

    """
    5. 合并视频
    """
    final_video_paths = []
    combined_video_paths = []

    combined_video_path = path.join(utils.task_dir(task_id), f"merger.mp4")
    logger.info(f"\n\n## 5. 合并视频: => {combined_video_path}")
    # 如果 new_script_list 中没有 video，则使用 subclip_path_videos 中的视频
    video_clips = [new_script['video'] if new_script.get('video') else subclip_path_videos.get(new_script.get('_id', '')) for new_script in new_script_list]
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

    bgm_path = '/Users/apple/Desktop/home/NarratoAI/resource/songs/bgm.mp3'
    # bgm_path = params.bgm_file

    # 调用示例
    options = {
        'voice_volume': params.tts_volume,  # 配音音量
        'bgm_volume': params.bgm_volume,  # 背景音乐音量
        'original_audio_volume': params.original_volume,  # 视频原声音量，0表示不保留
        'keep_original_audio': True,  # 是否保留原声
        'subtitle_font': 'MicrosoftYaHeiNormal.ttc',  # 这里使用相对字体路径，会自动在 font_dir() 目录下查找
        'subtitle_font_size': params.font_size,
        'subtitle_color': '#FFFFFF',
        'subtitle_bg_color': None,  # 直接使用None表示透明背景
        'subtitle_position': params.subtitle_position,
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
        1: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-00-00-00-01-15.mp4',
        2: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-01-15-00-04-40.mp4',
        3: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-04-41-00-04-58.mp4',
        4: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-04-58-00-05-45.mp4',
        5: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-05-45-00-06-00.mp4',
        6: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/6e7e343c7592c7d6f9a9636b55000f23/vid-00-06-00-00-06-03.mp4',
    }

    params = VideoClipParams(
        video_clip_json_path="/Users/apple/Desktop/home/NarratoAI/resource/scripts/demo.json",
        video_origin_path="/Users/apple/Desktop/home/NarratoAI/resource/videos/qyn2-2无片头片尾.mp4",
    )
    start_subclip(task_id, params, subclip_path_videos)
