import json
import os
import re
import shutil
import subprocess
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

from app.models.schema import VideoClipParams
from app.services import script_subtitle


MICROSECONDS = 1_000_000
DRAFT_PATH_PLACEHOLDER = "##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##"
DRAFT_PATH_PLACEHOLDER_PATTERN = re.compile(r"^##_draftpath_placeholder_[^#]+_##/")

MATERIAL_COLLECTION_KEYS = [
    "ai_translates",
    "audio_balances",
    "audio_effects",
    "audio_fades",
    "audio_pannings",
    "audio_pitch_shifts",
    "audio_track_indexes",
    "audios",
    "beats",
    "canvases",
    "chromas",
    "color_curves",
    "common_mask",
    "digital_human_model_dressing",
    "digital_humans",
    "drafts",
    "effects",
    "flowers",
    "green_screens",
    "handwrites",
    "hsl",
    "hsl_curves",
    "images",
    "log_color_wheels",
    "loudnesses",
    "manual_beautys",
    "manual_deformations",
    "material_animations",
    "material_colors",
    "multi_language_refs",
    "placeholder_infos",
    "placeholders",
    "plugin_effects",
    "primary_color_wheels",
    "realtime_denoises",
    "shapes",
    "smart_crops",
    "smart_relights",
    "sound_channel_mappings",
    "speeds",
    "stickers",
    "tail_leaders",
    "text_templates",
    "texts",
    "time_marks",
    "transitions",
    "video_effects",
    "video_radius",
    "video_shadows",
    "video_strokes",
    "video_trackings",
    "videos",
    "vocal_beautifys",
    "vocal_separations",
]

DRAFT_PACKAGE_DIRECTORIES = [
    "qr_upload",
    "matting",
    "common_attachment",
    "Resources/audioAlg",
    "Resources/digitalHuman",
    "Resources/restore_lut",
    "Resources/videoAlg",
    "subdraft",
    "adjust_mask",
    "assets/audio",
    "assets/video",
    "smart_crop",
]

DEFAULT_DRAFT_COVER_BYTES = bytes([
    0xFF, 0xD8, 0xFF, 0xDB, 0x00, 0x43, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00,
    0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x14, 0x00, 0x01, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x01, 0xFF, 0xC4, 0x00, 0x14, 0x10, 0x01, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x01, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7F,
    0xFF, 0xD9,
])


def _write_json_file(file_path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def _floor_duration_to_milliseconds(duration: float) -> float:
    return int(max(duration, 0.0) * 1000) / 1000.0


def _seconds_to_microseconds(seconds: float) -> int:
    return int(round(max(seconds, 0.0) * MICROSECONDS))


def _get_media_duration_ffprobe(media_file: str) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        media_file,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def _get_cached_media_duration(media_file: str, duration_cache: Dict[str, float]) -> float:
    if media_file not in duration_cache:
        duration_cache[media_file] = _floor_duration_to_milliseconds(
            _get_media_duration_ffprobe(media_file)
        )
    return duration_cache[media_file]


def _clamp_duration_to_media(
    requested_duration: float,
    media_file: str,
    duration_cache: Dict[str, float],
    media_label: str,
    source_start_time: float = 0.0,
) -> float:
    requested_duration = _floor_duration_to_milliseconds(requested_duration)
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


def _get_video_metadata_ffprobe(
    media_file: str,
    metadata_cache: Dict[str, Tuple[int, int, int]],
) -> Tuple[int, int, int]:
    if media_file in metadata_cache:
        return metadata_cache[media_file]

    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "stream=width,height:format=duration",
            "-of", "json",
            media_file,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout or "{}")
        stream = next(
            (
                item for item in info.get("streams", [])
                if item.get("width") and item.get("height")
            ),
            {},
        )
        duration = _floor_duration_to_milliseconds(
            float(info.get("format", {}).get("duration") or 0.0)
        )
        width = int(stream.get("width") or 1920)
        height = int(stream.get("height") or 1080)
        metadata_cache[media_file] = (_seconds_to_microseconds(duration), width, height)
    except Exception as e:
        logger.warning(f"读取视频元信息失败，将使用默认分辨率: {media_file}, {e}")
        duration = _floor_duration_to_milliseconds(_get_media_duration_ffprobe(media_file))
        metadata_cache[media_file] = (_seconds_to_microseconds(duration), 1920, 1080)

    return metadata_cache[media_file]


def _format_draft_uuid(draft_id: str) -> str:
    compact = draft_id.replace("-", "")
    if not re.fullmatch(r"[a-fA-F0-9]{32}", compact):
        return draft_id
    return "-".join([
        compact[0:8],
        compact[8:12],
        compact[12:16],
        compact[16:20],
        compact[20:32],
    ]).upper()


def _detect_platform(draft_root_path: str) -> str:
    return "windows" if re.match(r"^(?:[a-zA-Z]:[\\/]|\\\\)", draft_root_path) else "mac"


def _create_platform_info(draft_root_path: str) -> Dict[str, Any]:
    return {
        "app_id": 3704,
        "app_source": "lv",
        "app_version": "10.6.0",
        "device_id": "",
        "hard_disk_id": "",
        "mac_address": "",
        "os": _detect_platform(draft_root_path),
        "os_version": "",
    }


def _default_function_assistant_info() -> Dict[str, Any]:
    return {
        "audio_noise_segid_list": [],
        "auto_adjust": False,
        "auto_adjust_fixed": False,
        "auto_adjust_fixed_value": 50.0,
        "auto_adjust_segid_list": [],
        "auto_caption": False,
        "auto_caption_segid_list": [],
        "auto_caption_template_id": "",
        "caption_opt": False,
        "caption_opt_segid_list": [],
        "color_correction": False,
        "color_correction_fixed": False,
        "color_correction_fixed_value": 50.0,
        "color_correction_segid_list": [],
        "deflicker_segid_list": [],
        "enhance_quality": False,
        "enhance_quality_fixed": False,
        "enhance_quality_segid_list": [],
        "enhance_voice_segid_list": [],
        "enhande_voice": False,
        "enhande_voice_fixed": False,
        "eye_correction": False,
        "eye_correction_segid_list": [],
        "fixed_rec_applied": False,
        "fps": {"den": 1, "num": 0},
        "normalize_loudness": False,
        "normalize_loudness_audio_denoise_segid_list": [],
        "normalize_loudness_fixed": False,
        "normalize_loudness_segid_list": [],
        "retouch": False,
        "retouch_fixed": False,
        "retouch_segid_list": [],
        "smart_rec_applied": False,
        "smart_segid_list": [],
        "smooth_slow_motion": False,
        "smooth_slow_motion_fixed": False,
        "video_noise_segid_list": [],
    }


def _safe_file_name(file_path: str, fallback: str) -> str:
    name = os.path.basename(file_path) or fallback
    name = re.sub(r'[<>:"|?*\x00-\x1f/\\]+', "_", name).strip(" ._")
    return name or fallback


def _normalize_asset_path(file_path: Optional[str], fallback: str) -> str:
    normalized = (file_path or "").replace("\\", "/").lstrip("./")
    without_draft_placeholder = DRAFT_PATH_PLACEHOLDER_PATTERN.sub("", normalized)
    if without_draft_placeholder.startswith("assets/"):
        return without_draft_placeholder
    assets_index = without_draft_placeholder.rfind("/assets/")
    if assets_index >= 0:
        return without_draft_placeholder[assets_index + 1:]
    return fallback


def _to_draft_material_path(relative_path: str) -> str:
    return f"{DRAFT_PATH_PLACEHOLDER}/{relative_path}"


def _unique_relative_asset_path(
    directory: str,
    file_name: str,
    used_paths: Set[str],
) -> str:
    base_name, ext = os.path.splitext(file_name)
    candidate_name = file_name
    counter = 2
    while True:
        relative_path = f"{directory}/{candidate_name}"
        if relative_path not in used_paths:
            used_paths.add(relative_path)
            return relative_path
        candidate_name = f"{base_name}_{counter}{ext}"
        counter += 1


def _copy_asset_into_draft(source_file: str, draft_path: str, relative_path: str) -> None:
    destination = os.path.join(draft_path, *relative_path.split("/"))
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if os.path.abspath(source_file) != os.path.abspath(destination):
        shutil.copy2(source_file, destination)


def _register_asset(
    source_file: str,
    draft_path: str,
    asset_dir: str,
    fallback_name: str,
    used_paths: Set[str],
    asset_path_cache: Dict[str, str],
) -> str:
    source_key = os.path.abspath(source_file)
    if source_key in asset_path_cache:
        return asset_path_cache[source_key]

    file_name = _safe_file_name(source_file, fallback_name)
    relative_path = _unique_relative_asset_path(asset_dir, file_name, used_paths)
    _copy_asset_into_draft(source_file, draft_path, relative_path)
    asset_path_cache[source_key] = relative_path
    return relative_path


def _create_unique_draft_path(drafts_root: str, draft_name: str) -> Tuple[str, str]:
    folder_base = _safe_file_name(draft_name, f"NarratoAI_{int(time.time())}")
    folder_name = folder_base
    counter = 2
    while os.path.exists(os.path.join(drafts_root, folder_name)):
        folder_name = f"{folder_base}_{counter}"
        counter += 1
    return folder_name, os.path.join(drafts_root, folder_name)


def _create_material_collections() -> Dict[str, List[Any]]:
    return {key: [] for key in MATERIAL_COLLECTION_KEYS}


def _create_draft_template(
    draft_id: str,
    draft_name: str,
    draft_root_path: str,
    width: int = 1920,
    height: int = 1080,
) -> Dict[str, Any]:
    now_us = int(time.time() * MICROSECONDS)
    platform_info = _create_platform_info(draft_root_path)
    return {
        "canvas_config": {"height": height, "ratio": "original", "width": width},
        "color_space": 0,
        "config": {
            "adjust_max_index": 1,
            "attachment_info": [],
            "combination_max_index": 1,
            "export_range": None,
            "extract_audio_last_index": 1,
            "lyrics_recognition_id": "",
            "lyrics_sync": True,
            "lyrics_taskinfo": [],
            "maintrack_adsorb": True,
            "material_save_mode": 0,
            "multi_language_current": "none",
            "multi_language_list": [],
            "multi_language_main": "none",
            "multi_language_mode": "none",
            "original_sound_last_index": 1,
            "record_audio_last_index": 1,
            "sticker_max_index": 1,
            "subtitle_keywords_config": None,
            "subtitle_recognition_id": "",
            "subtitle_sync": True,
            "subtitle_taskinfo": [],
            "system_font_list": [],
            "video_mute": False,
            "zoom_info_params": None,
        },
        "cover": None,
        "create_time": now_us,
        "duration": 0,
        "extra_info": None,
        "fps": 30.0,
        "free_render_index_mode_on": False,
        "group_container": None,
        "id": draft_id,
        "keyframe_graph_list": [],
        "keyframes": {
            "adjusts": [],
            "audios": [],
            "effects": [],
            "filters": [],
            "handwrites": [],
            "stickers": [],
            "texts": [],
            "videos": [],
        },
        "last_modified_platform": platform_info,
        "materials": _create_material_collections(),
        "mutable_config": None,
        "name": draft_name,
        "new_version": "169.0.0",
        "relationships": [],
        "render_index_track_mode_on": True,
        "retouch_cover": None,
        "source": "default",
        "static_cover_image_path": "",
        "time_marks": None,
        "tracks": [],
        "update_time": now_us,
        "version": 360000,
    }


def _create_track(track_type: str, name: str) -> Dict[str, Any]:
    return {
        "attribute": 0,
        "flag": 0,
        "id": uuid.uuid4().hex,
        "is_default_name": True,
        "name": name,
        "segments": [],
        "type": track_type,
    }


def _create_video_material(
    relative_path: str,
    duration_us: int,
    width: int,
    height: int,
) -> Dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "path": relative_path,
        "type": "video",
        "duration": duration_us,
        "width": width,
        "height": height,
        "material_name": os.path.basename(relative_path),
        "create_time": int(time.time() * MICROSECONDS),
        "crop": {
            "lower_left_x": 0.0,
            "lower_left_y": 1.0,
            "lower_right_x": 1.0,
            "lower_right_y": 1.0,
            "upper_left_x": 0.0,
            "upper_left_y": 0.0,
            "upper_right_x": 1.0,
            "upper_right_y": 0.0,
        },
        "extra_type_option": 0,
        "source_platform": 0,
    }


def _create_audio_material(relative_path: str, duration_us: int) -> Dict[str, Any]:
    material_id = uuid.uuid4().hex
    return {
        "app_id": 0,
        "category_id": "",
        "category_name": "local",
        "check_flag": 1,
        "copyright_limit_type": "none",
        "duration": duration_us,
        "effect_id": "",
        "formula_id": "",
        "id": material_id,
        "intensifies_path": "",
        "is_ai_clone_tone": False,
        "is_text_edit_overdub": False,
        "is_ugc": False,
        "local_material_id": material_id,
        "music_id": material_id,
        "name": os.path.basename(relative_path),
        "path": relative_path,
        "remote_url": "",
        "query": "",
        "request_id": "",
        "resource_id": "",
        "search_id": "",
        "source_from": "",
        "source_platform": 0,
        "team_id": "",
        "text_id": "",
        "tone_category_id": "",
        "tone_category_name": "",
        "tone_effect_id": "",
        "tone_effect_name": "",
        "tone_platform": "",
        "tone_second_category_id": "",
        "tone_second_category_name": "",
        "tone_speaker": "",
        "tone_type": "",
        "type": "extract_music",
        "video_id": "",
        "wave_points": [],
    }


def _create_video_segment(
    material_id: str,
    source_start_us: int,
    duration_us: int,
    target_start_us: int,
    volume: float,
) -> Dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "material_id": material_id,
        "target_timerange": {"start": target_start_us, "duration": duration_us},
        "source_timerange": {"start": source_start_us, "duration": duration_us},
        "speed": 1.0,
        "volume": volume,
        "enable_adjust": True,
        "enable_color_curves": True,
        "enable_color_match_adjust": False,
        "enable_color_wheels": True,
        "enable_lut": True,
        "enable_smart_color_adjust": False,
        "extra_material_refs": [],
        "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000},
        "uniform_scale": {"on": True, "value": 1.0},
        "clip": {
            "alpha": 1.0,
            "flip": {"horizontal": False, "vertical": False},
            "rotation": 0.0,
            "scale": {"x": 1.0, "y": 1.0},
            "transform": {"x": 0.0, "y": 0.0},
        },
        "common_keyframes": [],
    }


def _create_audio_segment(
    material_id: str,
    duration_us: int,
    target_start_us: int,
    volume: float,
) -> Dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "material_id": material_id,
        "target_timerange": {"start": target_start_us, "duration": duration_us},
        "source_timerange": {"start": 0, "duration": duration_us},
        "speed": 1.0,
        "volume": volume,
        "extra_material_refs": [],
        "clip": None,
        "hdr_settings": None,
        "uniform_scale": None,
        "common_keyframes": [],
    }


def _normalize_hex_color(color: Optional[str], default: str = "#FFFFFF") -> str:
    color = str(color or default).strip()
    if not color.startswith("#"):
        color = f"#{color}"
    if re.fullmatch(r"#[0-9a-fA-F]{3}", color):
        color = "#" + "".join(char * 2 for char in color[1:])
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = default
    return color.upper()


def _hex_color_to_rgb_float(color: Optional[str], default: str = "#FFFFFF") -> Tuple[float, float, float]:
    normalized = _normalize_hex_color(color, default)
    return (
        int(normalized[1:3], 16) / 255,
        int(normalized[3:5], 16) / 255,
        int(normalized[5:7], 16) / 255,
    )


def _resolve_subtitle_text_size(params: VideoClipParams) -> float:
    raw_size = getattr(params, "font_size", 60) or 60
    try:
        font_size = float(raw_size)
    except (TypeError, ValueError):
        font_size = 60.0
    return max(4.0, min(10.0, font_size / 12.0))


def _resolve_subtitle_transform_y(params: VideoClipParams) -> float:
    subtitle_position = str(getattr(params, "subtitle_position", "bottom") or "bottom").lower()
    if subtitle_position == "top":
        return 0.82
    if subtitle_position == "center":
        return 0.0
    if subtitle_position == "custom":
        try:
            y_percent = float(getattr(params, "custom_position", 85.0))
        except (TypeError, ValueError):
            y_percent = 85.0
        y_percent = max(0.0, min(100.0, y_percent))
        return max(-0.92, min(0.92, 1.0 - 2.0 * (y_percent / 100.0)))
    return -0.8


def _create_text_material(text: str, params: VideoClipParams) -> Dict[str, Any]:
    material_id = uuid.uuid4().hex
    text = str(text or "")
    text_color = _hex_color_to_rgb_float(getattr(params, "text_fore_color", "#FFFFFF"), "#FFFFFF")
    stroke_color = _hex_color_to_rgb_float(getattr(params, "stroke_color", "#000000"), "#000000")
    try:
        stroke_width = float(getattr(params, "stroke_width", 1.5) or 0)
    except (TypeError, ValueError):
        stroke_width = 1.5

    text_style = {
        "fill": {
            "alpha": 1.0,
            "content": {
                "render_type": "solid",
                "solid": {
                    "alpha": 1.0,
                    "color": list(text_color),
                },
            },
        },
        "range": [0, len(text)],
        "size": _resolve_subtitle_text_size(params),
        "bold": False,
        "italic": False,
        "underline": False,
        "strokes": [],
    }
    check_flag = 7
    if stroke_width > 0:
        text_style["strokes"] = [
            {
                "content": {
                    "solid": {
                        "alpha": 1.0,
                        "color": list(stroke_color),
                    }
                },
                "width": max(0.0, min(0.2, stroke_width / 100.0 * 0.2)),
            }
        ]
        check_flag |= 8

    return {
        "id": material_id,
        "content": json.dumps(
            {
                "styles": [text_style],
                "text": text,
            },
            ensure_ascii=False,
        ),
        "typesetting": 0,
        "alignment": 1,
        "letter_spacing": 0.0,
        "line_spacing": 0.02,
        "line_feed": 1,
        "line_max_width": 0.82,
        "force_apply_line_max_width": False,
        "check_flag": check_flag,
        "type": "subtitle",
        "global_alpha": 1.0,
    }


def _create_text_segment(
    material_id: str,
    start_us: int,
    duration_us: int,
    params: VideoClipParams,
) -> Dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "material_id": material_id,
        "target_timerange": {"start": start_us, "duration": duration_us},
        "source_timerange": None,
        "speed": 1.0,
        "volume": 1.0,
        "extra_material_refs": [],
        "is_tone_modify": False,
        "clip": {
            "alpha": 1.0,
            "flip": {"horizontal": False, "vertical": False},
            "rotation": 0.0,
            "scale": {"x": 1.0, "y": 1.0},
            "transform": {"x": 0.0, "y": _resolve_subtitle_transform_y(params)},
        },
        "uniform_scale": {"on": True, "value": 1.0},
        "render_index": 15000,
        "common_keyframes": [],
    }


def _parse_srt_entries(subtitle_path: str) -> List[Tuple[float, float, str]]:
    if not subtitle_path or not os.path.exists(subtitle_path):
        return []

    with open(subtitle_path, "r", encoding="utf-8-sig") as f:
        content = f.read().strip()
    if not content:
        return []

    entries: List[Tuple[float, float, str]] = []
    for block in re.split(r"\n\s*\n", content):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        time_line_index = next(
            (index for index, line in enumerate(lines) if "-->" in line),
            None,
        )
        if time_line_index is None or time_line_index + 1 >= len(lines):
            continue

        try:
            start_text, end_text = lines[time_line_index].split("-->", 1)
            start = script_subtitle.parse_srt_like_time(start_text)
            end = script_subtitle.parse_srt_like_time(end_text)
        except Exception as e:
            logger.warning(f"解析剪映字幕时间失败，跳过字幕块: {e}")
            continue

        text = "\n".join(lines[time_line_index + 1:]).strip()
        if end <= start or not text:
            continue
        entries.append((start, end, text))

    return entries


def _add_subtitle_track_from_srt(
    draft: Dict[str, Any],
    subtitle_path: str,
    params: VideoClipParams,
) -> int:
    entries = _parse_srt_entries(subtitle_path)
    if not entries:
        return 0

    text_track = _create_track("text", "字幕轨道")
    text_track["is_default_name"] = False
    max_end_us = 0
    for start, end, text in entries:
        start_us = _seconds_to_microseconds(start)
        duration_us = _seconds_to_microseconds(end - start)
        if duration_us <= 0:
            continue

        text_material = _create_text_material(text, params)
        draft["materials"]["texts"].append(text_material)
        text_track["segments"].append(_create_text_segment(
            text_material["id"],
            start_us,
            duration_us,
            params,
        ))
        max_end_us = max(max_end_us, start_us + duration_us)

    if text_track["segments"]:
        draft["tracks"].append(text_track)
        logger.info(f"已写入剪映字幕轨: {len(text_track['segments'])} 条, {subtitle_path}")
    return max_end_us


def _normalize_video_material(material: Dict[str, Any]) -> Dict[str, Any]:
    fallback_path = f"assets/video/{material.get('material_name') or 'source.mp4'}"
    result = {
        "aigc_history_id": "",
        "aigc_item_id": "",
        "aigc_type": "none",
        "audio_fade": None,
        "beauty_body_auto_preset": None,
        "beauty_body_preset_id": "",
        "beauty_face_auto_preset": None,
        "beauty_face_auto_preset_infos": [],
        "beauty_face_preset_infos": [],
        "cartoon_path": "",
        "category_id": "",
        "category_name": "local",
        "check_flag": 65535,
        "content_feature_info": None,
        "corner_pin": None,
        "crop_ratio": "free",
        "crop_scale": 1.0,
        "formula_id": "",
        "freeze": None,
        "has_audio": True,
        "has_sound_separated": False,
        "intensifies_audio_path": "",
        "intensifies_path": "",
        "is_ai_generate_content": False,
        "is_copyright": False,
        "is_set_beauty_mode": False,
        "is_text_edit_overdub": False,
        "is_unified_beauty_mode": False,
        "live_photo_cover_path": "",
        "live_photo_timestamp": 0,
        "local_id": "",
        "local_material_from": 0,
        "local_material_id": "",
        "material_id": "",
        "material_url": "",
        "matting": None,
        "media_path": "",
        "multi_camera_info": None,
        "object_locked": None,
        "origin_material_id": "",
        "picture_from": "none",
        "picture_set_category_id": "",
        "picture_set_category_name": "",
        "request_id": "",
        "reverse_intensifies_path": "",
        "reverse_path": "",
        "smart_match_info": None,
        "smart_motion": None,
        "source": 0,
        "stable": None,
        "surface_trackings": None,
        "team_id": "",
        "unique_id": "",
        "video_algorithm": None,
        "video_mask_shadow": None,
        "video_mask_stroke": None,
    }
    result.update(material)
    result["path"] = _to_draft_material_path(
        _normalize_asset_path(material.get("path"), fallback_path)
    )
    result["type"] = "video"
    return result


def _normalize_audio_material(material: Dict[str, Any]) -> Dict[str, Any]:
    fallback_path = f"assets/audio/{material.get('name') or 'audio.mp3'}"
    result = {
        "ai_music_enter_from": "",
        "ai_music_generate_scene": "",
        "ai_music_type": 0,
        "aigc_history_id": "",
        "aigc_item_id": "",
        "app_id": 0,
        "category_id": "",
        "category_name": "local",
        "check_flag": 1,
        "cloned_model_type": "",
        "copyright_limit_type": "none",
        "effect_id": "",
        "formula_id": "",
        "intensifies_path": "",
        "is_ai_clone_tone": False,
        "is_ai_clone_tone_post": False,
        "is_text_edit_overdub": False,
        "is_ugc": False,
        "lyric_type": 0,
        "mock_tone_speaker": "",
        "moyin_emotion": "",
        "music_source": "",
        "pgc_id": "",
        "pgc_name": "",
        "query": "",
        "request_id": "",
        "resource_id": "",
        "search_id": "",
        "similiar_music_info": None,
        "sound_separate_type": 0,
        "source_from": "",
        "source_platform": 0,
        "team_id": "",
        "text_id": "",
        "third_resource_id": "",
        "tone_category_id": "",
        "tone_category_name": "",
        "tone_effect_id": "",
        "tone_effect_name": "",
        "tone_emotion_name_key": "",
        "tone_emotion_role": "",
        "tone_emotion_scale": 0,
        "tone_emotion_selection": "",
        "tone_emotion_style": "",
        "tone_platform": "",
        "tone_second_category_id": "",
        "tone_second_category_name": "",
        "tone_speaker": "",
        "tone_type": "",
        "tts_benefit_info": None,
        "tts_generate_scene": 0,
        "tts_task_id": "",
        "unique_id": "",
        "video_id": "",
        "wave_points": [],
    }
    result.update(material)
    result["path"] = _to_draft_material_path(
        _normalize_asset_path(material.get("path"), fallback_path)
    )
    result["type"] = "extract_music"
    return result


def _normalize_materials(draft: Dict[str, Any]) -> Dict[str, List[Any]]:
    source = draft.get("materials", {})
    materials = {
        key: source.get(key, []) if isinstance(source.get(key, []), list) else []
        for key in MATERIAL_COLLECTION_KEYS
    }
    materials["videos"] = [_normalize_video_material(item) for item in source.get("videos", [])]
    materials["audios"] = [_normalize_audio_material(item) for item in source.get("audios", [])]
    return materials


def _create_responsive_layout() -> Dict[str, Any]:
    return {
        "enable": False,
        "horizontal_pos_layout": 0,
        "size_layout": 0,
        "target_follow": "",
        "vertical_pos_layout": 0,
    }


def _normalize_segment(
    segment: Dict[str, Any],
    track_type: str,
    track_index: int,
    track_attribute: int,
) -> Dict[str, Any]:
    is_video = track_type == "video"
    result = {
        "caption_info": None,
        "cartoon": False,
        "color_correct_alg_result": "",
        "common_keyframes": [],
        "desc": "",
        "digital_human_template_group_id": "",
        "enable_adjust": is_video,
        "enable_adjust_mask": is_video,
        "enable_color_adjust_pro": False,
        "enable_color_correct_adjust": False,
        "enable_color_curves": True,
        "enable_color_match_adjust": False,
        "enable_color_wheels": True,
        "enable_hsl": is_video,
        "enable_hsl_curves": True,
        "enable_lut": is_video,
        "enable_mask_shadow": False,
        "enable_mask_stroke": False,
        "enable_smart_color_adjust": False,
        "enable_video_mask": True,
        "extra_material_refs": [],
        "group_id": "",
        "hdr_settings": segment.get("hdr_settings"),
        "intensifies_audio": False,
        "is_loop": False,
        "is_placeholder": False,
        "is_tone_modify": False,
        "keyframe_refs": [],
        "last_nonzero_volume": 1.0,
        "lyric_keyframes": None,
        "raw_segment_id": "",
        "render_index": 0,
        "render_timerange": {"duration": 0, "start": 0},
        "responsive_layout": _create_responsive_layout(),
        "reverse": False,
        "source": "segmentsourcenormal",
        "state": 0,
        "template_id": "",
        "template_scene": "default",
        "uniform_scale": {"on": True, "value": 1.0},
        "visible": True,
    }
    result.update(segment)
    result["track_attribute"] = track_attribute
    result["track_render_index"] = track_index
    return result


def _normalize_tracks(draft: Dict[str, Any]) -> List[Dict[str, Any]]:
    tracks = []
    for index, track in enumerate(draft.get("tracks", [])):
        track_copy = dict(track)
        track_attribute = int(track_copy.get("attribute", 0) or 0)
        track_copy["segments"] = [
            _normalize_segment(segment, track_copy.get("type", ""), index, track_attribute)
            for segment in track.get("segments", [])
        ]
        tracks.append(track_copy)
    return tracks


def _create_draft_info(
    draft: Dict[str, Any],
    draft_name: str,
    draft_root_path: str,
    new_version: str = "169.0.0",
) -> Dict[str, Any]:
    info = json.loads(json.dumps(draft, ensure_ascii=False))
    canvas_config = info.get("canvas_config", {})
    platform_info = _create_platform_info(draft_root_path)
    info.update({
        "canvas_config": {
            "background": canvas_config.get("background"),
            "height": canvas_config.get("height", 1080),
            "ratio": canvas_config.get("ratio", "original"),
            "width": canvas_config.get("width", 1920),
        },
        "draft_type": "video",
        "function_assistant_info": _default_function_assistant_info(),
        "is_drop_frame_timecode": False,
        "last_modified_platform": platform_info,
        "lyrics_effects": [],
        "materials": _normalize_materials(info),
        "name": draft_name,
        "new_version": new_version,
        "path": "",
        "platform": platform_info,
        "render_index_track_mode_on": True,
        "smart_ads_info": {"draft_url": "", "page_from": "", "routine": ""},
        "tracks": _normalize_tracks(info),
        "uneven_animation_template_info": {
            "composition": "",
            "content": "",
            "order": "",
            "sub_template_info_list": [],
        },
    })
    return info


def _create_empty_template(draft: Dict[str, Any], draft_root_path: str) -> Dict[str, Any]:
    empty_draft = json.loads(json.dumps(draft, ensure_ascii=False))
    empty_draft["canvas_config"] = {
        "background": None,
        "height": 0,
        "ratio": "original",
        "width": 0,
    }
    empty_draft["color_space"] = -1
    empty_draft["duration"] = 0
    empty_draft["keyframes"] = {
        "adjusts": [],
        "audios": [],
        "effects": [],
        "filters": [],
        "handwrites": [],
        "stickers": [],
        "texts": [],
        "videos": [],
    }
    empty_draft["materials"] = _create_material_collections()
    empty_draft["tracks"] = []
    return _create_draft_info(empty_draft, "", draft_root_path, "75.0.0")


def _create_draft_material_index_item(
    material: Dict[str, Any],
    file_name: str,
    metetype: str,
    width: int,
    height: int,
) -> Dict[str, Any]:
    duration = int(material.get("duration", 0) or 0)
    return {
        "ai_group_type": "",
        "create_time": -1,
        "duration": duration,
        "enter_from": 0,
        "extra_info": file_name,
        "file_Path": material.get("path", ""),
        "height": height,
        "id": material.get("id", ""),
        "import_time": -1,
        "import_time_ms": -1,
        "item_source": 1,
        "md5": "",
        "metetype": metetype,
        "roughcut_time_range": {"duration": duration, "start": 0},
        "sub_time_range": {"duration": -1, "start": -1},
        "type": 0,
        "width": width,
    }


def _create_draft_material_index(draft: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for video in draft.get("materials", {}).get("videos", []):
        relative_path = _normalize_asset_path(
            video.get("path"),
            f"assets/video/{video.get('material_name') or 'source.mp4'}",
        )
        items.append(_create_draft_material_index_item(
            {**video, "path": _to_draft_material_path(relative_path)},
            os.path.basename(relative_path),
            "video",
            int(video.get("width", 0) or 0),
            int(video.get("height", 0) or 0),
        ))
    for audio in draft.get("materials", {}).get("audios", []):
        relative_path = _normalize_asset_path(
            audio.get("path"),
            f"assets/audio/{audio.get('name') or 'audio.mp3'}",
        )
        items.append(_create_draft_material_index_item(
            {**audio, "path": _to_draft_material_path(relative_path)},
            os.path.basename(relative_path),
            "music",
            0,
            0,
        ))
    return items


def _create_meta_info(
    draft: Dict[str, Any],
    draft_name: str,
    draft_id: str,
    draft_root_path: str,
    draft_path: str,
    asset_size: int,
) -> Dict[str, Any]:
    return {
        "cloud_draft_cover": False,
        "cloud_draft_sync": False,
        "cloud_package_completed_time": "",
        "draft_cloud_capcut_purchase_info": "",
        "draft_cloud_last_action_download": False,
        "draft_cloud_package_type": "",
        "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": "draft_cover.jpg",
        "draft_deeplink_url": "",
        "draft_enterprise_info": {
            "draft_enterprise_extra": "",
            "draft_enterprise_id": "",
            "draft_enterprise_name": "",
            "enterprise_material": [],
        },
        "draft_fold_path": draft_path,
        "draft_id": _format_draft_uuid(draft_id),
        "draft_is_ae_produce": False,
        "draft_is_ai_packaging_used": False,
        "draft_is_ai_shorts": False,
        "draft_is_ai_translate": False,
        "draft_is_article_video_draft": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_from_deeplink": "false",
        "draft_is_invisible": False,
        "draft_is_pippit_draft": False,
        "draft_is_web_article_video": False,
        "draft_materials": [
            {"type": 0, "value": _create_draft_material_index(draft)},
            {"type": 1, "value": []},
            {"type": 2, "value": []},
            {"type": 3, "value": []},
            {"type": 6, "value": []},
            {"type": 7, "value": []},
            {"type": 8, "value": []},
        ],
        "draft_materials_copied_info": [],
        "draft_name": draft_name,
        "draft_need_rename_folder": False,
        "draft_new_version": "",
        "draft_removable_storage_device": "",
        "draft_root_path": draft_root_path,
        "draft_segment_extra_info": [],
        "draft_timeline_materials_size_": asset_size,
        "draft_type": "",
        "draft_web_article_video_enter_from": "",
        "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1,
        "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1,
        "tm_draft_create": draft.get("create_time", 0),
        "tm_draft_modified": draft.get("update_time", 0),
        "tm_draft_removed": 0,
        "tm_duration": draft.get("duration", 0),
    }


def _create_root_meta_entry(
    draft: Dict[str, Any],
    draft_name: str,
    draft_id: str,
    draft_root_path: str,
    draft_path: str,
    asset_size: int,
) -> Dict[str, Any]:
    return {
        "cloud_draft_cover": False,
        "cloud_draft_sync": False,
        "draft_cloud_last_action_download": False,
        "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": os.path.join(draft_path, "draft_cover.jpg"),
        "draft_fold_path": draft_path,
        "draft_id": _format_draft_uuid(draft_id),
        "draft_is_ai_shorts": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_invisible": False,
        "draft_is_web_article_video": False,
        "draft_json_file": os.path.join(draft_path, "draft_info.json"),
        "draft_name": draft_name,
        "draft_new_version": "",
        "draft_root_path": draft_root_path,
        "draft_timeline_materials_size": asset_size,
        "draft_type": "",
        "draft_web_article_video_enter_from": "",
        "streaming_edit_draft_ready": True,
        "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1,
        "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1,
        "tm_draft_create": draft.get("create_time", 0),
        "tm_draft_modified": draft.get("update_time", 0),
        "tm_draft_removed": 0,
        "tm_duration": draft.get("duration", 0),
    }


def _merge_root_meta_info(
    existing_value: Any,
    next_entry: Dict[str, Any],
    root_path: str,
) -> Dict[str, Any]:
    existing = existing_value if isinstance(existing_value, dict) else {}
    existing_store = existing.get("all_draft_store")
    if not isinstance(existing_store, list):
        existing_store = []

    all_draft_store = [
        next_entry,
        *[
            entry for entry in existing_store
            if (
                isinstance(entry, dict)
                and entry.get("draft_id") != next_entry.get("draft_id")
                and entry.get("draft_fold_path") != next_entry.get("draft_fold_path")
                and entry.get("draft_name") != next_entry.get("draft_name")
            )
        ],
    ]
    return {
        "all_draft_store": all_draft_store,
        "draft_ids": existing.get("draft_ids") if isinstance(existing.get("draft_ids"), int) else 1,
        "root_path": existing.get("root_path") or root_path,
    }


def _create_draft_settings(draft: Dict[str, Any], draft_root_path: str) -> str:
    created_at = round(int(draft.get("create_time", 0) or 0) / MICROSECONDS)
    updated_at = round(int(draft.get("update_time", 0) or 0) / MICROSECONDS)
    return "\n".join([
        "[General]",
        f"cloud_last_modify_platform={_detect_platform(draft_root_path)}",
        f"draft_create_time={created_at}",
        f"draft_last_edit_time={updated_at}",
        "real_edit_keys=1",
        "real_edit_seconds=0",
        "",
    ])


def _create_reference_line_attachment() -> Dict[str, Any]:
    return {
        "reference_lines_config": {
            "horizontal_lines": [],
            "is_lock": False,
            "is_visible": False,
            "vertical_lines": [],
        },
        "safe_area_type": 0,
    }


def _create_editing_attachment() -> Dict[str, Any]:
    return {
        "editing_draft": {
            "ai_remove_filter_words": {
                "enter_source": "",
                "right_id": "",
            },
            "ai_shorts_info": {
                "report_params": "",
                "type": 0,
            },
            "cover_extra_info": {
                "draft_id": "",
                "position": 0,
                "select_segment_id": "",
                "select_segment_source_start": 0,
                "select_segment_target_start": 0,
                "type": 1,
            },
            "crop_info_extra": {
                "crop_mirror_type": 0,
                "crop_rotate": 0,
                "crop_rotate_total": 0,
            },
            "digital_human_template_to_video_info": {
                "has_upload_material": False,
                "template_type": 0,
            },
            "draft_used_recommend_function": "",
            "edit_type": 0,
            "eye_correct_enabled_multi_face_time": 0,
            "has_adjusted_render_layer": False,
            "image_ai_chat_info": {
                "before_chat_edit": False,
                "draft_modify_time": 0,
                "generate_type": "",
                "keyword_content": "",
                "keyword_type": "",
                "message_id": "",
                "model_name": "",
                "need_restore": False,
                "picture_id": "",
                "prompt_content": "",
                "prompt_from": "",
                "sugs_info": [],
            },
            "is_open_expand_player": False,
            "is_template_text_ai_generate": False,
            "is_use_adjust": False,
            "is_use_ai_expand": False,
            "is_use_ai_remove": False,
            "is_use_ai_video": False,
            "is_use_audio_separation": False,
            "is_use_chroma_key": False,
            "is_use_curve_speed": False,
            "is_use_digital_human": False,
            "is_use_edit_multi_camera": False,
            "is_use_lip_sync": False,
            "is_use_lock_object": False,
            "is_use_loudness_unify": False,
            "is_use_noise_reduction": False,
            "is_use_one_click_beauty": False,
            "is_use_one_click_ultra_hd": False,
            "is_use_retouch_face": False,
            "is_use_smart_adjust_color": False,
            "is_use_smart_body_beautify": False,
            "is_use_smart_motion": False,
            "is_use_subtitle_recognition": False,
            "is_use_text_to_audio": False,
            "material_edit_session": {
                "material_edit_info": [],
                "session_id": "",
                "session_time": 0,
            },
            "paste_segment_list": [],
            "profile_entrance_type": "",
            "publish_enter_from": "",
            "publish_type": "",
            "single_function_type": 0,
            "text_convert_case_types": [],
            "version": "1.0.0",
            "video_recording_create_draft": "",
        }
    }


def _create_draft_virtual_store(draft: Dict[str, Any]) -> Dict[str, Any]:
    materials = [
        *draft.get("materials", {}).get("videos", []),
        *draft.get("materials", {}).get("audios", []),
    ]
    return {
        "draft_materials": [],
        "draft_virtual_store": [
            {
                "type": 0,
                "value": [
                    {
                        "creation_time": 0,
                        "display_name": "",
                        "filter_type": 0,
                        "id": "",
                        "import_time": 0,
                        "import_time_us": 0,
                        "sort_sub_type": 0,
                        "sort_type": 0,
                        "subdraft_filter_type": 0,
                    }
                ],
            },
            {
                "type": 1,
                "value": [
                    {"child_id": material.get("id", ""), "parent_id": ""}
                    for material in materials
                ],
            },
            {"type": 2, "value": []},
        ],
    }


def _write_root_meta_info(draft_root_path: str, root_meta_entry: Dict[str, Any]) -> None:
    root_meta_path = os.path.join(draft_root_path, "root_meta_info.json")
    existing_value: Any = {}
    if os.path.exists(root_meta_path):
        try:
            with open(root_meta_path, "r", encoding="utf-8") as f:
                existing_value = json.load(f)
        except Exception as e:
            logger.warning(f"读取 root_meta_info.json 失败，将重建索引: {e}")

    _write_json_file(
        root_meta_path,
        _merge_root_meta_info(existing_value, root_meta_entry, draft_root_path),
    )


def _write_plaintext_draft_files(
    draft_root_path: str,
    draft_path: str,
    draft_name: str,
    draft_id: str,
    draft: Dict[str, Any],
    asset_size: int,
) -> None:
    draft_info = _create_draft_info(draft, draft_name, draft_root_path)
    empty_template = _create_empty_template(draft, draft_root_path)

    _write_json_file(
        os.path.join(draft_path, "draft_meta_info.json"),
        _create_meta_info(draft, draft_name, draft_id, draft_root_path, draft_path, asset_size),
    )
    with open(os.path.join(draft_path, "draft_settings"), "w", encoding="utf-8") as f:
        f.write(_create_draft_settings(draft, draft_root_path))
    with open(os.path.join(draft_path, "draft_cover.jpg"), "wb") as f:
        f.write(DEFAULT_DRAFT_COVER_BYTES)
    _write_json_file(os.path.join(draft_path, "draft_info.json"), draft_info)
    _write_json_file(os.path.join(draft_path, "template-2.tmp"), draft_info)
    _write_json_file(os.path.join(draft_path, "template.tmp"), empty_template)
    _write_json_file(
        os.path.join(draft_path, "common_attachment", "attachment_pc_timeline.json"),
        _create_reference_line_attachment(),
    )
    _write_json_file(os.path.join(draft_path, "common_attachment", "attachment_action_scene.json"), {})
    _write_json_file(os.path.join(draft_path, "common_attachment", "attachment_script_video.json"), {})
    _write_json_file(os.path.join(draft_path, "common_attachment", "attachment_gen_ai_info.json"), {})
    _write_json_file(os.path.join(draft_path, "attachment_editing.json"), _create_editing_attachment())
    _write_json_file(
        os.path.join(draft_path, "draft_agency_config.json"),
        {
            "is_auto_agency_enabled": False,
            "is_auto_agency_popup": False,
            "is_single_agency_mode": False,
            "marterials": None,
            "use_converter": False,
            "video_resolution": draft.get("canvas_config", {}).get("height", 1080),
        },
    )
    with open(os.path.join(draft_path, "draft_biz_config.json"), "w", encoding="utf-8"):
        pass
    _write_json_file(
        os.path.join(draft_path, "draft_virtual_store.json"),
        _create_draft_virtual_store(draft),
    )
    _write_json_file(
        os.path.join(draft_path, "performance_opt_info.json"),
        {"manual_cancle_precombine_segs": None, "need_auto_precombine_segs": None},
    )
    _write_json_file(
        os.path.join(draft_path, "timeline_layout.json"),
        {
            "activeTimeline": draft_id,
            "dockItems": [
                {
                    "dockIndex": 0,
                    "ratio": 1,
                    "timelineIds": [draft_id],
                    "timelineNames": ["时间线01"],
                }
            ],
            "layoutOrientation": 1,
        },
    )
    _write_root_meta_info(
        draft_root_path,
        _create_root_meta_entry(draft, draft_name, draft_id, draft_root_path, draft_path, asset_size),
    )


def _resolve_item_audio_file(item: Dict[str, Any], output_dir: str) -> str:
    audio_file = ""
    timestamp = item.get("timestamp", "")
    if timestamp:
        audio_file = os.path.join(output_dir, f"audio_{timestamp.replace(':', '_')}.mp3")

    item_audio_file = item.get("audio", "")
    if item_audio_file and os.path.exists(item_audio_file):
        audio_file = item_audio_file

    return audio_file


def write_plaintext_jianying_draft(
    jianying_draft_path: str,
    draft_name: str,
    new_script_list: List[Dict[str, Any]],
    params: VideoClipParams,
    output_dir: str,
    subtitle_path: str = "",
) -> Tuple[str, str]:
    os.makedirs(jianying_draft_path, exist_ok=True)

    display_name = draft_name or f"NarratoAI_{int(time.time())}"
    folder_name, draft_path = _create_unique_draft_path(jianying_draft_path, display_name)
    os.makedirs(draft_path, exist_ok=False)
    for rel_dir in DRAFT_PACKAGE_DIRECTORIES:
        os.makedirs(os.path.join(draft_path, *rel_dir.split("/")), exist_ok=True)

    draft_id = uuid.uuid4().hex
    draft = _create_draft_template(draft_id, display_name, jianying_draft_path)
    video_track = _create_track("video", "视频轨道")
    audio_track = _create_track("audio", "音频轨道")
    draft["tracks"] = [video_track, audio_track]

    duration_cache: Dict[str, float] = {}
    metadata_cache: Dict[str, Tuple[int, int, int]] = {}
    used_asset_paths: Set[str] = set()
    asset_path_cache: Dict[str, str] = {}
    video_material_cache: Dict[str, Dict[str, Any]] = {}
    current_time_us = 0

    for item in new_script_list:
        start_time = float(item.get("start_time", 0.0) or 0.0)
        source_start_time = float(item.get("source_start_time", start_time) or 0.0)
        requested_duration = float(item.get("duration", 0.0) or 0.0)
        timestamp = item.get("timestamp", "")
        ost = int(item.get("OST", 0) or 0)
        use_source_timerange = bool(item.get("use_source_timerange", False))

        logger.info(
            f"处理片段: OST={ost}, start_time={start_time}, "
            f"duration={requested_duration}, timestamp={timestamp}"
        )

        video_file = item.get("video", "")
        use_clipped_video = bool(video_file and os.path.exists(video_file) and not use_source_timerange)
        if not use_clipped_video and not video_file:
            video_file = params.video_origin_path

        if not video_file or not os.path.exists(video_file):
            logger.warning(f"视频素材不存在，跳过片段: {video_file or timestamp}")
            continue

        source_start_time = 0.0 if use_clipped_video else source_start_time
        video_duration = _clamp_duration_to_media(
            requested_duration,
            video_file,
            duration_cache,
            "视频素材" if use_clipped_video else "原始视频素材",
            source_start_time=source_start_time,
        )

        audio_file = _resolve_item_audio_file(item, output_dir)
        audio_duration = None
        if ost in [0, 2] and audio_file and os.path.exists(audio_file):
            audio_duration = _get_cached_media_duration(audio_file, duration_cache)
            logger.info(
                f"音频文件实际时长: {audio_duration:.6f}秒, 视频片段时长: {video_duration:.3f}秒"
            )

        segment_duration = min(
            video_duration,
            audio_duration if audio_duration is not None else video_duration,
        )
        segment_duration = _floor_duration_to_milliseconds(segment_duration)
        if segment_duration <= 0:
            logger.warning(f"片段时长无效，跳过: {timestamp}")
            continue

        segment_duration_us = _seconds_to_microseconds(segment_duration)
        video_material_key = os.path.abspath(video_file)
        video_material = video_material_cache.get(video_material_key)
        if video_material is None:
            video_material_duration_us, width, height = _get_video_metadata_ffprobe(video_file, metadata_cache)
            video_relative_path = _register_asset(
                video_file,
                draft_path,
                "assets/video",
                f"video_{len(video_material_cache) + 1}.mp4",
                used_asset_paths,
                asset_path_cache,
            )
            video_material = _create_video_material(video_relative_path, video_material_duration_us, width, height)
            draft["materials"]["videos"].append(video_material)
            video_material_cache[video_material_key] = video_material
        video_volume = (
            0.0
            if ost == 0
            else float(getattr(params, "original_volume", 1.0) or 1.0)
        )
        video_track["segments"].append(_create_video_segment(
            video_material["id"],
            _seconds_to_microseconds(_floor_duration_to_milliseconds(source_start_time)),
            segment_duration_us,
            current_time_us,
            video_volume,
        ))

        if ost in [0, 2] and audio_file and os.path.exists(audio_file):
            audio_material_duration_us = _seconds_to_microseconds(
                _get_cached_media_duration(audio_file, duration_cache)
            )
            audio_relative_path = _register_asset(
                audio_file,
                draft_path,
                "assets/audio",
                f"audio_{len(audio_track['segments']) + 1}.mp3",
                used_asset_paths,
                asset_path_cache,
            )
            audio_material = _create_audio_material(audio_relative_path, audio_material_duration_us)
            draft["materials"]["audios"].append(audio_material)
            audio_track["segments"].append(_create_audio_segment(
                audio_material["id"],
                segment_duration_us,
                current_time_us,
                float(getattr(params, "tts_volume", 1.0) or 1.0),
            ))
        elif ost in [0, 2]:
            logger.warning(f"音频文件不存在: {audio_file}")

        current_time_us += segment_duration_us

    if not video_track["segments"]:
        raise ValueError("没有可写入剪映草稿的视频片段")

    subtitle_end_us = 0
    if getattr(params, "subtitle_enabled", True) and subtitle_path:
        subtitle_end_us = _add_subtitle_track_from_srt(draft, subtitle_path, params)

    first_video = draft["materials"]["videos"][0]
    draft["canvas_config"]["width"] = int(first_video.get("width", 1920) or 1920)
    draft["canvas_config"]["height"] = int(first_video.get("height", 1080) or 1080)
    draft["duration"] = max(current_time_us, subtitle_end_us)
    draft["update_time"] = int(time.time() * MICROSECONDS)

    asset_size = sum(
        os.path.getsize(source_file)
        for source_file in asset_path_cache.keys()
        if os.path.exists(source_file)
    )
    _write_plaintext_draft_files(
        jianying_draft_path,
        draft_path,
        display_name,
        draft_id,
        draft,
        asset_size,
    )

    logger.info(f"剪映明文草稿包已写入: {draft_path} (folder={folder_name})")
    return draft_path, display_name
