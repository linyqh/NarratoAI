import re
import os
import glob
import random
from typing import List
from typing import Union
import traceback

from loguru import logger
from moviepy.editor import *
from moviepy.video.tools.subtitles import SubtitlesClip
from PIL import ImageFont
from contextlib import contextmanager

from app.models import const
from app.models.schema import MaterialInfo, VideoAspect, VideoConcatMode, VideoParams, VideoClipParams
from app.utils import utils


def get_bgm_file(bgm_type: str = "random", bgm_file: str = ""):
    if not bgm_type:
        return ""

    if bgm_file and os.path.exists(bgm_file):
        return bgm_file

    if bgm_type == "random":
        song_dir = utils.song_dir()

        # 检查目录是否存在
        if not os.path.exists(song_dir):
            logger.warning(f"背景音乐目录不存在: {song_dir}")
            return ""

        # 支持 mp3 和 flac 格式
        mp3_files = glob.glob(os.path.join(song_dir, "*.mp3"))
        flac_files = glob.glob(os.path.join(song_dir, "*.flac"))
        files = mp3_files + flac_files

        # 检查是否找到音乐文件
        if not files:
            logger.warning(f"在目录 {song_dir} 中没有找到 MP3 或 FLAC 文件")
            return ""

        return random.choice(files)

    return ""


def combine_videos(
    combined_video_path: str,
    video_paths: List[str],
    audio_file: str,
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_concat_mode: VideoConcatMode = VideoConcatMode.random,
    max_clip_duration: int = 5,
    threads: int = 2,
) -> str:
    audio_clip = AudioFileClip(audio_file)
    audio_duration = audio_clip.duration
    logger.info(f"max duration of audio: {audio_duration} seconds")
    # Required duration of each clip
    req_dur = audio_duration / len(video_paths)
    req_dur = max_clip_duration
    logger.info(f"each clip will be maximum {req_dur} seconds long")
    output_dir = os.path.dirname(combined_video_path)

    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()

    clips = []
    video_duration = 0

    raw_clips = []
    for video_path in video_paths:
        clip = VideoFileClip(video_path).without_audio()
        clip_duration = clip.duration
        start_time = 0

        while start_time < clip_duration:
            end_time = min(start_time + max_clip_duration, clip_duration)
            split_clip = clip.subclip(start_time, end_time)
            raw_clips.append(split_clip)
            # logger.info(f"splitting from {start_time:.2f} to {end_time:.2f}, clip duration {clip_duration:.2f}, split_clip duration {split_clip.duration:.2f}")
            start_time = end_time
            if video_concat_mode.value == VideoConcatMode.sequential.value:
                break

    # random video_paths order
    if video_concat_mode.value == VideoConcatMode.random.value:
        random.shuffle(raw_clips)

    # Add downloaded clips over and over until the duration of the audio (max_duration) has been reached
    while video_duration < audio_duration:
        for clip in raw_clips:
            # Check if clip is longer than the remaining audio
            if (audio_duration - video_duration) < clip.duration:
                clip = clip.subclip(0, (audio_duration - video_duration))
            # Only shorten clips if the calculated clip length (req_dur) is shorter than the actual clip to prevent still image
            elif req_dur < clip.duration:
                clip = clip.subclip(0, req_dur)
            clip = clip.set_fps(30)

            # Not all videos are same size, so we need to resize them
            clip_w, clip_h = clip.size
            if clip_w != video_width or clip_h != video_height:
                clip_ratio = clip.w / clip.h
                video_ratio = video_width / video_height

                if clip_ratio == video_ratio:
                    # 等比例缩放
                    clip = clip.resize((video_width, video_height))
                else:
                    # 等比缩放视频
                    if clip_ratio > video_ratio:
                        # 按照目标宽度等比缩放
                        scale_factor = video_width / clip_w
                    else:
                        # 按照目标高度等比缩放
                        scale_factor = video_height / clip_h

                    new_width = int(clip_w * scale_factor)
                    new_height = int(clip_h * scale_factor)
                    clip_resized = clip.resize(newsize=(new_width, new_height))

                    background = ColorClip(
                        size=(video_width, video_height), color=(0, 0, 0)
                    )
                    clip = CompositeVideoClip(
                        [
                            background.set_duration(clip.duration),
                            clip_resized.set_position("center"),
                        ]
                    )

                logger.info(
                    f"resizing video to {video_width} x {video_height}, clip size: {clip_w} x {clip_h}"
                )

            if clip.duration > max_clip_duration:
                clip = clip.subclip(0, max_clip_duration)

            clips.append(clip)
            video_duration += clip.duration

    video_clip = concatenate_videoclips(clips)
    video_clip = video_clip.set_fps(30)
    logger.info("writing")
    # https://github.com/harry0703/NarratoAI/issues/111#issuecomment-2032354030
    video_clip.write_videofile(
        filename=combined_video_path,
        threads=threads,
        logger=None,
        temp_audiofile_path=output_dir,
        audio_codec="aac",
        fps=30,
    )
    video_clip.close()
    logger.success("completed")
    return combined_video_path


def wrap_text(text, max_width, font, fontsize=60):
    # 创建字体对象
    font = ImageFont.truetype(font, fontsize)

    def get_text_size(inner_text):
        inner_text = inner_text.strip()
        left, top, right, bottom = font.getbbox(inner_text)
        return right - left, bottom - top

    width, height = get_text_size(text)
    if width <= max_width:
        return text, height

    logger.debug(f"换行文本, 最大宽度: {max_width}, 文本宽度: {width}, 本: {text}")

    processed = True

    _wrapped_lines_ = []
    words = text.split(" ")
    _txt_ = ""
    for word in words:
        _before = _txt_
        _txt_ += f"{word} "
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            if _txt_.strip() == word.strip():
                processed = False
                break
            _wrapped_lines_.append(_before)
            _txt_ = f"{word} "
    _wrapped_lines_.append(_txt_)
    if processed:
        _wrapped_lines_ = [line.strip() for line in _wrapped_lines_]
        result = "\n".join(_wrapped_lines_).strip()
        height = len(_wrapped_lines_) * height
        # logger.warning(f"wrapped text: {result}")
        return result, height

    _wrapped_lines_ = []
    chars = list(text)
    _txt_ = ""
    for word in chars:
        _txt_ += word
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            _wrapped_lines_.append(_txt_)
            _txt_ = ""
    _wrapped_lines_.append(_txt_)
    result = "\n".join(_wrapped_lines_).strip()
    height = len(_wrapped_lines_) * height
    logger.debug(f"换行文本: {result}")
    return result, height


@contextmanager
def manage_clip(clip):
    try:
        yield clip
    finally:
        clip.close()
        del clip


def generate_video_v2(
    video_path: str,
    audio_path: str,
    subtitle_path: str,
    output_file: str,
    params: VideoClipParams,
    list_script: list = None
):
    """
    生成最终视频，处理音频和字幕

    Args:
        video_path: 视频文件路径
        audio_path: 音频文件路径
        subtitle_path: 字幕文件路径
        output_file: 输出文件路径
        params: 视频参数
        list_script: 视频脚本列表，包含OST设置
    """
    try:
        video_clip = VideoFileClip(video_path)
        
        # 处理音频
        if audio_path and os.path.exists(audio_path):
            audio_clip = AudioFileClip(audio_path)
            
            if list_script:
                # 根据OST设置处理音频
                # OST=0: 只使用TTS音频
                # OST=1: 只使用视频原声
                # OST=2: 混合TTS音频和视频原声
                original_audio = video_clip.audio
                
                # 设置音频音量
                tts_volume = params.tts_volume if hasattr(params, 'tts_volume') else 1.0
                video_volume = params.video_volume if hasattr(params, 'video_volume') else 0.1
                
                # 创建最终音频
                if original_audio:
                    # 有些片段需要原声，有些需要TTS
                    final_audio = CompositeAudioClip([
                        audio_clip.volumex(tts_volume),  # TTS音频
                        original_audio.volumex(video_volume)  # 原声音频
                    ])
                else:
                    final_audio = audio_clip.volumex(tts_volume)
            else:
                # 如果没有OST设置，使用默认行为
                final_audio = audio_clip
                
            video_clip = video_clip.set_audio(final_audio)

        # 处理字幕
        if subtitle_path and os.path.exists(subtitle_path):
            # 添加字幕
            video_clip = add_subtitles(
                video_clip,
                subtitle_path,
                params.font_size,
                params.font_name,
                params.text_fore_color,
                params.subtitle_position,
                params.stroke_color,
                params.stroke_width
            )

        # 写入最终视频文件
        video_clip.write_videofile(
            output_file,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
            threads=params.n_threads
        )

    except Exception as e:
        logger.error(f"生成视频时发生错误: {str(e)}")
        raise e

    finally:
        # 清理资源
        if 'video_clip' in locals():
            video_clip.close()
        if 'audio_clip' in locals():
            audio_clip.close()
        if 'final_audio' in locals():
            final_audio.close()


def process_audio_tracks(original_audio, new_audio, params, video_duration):
    """处理所有音轨"""
    audio_tracks = []
    
    if original_audio is not None:
        audio_tracks.append(original_audio)
    
    new_audio = new_audio.volumex(params.voice_volume)
    audio_tracks.append(new_audio)
    
    # 处理背景音乐
    bgm_file = get_bgm_file(bgm_type=params.bgm_type, bgm_file=params.bgm_file)
    if bgm_file:
        try:
            bgm_clip = AudioFileClip(bgm_file).volumex(params.bgm_volume).audio_fadeout(3)
            bgm_clip = afx.audio_loop(bgm_clip, duration=video_duration)
            audio_tracks.append(bgm_clip)
        except Exception as e:
            logger.error(f"添加背景音乐失败: {str(e)}")
    
    return CompositeAudioClip(audio_tracks) if audio_tracks else new_audio


def process_subtitles(subtitle_path, video_clip, video_duration, create_text_clip):
    """处理字幕"""
    if not (subtitle_path and os.path.exists(subtitle_path)):
        return video_clip
        
    sub = SubtitlesClip(subtitles=subtitle_path, encoding="utf-8")
    text_clips = []
    
    for item in sub.subtitles:
        clip = create_text_clip(subtitle_item=item)
        
        # 时间范围��整
        start_time = max(clip.start, 0)
        if start_time >= video_duration:
            continue
            
        end_time = min(clip.end, video_duration)
        clip = clip.set_start(start_time).set_end(end_time)
        text_clips.append(clip)
    
    logger.info(f"处理了 {len(text_clips)} 段字幕")
    return CompositeVideoClip([video_clip, *text_clips])


def preprocess_video(materials: List[MaterialInfo], clip_duration=4):
    for material in materials:
        if not material.url:
            continue

        ext = utils.parse_extension(material.url)
        try:
            clip = VideoFileClip(material.url)
        except Exception:
            clip = ImageClip(material.url)

        width = clip.size[0]
        height = clip.size[1]
        if width < 480 or height < 480:
            logger.warning(f"video is too small, width: {width}, height: {height}")
            continue

        if ext in const.FILE_TYPE_IMAGES:
            logger.info(f"processing image: {material.url}")
            # 创建一个图片剪辑，并设置持续时间为3秒钟
            clip = (
                ImageClip(material.url)
                .set_duration(clip_duration)
                .set_position("center")
            )
            # 使用resize方法来添加缩放效果。这里使用了lambda函数来使得缩放效果随时间变化。
            # 假设我们想要从原始大小逐渐放大到120%的大小。
            # t代表当前时间，clip.duration为视频总时长，这里是3秒。
            # 注意：1 表示100%的大小，所以1.2表示120%的大小
            zoom_clip = clip.resize(
                lambda t: 1 + (clip_duration * 0.03) * (t / clip.duration)
            )

            # 如果需要，可以创建一个包含缩放剪辑的复合视频剪辑
            # （这在您想要在视频中添加其他元素时非常有用）
            final_clip = CompositeVideoClip([zoom_clip])

            # 输出视频
            video_file = f"{material.url}.mp4"
            final_clip.write_videofile(video_file, fps=30, logger=None)
            final_clip.close()
            del final_clip
            material.url = video_file
            logger.success(f"completed: {video_file}")
    return materials


def combine_clip_videos(combined_video_path: str,
                       video_paths: List[str],
                       video_ost_list: List[int],
                       list_script: list,
                       video_aspect: VideoAspect = VideoAspect.portrait,
                       threads: int = 2,
                       ) -> str:
    """
    合并子视频
    Args:
        combined_video_path: 合并后的存储路径
        video_paths: 子视频路径列表
        video_ost_list: 原声播放列表 (0: 不保留原声, 1: 只保留原声, 2: 保留原声并保留解说)
        list_script: 剪辑脚本
        video_aspect: 屏幕比例
        threads: 线程数

    Returns:
        str: 合并后的视频路径
    """
    # 计算总时长时需要考虑毫秒精度
    total_duration = 0.0
    for item in list_script:
        timestamp = item.get('new_timestamp', '')
        if timestamp:
            start_str, end_str = timestamp.split('-')
            start_time = utils.time_to_seconds(start_str)
            end_time = utils.time_to_seconds(end_str)
            duration = end_time - start_time
            total_duration += duration
            
    logger.info(f"音频的最大持续时间: {total_duration:.3f} s")
    
    output_dir = os.path.dirname(combined_video_path)
    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()

    clips = []
    for video_path, video_ost in zip(video_paths, video_ost_list):
        try:
            # 加载视频片段
            clip = VideoFileClip(video_path)
            
            # 根据OST设置处理音频
            if video_ost == 0:  # 不保留原声
                clip = clip.without_audio()
            elif video_ost == 1:  # 只保留原声
                # 保持原声，但可能需要调整音量
                if clip.audio:
                    clip = clip.set_audio(clip.audio.volumex(1.0))  # 可以调整音量系数
            # OST == 2 的情况会在后续处理中混合音频
                
            clip = clip.set_fps(30)

            # 处理视频尺寸
            clip_w, clip_h = clip.size
            if clip_w != video_width or clip_h != video_height:
                clip = resize_video_with_padding(
                    clip, 
                    target_width=video_width, 
                    target_height=video_height
                )
                logger.info(f"视频 {video_path} 已调整尺寸为 {video_width} x {video_height}")

            # 精确控制视频时长
            filename = os.path.basename(video_path)
            timestamp = extract_timestamp_from_filename(filename)
            if timestamp:
                start_time, end_time = timestamp
                clip_duration = end_time - start_time
                if abs(clip.duration - clip_duration) > 0.1:  # 允许0.1秒的误差
                    logger.warning(f"视频 {video_path} 时长与时间戳不匹配，进行调整")
                    clip = clip.set_duration(clip_duration)

            clips.append(clip)
            
        except Exception as e:
            logger.error(f"处理视频 {video_path} 时出错: {str(e)}")
            continue

    if not clips:
        raise ValueError("没有有效的视频片段可以合并")

    try:
        # 合并所有视频片段
        video_clip = concatenate_videoclips(clips)
        video_clip = video_clip.set_fps(30)
        
        logger.info("开始合并视频...")
        video_clip.write_videofile(
            filename=combined_video_path,
            threads=threads,
            logger=None,
            audio_codec="aac",
            fps=30,
            temp_audiofile=os.path.join(output_dir, "temp-audio.m4a")
        )
    finally:
        # 确保资源被正确释放
        video_clip.close()
        for clip in clips:
            clip.close()

    logger.success("视频合并完成")
    return combined_video_path


def extract_timestamp_from_filename(filename: str) -> tuple:
    """
    从文件名中提取时间戳，支持多种格式：
    - "vid-00_06,500-00_24,800.mp4" -> (6.5, 24.8)
    - "vid-00_00_00-020-00_00_10-400.mp4" -> (0.02, 10.4)
    """
    try:
        # 提取时间戳部分
        match = re.search(r'vid-(.+?)\.mp4$', filename)
        if not match:
            logger.warning(f"文件名格式不正确: {filename}")
            return None
            
        timestamp = match.group(1)
        
        # 处理包含毫秒的格式 (00_00_00-020-00_00_10-400)
        if timestamp.count('-') == 3:
            parts = timestamp.split('-')
            start_time = f"{parts[0]}-{parts[1]}"  # 组合开始时间和毫秒
            end_time = f"{parts[2]}-{parts[3]}"    # 组合结束时间和毫秒
            
            # 转换开始时间
            start_time_str = start_time.replace('_', ':')
            if start_time_str.count(':') == 2:  # 如果是 00:00:00-020 格式
                start_base = utils.time_to_seconds(start_time_str.split('-')[0])
                start_ms = int(start_time_str.split('-')[1]) / 1000
                start_seconds = start_base + start_ms
            else:
                start_seconds = utils.time_to_seconds(start_time_str)
            
            # 转换结束时间
            end_time_str = end_time.replace('_', ':')
            if end_time_str.count(':') == 2:  # 如果是 00:00:10-400 格式
                end_base = utils.time_to_seconds(end_time_str.split('-')[0])
                end_ms = int(end_time_str.split('-')[1]) / 1000
                end_seconds = end_base + end_ms
            else:
                end_seconds = utils.time_to_seconds(end_time_str)
                
        # 处理简单格式 (00_06-00_24)
        else:
            start_str, end_str = timestamp.split('-')
            start_seconds = utils.time_to_seconds(start_str.replace('_', ':'))
            end_seconds = utils.time_to_seconds(end_str.replace('_', ':'))
        
        logger.debug(f"从文件名 {filename} 提取时间戳: {start_seconds:.3f} - {end_seconds:.3f}")
        return start_seconds, end_seconds
        
    except Exception as e:
        logger.error(f"从文件名提取时间戳失败 {filename}: {str(e)}\n{traceback.format_exc()}")
        return None


def resize_video_with_padding(clip, target_width: int, target_height: int):
    """辅助函数：调整视频尺寸并添加黑边"""
    clip_ratio = clip.w / clip.h
    target_ratio = target_width / target_height

    if clip_ratio == target_ratio:
        return clip.resize((target_width, target_height))
    
    if clip_ratio > target_ratio:
        scale_factor = target_width / clip.w
    else:
        scale_factor = target_height / clip.h

    new_width = int(clip.w * scale_factor)
    new_height = int(clip.h * scale_factor)
    clip_resized = clip.resize(newsize=(new_width, new_height))

    background = ColorClip(
        size=(target_width, target_height), 
        color=(0, 0, 0)
    ).set_duration(clip.duration)
    
    return CompositeVideoClip([
        background,
        clip_resized.set_position("center")
    ])


def validate_params(video_path, audio_path, output_file, params):
    """验证输入参数"""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        raise FileNotFoundError(f"输出目录不存在: {output_dir}")
        
    if not hasattr(params, 'video_aspect'):
        raise ValueError("params 缺少必要参数 video_aspect")


def add_subtitles(video_clip, subtitle_path, font_size, font_name, font_color, position, shadow_color, shadow_offset):
    """
    为视频添加字幕

    Args:
        video_clip: 视频剪辑对象
        subtitle_path: 字幕文件路径
        font_size: 字体大小
        font_name: 字体名称
        font_color: 字体颜色
        position: 字幕位置 ('top', 'center', 'bottom')
        shadow_color: 阴影颜色
        shadow_offset: 阴影偏移

    Returns:
        带有字幕的视频剪辑对象
    """
    try:
        # 确保字体文件存在
        font_path = os.path.join(utils.font_dir(), font_name)
        if not os.path.exists(font_path):
            logger.error(f"字体文件不存在: {font_path}")
            # 尝试使用系统默认字体
            font_path = "Arial" if os.name == 'nt' else "/System/Library/Fonts/STHeiti Light.ttc"
            logger.info(f"使用默认字体: {font_path}")

        # 设置字幕位置
        if position == "top":
            pos = ("center", 50)
        elif position == "center":
            pos = "center"
        else:  # bottom
            pos = ("center", -50)

        def subtitle_generator(txt):
            return TextClip(
                txt, 
                fontsize=font_size,
                font=font_path,
                color=font_color,
                stroke_color=shadow_color,
                stroke_width=shadow_offset,
                method='caption',  # 使用 caption 方法可能更稳定
                size=(video_clip.w * 0.9, None)  # 限制字幕宽度
            )

        subtitles = SubtitlesClip(
            subtitle_path,
            subtitle_generator
        )
        
        # 添加字幕到视频
        video_with_subtitles = CompositeVideoClip([
            video_clip,
            subtitles.set_position(pos)
        ])
        
        return video_with_subtitles

    except Exception as e:
        logger.error(f"添加字幕时出错: {str(e)}\n{traceback.format_exc()}")
        # 如果添加字幕失败，返回原始视频
        return video_clip


if __name__ == "__main__":
    # combined_video_path = "../../storage/tasks/12312312/com123.mp4"
    #
    # video_paths = ['../../storage/cache_videos/vid-00_00-00_03.mp4',
    #                '../../storage/cache_videos/vid-00_03-00_07.mp4',
    #                '../../storage/cache_videos/vid-00_12-00_17.mp4',
    #                '../../storage/cache_videos/vid-00_26-00_31.mp4']
    # video_ost_list = [False, True, False, True]
    # list_script = [
    #     {
    #         "picture": "夜晚，一个小孩在树林里奔跑，后面有人拿着火把在追赶",
    #         "timestamp": "00:00-00:03",
    #         "narration": "夜���风高的树林，一个小孩在拼命奔跑，后面的人穷追不舍！",
    #         "OST": False,
    #         "new_timestamp": "00:00-00:03"
    #     },
    #     {
    #         "picture": "追赶的人命令抓住小孩",
    #         "timestamp": "00:03-00:07",
    #         "narration": "原声播放1",
    #         "OST": True,
    #         "new_timestamp": "00:03-00:07"
    #     },
    #     {
    #         "picture": "小孩躲在草丛里，黑衣人用脚踢了踢他",
    #         "timestamp": "00:12-00:17",
    #         "narration": "小孩脱下外套，跑进树林, 一路奔跑，直到第二天清晨",
    #         "OST": False,
    #         "new_timestamp": "00:07-00:12"
    #     },
    #     {
    #         "picture": "小孩跑到车前，慌慌张张地对女人说有人要杀他",
    #         "timestamp": "00:26-00:31",
    #         "narration": "原声播放2",
    #         "OST": True,
    #         "new_timestamp": "00:12-00:17"
    #     }
    # ]
    # combine_clip_videos(combined_video_path=combined_video_path, video_paths=video_paths, video_ost_list=video_ost_list, list_script=list_script)

    # cfg = VideoClipParams()
    # cfg.video_aspect = VideoAspect.portrait
    # cfg.font_name = "STHeitiMedium.ttc"
    # cfg.font_size = 60
    # cfg.stroke_color = "#000000"
    # cfg.stroke_width = 1.5
    # cfg.text_fore_color = "#FFFFFF"
    # cfg.text_background_color = "transparent"
    # cfg.bgm_type = "random"
    # cfg.bgm_file = ""
    # cfg.bgm_volume = 1.0
    # cfg.subtitle_enabled = True
    # cfg.subtitle_position = "bottom"
    # cfg.n_threads = 2
    # cfg.paragraph_number = 1
    #
    # cfg.voice_volume = 1.0

    # generate_video(video_path=video_file,
    #                audio_path=audio_file,
    #                subtitle_path=subtitle_file,
    #                output_file=output_file,
    #                params=cfg
    #                )
    #
    # video_path = "../../storage/tasks/7f5ae494-abce-43cf-8f4f-4be43320eafa/combined-1.mp4"
    #
    # audio_path = "../../storage/tasks/7f5ae494-abce-43cf-8f4f-4be43320eafa/audio_00-00-00-07.mp3"
    #
    # subtitle_path = "../../storage/tasks/7f5ae494-abce-43cf-8f4f-4be43320eafa\subtitle.srt"
    #
    # output_file = "../../storage/tasks/7f5ae494-abce-43cf-8f4f-4be43320eafa/final-123.mp4"
    #
    # generate_video_v2(video_path=video_path,
    #                    audio_path=audio_path,
    #                    subtitle_path=subtitle_path,
    #                    output_file=output_file,
    #                    params=cfg
    #                   )

    # 合并视频
    video_list = [
        './storage/cache_videos/vid-01_03-01_50.mp4',
        './storage/cache_videos/vid-01_55-02_29.mp4',
        './storage/cache_videos/vid-03_24-04_04.mp4',
        './storage/cache_videos/vid-04_50-05_28.mp4'
    ]

