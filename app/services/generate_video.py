#!/usr/bin/env python
# -*- coding: UTF-8 -*-

'''
@Project: NarratoAI
@File   : generate_video
@Author : Viccy同学
@Date   : 2025/5/7 上午11:55 
'''

import os
import traceback
import tempfile
from typing import Optional, Dict, Any
from loguru import logger
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    afx
)
from moviepy.video.tools.subtitles import SubtitlesClip
from PIL import ImageFont

from app.utils import utils
from app.models.schema import AudioVolumeDefaults
from app.services.audio_normalizer import AudioNormalizer, normalize_audio_for_mixing


def is_valid_subtitle_file(subtitle_path: str) -> bool:
    """
    检查字幕文件是否有效

    参数:
        subtitle_path: 字幕文件路径

    返回:
        bool: 如果字幕文件存在且包含有效内容则返回True，否则返回False
    """
    if not subtitle_path or not os.path.exists(subtitle_path):
        return False

    try:
        with open(subtitle_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()

        # 检查文件是否为空
        if not content:
            return False

        # 检查是否包含时间戳格式（SRT格式的基本特征）
        # SRT格式应该包含类似 "00:00:00,000 --> 00:00:00,000" 的时间戳
        import re
        time_pattern = r'\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}'
        if not re.search(time_pattern, content):
            return False

        return True
    except Exception as e:
        logger.warning(f"检查字幕文件时出错: {str(e)}")
        return False


def merge_materials(
    video_path: str,
    audio_path: str,
    output_path: str,
    subtitle_path: Optional[str] = None,
    bgm_path: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None
) -> str:
    """
    合并视频、音频、BGM和字幕素材生成最终视频
    
    参数:
        video_path: 视频文件路径
        audio_path: 音频文件路径
        output_path: 输出文件路径
        subtitle_path: 字幕文件路径，可选
        bgm_path: 背景音乐文件路径，可选
        options: 其他选项配置，可包含以下字段:
            - voice_volume: 人声音量，默认1.0
            - bgm_volume: 背景音乐音量，默认0.3
            - original_audio_volume: 原始音频音量，默认0.0
            - keep_original_audio: 是否保留原始音频，默认False
            - subtitle_font: 字幕字体，默认None，系统会使用默认字体
            - subtitle_font_size: 字幕字体大小，默认40
            - subtitle_color: 字幕颜色，默认白色
            - subtitle_bg_color: 字幕背景颜色，默认透明
            - subtitle_position: 字幕位置，可选值'bottom', 'top', 'center'，默认'bottom'
            - custom_position: 自定义位置
            - stroke_color: 描边颜色，默认黑色
            - stroke_width: 描边宽度，默认1
            - threads: 处理线程数，默认2
            - fps: 输出帧率，默认30
            - subtitle_enabled: 是否启用字幕，默认True
            
    返回:
        输出视频的路径
    """
    # 合并选项默认值
    if options is None:
        options = {}
    
    # 设置默认参数值 - 使用统一的音量配置
    voice_volume = options.get('voice_volume', AudioVolumeDefaults.VOICE_VOLUME)
    bgm_volume = options.get('bgm_volume', AudioVolumeDefaults.BGM_VOLUME)
    # 修复bug: 将原声音量默认值从0.0改为0.7，确保短剧解说模式下原片音量正常
    original_audio_volume = options.get('original_audio_volume', AudioVolumeDefaults.ORIGINAL_VOLUME)
    keep_original_audio = options.get('keep_original_audio', True)  # 默认保留原声
    subtitle_font = options.get('subtitle_font', '')
    subtitle_font_size = options.get('subtitle_font_size', 40)
    subtitle_color = options.get('subtitle_color', '#FFFFFF')
    subtitle_bg_color = options.get('subtitle_bg_color', 'transparent')
    subtitle_position = options.get('subtitle_position', 'bottom')
    custom_position = options.get('custom_position', 70)
    stroke_color = options.get('stroke_color', '#000000')
    stroke_width = options.get('stroke_width', 1)
    threads = options.get('threads', 2)
    fps = options.get('fps', 30)
    subtitle_enabled = options.get('subtitle_enabled', True)

    # 配置日志 - 便于调试问题
    logger.info(f"音量配置详情:")
    logger.info(f"  - 配音音量: {voice_volume}")
    logger.info(f"  - 背景音乐音量: {bgm_volume}")
    logger.info(f"  - 原声音量: {original_audio_volume}")
    logger.info(f"  - 是否保留原声: {keep_original_audio}")
    logger.info(f"字幕配置详情:")
    logger.info(f"  - 是否启用字幕: {subtitle_enabled}")
    logger.info(f"  - 字幕文件路径: {subtitle_path}")

    # 音量参数验证
    def validate_volume(volume, name):
        if not (AudioVolumeDefaults.MIN_VOLUME <= volume <= AudioVolumeDefaults.MAX_VOLUME):
            logger.warning(f"{name}音量 {volume} 超出有效范围 [{AudioVolumeDefaults.MIN_VOLUME}, {AudioVolumeDefaults.MAX_VOLUME}]，将被限制")
            return max(AudioVolumeDefaults.MIN_VOLUME, min(volume, AudioVolumeDefaults.MAX_VOLUME))
        return volume

    voice_volume = validate_volume(voice_volume, "配音")
    bgm_volume = validate_volume(bgm_volume, "背景音乐")
    original_audio_volume = validate_volume(original_audio_volume, "原声")

    # 处理透明背景色问题 - MoviePy 2.1.1不支持'transparent'值
    if subtitle_bg_color == 'transparent':
        subtitle_bg_color = None  # None在新版MoviePy中表示透明背景

    # 创建输出目录（如果不存在）
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)
    
    logger.info(f"开始合并素材...")
    logger.info(f"  ① 视频: {video_path}")
    logger.info(f"  ② 音频: {audio_path}")
    if subtitle_path:
        logger.info(f"  ③ 字幕: {subtitle_path}")
    if bgm_path:
        logger.info(f"  ④ 背景音乐: {bgm_path}")
    logger.info(f"  ⑤ 输出: {output_path}")
    
    # 加载视频
    try:
        video_clip = VideoFileClip(video_path)
        logger.info(f"视频尺寸: {video_clip.size[0]}x{video_clip.size[1]}, 时长: {video_clip.duration}秒")
        
        # 提取视频原声(如果需要)
        original_audio = None
        if keep_original_audio and original_audio_volume > 0:
            try:
                original_audio = video_clip.audio
                if original_audio:
                    # 关键修复：只有当音量不为1.0时才进行音量调整，保持原声音量不变
                    if abs(original_audio_volume - 1.0) > 0.001:  # 使用小的容差值比较浮点数
                        original_audio = original_audio.with_effects([afx.MultiplyVolume(original_audio_volume)])
                        logger.info(f"已提取视频原声，音量调整为: {original_audio_volume}")
                    else:
                        logger.info("已提取视频原声，保持原始音量不变")
                else:
                    logger.warning("视频没有音轨，无法提取原声")
            except Exception as e:
                logger.error(f"提取视频原声失败: {str(e)}")
                original_audio = None
        
        # 移除原始音轨，稍后会合并新的音频
        video_clip = video_clip.without_audio()
        
    except Exception as e:
        logger.error(f"加载视频失败: {str(e)}")
        raise
    
    # 处理背景音乐和所有音频轨道合成
    audio_tracks = []

    # 智能音量调整（可选功能）
    if AudioVolumeDefaults.ENABLE_SMART_VOLUME and audio_path and os.path.exists(audio_path) and original_audio is not None:
        try:
            normalizer = AudioNormalizer()
            temp_dir = tempfile.mkdtemp()
            temp_original_path = os.path.join(temp_dir, "temp_original.wav")

            # 保存原声到临时文件进行分析
            original_audio.write_audiofile(temp_original_path, verbose=False, logger=None)

            # 计算智能音量调整
            tts_adjustment, original_adjustment = normalizer.calculate_volume_adjustment(
                audio_path, temp_original_path
            )

            # 应用智能调整，但保留用户设置的相对比例
            smart_voice_volume = voice_volume * tts_adjustment
            smart_original_volume = original_audio_volume * original_adjustment

            # 限制音量范围，避免过度调整
            smart_voice_volume = max(0.1, min(1.5, smart_voice_volume))
            smart_original_volume = max(0.1, min(2.0, smart_original_volume))

            voice_volume = smart_voice_volume
            original_audio_volume = smart_original_volume

            logger.info(f"智能音量调整 - TTS: {voice_volume:.2f}, 原声: {original_audio_volume:.2f}")

            # 清理临时文件
            import shutil
            shutil.rmtree(temp_dir)

        except Exception as e:
            logger.warning(f"智能音量分析失败，使用原始设置: {e}")

    # 先添加主音频（配音）
    if audio_path and os.path.exists(audio_path):
        try:
            voice_audio = AudioFileClip(audio_path).with_effects([afx.MultiplyVolume(voice_volume)])
            audio_tracks.append(voice_audio)
            logger.info(f"已添加配音音频，音量: {voice_volume}")
        except Exception as e:
            logger.error(f"加载配音音频失败: {str(e)}")

    # 添加原声（如果需要）
    if original_audio is not None:
        # 重新应用调整后的音量（因为original_audio已经应用了一次音量）
        # 计算需要的额外调整
        current_volume_in_original = 1.0  # original_audio中已应用的音量
        additional_adjustment = original_audio_volume / current_volume_in_original

        adjusted_original_audio = original_audio.with_effects([afx.MultiplyVolume(additional_adjustment)])
        audio_tracks.append(adjusted_original_audio)
        logger.info(f"已添加视频原声，最终音量: {original_audio_volume}")

    # 添加背景音乐（如果有）
    if bgm_path and os.path.exists(bgm_path):
        try:
            bgm_clip = AudioFileClip(bgm_path).with_effects([
                afx.MultiplyVolume(bgm_volume),
                afx.AudioFadeOut(3),
                afx.AudioLoop(duration=video_clip.duration),
            ])
            audio_tracks.append(bgm_clip)
            logger.info(f"已添加背景音乐，音量: {bgm_volume}")
        except Exception as e:
            logger.error(f"添加背景音乐失败: \n{traceback.format_exc()}")

    # 合成最终的音频轨道
    if audio_tracks:
        final_audio = CompositeAudioClip(audio_tracks)
        video_clip = video_clip.with_audio(final_audio)
        logger.info(f"已合成所有音频轨道，共{len(audio_tracks)}个")
    else:
        logger.warning("没有可用的音频轨道，输出视频将没有声音")
    
    # 处理字体路径
    font_path = None
    if subtitle_path and subtitle_font:
        font_path = os.path.join(utils.font_dir(), subtitle_font)
        if os.name == "nt":
            font_path = font_path.replace("\\", "/")
        logger.info(f"使用字体: {font_path}")
    
    # 处理视频尺寸
    video_width, video_height = video_clip.size
    
    # 字幕处理函数
    def create_text_clip(subtitle_item):
        """创建单个字幕片段"""
        phrase = subtitle_item[1]
        max_width = video_width * 0.9
        
        # 如果有字体路径，进行文本换行处理
        wrapped_txt = phrase
        txt_height = 0
        if font_path:
            wrapped_txt, txt_height = wrap_text(
                phrase, 
                max_width=max_width, 
                font=font_path, 
                fontsize=subtitle_font_size
            )
        
        # 创建文本片段
        try:
            _clip = TextClip(
                text=wrapped_txt,
                font=font_path,
                font_size=subtitle_font_size,
                color=subtitle_color,
                bg_color=subtitle_bg_color,  # 这里已经在前面处理过，None表示透明
                stroke_color=stroke_color,
                stroke_width=stroke_width,
            )
        except Exception as e:
            logger.error(f"创建字幕片段失败: {str(e)}, 使用简化参数重试")
            # 如果上面的方法失败，尝试使用更简单的参数
            _clip = TextClip(
                text=wrapped_txt,
                font=font_path,
                font_size=subtitle_font_size,
                color=subtitle_color,
            )
        
        # 设置字幕时间
        duration = subtitle_item[0][1] - subtitle_item[0][0]
        _clip = _clip.with_start(subtitle_item[0][0])
        _clip = _clip.with_end(subtitle_item[0][1])
        _clip = _clip.with_duration(duration)
        
        # 设置字幕位置
        if subtitle_position == "bottom":
            _clip = _clip.with_position(("center", video_height * 0.95 - _clip.h))
        elif subtitle_position == "top":
            _clip = _clip.with_position(("center", video_height * 0.05))
        elif subtitle_position == "custom":
            margin = 10
            max_y = video_height - _clip.h - margin
            min_y = margin
            custom_y = (video_height - _clip.h) * (custom_position / 100)
            custom_y = max(
                min_y, min(custom_y, max_y)
            )
            _clip = _clip.with_position(("center", custom_y))
        else:  # center
            _clip = _clip.with_position(("center", "center"))
            
        return _clip
        
    # 创建TextClip工厂函数
    def make_textclip(text):
        return TextClip(
            text=text,
            font=font_path,
            font_size=subtitle_font_size,
            color=subtitle_color,
        )
    
    # 处理字幕 - 修复字幕开关bug和空字幕文件问题
    if subtitle_enabled and subtitle_path:
        if is_valid_subtitle_file(subtitle_path):
            logger.info("字幕已启用，开始处理字幕文件")
            try:
                # 加载字幕文件
                sub = SubtitlesClip(
                    subtitles=subtitle_path,
                    encoding="utf-8",
                    make_textclip=make_textclip
                )

                # 创建每个字幕片段
                text_clips = []
                for item in sub.subtitles:
                    clip = create_text_clip(subtitle_item=item)
                    text_clips.append(clip)

                # 合成视频和字幕
                video_clip = CompositeVideoClip([video_clip, *text_clips])
                logger.info(f"已添加{len(text_clips)}个字幕片段")
            except Exception as e:
                logger.error(f"处理字幕失败: \n{traceback.format_exc()}")
                logger.warning("字幕处理失败，继续生成无字幕视频")
        else:
            logger.warning(f"字幕文件无效或为空: {subtitle_path}，跳过字幕处理")
    elif not subtitle_enabled:
        logger.info("字幕已禁用，跳过字幕处理")
    elif not subtitle_path:
        logger.info("未提供字幕文件路径，跳过字幕处理")
    
    # 导出最终视频
    try:
        video_clip.write_videofile(
            output_path,
            audio_codec="aac",
            temp_audiofile_path=output_dir,
            threads=threads,
            fps=fps,
        )
        logger.success(f"素材合并完成: {output_path}")
    except Exception as e:
        logger.error(f"导出视频失败: {str(e)}")
        raise
    finally:
        # 释放资源
        video_clip.close()
        del video_clip
    
    return output_path


def wrap_text(text, max_width, font="Arial", fontsize=60):
    """
    文本换行函数，使长文本适应指定宽度
    
    参数:
        text: 需要换行的文本
        max_width: 最大宽度（像素）
        font: 字体路径
        fontsize: 字体大小
        
    返回:
        换行后的文本和文本高度
    """
    # 创建ImageFont对象
    try:
        font_obj = ImageFont.truetype(font, fontsize)
    except:
        # 如果无法加载指定字体，使用默认字体
        font_obj = ImageFont.load_default()
    
    def get_text_size(inner_text):
        inner_text = inner_text.strip()
        left, top, right, bottom = font_obj.getbbox(inner_text)
        return right - left, bottom - top

    width, height = get_text_size(text)
    if width <= max_width:
        return text, height

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
    return result, height


if __name__ == '__main__':
    merger_mp4 = '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/merger.mp4'
    merger_sub = '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/merged_subtitle_00_00_00-00_01_30.srt'
    merger_audio = '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/merger_audio.mp3'
    bgm_path = '/Users/apple/Desktop/home/NarratoAI/resource/songs/bgm.mp3'
    output_video = '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/combined_test.mp4'
    
    # 调用示例
    options = {
        'voice_volume': 1.0,            # 配音音量
        'bgm_volume': 0.1,              # 背景音乐音量
        'original_audio_volume': 1.0,   # 视频原声音量，0表示不保留
        'keep_original_audio': True,    # 是否保留原声
        'subtitle_enabled': True,       # 是否启用字幕 - 修复字幕开关bug
        'subtitle_font': 'MicrosoftYaHeiNormal.ttc',  # 这里使用相对字体路径，会自动在 font_dir() 目录下查找
        'subtitle_font_size': 40,
        'subtitle_color': '#FFFFFF',
        'subtitle_bg_color': None,      # 直接使用None表示透明背景
        'subtitle_position': 'bottom',
        'threads': 2
    }
    
    try:
        merge_materials(
            video_path=merger_mp4,
            audio_path=merger_audio,
            subtitle_path=merger_sub,
            bgm_path=bgm_path,
            output_path=output_video,
            options=options
        )
    except Exception as e:
        logger.error(f"合并素材失败: \n{traceback.format_exc()}")
