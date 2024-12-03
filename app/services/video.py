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

    logger.debug(f"换行文本, 最大宽度: {max_width}, 文本宽度: {width}, 文本: {text}")

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
        params: Union[VideoParams, VideoClipParams],
        progress_callback=None,
):
    """
    合并所有素材
    Args:
        video_path: 视频路径
        audio_path: 单个音频文件路径
        subtitle_path: 字幕文件路径
        output_file: 输出文件路径
        params: 视频参数
        progress_callback: 进度回调函数，接收 0-100 的进度值

    Returns:

    """
    total_steps = 4
    current_step = 0

    def update_progress(step_name):
        nonlocal current_step
        current_step += 1
        if progress_callback:
            progress_callback(int(current_step * 100 / total_steps))
        logger.info(f"完成步骤: {step_name}")

    try:
        validate_params(video_path, audio_path, output_file, params)

        with manage_clip(VideoFileClip(video_path)) as video_clip:
            aspect = VideoAspect(params.video_aspect)
            video_width, video_height = aspect.to_resolution()

            logger.info(f"开始，视频尺寸: {video_width} x {video_height}")
            logger.info(f"  ① 视频: {video_path}")
            logger.info(f"  ② 音频: {audio_path}")
            logger.info(f"  ③ 字幕: {subtitle_path}")
            logger.info(f"  ④ 输出: {output_file}")

            output_dir = os.path.dirname(output_file)
            update_progress("初始化完成")

            # 字体设置
            font_path = ""
            if params.subtitle_enabled:
                if not params.font_name:
                    params.font_name = "STHeitiMedium.ttc"
                font_path = os.path.join(utils.font_dir(), params.font_name)
                if os.name == "nt":
                    font_path = font_path.replace("\\", "/")
                logger.info(f"使用字体: {font_path}")

            def create_text_clip(subtitle_item):
                phrase = subtitle_item[1]
                max_width = video_width * 0.9
                wrapped_txt, txt_height = wrap_text(
                    phrase, max_width=max_width, font=font_path, fontsize=params.font_size
                )
                _clip = TextClip(
                    wrapped_txt,
                    font=font_path,
                    fontsize=params.font_size,
                    color=params.text_fore_color,
                    bg_color=params.text_background_color,
                    stroke_color=params.stroke_color,
                    stroke_width=params.stroke_width,
                    print_cmd=False,
                )
                duration = subtitle_item[0][1] - subtitle_item[0][0]
                _clip = _clip.set_start(subtitle_item[0][0])
                _clip = _clip.set_end(subtitle_item[0][1])
                _clip = _clip.set_duration(duration)

                if params.subtitle_position == "bottom":
                    _clip = _clip.set_position(("center", video_height * 0.95 - _clip.h))
                elif params.subtitle_position == "top":
                    _clip = _clip.set_position(("center", video_height * 0.05))
                elif params.subtitle_position == "custom":
                    margin = 10
                    max_y = video_height - _clip.h - margin
                    min_y = margin
                    custom_y = (video_height - _clip.h) * (params.custom_position / 100)
                    custom_y = max(min_y, min(custom_y, max_y))
                    _clip = _clip.set_position(("center", custom_y))
                else:  # center
                    _clip = _clip.set_position(("center", "center"))
                return _clip

            update_progress("字体设置完成")

            # 处理音频
            original_audio = video_clip.audio
            video_duration = video_clip.duration
            new_audio = AudioFileClip(audio_path)
            final_audio = process_audio_tracks(original_audio, new_audio, params, video_duration)
            update_progress("音频处理完成")

            # 处理字幕
            if subtitle_path and os.path.exists(subtitle_path):
                video_clip = process_subtitles(subtitle_path, video_clip, video_duration, create_text_clip)
            update_progress("字幕处理完成")

            # 合并音频和导出
            video_clip = video_clip.set_audio(final_audio)
            video_clip.write_videofile(
                output_file,
                audio_codec="aac",
                temp_audiofile=os.path.join(output_dir, "temp-audio.m4a"),
                threads=params.n_threads,
                logger=None,
                fps=30,
            )

    except FileNotFoundError as e:
        logger.error(f"文件不存在: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"视频生成失败: {str(e)}")
        raise
    finally:
        logger.success("完成")


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

        # 时间范围调整
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
    from app.utils.utils import calculate_total_duration
    audio_duration = calculate_total_duration(list_script)
    logger.info(f"音频的最大持续时间: {audio_duration} s")

    output_dir = os.path.dirname(combined_video_path)
    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()

    clips = []
    for video_path, video_ost in zip(video_paths, video_ost_list):
        try:
            clip = VideoFileClip(video_path)

            if video_ost == 0:  # 不保留原声
                clip = clip.without_audio()
            # video_ost 为 1 或 2 时都保留原声，不需要特殊处理

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

            clips.append(clip)

        except Exception as e:
            logger.error(f"处理视频 {video_path} 时出错: {str(e)}")
            continue

    if not clips:
        raise ValueError("没有有效的视频片段可以合并")

    try:
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
        # 确保资源被正确���放
        video_clip.close()
        for clip in clips:
            clip.close()

    logger.success("视频合并完成")
    return combined_video_path


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


if __name__ == "__main__":
    combined_video_path = "../../storage/tasks/123/combined.mp4"

    video_paths = ['../../storage/temp/clip_video/0b545e689a182a91af2163c7c0ca7ca3/vid-00-00-10_000-00-00-43_039.mp4',
                   '../../storage/temp/clip_video/0b545e689a182a91af2163c7c0ca7ca3/vid-00-00-45_439-00-01-01_600.mp4',
                   '../../storage/temp/clip_video/0b545e689a182a91af2163c7c0ca7ca3/vid-00-01-07_920-00-01-25_719.mp4',
                   '../../storage/temp/clip_video/0b545e689a182a91af2163c7c0ca7ca3/vid-00-01-36_959-00-01-53_719.mp4']
    video_ost_list = [2, 2, 2, 2]
    list_script = [
        {
            "timestamp": "00:10-00:43",
            "picture": "好的，以下是视频画面的客观描述：\n\n视频显示一个男人在一个树木繁茂的地区，靠近一个泥土斜坡他穿着一件深色T恤、卡其色长裤和登山靴。他背着一个军绿色背包，里面似乎装有头和其他工具。\n\n第一个镜头显示该男子从远处走近斜坡，背对着镜头。下一个镜头特写显示了的背包，一个镐头从背包中伸出来。下一个镜头显示该男子用镐头敲打斜坡。下一个镜头是该男子脚上的特写镜头，他穿着登山靴，正站在泥土斜坡上。最后一个镜显示该男子在斜坡上，仔细地拨开树根和泥土。周围的环境是树木繁茂的，阳光透过树叶照射下来。土壤是浅棕色的，斜坡上有许多树根和植被。",
            "narration": "（接上文）好吧，今天我们的男主角，背着一个看似随时要发射军绿色背包，竟然化身“泥土探险家”，在斜坡上挥舞着镐头！他这是准备挖宝还是给树根做个“美容”？阳光洒下来，简直是自然界的聚光灯，仿佛在说：“快来看看，这位勇士要挑战泥土极限！”我只能默默想，如果树根能说话，它们一定会喊：“别打我，我还有家人！”这就是生活，总有些搞笑的瞬间等着我们去发现！",
            "OST": 2,
            "new_timestamp": "00:00:00,000-00:00:33,000"
        },
        {
            "timestamp": "00:45-01:01",
            "picture": "好的以下是视频画面的客观描述：\n\n视频显示了一个人在森林里挖掘。\n\n第一个镜头是地面特写，显示出松散的泥土、碎石和落叶。光线照在部分区域。\n\n第二个镜头中，一模糊不清的蹲一个树根旁挖掘，一个橄榄绿色的背包放在地上。树根缠绕着常春藤。\n\n第三个镜头显示该人在一个更开阔的区域挖掘，那里有一些树根，以及部分倒的树干。他起来像是在挖掘一个较大的坑。\n\n第四个镜头是特写镜头，显示该人用工具清理土坑的墙壁。\n\n第五个镜头是土坑内部的特写镜头，可以看到土质的纹理，有一些小树根和其它植被的残留物。",
            "narration": "现在，这位勇敢的挖掘者就像个“现代版的土豆农夫”，在森林里开辟新天地。的目标是什么？挖出一个宝藏还一块“树根披萨”？小心哦，别让树根追着你喊：“不要挖我，我也是有故事的！”",
            "OST": 2,
            "new_timestamp": "00:00:33,000-00:00:49,000"
        },
        {
            "timestamp": "01:07-01:25",
            "picture": "好，以下是视频画面的客观描述：\n\n画面1：特写镜头，显示出一丛带有水珠的深绿色灌木叶片。叶片呈椭圆形，边缘光滑。背景是树根和泥土。\n\n画面2：一个留着胡子的男人正在一个森林中土坑里挖掘。他穿着黑色T恤和卡其色裤子，跪在地上，用具挖掘泥土。周围环绕着树木、树根和灌木。一个倒下的树干横跨土坑上方。\n\n画面3：同一个男人坐在他刚才挖的坑的边缘，看着前方。他的表情似乎略带沉思。背景与画面2相同。\n\n画面4：一个广角镜头显示出他挖出的坑。这是一个不规则形状的土坑，在树木繁茂的斜坡上。土壤呈深棕色，可见树根。\n\n画面5：同一个男人跪在地上，用一把小斧头砍一根木头。他穿着与前几个画面相同的衣服。地面上覆盖着落叶。周围是树木和灌木。",
            "narration": "“哎呀，这片灌木叶子滴水如雨，感觉像是大自然的洗发水广告！但我这位‘挖宝达人’似乎更适合拍个‘森林里的单身狗’真人秀。等会儿，我要给树根唱首歌，听说它们爱音乐！”",
            "OST": 2,
            "new_timestamp": "00:00:49,000-00:01:07,000"
        },
        {
            "timestamp": "01:36-01:53",
            "picture": "好的，以下是视频画面内容的客观描述：\n\n视频包含三个镜头：\n\n**镜头一：**个小型、浅水池塘，位于树林中。池塘的水看起来浑浊，呈绿褐色。池塘周围遍布泥土和落叶。多根树枝和树干横跨池塘，部分浸没在水中。周围的植被茂密，主要是深色树木和灌木。\n\n**镜头二：**距拍摄树深处，阳光透过树叶洒落在植被上。镜头中可见粗大的树干、树枝和各种绿叶植物。部分树枝似乎被砍断，切口可见。\n\n**镜头三：**近距离特写镜头，聚焦在树枝和绿叶上。叶片呈圆形，颜色为鲜绿色，有些叶片上有缺损。树枝颜色较深，呈现深褐色。背景是模糊的树林。\n",
            "narration": "“好吧，看来我们的‘挖宝达人’终于找到了一‘宝藏’——一个色泽如同绿豆汤的池塘！我敢打赌，这里不仅是小鱼儿的游乐场更是树枝们的‘水疗中心’！下次来这里，我得带上浮潜装备！”",
            "OST": 2,
            "new_timestamp": "00:01:07,000-00:01:24,000"
        }
    ]
    # 合并子视频
    # combine_clip_videos(combined_video_path=combined_video_path, video_paths=video_paths, video_ost_list=video_ost_list, list_script=list_script)

    cfg = VideoClipParams()
    cfg.video_aspect = VideoAspect.portrait
    cfg.font_name = "STHeitiMedium.ttc"
    cfg.font_size = 60
    cfg.stroke_color = "#000000"
    cfg.stroke_width = 1.5
    cfg.text_fore_color = "#FFFFFF"
    cfg.text_background_color = "transparent"
    cfg.bgm_type = "random"
    cfg.bgm_file = ""
    cfg.bgm_volume = 1.0
    cfg.subtitle_enabled = True
    cfg.subtitle_position = "bottom"
    cfg.n_threads = 2
    cfg.video_volume = 1

    cfg.voice_volume = 1.0

    video_path = "../../storage/tasks/123/combined.mp4"
    audio_path = "../../storage/tasks/123/final_audio.mp3"
    subtitle_path = "../../storage/tasks/123/subtitle.srt"
    output_file = "../../storage/tasks/123/final-123.mp4"

    generate_video_v2(video_path=video_path,
                       audio_path=audio_path,
                       subtitle_path=subtitle_path,
                       output_file=output_file,
                       params=cfg
                      )
