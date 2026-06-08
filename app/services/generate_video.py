#!/usr/bin/env python
# -*- coding: UTF-8 -*-

'''
@Project: NarratoAI
@File   : generate_video
@Author : Viccy同学
@Date   : 2025/5/7 上午11:55 
'''

import os
import json
import re
import shlex
import subprocess
import traceback
import tempfile
from typing import Optional, Dict, Any
from loguru import logger
import numpy as np
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    afx
)
from moviepy.video.tools.subtitles import SubtitlesClip
from PIL import ImageFont, Image, ImageDraw, ImageEnhance, ImageFilter

from app.utils import utils
from app.models.schema import AudioVolumeDefaults
from app.services.audio_normalizer import AudioNormalizer, normalize_audio_for_mixing


SUBTITLE_MASK_DEFAULTS = {
    "landscape": {
        "x_percent": 10.0,
        "y_percent": 78.0,
        "width_percent": 80.0,
        "height_percent": 14.0,
        "blur_radius": 18,
        "opacity_percent": 82,
    },
    "portrait": {
        "x_percent": 8.0,
        "y_percent": 79.0,
        "width_percent": 84.0,
        "height_percent": 16.0,
        "blur_radius": 26,
        "opacity_percent": 84,
    },
}

_FFMPEG_FILTER_CACHE: Dict[tuple[str, str], bool] = {}
_FFMPEG_ENCODER_CACHE: Dict[tuple[str, str], bool] = {}


def _clamp(value, minimum, maximum):
    return min(max(value, minimum), maximum)


def _get_numeric_option(options, key, default, integer=False):
    try:
        value = float(options.get(key, default))
    except (TypeError, ValueError):
        value = float(default)
    return int(round(value)) if integer else value


def _get_subtitle_mask_region_options(options, orientation):
    defaults = SUBTITLE_MASK_DEFAULTS[orientation]
    prefix = f"subtitle_mask_{orientation}_"

    x_percent = _clamp(_get_numeric_option(options, f"{prefix}x_percent", defaults["x_percent"]), 0, 99)
    y_percent = _clamp(_get_numeric_option(options, f"{prefix}y_percent", defaults["y_percent"]), 0, 99)
    width_percent = _clamp(
        _get_numeric_option(options, f"{prefix}width_percent", defaults["width_percent"]),
        2,
        100 - x_percent,
    )
    height_percent = _clamp(
        _get_numeric_option(options, f"{prefix}height_percent", defaults["height_percent"]),
        2,
        100 - y_percent,
    )
    blur_radius = _clamp(
        _get_numeric_option(options, f"{prefix}blur_radius", defaults["blur_radius"], integer=True),
        0,
        200,
    )
    opacity_percent = _clamp(
        _get_numeric_option(options, f"{prefix}opacity_percent", defaults["opacity_percent"], integer=True),
        0,
        100,
    )

    return {
        "x_percent": x_percent,
        "y_percent": y_percent,
        "width_percent": width_percent,
        "height_percent": height_percent,
        "blur_radius": blur_radius,
        "opacity_percent": opacity_percent,
    }


def _resolve_subtitle_mask_region(video_width, video_height, options):
    orientation = "portrait" if video_height > video_width else "landscape"
    region = _get_subtitle_mask_region_options(options, orientation)

    x = _clamp(round(video_width * region["x_percent"] / 100), 0, max(0, video_width - 2))
    y = _clamp(round(video_height * region["y_percent"] / 100), 0, max(0, video_height - 2))
    width = _clamp(round(video_width * region["width_percent"] / 100), 2, max(2, video_width - x))
    height = _clamp(round(video_height * region["height_percent"] / 100), 2, max(2, video_height - y))

    base_height = 1920 if orientation == "portrait" else 1080
    blur_radius = (
        0
        if region["blur_radius"] == 0
        else max(1, round(region["blur_radius"] * (video_height / base_height)))
    )
    corner_radius = max(8, round(min(height * 0.32, blur_radius * 1.4 or height * 0.24)))
    feather = max(6, round(max(blur_radius * 0.85, 8)))
    padding = blur_radius
    padded_x = max(0, x - padding)
    padded_y = max(0, y - padding)
    padded_width = _clamp(width + padding * 2, 2, video_width - padded_x)
    padded_height = _clamp(height + padding * 2, 2, video_height - padded_y)

    return {
        "orientation": orientation,
        "x": int(x),
        "y": int(y),
        "width": int(width),
        "height": int(height),
        "blur_radius": int(blur_radius),
        "opacity": _clamp(region["opacity_percent"] / 100, 0, 1),
        "corner_radius": int(corner_radius),
        "feather": int(feather),
        "padded_x": int(padded_x),
        "padded_y": int(padded_y),
        "padded_width": int(padded_width),
        "padded_height": int(padded_height),
    }


def _build_subtitle_mask_alpha(region):
    alpha = Image.new("L", (region["padded_width"], region["padded_height"]), 0)
    draw = ImageDraw.Draw(alpha)
    left = region["x"] - region["padded_x"]
    top = region["y"] - region["padded_y"]
    right = left + region["width"]
    bottom = top + region["height"]
    draw.rounded_rectangle(
        (left, top, right, bottom),
        radius=region["corner_radius"],
        fill=255,
    )
    if region["feather"] > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(radius=max(1, region["feather"] / 2)))
    return alpha


def apply_subtitle_mask(video_clip, options):
    """Apply a Speclip-style blurred subtitle mask before subtitle burn-in."""
    if not options.get("subtitle_mask_enabled", False):
        return video_clip

    video_width, video_height = video_clip.size
    region = _resolve_subtitle_mask_region(video_width, video_height, options)
    logger.info(
        "字幕遮罩已启用: "
        f"{region['orientation']} x={region['x']} y={region['y']} "
        f"w={region['width']} h={region['height']} blur={region['blur_radius']}"
    )

    alpha = _build_subtitle_mask_alpha(region)
    tint_alpha = _clamp(round((0.05 + region["opacity"] * 0.07) * 100) / 100, 0.05, 0.14)
    blur_sigma = (
        max(4, round(region["blur_radius"] * (0.9 + region["opacity"] * 0.35)))
        if region["blur_radius"] > 0
        else 0
    )
    brightness = 1.0 + 0.03 + region["opacity"] * 0.04
    contrast = 0.975 - region["opacity"] * 0.035
    saturation = 1.0 + region["opacity"] * 0.03
    obliterate_width = max(24, round(region["padded_width"] * 0.12))
    obliterate_height = max(12, round(region["padded_height"] * 0.18))

    def mask_frame(get_frame, t):
        frame = np.asarray(get_frame(t))
        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)
        image = Image.fromarray(frame).convert("RGB")
        crop_box = (
            region["padded_x"],
            region["padded_y"],
            region["padded_x"] + region["padded_width"],
            region["padded_y"] + region["padded_height"],
        )
        mask_image = image.crop(crop_box)
        mask_image = mask_image.resize(
            (obliterate_width, obliterate_height),
            Image.Resampling.BICUBIC,
        ).resize(
            (region["padded_width"], region["padded_height"]),
            Image.Resampling.LANCZOS,
        )

        if blur_sigma > 0:
            mask_image = mask_image.filter(ImageFilter.GaussianBlur(radius=blur_sigma))
        mask_image = mask_image.filter(ImageFilter.BoxBlur(4))
        mask_image = ImageEnhance.Brightness(mask_image).enhance(brightness)
        mask_image = ImageEnhance.Contrast(mask_image).enhance(contrast)
        mask_image = ImageEnhance.Color(mask_image).enhance(saturation)

        blurred = mask_image.convert("RGBA")
        blurred.putalpha(alpha)

        tint = Image.new("RGBA", blurred.size, (255, 255, 255, 0))
        tint_alpha_mask = alpha.point(lambda value: int(value * tint_alpha))
        tint.putalpha(tint_alpha_mask)
        masked_region = Image.alpha_composite(blurred, tint)

        output = image.convert("RGBA")
        output.alpha_composite(masked_region, dest=(region["padded_x"], region["padded_y"]))
        return np.asarray(output.convert("RGB"))

    return video_clip.transform(mask_frame)


def _resolve_orientation_subtitle_y_percent(video_width, video_height, options):
    orientation = "portrait" if video_height > video_width else "landscape"
    key = f"subtitle_position_{orientation}_y_percent"
    if key not in options:
        return None
    return _clamp(_get_numeric_option(options, key, 85 if orientation == "landscape" else 82), 0, 99)


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


def _has_existing_file(file_path: Optional[str]) -> bool:
    return bool(file_path and os.path.exists(file_path))


def _get_ffmpeg_binary() -> str:
    for env_name in ("NARRATO_FFMPEG_EXE", "IMAGEIO_FFMPEG_EXE"):
        candidate = os.environ.get(env_name, "").strip()
        if candidate and os.path.isfile(candidate):
            return candidate

    try:
        import imageio_ffmpeg

        candidate = imageio_ffmpeg.get_ffmpeg_exe()
        if candidate and os.path.isfile(candidate):
            return candidate
    except Exception as e:
        logger.debug(f"未找到 imageio-ffmpeg 二进制: {e}")

    return "ffmpeg"


def _get_ffprobe_binary(ffmpeg_binary: Optional[str] = None) -> str:
    for env_name in ("NARRATO_FFPROBE_EXE", "IMAGEIO_FFPROBE_EXE"):
        candidate = os.environ.get(env_name, "").strip()
        if candidate and os.path.isfile(candidate):
            return candidate

    if ffmpeg_binary:
        sibling = os.path.join(os.path.dirname(ffmpeg_binary), "ffprobe")
        if os.path.isfile(sibling):
            return sibling

    return "ffprobe"


def _check_ffmpeg_binary(ffmpeg_binary: str) -> bool:
    try:
        subprocess.run(
            [ffmpeg_binary, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"ffmpeg 不可用: {ffmpeg_binary}, {e}")
        return False


def _format_ffmpeg_float(value: float) -> str:
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


def _quote_filter_value(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _probe_video(video_path: str) -> Dict[str, Any]:
    ffmpeg_binary = _get_ffmpeg_binary()
    ffprobe_binary = _get_ffprobe_binary(ffmpeg_binary)
    cmd = [
        ffprobe_binary,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        video_path,
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 读取视频失败: {result.stderr.strip()}")

    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if not video_stream:
        raise RuntimeError("ffprobe 未找到视频流")

    duration = (
        video_stream.get("duration")
        or data.get("format", {}).get("duration")
        or 0
    )
    duration = float(duration)
    if duration <= 0:
        raise RuntimeError("ffprobe 未获取到有效视频时长")

    return {
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "duration": duration,
        "has_audio": any(stream.get("codec_type") == "audio" for stream in streams),
    }


def _ffmpeg_filter_available(filter_name: str) -> bool:
    ffmpeg_binary = _get_ffmpeg_binary()
    cache_key = (ffmpeg_binary, filter_name)
    if cache_key in _FFMPEG_FILTER_CACHE:
        return _FFMPEG_FILTER_CACHE[cache_key]

    try:
        result = subprocess.run(
            [ffmpeg_binary, "-hide_banner", "-filters"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        available = False
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == filter_name:
                    available = True
                    break
        _FFMPEG_FILTER_CACHE[cache_key] = available
        return available
    except Exception:
        _FFMPEG_FILTER_CACHE[cache_key] = False
        return False


def _ffmpeg_encoder_available(encoder_name: str) -> bool:
    ffmpeg_binary = _get_ffmpeg_binary()
    cache_key = (ffmpeg_binary, encoder_name)
    if cache_key in _FFMPEG_ENCODER_CACHE:
        return _FFMPEG_ENCODER_CACHE[cache_key]

    try:
        result = subprocess.run(
            [ffmpeg_binary, "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        available = result.returncode == 0 and encoder_name in result.stdout
        _FFMPEG_ENCODER_CACHE[cache_key] = available
        return available
    except Exception:
        _FFMPEG_ENCODER_CACHE[cache_key] = False
        return False


def _select_compatible_encoder(preferred_encoder: str) -> str:
    if _ffmpeg_encoder_available(preferred_encoder):
        return preferred_encoder
    logger.warning(f"当前 ffmpeg 二进制不支持编码器 {preferred_encoder}，回退 libx264")
    return "libx264"


def _srt_timestamp_to_seconds(timestamp: str) -> float:
    match = re.match(
        r"(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2}),(?P<millis>\d{3})",
        timestamp.strip(),
    )
    if not match:
        raise ValueError(f"无效 SRT 时间戳: {timestamp}")
    parts = {key: int(value) for key, value in match.groupdict().items()}
    return (
        parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
        + parts["millis"] / 1000
    )


def _parse_srt_subtitles(subtitle_path: str) -> list[tuple[float, float, str]]:
    with open(subtitle_path, "r", encoding="utf-8-sig") as file:
        content = file.read().strip()

    if not content:
        return []

    subtitles = []
    blocks = re.split(r"\n\s*\n", content)
    time_pattern = re.compile(
        r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*"
        r"(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
    )
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        time_index = next(
            (index for index, line in enumerate(lines) if time_pattern.search(line)),
            None,
        )
        if time_index is None:
            continue

        match = time_pattern.search(lines[time_index])
        if not match:
            continue

        text = "\n".join(lines[time_index + 1:]).strip()
        if not text:
            continue

        subtitles.append(
            (
                _srt_timestamp_to_seconds(match.group("start")),
                _srt_timestamp_to_seconds(match.group("end")),
                text,
            )
        )
    return subtitles


def _normalize_hex_color(color: Optional[str], default: str) -> str:
    color_names = {
        "white": "#FFFFFF",
        "black": "#000000",
        "red": "#FF0000",
        "green": "#008000",
        "blue": "#0000FF",
        "yellow": "#FFFF00",
        "cyan": "#00FFFF",
        "magenta": "#FF00FF",
    }
    value = (color or default or "").strip()
    value = color_names.get(value.lower(), value)

    if not value.startswith("#"):
        return default
    value = value[1:]
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if len(value) != 6:
        return default
    try:
        int(value, 16)
    except ValueError:
        return default
    return f"#{value.upper()}"


def _css_color_to_ass(color: Optional[str], default: str) -> str:
    hex_color = _normalize_hex_color(color, default)[1:]
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"&H00{blue:02X}{green:02X}{red:02X}"


def _resolve_font_path(subtitle_font: str) -> Optional[str]:
    if subtitle_font and os.path.isabs(subtitle_font) and os.path.exists(subtitle_font):
        return subtitle_font

    if subtitle_font:
        font_path = os.path.join(utils.font_dir(), subtitle_font)
        if os.path.exists(font_path):
            return font_path

    for candidate in [
        os.path.join(utils.font_dir(), "SourceHanSansCN-Regular.otf"),
        os.path.join(utils.font_dir(), "SimHei.ttf"),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]:
        if os.path.exists(candidate):
            return candidate
    return None


def _resolve_font_family(font_path: Optional[str], subtitle_font: str) -> str:
    if font_path:
        try:
            return ImageFont.truetype(font_path, 12).getname()[0]
        except Exception:
            pass
    if subtitle_font:
        return os.path.splitext(os.path.basename(subtitle_font))[0]
    return "Arial"


def _estimate_subtitle_margin(
    video_height: int,
    font_size: int,
    subtitle_position: str,
    custom_position: float,
    orientation_subtitle_y_percent: Optional[float],
) -> tuple[int, int]:
    if subtitle_position == "top":
        return 8, max(10, round(video_height * 0.05))
    if subtitle_position == "center":
        return 5, 10

    y_percent = orientation_subtitle_y_percent
    if y_percent is None and subtitle_position == "custom":
        y_percent = custom_position

    if y_percent is not None:
        estimated_text_height = max(24, round(font_size * 1.35))
        y = (video_height - estimated_text_height) * (y_percent / 100)
        margin = video_height - y - estimated_text_height
        return 2, max(10, round(margin))

    return 2, max(10, round(video_height * 0.05))


def _build_subtitle_filter(
    subtitle_path: str,
    font_path: Optional[str],
    subtitle_font: str,
    subtitle_font_size: int,
    subtitle_color: str,
    stroke_color: str,
    stroke_width: float,
    video_width: int,
    video_height: int,
    subtitle_position: str,
    custom_position: float,
    orientation_subtitle_y_percent: Optional[float],
) -> str:
    font_family = _resolve_font_family(font_path, subtitle_font)
    alignment, margin_v = _estimate_subtitle_margin(
        video_height=video_height,
        font_size=subtitle_font_size,
        subtitle_position=subtitle_position,
        custom_position=custom_position,
        orientation_subtitle_y_percent=orientation_subtitle_y_percent,
    )
    force_style = ",".join(
        [
            f"Fontname={font_family}",
            f"Fontsize={subtitle_font_size}",
            f"PrimaryColour={_css_color_to_ass(subtitle_color, '#FFFFFF')}",
            f"OutlineColour={_css_color_to_ass(stroke_color, '#000000')}",
            "BorderStyle=1",
            f"Outline={stroke_width}",
            "Shadow=0",
            f"Alignment={alignment}",
            f"MarginV={margin_v}",
        ]
    )

    args = [f"filename={_quote_filter_value(subtitle_path)}"]
    args.append(f"original_size={video_width}x{video_height}")
    if font_path:
        args.append(f"fontsdir={_quote_filter_value(os.path.dirname(font_path))}")
    args.append(f"force_style={_quote_filter_value(force_style)}")
    return f"subtitles={':'.join(args)}"


def _css_color_to_drawtext(color: Optional[str], default: str) -> str:
    return f"0x{_normalize_hex_color(color, default)[1:]}"


def _escape_drawtext_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
    )


def _resolve_drawtext_y_expression(
    subtitle_position: str,
    custom_position: float,
    orientation_subtitle_y_percent: Optional[float],
) -> str:
    if subtitle_position == "top":
        return "h*0.05"
    if subtitle_position == "center":
        return "(h-text_h)/2"

    y_percent = orientation_subtitle_y_percent
    if y_percent is None and subtitle_position == "custom":
        y_percent = custom_position

    if y_percent is not None:
        return f"(h-text_h)*{_format_ffmpeg_float(y_percent / 100)}"
    return "h*0.95-text_h"


def _build_drawtext_filters(
    subtitle_path: str,
    font_path: Optional[str],
    subtitle_font_size: int,
    subtitle_color: str,
    stroke_color: str,
    stroke_width: float,
    subtitle_position: str,
    custom_position: float,
    orientation_subtitle_y_percent: Optional[float],
    video_width: int,
) -> list[str]:
    subtitles = _parse_srt_subtitles(subtitle_path)
    if not subtitles:
        raise RuntimeError("SRT 字幕解析结果为空，无法使用 drawtext 快路径")

    y_expr = _resolve_drawtext_y_expression(
        subtitle_position=subtitle_position,
        custom_position=custom_position,
        orientation_subtitle_y_percent=orientation_subtitle_y_percent,
    )
    max_width = video_width * 0.9
    drawtext_filters = []

    for start, end, text in subtitles:
        wrapped_text = text
        if font_path:
            wrapped_text, _ = wrap_text(
                text,
                max_width=max_width,
                font=font_path,
                fontsize=subtitle_font_size,
            )

        args = []
        if font_path:
            args.append(f"fontfile={_quote_filter_value(font_path)}")
        args.extend(
            [
                f"text={_quote_filter_value(_escape_drawtext_text(wrapped_text))}",
                f"fontcolor={_css_color_to_drawtext(subtitle_color, '#FFFFFF')}",
                f"fontsize={subtitle_font_size}",
                f"borderw={stroke_width}",
                f"bordercolor={_css_color_to_drawtext(stroke_color, '#000000')}",
                "x=(w-text_w)/2",
                f"y={y_expr}",
                (
                    "enable="
                    f"{_quote_filter_value(f'between(t,{_format_ffmpeg_float(start)},{_format_ffmpeg_float(end)})')}"
                ),
            ]
        )
        drawtext_filters.append(f"drawtext={':'.join(args)}")

    return drawtext_filters


def _hex_to_rgba(color: Optional[str], default: str, alpha: int = 255) -> tuple[int, int, int, int]:
    hex_color = _normalize_hex_color(color, default)[1:]
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
        alpha,
    )


def _create_subtitle_png_file(
    text: str,
    font_path: Optional[str],
    subtitle_font_size: int,
    subtitle_color: str,
    stroke_color: str,
    stroke_width: float,
    video_width: int,
    output_dir: str,
) -> str:
    font = ImageFont.truetype(font_path, subtitle_font_size) if font_path else ImageFont.load_default()
    wrapped_text, _ = wrap_text(
        text,
        max_width=video_width * 0.9,
        font=font_path or "Arial",
        fontsize=subtitle_font_size,
    )
    stroke_width_px = max(0, int(round(float(stroke_width))))
    padding = max(8, stroke_width_px * 3 + 6)

    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.multiline_textbbox(
        (0, 0),
        wrapped_text,
        font=font,
        spacing=4,
        stroke_width=stroke_width_px,
        align="center",
    )
    text_width = max(1, bbox[2] - bbox[0])
    text_height = max(1, bbox[3] - bbox[1])
    image = Image.new(
        "RGBA",
        (text_width + padding * 2, text_height + padding * 2),
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(image)
    draw.multiline_text(
        (image.width / 2, padding - bbox[1]),
        wrapped_text,
        font=font,
        fill=_hex_to_rgba(subtitle_color, "#FFFFFF"),
        anchor="ma",
        spacing=4,
        align="center",
        stroke_width=stroke_width_px,
        stroke_fill=_hex_to_rgba(stroke_color, "#000000"),
    )

    temp_file = tempfile.NamedTemporaryFile(
        suffix=".png",
        prefix="subtitle_text_",
        dir=output_dir,
        delete=False,
    )
    temp_file.close()
    image.save(temp_file.name)
    return temp_file.name


def _resolve_overlay_y_expression(
    subtitle_position: str,
    custom_position: float,
    orientation_subtitle_y_percent: Optional[float],
) -> str:
    if subtitle_position == "top":
        return "main_h*0.05"
    if subtitle_position == "center":
        return "(main_h-overlay_h)/2"

    y_percent = orientation_subtitle_y_percent
    if y_percent is None and subtitle_position == "custom":
        y_percent = custom_position

    if y_percent is not None:
        return f"(main_h-overlay_h)*{_format_ffmpeg_float(y_percent / 100)}"
    return "main_h*0.95-overlay_h"


def _create_subtitle_mask_alpha_file(region: Dict[str, Any], output_dir: str) -> str:
    alpha = _build_subtitle_mask_alpha(region)
    temp_file = tempfile.NamedTemporaryFile(
        suffix=".png",
        prefix="subtitle_mask_",
        dir=output_dir,
        delete=False,
    )
    temp_file.close()
    alpha.save(temp_file.name)
    return temp_file.name


def _build_mask_filter(
    input_label: str,
    mask_input_index: int,
    region: Dict[str, Any],
    output_label: str,
) -> list[str]:
    blur_sigma = (
        max(4, round(region["blur_radius"] * (0.9 + region["opacity"] * 0.35)))
        if region["blur_radius"] > 0
        else 0
    )
    brightness = 1.0 + 0.03 + region["opacity"] * 0.04
    contrast = 0.975 - region["opacity"] * 0.035
    saturation = 1.0 + region["opacity"] * 0.03
    obliterate_width = max(24, round(region["padded_width"] * 0.12))
    obliterate_height = max(12, round(region["padded_height"] * 0.18))

    blur_chain = (
        f"[masksrc]crop={region['padded_width']}:{region['padded_height']}:"
        f"{region['padded_x']}:{region['padded_y']},"
        f"scale={obliterate_width}:{obliterate_height}:flags=bicubic,"
        f"scale={region['padded_width']}:{region['padded_height']}:flags=lanczos"
    )
    if blur_sigma > 0:
        blur_chain += f",gblur=sigma={blur_sigma}"
    blur_chain += (
        ",boxblur=4,"
        f"eq=brightness={brightness - 1.0:.3f}:"
        f"contrast={contrast:.3f}:saturation={saturation:.3f},"
        "format=rgba[maskblur]"
    )

    return [
        f"{input_label}split[maskbase][masksrc]",
        blur_chain,
        (
            f"[{mask_input_index}:v]format=gray,"
            f"scale={region['padded_width']}:{region['padded_height']}[maskalpha]"
        ),
        "[maskblur][maskalpha]alphamerge[masked]",
        (
            f"[maskbase][masked]overlay={region['padded_x']}:{region['padded_y']}:"
            f"format=auto{output_label}"
        ),
    ]


def _build_video_encoder_args(encoder: str, threads: int) -> list[str]:
    if encoder == "h264_vaapi":
        logger.warning("当前合成滤镜链暂不使用 VAAPI 编码，回退到 libx264")
        encoder = "libx264"

    args = ["-c:v", encoder]
    if encoder == "h264_nvenc":
        args.extend(["-preset", "fast", "-cq", "23"])
    elif encoder == "h264_videotoolbox":
        args.extend(["-q:v", "65"])
    elif encoder == "h264_qsv":
        args.extend(["-preset", "veryfast", "-global_quality", "23"])
    elif encoder == "h264_amf":
        args.extend(["-quality", "speed", "-qp_i", "23", "-qp_p", "23"])
    else:
        args.extend(["-preset", "veryfast", "-crf", "23", "-threads", str(threads)])
    return args


def _build_moviepy_encoder_options() -> tuple[str, list[str]]:
    from app.utils import ffmpeg_utils

    encoder = _select_compatible_encoder(ffmpeg_utils.get_optimal_ffmpeg_encoder())
    if encoder == "h264_vaapi":
        logger.warning("MoviePy 兼容路径暂不使用 VAAPI 编码，回退到 libx264")
        encoder = "libx264"

    if encoder == "h264_nvenc":
        return encoder, ["-preset", "fast", "-cq", "23", "-pix_fmt", "yuv420p"]
    if encoder == "h264_videotoolbox":
        return encoder, ["-q:v", "65", "-pix_fmt", "yuv420p"]
    if encoder == "h264_qsv":
        return encoder, ["-preset", "veryfast", "-global_quality", "23", "-pix_fmt", "yuv420p"]
    if encoder == "h264_amf":
        return encoder, ["-quality", "speed", "-qp_i", "23", "-qp_p", "23", "-pix_fmt", "yuv420p"]
    return "libx264", ["-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]


def _build_ffmpeg_merge_command(
    video_path: str,
    audio_path: str,
    output_path: str,
    subtitle_path: Optional[str],
    bgm_path: Optional[str],
    options: Dict[str, Any],
) -> tuple[list[str], list[str]]:
    from app.utils import ffmpeg_utils

    video_meta = _probe_video(video_path)
    output_dir = os.path.dirname(output_path)
    duration = float(video_meta["duration"])
    duration_arg = _format_ffmpeg_float(duration)
    video_width = int(video_meta["width"])
    video_height = int(video_meta["height"])

    voice_volume = options.get("voice_volume", AudioVolumeDefaults.VOICE_VOLUME)
    bgm_volume = options.get("bgm_volume", AudioVolumeDefaults.BGM_VOLUME)
    original_audio_volume = options.get("original_audio_volume", AudioVolumeDefaults.ORIGINAL_VOLUME)
    keep_original_audio = options.get("keep_original_audio", True)
    subtitle_font = options.get("subtitle_font", "")
    subtitle_font_size = int(options.get("subtitle_font_size", 40))
    subtitle_color = options.get("subtitle_color", "#FFFFFF")
    subtitle_position = options.get("subtitle_position", "bottom")
    custom_position = float(options.get("custom_position", 70))
    stroke_color = options.get("stroke_color", "#000000")
    stroke_width = options.get("stroke_width", 1)
    threads = int(options.get("threads", 2))
    fps = options.get("fps", 30)
    subtitle_enabled = options.get("subtitle_enabled", True)
    subtitle_mask_enabled = bool(options.get("subtitle_mask_enabled", False))

    input_args = ["-i", video_path]
    next_input_index = 1
    audio_filters = []
    audio_labels = []
    temp_files = []

    if keep_original_audio and original_audio_volume > 0 and video_meta["has_audio"]:
        label = f"a{len(audio_labels)}"
        audio_filters.append(
            f"[0:a]volume={original_audio_volume},atrim=0:{duration_arg},"
            f"asetpts=PTS-STARTPTS[{label}]"
        )
        audio_labels.append(f"[{label}]")

    if _has_existing_file(audio_path):
        voice_input_index = next_input_index
        next_input_index += 1
        input_args.extend(["-i", audio_path])
        label = f"a{len(audio_labels)}"
        audio_filters.append(
            f"[{voice_input_index}:a]volume={voice_volume},atrim=0:{duration_arg},"
            f"asetpts=PTS-STARTPTS[{label}]"
        )
        audio_labels.append(f"[{label}]")

    if _has_existing_file(bgm_path) and bgm_volume > 0:
        bgm_input_index = next_input_index
        next_input_index += 1
        input_args.extend(["-stream_loop", "-1", "-i", bgm_path])
        fade_start = max(0.0, duration - 3.0)
        label = f"a{len(audio_labels)}"
        audio_filters.append(
            f"[{bgm_input_index}:a]volume={bgm_volume},atrim=0:{duration_arg},"
            f"afade=t=out:st={_format_ffmpeg_float(fade_start)}:d=3,"
            f"asetpts=PTS-STARTPTS[{label}]"
        )
        audio_labels.append(f"[{label}]")

    if len(audio_labels) == 1:
        audio_filters.append(
            f"{audio_labels[0]}atrim=0:{duration_arg},asetpts=PTS-STARTPTS[aout]"
        )
    elif len(audio_labels) > 1:
        audio_filters.append(
            f"{''.join(audio_labels)}amix=inputs={len(audio_labels)}:"
            f"duration=longest:dropout_transition=0:normalize=0,"
            f"atrim=0:{duration_arg},asetpts=PTS-STARTPTS[aout]"
        )

    valid_subtitle = bool(
        subtitle_enabled
        and subtitle_path
        and is_valid_subtitle_file(subtitle_path)
    )
    has_subtitles_filter = _ffmpeg_filter_available("subtitles") if valid_subtitle else False
    has_drawtext_filter = _ffmpeg_filter_available("drawtext") if valid_subtitle else False
    if valid_subtitle and not has_subtitles_filter and not has_drawtext_filter:
        if not _ffmpeg_filter_available("overlay"):
            raise RuntimeError("当前 ffmpeg 缺少 subtitles/drawtext/overlay 字幕处理滤镜")
        logger.warning("当前 ffmpeg 缺少 subtitles/drawtext，改用 PNG 字幕叠加快路径")

    video_filters = []
    current_video_label = "[0:v]"

    if subtitle_enabled and subtitle_mask_enabled:
        region = _resolve_subtitle_mask_region(video_width, video_height, options)
        mask_path = _create_subtitle_mask_alpha_file(region, output_dir)
        temp_files.append(mask_path)
        mask_input_index = next_input_index
        next_input_index += 1
        input_args.extend(["-loop", "1", "-t", duration_arg, "-i", mask_path])
        logger.info(
            "ffmpeg 字幕遮罩已启用: "
            f"{region['orientation']} x={region['x']} y={region['y']} "
            f"w={region['width']} h={region['height']} blur={region['blur_radius']}"
        )
        video_filters.extend(
            _build_mask_filter(
                input_label=current_video_label,
                mask_input_index=mask_input_index,
                region=region,
                output_label="[v_masked]",
            )
        )
        current_video_label = "[v_masked]"

    if valid_subtitle:
        font_path = _resolve_font_path(subtitle_font)
        if font_path:
            logger.info(f"ffmpeg 使用字幕字体: {font_path}")
        orientation_subtitle_y_percent = _resolve_orientation_subtitle_y_percent(
            video_width,
            video_height,
            options,
        )
        if has_drawtext_filter:
            drawtext_filters = _build_drawtext_filters(
                subtitle_path=subtitle_path,
                font_path=font_path,
                subtitle_font_size=subtitle_font_size,
                subtitle_color=subtitle_color,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                subtitle_position=subtitle_position,
                custom_position=custom_position,
                orientation_subtitle_y_percent=orientation_subtitle_y_percent,
                video_width=video_width,
            )
            for index, drawtext_filter in enumerate(drawtext_filters):
                next_label = f"[v_drawtext_{index}]"
                video_filters.append(f"{current_video_label}{drawtext_filter}{next_label}")
                current_video_label = next_label
        elif has_subtitles_filter:
            subtitle_filter = _build_subtitle_filter(
                subtitle_path=subtitle_path,
                font_path=font_path,
                subtitle_font=subtitle_font,
                subtitle_font_size=subtitle_font_size,
                subtitle_color=subtitle_color,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                video_width=video_width,
                video_height=video_height,
                subtitle_position=subtitle_position,
                custom_position=custom_position,
                orientation_subtitle_y_percent=orientation_subtitle_y_percent,
            )
            video_filters.append(f"{current_video_label}{subtitle_filter}[v_subtitled]")
            current_video_label = "[v_subtitled]"
        else:
            y_expr = _resolve_overlay_y_expression(
                subtitle_position=subtitle_position,
                custom_position=custom_position,
                orientation_subtitle_y_percent=orientation_subtitle_y_percent,
            )
            for index, (start, end, text) in enumerate(_parse_srt_subtitles(subtitle_path)):
                png_path = _create_subtitle_png_file(
                    text=text,
                    font_path=font_path,
                    subtitle_font_size=subtitle_font_size,
                    subtitle_color=subtitle_color,
                    stroke_color=stroke_color,
                    stroke_width=stroke_width,
                    video_width=video_width,
                    output_dir=output_dir,
                )
                temp_files.append(png_path)
                subtitle_input_index = next_input_index
                next_input_index += 1
                input_args.extend(["-loop", "1", "-t", duration_arg, "-i", png_path])
                next_label = f"[v_subtitle_png_{index}]"
                enable_expr = (
                    f"between(t,{_format_ffmpeg_float(start)},{_format_ffmpeg_float(end)})"
                )
                video_filters.append(
                    f"{current_video_label}[{subtitle_input_index}:v]"
                    f"overlay=x=(main_w-overlay_w)/2:y={y_expr}:"
                    f"enable={_quote_filter_value(enable_expr)}:format=auto{next_label}"
                )
                current_video_label = next_label
    elif subtitle_enabled and subtitle_path:
        logger.warning(f"字幕文件无效或为空: {subtitle_path}，ffmpeg 快路径跳过字幕")

    has_video_filter = bool(video_filters)
    if has_video_filter:
        final_video_filters = []
        if fps:
            final_video_filters.append(f"fps={fps}")
        final_video_filters.append("format=yuv420p")
        video_filters.append(
            f"{current_video_label}{','.join(final_video_filters)}[vout]"
        )

    filter_parts = [*video_filters, *audio_filters]
    ffmpeg_binary = _get_ffmpeg_binary()
    cmd = [ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error", *input_args]
    if filter_parts:
        cmd.extend(["-filter_complex", ";".join(filter_parts)])

    if has_video_filter:
        encoder = _select_compatible_encoder(ffmpeg_utils.get_optimal_ffmpeg_encoder())
        cmd.extend(["-map", "[vout]", *_build_video_encoder_args(encoder, threads)])
    else:
        cmd.extend(["-map", "0:v:0", "-c:v", "copy"])

    if audio_labels:
        cmd.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
    else:
        cmd.append("-an")

    cmd.extend(["-t", duration_arg, "-movflags", "+faststart", output_path])
    return cmd, temp_files


def _merge_materials_with_ffmpeg(
    video_path: str,
    audio_path: str,
    output_path: str,
    subtitle_path: Optional[str] = None,
    bgm_path: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> bool:
    ffmpeg_binary = _get_ffmpeg_binary()
    if not _check_ffmpeg_binary(ffmpeg_binary):
        return False

    options = options or {}
    temp_files = []
    try:
        cmd, temp_files = _build_ffmpeg_merge_command(
            video_path=video_path,
            audio_path=audio_path,
            output_path=output_path,
            subtitle_path=subtitle_path,
            bgm_path=bgm_path,
            options=options,
        )
        logger.info(f"使用 ffmpeg 快速合并素材: {shlex.join(cmd)}")
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.warning(f"ffmpeg 快速合并失败，将回退 MoviePy: {result.stderr[-3000:]}")
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            return False

        logger.success(f"ffmpeg 素材合并完成: {output_path}")
        return True
    except Exception as e:
        logger.warning(f"ffmpeg 快速合并不可用，将回退 MoviePy: {e}")
        return False
    finally:
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except OSError:
                pass


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
    subtitle_mask_enabled = bool(options.get('subtitle_mask_enabled', False))

    # 配置日志 - 便于调试问题
    logger.info(f"音量配置详情:")
    logger.info(f"  - 配音音量: {voice_volume}")
    logger.info(f"  - 背景音乐音量: {bgm_volume}")
    logger.info(f"  - 原声音量: {original_audio_volume}")
    logger.info(f"  - 是否保留原声: {keep_original_audio}")
    logger.info(f"字幕配置详情:")
    logger.info(f"  - 是否启用字幕: {subtitle_enabled}")
    logger.info(f"  - 是否启用字幕遮罩: {subtitle_mask_enabled}")
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

    merge_engine = str(options.get("merge_engine", "ffmpeg")).lower()
    use_ffmpeg_merge = bool(options.get("use_ffmpeg_merge", True))
    if use_ffmpeg_merge and merge_engine != "moviepy":
        ffmpeg_options = dict(options)
        ffmpeg_options.update(
            {
                "voice_volume": voice_volume,
                "bgm_volume": bgm_volume,
                "original_audio_volume": original_audio_volume,
                "keep_original_audio": keep_original_audio,
                "subtitle_font": subtitle_font,
                "subtitle_font_size": subtitle_font_size,
                "subtitle_color": subtitle_color,
                "subtitle_bg_color": subtitle_bg_color,
                "subtitle_position": subtitle_position,
                "custom_position": custom_position,
                "stroke_color": stroke_color,
                "stroke_width": stroke_width,
                "threads": threads,
                "fps": fps,
                "subtitle_enabled": subtitle_enabled,
                "subtitle_mask_enabled": subtitle_mask_enabled,
            }
        )
        if _merge_materials_with_ffmpeg(
            video_path=video_path,
            audio_path=audio_path,
            output_path=output_path,
            subtitle_path=subtitle_path,
            bgm_path=bgm_path,
            options=ffmpeg_options,
        ):
            return output_path
        logger.warning("ffmpeg 快速合并失败，继续使用 MoviePy 兼容路径")
    
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
            original_audio.write_audiofile(temp_original_path, logger=None)

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
    font_path = _resolve_font_path(subtitle_font) if subtitle_path else None
    if font_path:
        if os.name == "nt":
            font_path = font_path.replace("\\", "/")
        logger.info(f"使用字体: {font_path}")
    
    # 处理视频尺寸
    video_width, video_height = video_clip.size
    orientation_subtitle_y_percent = _resolve_orientation_subtitle_y_percent(video_width, video_height, options)

    if subtitle_enabled and subtitle_mask_enabled:
        video_clip = apply_subtitle_mask(video_clip, options)
    
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
            text_clip_kwargs = {
                "text": wrapped_txt,
                "font_size": subtitle_font_size,
                "color": subtitle_color,
                "bg_color": subtitle_bg_color,  # 这里已经在前面处理过，None表示透明
                "stroke_color": stroke_color,
                "stroke_width": stroke_width,
            }
            if font_path:
                text_clip_kwargs["font"] = font_path
            _clip = TextClip(**text_clip_kwargs)
        except Exception as e:
            logger.error(f"创建字幕片段失败: {str(e)}, 使用简化参数重试")
            # 如果上面的方法失败，尝试使用更简单的参数
            fallback_kwargs = {
                "text": wrapped_txt,
                "font_size": subtitle_font_size,
                "color": subtitle_color,
            }
            if font_path:
                fallback_kwargs["font"] = font_path
            _clip = TextClip(**fallback_kwargs)
        
        # 设置字幕时间
        duration = subtitle_item[0][1] - subtitle_item[0][0]
        _clip = _clip.with_start(subtitle_item[0][0])
        _clip = _clip.with_end(subtitle_item[0][1])
        _clip = _clip.with_duration(duration)
        
        # 设置字幕位置
        if orientation_subtitle_y_percent is not None:
            margin = 10
            max_y = video_height - _clip.h - margin
            min_y = margin
            custom_y = (video_height - _clip.h) * (orientation_subtitle_y_percent / 100)
            custom_y = max(min_y, min(custom_y, max_y))
            _clip = _clip.with_position(("center", custom_y))
        elif subtitle_position == "bottom":
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
        text_clip_kwargs = {
            "text": text,
            "font_size": subtitle_font_size,
            "color": subtitle_color,
        }
        if font_path:
            text_clip_kwargs["font"] = font_path
        return TextClip(**text_clip_kwargs)
    
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
        encoder, ffmpeg_params = _build_moviepy_encoder_options()
        logger.info(f"MoviePy 导出编码器: {encoder}, 参数: {ffmpeg_params}")
        try:
            video_clip.write_videofile(
                output_path,
                codec=encoder,
                audio_codec="aac",
                temp_audiofile_path=output_dir,
                threads=threads,
                fps=fps,
                ffmpeg_params=ffmpeg_params,
            )
        except Exception:
            if encoder == "libx264":
                raise
            logger.warning(f"MoviePy 使用 {encoder} 导出失败，回退 libx264: {traceback.format_exc()}")
            video_clip.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                temp_audiofile_path=output_dir,
                threads=threads,
                fps=fps,
                ffmpeg_params=["-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"],
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
